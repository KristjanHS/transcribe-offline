# transcribe-offline — minimal reviewable GUI app (design)

**Status:** ✅ SHIPPED 2026-09-27 (slices 1–4 on `main`); owed: first Windows run of `release.yml` via workflow_dispatch.

**Date:** 2026-09-27 · **Repo:** https://github.com/KristjanHS/transcribe-offline (local: `~/projects/transcribe-offline`) · **Source of behaviour:** stt-faster (`~/projects/stt-faster`) at `f967efa`; all `backend/…`, `installer/…` cites below are stt-faster paths. · **Spec review:** fresh-agent review 2026-09-27, corrections folded in.

## Goal

A drastically minimized, standalone re-implementation of stt-faster's **non-IT-user GUI** so security-conscious developers can review the whole codebase quickly and approve it for corporate user machines. Success = a reviewer can read every line we ship (~500 lines of Python + three short `.bat` files, vs ~12.5k today), verify every network download against a pin, and confirm the app makes **zero network calls at runtime**.

## Decisions (settled in brainstorm)

| # | Decision | Rejected alternatives |
|---|----------|-----------------------|
| 1 | **One-time clean extraction** — rewrite the minimal path from scratch; stt-faster stays the lab; fixes ported by hand | generated export (can't shrink — core keeps variant seams); shared core lib (big stt-faster refactor, seams add review surface) |
| 2 | **Features: transcription only.** Estonian + English, CPU only, file picker, `.txt` output, timestamps toggle | speaker identification (torch/pyannote ~2 GB deps), GPU/CUDA, drag-and-drop (tkinterdnd2 native DLL), audio denoise/preprocess |
| 3 | **Text-only bootstrap installer** (`install.bat` → pinned uv → `uv sync --frozen` → `python -m transcribe_offline.setup`); zero shipped binaries | PyInstaller exe (unsigned opaque binary, SmartScreen/AV flags; SignPath ruled out) |
| 4 | **Every install-time download pinned** (version + SHA-256 / lock hash / commit + SHA-256); no "latest" lookups, no self-update | fully offline multi-GB bundle; no installer (IT-only) |
| 5 | **Install in place**: user extracts the zip to any folder and runs `install.bat` without admin; that folder *is* the install | copy to `%LOCALAPPDATA%` (user rejected) |
| 6 | No subprocess, no CLI at runtime — transcription runs in a worker thread inside the GUI process | subprocess to a CLI (today's design) |
| 7 | Model downloads via stdlib `urllib` against explicit `huggingface.co/<repo>/resolve/<commit>/<file>` URLs; runtime loads models from a local folder path | `huggingface_hub.snapshot_download` (implicit URLs, HF cache outside the folder) |

## Parity facts (what the stt-faster GUI actually does today)

Traced from `backend/gui.py:208-236` → `VariantTranscriptionService` minimal path (`backend/variants/executor.py:569-633, 849-923`), variant 61 (`backend/variants/registry.py:249-262`). The new app must reproduce this output:

- **Profiles** (`backend/gui.py:68-70`, `backend/model_config.py:34-50`):
  - Estonian → `TalTechNLP/whisper-large-v3-turbo-et-verbatim`, only the `ct2/*` subfolder, model path = `<snapshot>/ct2`.
  - English → `Systran/faster-distil-whisper-large-v3` (full repo; named preset "turbo" but it is distil-large-v3).
- **Model construction on CPU:** `WhisperModel(path, device="cpu", compute_type="int8")` — CPU forces int8 regardless of preset (`backend/model_loader.py:108,167-169`); all other constructor args default.
- **Transcribe call:** `model.transcribe(path, language="et"|"en", beam_size=7, patience=1.2, repetition_penalty=1.05)`. Everything else is faster-whisper 1.2.1 default — notably **`vad_filter=False`**, `condition_on_previous_text=True`, temperature fallback list, `word_timestamps=False`. stt-faster's own `TranscriptionConfig` defaults (VAD, beam 5, `no_repeat_ngram_size=3`) are **not** applied on this path.
- **Audio:** no preprocessing; faster-whisper decodes via PyAV. Today ffprobe is called only for a duration hint/ETA — the new app uses `info.duration` instead, so **no ffmpeg binary is needed**.
- **TXT output** (`backend/transcribe.py:399-432`): each segment `text.strip()`; one line per segment, UTF-8, written with `open(..., "w")` and no `newline=` (`backend/services/json_output_writer.py:25`), so **CRLF on Windows**. The new app keeps that platform default; golden comparisons normalise line endings.
  - timestamps on: `[HH:MM:SS.cc --> HH:MM:SS.cc] text` (rounded to the nearest hundredth, negative times clamped to 0, NaN/inf → `??:??:??.??`; `backend/transcribe.py:399-415`)
  - timestamps off: `text`
  - No dedup, joining, or hallucination filtering.
- **Extensions** (`backend/components.py:27`): `.wav .mp3 .m4a .flac .ogg .wma .aac .mp4 .mkv` (new app: case-insensitive match).
- **Output location:** `.txt` beside the original; name collision → `<stem> (2).txt` etc. (`backend/gui.py:308-323`).

Deliberate differences from today: model loaded once per job (today: once per file); models pinned to a commit (today: unpinned `main`); `HF_HUB_OFFLINE=1` always (today: only if the install dir's hf_home exists).

## Design

### Folder layout (release zip = repo tree; install adds the dot-dirs, `models\`, `logs\`)

```
<any folder>\transcribe-offline-vX.Y.Z\
├─ install.bat  uninstall.bat  Transcribe.bat
├─ pyproject.toml  uv.lock  README.md  SECURITY.md  LICENSE
├─ transcribe_offline\          (flat layout at the repo root — see "Dependencies": the project is never built)
│  ├─ __main__.py   → app.main()
│  ├─ app.py        ~200  tkinter GUI
│  ├─ engine.py     ~120  load model, transcribe one file, format + write txt
│  ├─ models.py      ~40  THE ONLY place URLs live: repo, commit, file list, SHA-256 per file, local subdir
│  └─ setup.py       ~80  install-time model fetch + verify (only module allowed network)
├─ tests\
├─ .uv\      uv.exe, UV_CACHE_DIR, UV_PYTHON_INSTALL_DIR   (install)
├─ .venv\                                                  (install)
├─ models\et\  models\en\                                  (install, SHA-256 verified)
└─ logs\app.log                                            (runtime, RotatingFileHandler 1 MB × 2)
```

Nothing is written outside this folder except: the Desktop shortcut, and the `.txt` transcripts beside the user's audio files.

### Dependencies

`pyproject.toml` runtime deps: `faster-whisper==1.2.1` only (its closure: ctranslate2, av, tokenizers, huggingface-hub, onnxruntime, tqdm, …). `requires-python = "==3.12.*"`. Dev group: ruff, pyright, bandit, pytest, pytest-socket, pip-audit. `onnxruntime` is installed but never loaded (VAD off; it is imported lazily only for VAD, faster_whisper `vad.py:298`) — dropping it via uv override is backlog.

**No build backend (`[tool.uv] package = false`).** `uv sync` would otherwise build and install the project itself, fetching a build backend (setuptools/uv_build) from PyPI that `uv.lock` does **not** hash-pin — a hole in the "every download pinned" claim. Instead the project is a virtual (non-installed) project: only the locked dependencies are installed, the `transcribe_offline` package sits at the repo root, and it is imported because every entry point runs with the install folder as its working directory (`install.bat` and `Transcribe.bat` start with `cd /d "%~dp0"`; the shortcut's WorkingDirectory is the folder). pytest uses `pythonpath = ["."]`. Decide this in slice 1 — the layout depends on it.

### `engine.py`

- `LANGUAGES: dict[str, Lang]` — `"Estonian": Lang(code="et", model_dir="et")`, `"English": Lang(code="en", model_dir="en")`; the model dir for Estonian points at the downloaded `ct2` content.
- `load_model(models_root, lang) -> WhisperModel` — first checks that **all** required files exist (`REQUIRED_FILES` from `models.py`, see below), then `WhisperModel(str(path), device="cpu", compute_type="int8")`; any missing file → clear error ("run install.bat"). This check is load-bearing, not cosmetic: without `tokenizer.json` faster-whisper silently **downloads** `openai/whisper-tiny`'s tokenizer from the internet (faster_whisper `transcribe.py:700-707`); without `preprocessor_config.json` it silently falls back to 80 mel bins, which is wrong for large-v3 (128) (`transcribe.py:729-736`).
- `transcribe_file(model, audio, lang, *, timestamps, on_progress, cancelled) -> Path`:
  - `dest = unique_destination(audio)` is computed once at file start; partial output goes to `dest.with_name(dest.name + ".partial")`
  - iterate segments; after each: `if cancelled(): raise Cancelled`; `on_progress(min(1.0, seg.end / info.duration))` when duration > 0
  - rename `.partial` → `dest` on success; delete `.partial` on cancel/error
- `format_line(seg, timestamps)`, `fmt_time(seconds)` (round to hundredth, clamp negatives to 0, NaN/inf → `??:??:??.??`), `unique_destination(audio)` — pure functions, unit-tested.
- File picker filter lists the supported extensions first plus "All files"; a picked file with an unsupported extension is dropped from the selection with a one-line notice ("skipped: notes.docx — not an audio file").
- `os.environ.setdefault("HF_HUB_OFFLINE", "1")` + `HF_HUB_DISABLE_TELEMETRY=1` at the very top of `__main__.py`, before any import of faster_whisper (belt-and-braces; a local path never hits the hub anyway).

### `app.py` (GUI)

```
┌─ Transcribe (offline) ──────────────────────────────┐
│ [ Choose audio files… ]   3 files selected          │
│ Language:  (•) Estonian  ( ) English                │
│ [x] Include timestamps                              │
│ [ Start ]  [ Cancel ]                               │
│ File 2 of 3: interview.m4a                          │
│ [███████████░░░░░░░░░░░]  48%                       │
│ Saved: C:\…\meeting.txt  [ Open folder ]            │
└─────────────────────────────────────────────────────┘
```

- One daemon worker thread per job: load model once → files sequentially → post events (`started(i, name)`, `progress(fraction)`, `done(i, txt)`, `failed(i, reason)`, `finished`) to a `queue.Queue`; Tk polls every 100 ms.
- Per-file error isolation: a failing file is reported and the job continues; end summary lists failures; tracebacks go to `logs\app.log`.
- Cancel: `threading.Event`, checked between segments (latency = one segment decode, seconds).
- Close during a run: "Cancel and quit?" confirm.
- "Open folder" uses `os.startfile(folder)` (Windows) — the **only** OS-launch call in the app, carrying an explicit `# noqa: TID251` so a reviewer finds it by grep; guarded to `sys.platform == "win32"`, no-op elsewhere. SECURITY.md lists it under "Does".
- Nothing persisted: no config file, no remembered settings, no device detection, no GPU fallback, no stage list.
- Runs on Linux too via `uv run python -m transcribe_offline` (dev convenience; installer is Windows-only).

### `models.py` + `setup.py`

- `models.py`: `MODELS = {"et": ModelPin(repo, commit, subfolder="ct2", files={relpath: sha256}), "en": ModelPin(...)}`, plus `REQUIRED_FILES = ("model.bin", "config.json", "tokenizer.json", "vocabulary.<json|txt>", "preprocessor_config.json")`. **All five are mandatory** (see `load_model` for why). If an upstream repo at the pinned commit lacks one, stop and surface it — do not silently omit.
  - Pin the commit of each repo's `main` at implementation time. (The reviewer saw Estonian `1ae5a487…` and English `c3058b47…` in the local cache on 2026-09-27; the local HF cache holds two Estonian snapshots, so confirm against the HF API rather than trusting the cache.)
  - Hashes: only `model.bin` is LFS, so HF's API/UI shows a SHA-256 for it alone. The small JSON/txt files are plain git blobs (SHA-1). **Compute every SHA-256 from the bytes downloaded from `resolve/<commit>/…`** and hard-code them; cross-check `model.bin` against the LFS SHA-256 HF shows.
- `setup.py` (`python -m transcribe_offline.setup`): for each pinned file: if `models\<lang>\<file>` exists and SHA-256 matches → skip; else stream `https://huggingface.co/<repo>/resolve/<commit>/<subfolder/><file>` via `urllib.request` to `.partial` (console progress: MB done / total), verify, rename. Mismatch → delete + exit 1 naming the file. Idempotent and resumable-by-rerun. Uses the Windows cert store (`ssl.create_default_context()` loads it on Windows) and honours `HTTPS_PROXY`.

### `install.bat`

```
@echo off & setlocal & cd /d "%~dp0"          (all paths quoted: spaces, õ/ä/ö/ü must work)
1. set UV_CACHE_DIR=%~dp0.uv\cache  UV_PYTHON_INSTALL_DIR=%~dp0.uv\python
   set UV_NO_CONFIG=1  UV_PYTHON_PREFERENCE=only-managed  UV_SYSTEM_CERTS=1
   set UV_PYTHON_INSTALL_BIN=0        no python.exe dropped into %USERPROFILE%\.local\bin
   set UV_PYTHON_INSTALL_REGISTRY=0   no HKCU PEP 514 registry entry
   (the last two are what make "nothing outside the folder, no registry" true; stt-faster sets them at installer/setup_gui.py:488-489)
2. if not .uv\uv.exe: curl.exe -fL https://github.com/astral-sh/uv/releases/download/<UV_VERSION>/uv-x86_64-pc-windows-msvc.zip
   certutil -hashfile .uv\uv.zip SHA256 | findstr /i /x "<pinned hash>"   (certutil prints the hash alone on line 2)
     → no match: delete zip, print expected vs. actual, exit /b 1
   tar -xf .uv\uv.zip -C .uv
3. .uv\uv.exe sync --frozen --no-dev --python 3.12.<N>
   (exact Python pinned here: UV_NO_CONFIG=1 makes uv ignore a .python-version file, so there is none)
4. .venv\Scripts\python.exe -m transcribe_offline.setup
5. Desktop shortcut → .venv\Scripts\pythonw.exe -m transcribe_offline, WorkingDirectory = folder
   (powershell -NoProfile -Command WScript.Shell COM one-liner, Desktop path from
    [Environment]::GetFolderPath('Desktop') because Desktop may be redirected to OneDrive;
    best effort — on failure print "use Transcribe.bat")
6. print "Done. Start from the Desktop shortcut or Transcribe.bat." & pause
```

- Pin `UV_VERSION` to the version stt-faster's installer uses (`installer/setup_gui.py:46`, currently `0.12.19`) and its published SHA-256.
- `UV_SYSTEM_CERTS` replaces the deprecated `UV_NATIVE_TLS` (uv 0.11.23 already warns). Confirm the name against the pinned uv version with `uv help sync`.
- Some EDR products flag `certutil` usage. A `Get-FileHash` fallback is backlog, not v1.
- `curl.exe`, `certutil`, `tar.exe` ship with Windows 10 1803+ — no other tools.
- `Transcribe.bat`: `cd /d "%~dp0"` then `start "" ".venv\Scripts\pythonw.exe" -m transcribe_offline` (the cwd is what makes the un-installed package importable).
- `uninstall.bat`: removes the Desktop shortcut and tells the user to delete the folder (a script can't cleanly delete its own folder while running).
- **Upgrade** = extract new zip to a new folder, optionally copy old `models\` in, run `install.bat` (hashes re-verified, matching files skipped). No self-update, no version check.
- README warns: don't extract into a OneDrive-synced folder (Desktop/Documents are often redirected). Known limit: NTLM-authenticating proxies may break `curl.exe`.

### `SECURITY.md`

- **Does:**
  - reads the audio files the user picks
  - writes `<name>.txt` beside each one
  - writes `logs\` inside the app folder
  - opens Explorer on the output folder via `os.startfile`, only when "Open folder" is clicked
- **Never:** network at runtime, telemetry, auto-update, admin rights, registry, services or scheduled tasks, starting child processes at runtime (other than that one Explorer call), or writes outside its folder (except the shortcut and the transcripts).
- **Honest scope of the import ban:** our code makes **no direct** use of network or process APIs outside `setup.py`. Importing `faster_whisper` itself loads `socket`, `subprocess`, `http` and `huggingface_hub` into the process. The runtime guarantee therefore rests on:
  - `HF_HUB_OFFLINE=1`
  - loading every model from a local path
  - `load_model` refusing to start with any required model file missing (so faster-whisper never falls back to its tokenizer download)
  - the "unplug the network" verification step below
- **Network egress (install time only):**

  | Host | What | Pin |
  |------|------|-----|
  | github.com | uv zip | SHA-256 in `install.bat` |
  | github.com (python-build-standalone, via uv) | Python 3.12 | uv's embedded hash table |
  | pypi.org / files.pythonhosted.org | wheels | `uv.lock` hashes (`--frozen`) |
  | huggingface.co | models | commit + SHA-256 in `models.py` |

- **Trust chain:** uv zip hash → uv's Python hashes → lock wheel hashes → model hashes.
- **Verify it yourself (~15 min):**
  1. Read `install.bat`.
  2. Run `uv lock --check`.
  3. Run `ruff check` — the banned-import rule proves `app`/`engine` never import network or process modules.
  4. Install, disconnect the network, transcribe — it works.
  5. Check the model hashes:
     - `model.bin`: compare with the LFS SHA-256 shown on Hugging Face.
     - The small files: `sha256sum` them after downloading from `resolve/<pinned commit>/…`.
- Vulnerability reporting: GitHub private vulnerability reporting (enable it in the repo settings: Security → Private vulnerability reporting). No email address is published.

### CI (GitHub Actions)

- All actions pinned by commit SHA; `permissions: contents: read`; no secrets.
- **Every push, ubuntu + windows:** `ruff check` + `ruff format --check`, `pyright`, `bandit -r transcribe_offline`, `pytest` (with `--disable-socket`), `uv lock --check`, and `pip-audit` on `uv export --frozen`.
  - Ruff config includes `S` (bandit), `T201`, and a `TID251` banned-api rule over `transcribe_offline/`.
    - Banned: `socket`, `urllib`, `http`, `subprocess`, `huggingface_hub`, `ctypes`, `os.system`, `os.popen`, `os.startfile`, `os.spawn*`, `os.exec*`.
    - A per-file ignore exists **only** for `transcribe_offline/setup.py`, plus the single inline `noqa` on the `os.startfile` line in `app.py`.
    - Checked against ruff 0.12.12: TID251 bans submodules and honours per-file-ignores.
  - **Falsifier:** during implementation, temporarily add `import subprocess` to `engine.py` and confirm `ruff check` fails; record that in the commit message.
- **On a tag, or manual `workflow_dispatch` (windows):**
  - run `install.bat` end to end, with the models cached via `actions/cache` keyed on the hash of `models.py`
  - then run the golden parity test with the network disabled.
  - There is no weekly schedule, to keep CI minimal.
- **Tag:** `git archive` → `transcribe-offline-vX.Y.Z.zip` + `SHA256SUMS` + `actions/attest-build-provenance`; attach to the GitHub release.

### Tests

- Unit tests, no models: `fmt_time` (incl. NaN/inf), `format_line` both modes, `unique_destination` collisions, extension filter case-insensitivity, `setup.py` verify logic (good hash / bad hash / partial file) against a local temp file — **no mocks/monkeypatch; inject the fetch function as a defaulted parameter**.
- Golden parity test (`-m slow`, needs models):
  - **Input (ruled 2026-09-27):** `et` = TalTech `demo/etteütlus2024.wav` (verbatim repo, commit `3b546a06`) trimmed to ~25 s; `en` = a ~25 s LibriVox public-domain clip. Source URLs + licenses in `tests/fixtures/README.md`.
  - **Runs:** both languages, with timestamps on and off.
  - **Goldens:** `.txt` files generated **once** from stt-faster's GUI command: `python -m backend.cli.main transcribe process <dir> --preset {et-large|turbo} --variant 61 --language {et|en} --output-format txt --no-diarize --timestamps|--no-timestamps`, with `STT_DEVICE=cpu`.
  - **Generate goldens at the pinned model commits.** stt-faster resolves the unpinned `main`, so run it with `HF_HUB_OFFLINE=1` against an HF cache whose `refs/main` points at the commit pinned in `models.py`. Record both commits in `tests/fixtures/README.md`.
  - **Comparison:** line endings are normalised first (CRLF on Windows).
  - int8 CPU decoding should be deterministic on the same machine. If goldens differ between the ubuntu and windows runners, compare on windows only and note it.

## Build slices (each one committable; thinnest visible first)

1. **Engine + GUI runnable from a dev checkout.** Repo skeleton (`pyproject.toml` with `[tool.uv] package = false`, flat `transcribe_offline/` layout, `uv.lock`, ruff/pyright config), `engine.py`, `app.py`, `__main__.py`. Models placed by hand in `models\` (copy from HF cache). Visible: the window transcribes a file on Linux/WSL. Unit tests for the pure functions.
2. **Pinned models.** `models.py` with the resolved commits and hashes, and `setup.py`. Visible: `python -m transcribe_offline.setup` fills `models\` from empty, and a re-run is a no-op.
3. **Windows installer.** `install.bat`, `Transcribe.bat`, `uninstall.bat`. Visible: a fresh Windows user without admin extracts to a path containing spaces and `õ`, installs, launches from the shortcut, transcribes with the network off.
4. **Reviewer proof.** `SECURITY.md`, `README.md`, `LICENSE` (match stt-faster's), CI workflow with the banned-api falsifier, golden parity test, release workflow.

## Out of scope / backlog

- `install.bat --models-from <old folder>` to automate upgrade model reuse
- dropping `onnxruntime` via a uv override
- NTLM proxy support
- `Get-FileHash` fallback if EDR blocks `certutil`
- Linux/macOS installer
- signed git tags
- Dependabot/Renovate for `uv.lock`
- porting any other stt-faster feature (speaker ID, GPU, drag-and-drop, denoise, variants, CLI, Docker, DB)
