# GPU support (NVIDIA, Windows): detect at install, CPU fallback at runtime

**Status:** slices 1–5 shipped on `main` (2026-10-07); slice 6 (owner host) and 7 (release) owed. Asked for explicitly on 2026-10-07, so invariant 4 ("minimal by default") is satisfied by that request. It reverses part of the archived design's decision #2 ("CPU only"; see `archive/2026-09-27-transcribe-offline-minimal-app-design.md:16,102,219`).

**Provenance:** this app never had GPU support. The GPU code lives in stt-faster, and the original rewrite left it out to keep the review surface small. This plan ports stt-faster's Windows GPU mode (`installer/setup_gui.py`, `backend/_cudnn_preload.py`, `backend/model_loader.py`, `backend/gui.py`) rather than inventing a new one. Each section below names the stt-faster lines it copies.

## Goal

- On a PC with a capable NVIDIA GPU, the installer also installs the CUDA libraries, and the app transcribes on the GPU (`cuda` / `float16`).
- On every other PC, the install is the same as today's CPU-only install: same downloads, same size.
- If the GPU fails at runtime, the app falls back to CPU (`int8`) and the transcript still gets written.

## Decisions

### D1. Detection: stt-faster's rule, unchanged
`setup_gui.py:62-67, 666-683`:
- Run `%SystemRoot%\System32\nvidia-smi.exe --query-gpu=name,memory.total,driver_version --format=csv,noheader,nounits`. Use the absolute path, so a same-named exe on PATH is never run. The timeout is 15 s.
- Parse only the first line, with `rsplit(",", 3)` (the query also asks `compute_cap`), because GPU names can contain commas.
- The GPU is capable when **driver ≥ 528.33** (the CUDA 12.0 floor on Windows), **VRAM ≥ 4000 MiB** **and `compute_cap` ≥ 7.0** (ctranslate2 refuses `float16` on Pascal and older; added after review).
- Any doubt (tool missing, non-zero exit, `[N/A]`, a parse error, a timeout) means **CPU**.
- Not ported: WMI queries, CUDA toolkit checks, the NVSMI legacy path. Old non-DCH drivers fall below the 528 floor anyway.

### D2. Where detection runs: `setup.py`, not `Setup.cs` or `install.bat` (user ruling 2026-10-07)
Both installers already run `python -m transcribe_offline.setup` right after `uv sync`. That module becomes the place that detects the GPU. If the GPU is capable, it runs one more sync, `app/.uv/uv.exe sync --frozen --no-dev --group gpu --python <running 3.12.x>` (pinned so an inherited `UV_PYTHON` cannot recreate `.venv`), before it downloads the models.

- **What this buys:**
  - **`installer/Setup.cs` and `install.bat` stay byte-identical.** The Setup.exe hash, and the SmartScreen reputation it has built up, carry over (`.claude/rules/installer-hash.md`).
  - `Setup.cs` keeps its documented antivirus posture: "starts only uv and Python". It does not also spawn `nvidia-smi`.
  - The logic is written once, in Python, and tested with pytest. The alternative is two copies, one in C# 5 and one in batch.
  - `setup.py` is already exempt from `TID251`, so `subprocess` is allowed there.
  - The child process inherits every `UV_*` setting, plus TMP/TEMP and the list of cleared variables, from whichever installer started it. Nothing new has to be pinned.
- **What it costs:**
  - `setup.py` is no longer only the model downloader. Its docstring and the `TID251` reason must say so.
  - On a GPU machine, every repair runs `uv sync --frozen --no-dev` first. That sync removes the gpu group, and `setup.py` then adds it back. The wheels come from `.uv/cache`, so the re-add is a local relink, not a download.
- **Rejected alternative: detect in `Setup.cs` and `install.bat` and pass `--group gpu` to the first sync.**
  - It needs one sync instead of two.
  - But it changes the exe hash, which resets its reputation. It adds a third process type for antivirus heuristics to look at. And the logic is duplicated in two languages with no unit tests.

### D3. Dependencies: a uv dependency group, locked in the one `uv.lock`
```toml
[dependency-groups]
gpu = [
    "nvidia-cublas-cu12==12.9.2.10; sys_platform == 'win32'",
    "nvidia-cudnn-cu12==9.1.0.70; sys_platform == 'win32'",
]
```
- **Why a group and not an extra:** `[tool.uv] package = false`, and that may not accept `[project.optional-dependencies]`. stt-faster uses an extra (`pyproject.toml:63-68`). Check with `uv lock` which form works. Prefer the group, because `--no-dev` does not touch it.
- **Why cuDNN 9.1.0.70 exactly:** the pinned ctranslate2 **4.6.2** `ctranslate2.dll` imports `cudnn64_9.dll`, and the bundled copy is FileVersion 9.1.0.70. This was checked by statically inspecting the wheel. cuBLAS 12.x is loaded by bare name (`cublas64_12.dll`).
- **Transitive dependency:** cuBLAS pulls in `nvidia-cuda-nvrtc-cu12==12.9.86` on win32 (76 MB). Keep it unless it is shown to be unneeded (see Open questions).
- **Download size:** about **1.3 GB** extra, only on GPU machines. cuBLAS is 553 MB, cuDNN 680 MB, nvrtc 76 MB.
- **Pinning:** `uv.lock` holds sha256 hashes for every wheel, and `--frozen` verifies them. That satisfies invariant 2 without adding pins to `pins.txt`.
- **Future bump trap:** ctranslate2 ≥ 4.7/4.8 appears to no longer need cuDNN. The 4.8.2 DLL names only `cublas64_12.dll`. **On the next ctranslate2 bump, re-check this and drop cuDNN (−680 MB).** The constraint pin in `pyproject.toml` needs a comment pointing at this.

### D4. Runtime device choice: the installed wheels are the only state
- **No config file, no saved device, no env-var override.** The archived design rule "nothing persisted" still holds, and so does invariant 3.
- **The rule:** if the `nvidia` namespace package is importable *and* `ctranslate2.get_cuda_device_count() > 0`, use `cuda` / `float16`. Otherwise use `cpu` / `int8`, as today.
- **DLL discovery** is ported from `_cudnn_preload.py:40-58`, about 15 lines. It must run before `faster_whisper` / `ctranslate2` are imported, so it goes in `engine.load_model`, ahead of the deferred import. It does three things:
  - `find_spec("nvidia").submodule_search_locations` → every `*/bin`.
  - `os.add_dll_directory` for each of those folders.
  - Prepend those folders to `PATH`, because ctranslate2 calls `LoadLibrary("cublas64_12.dll")`, which searches PATH.
- **Test seam:** inject `add_dll_directory` and `environ` as defaulted parameters, as stt-faster does. No mocks.
- **Guard compatibility:**
  - Neither `os.add_dll_directory` nor a change to `os.environ` is in `guard.BLOCKED`.
  - `ctypes` is not needed.
  - `get_cuda_device_count` is a native call. It does not spawn a process and does not touch the network.

### D5. Runtime fallback: retry the job on CPU, kept in memory only
- **Why the retry covers the first inference too:** CUDA DLLs load lazily, so a missing or broken cuBLAS often fails at the **first inference**, not at model load (stt-faster design §135). Catching errors only at load time is not enough.
- **In `app.run_job`:**
  - If `load_model` on `cuda` raises, reload on CPU.
  - Until one file has transcribed on `cuda`, a `RuntimeError` (how ctranslate2 reports CUDA errors; file errors do not count) reloads on CPU and retries that file once.
  - Stay on CPU for the rest of the session.
  - `transcribe_file` already deletes its `.partial` on any exception, so the retry starts clean.
- **Not ported:** stt-faster's "write `device=cpu` to config after a successful CPU retry" (`gui.py:437-478`). Without persistence, a broken GPU costs one failed attempt per app launch. That is an accepted trade for having no config file.
- **Residual risk:** a native `abort()` inside CUDA or cuDNN kills the process, and Python cannot catch it. stt-faster saw this on Linux (`f2b2f09`). If it happens on Windows, the user's fix is to delete `.venv/Lib/site-packages/nvidia` (Q2: no override). SECURITY.md should list it.

## Slices (thinnest visible first; re-pick the order after each)

1. **Lock the deps.** Add the `gpu` group and run `uv lock`. Then confirm three things: `uv sync --frozen --no-dev` on CI still installs no nvidia wheel; `uv sync --frozen --no-dev --group gpu` succeeds on the Windows runner; and the wheel sizes and hashes match D3. Also extend the pip-audit export to cover the group, and add a `uv sync --frozen --no-dev --group gpu` step to the Windows CI job (user ruling 2026-10-07).
2. **Detection in `setup.py`.**
   - Add `detect_gpu(run=subprocess.run) -> GpuInfo | None` and `gpu_capable(info)`.
   - Add the extra `uv sync --group gpu` call, made through the absolute path `APP_ROOT/.uv/uv.exe` with arguments passed as a list.
   - Add one log line with the result, e.g. "NVIDIA RTX 3060 (12 GB, driver 560.94): installing GPU libraries (~1.3 GB)" or "No capable NVIDIA GPU: CPU only".
   - Port the tests from stt-faster `tests/unit/test_setup_gui.py:1422-1545`: parsing, any-doubt → None, tool missing, 528.24 rejected, 3 GB rejected, sync arguments.
3. **Runtime DLL dirs and device choice in `engine.load_model`,** with tests ported from `test_cudnn_preload.py:9-35` and `test_model_loader.py:19-32`.
4. **CPU fallback in `app.run_job`** (D5). Tests use a fake model whose first `transcribe` raises.
5. **Docs:**
   - README: GPU note and sizes; the "about 3.5 GB" figure becomes "+1.3 GB with an NVIDIA GPU".
   - SECURITY.md: CUDA/cuDNN added to the native-code rows; the abort risk; the extra install-time process (`nvidia-smi`).
   - CLAUDE.md and the `pyproject.toml` description: replace "CPU".
   - The `setup.py` docstring and the `TID251` reason.
6. **Owner-host verification** (cannot run in CI; see the checklist below).
7. Release v0.2.7. Setup.exe is reused unchanged (D2), so `setup-exe-reuse.sh` should pick up the previous binary.

## Owner-host checklist (slice 6, ranked)

1. **GPU PC, fresh install:** the setup log shows the GPU line and roughly 1.3 GB more downloaded. `app/.venv/Lib/site-packages/nvidia/{cublas,cudnn}/bin` exist.
2. **Transcribe `tests/fixtures/et.wav` on the GPU PC:** the app log shows `cuda`/`float16`. The `.txt` matches the CPU output, either word-for-word or with differences only in timestamps or punctuation (record which). It is visibly faster than CPU; note the factor.
3. **Smart App Control / App Control enforcing PC:** the NVIDIA DLLs load. They are NVIDIA-signed, but av 18.1.0 was blocked on that PC (`822fa29`), so this must be checked, not assumed.
4. **Forced failure:** rename `nvidia/cublas/bin` → the job still finishes on CPU, and the log shows the fallback.
5. **CPU-only PC, or a GPU PC with nvidia-smi absent:** the install is identical to v0.2.6, with no nvidia wheels in `.venv`. A repair on a GPU PC keeps the group installed.

## Open questions

- **Q1. nvrtc:** is `nvidia-cuda-nvrtc-cu12` needed at runtime by cuBLAS for Whisper's kernels? If not, add it to `exclude-dependencies` (−76 MB). Verify on the owner host by deleting its `bin` and transcribing.
- **Q2. CPU override for a broken GPU:** stt-faster has `--cpu`, but Setup.exe takes no arguments and D2 keeps it unchanged.
  - **Ruled 2026-10-07: none.** Fixing a broken GPU means deleting `.venv/Lib/site-packages/nvidia`.
  - If one is wanted, the cheapest option is an env var that `setup.py` reads, e.g. `TRANSCRIBE_CPU=1`. That is a config knob, so only add it on request.
- **Q3. `float16` vs `int8_float16` on cuda:** stt-faster uses `float16`. `int8_float16` halves VRAM, so it would fit cards under 4 GB, but the output may differ. Keep `float16` unless the owner host shows a reason to change.
- **Q4. Running `uv sync` from inside the venv's own `python.exe`:** on Windows, check that adding packages while that interpreter is running cannot fail on a locked file. Only new `nvidia/*` files are written, so this is expected to work, but it is unverified.
