# Reviewer-trust simplification

**Status:** ✅ SHIPPED — Windows `workflow_dispatch` run owed (validates Stage 4.6)
**Date:** 2026-09-27

Goal: shrink what a security reviewer must read or take on trust. Scope: every tracked file + the locked runtime wheel set. User ruling (2026-09-27): stt-faster output parity is no longer a constraint.

## Premise probes (run 2026-09-27, read-only / scratch copy)

- `sys.modules['onnxruntime']=None; import faster_whisper; from faster_whisper import WhisperModel` → imports fine. onnxruntime is imported only lazily in `faster_whisper/vad.py:298`; `vad_filter` defaults to `False` and `engine.py:94-96` never sets it.
- Top-level imports in faster_whisper: `audio.py:15 av`, `transcribe.py:17 tqdm`, `utils.py:7 huggingface_hub` → hub, tokenizers, tqdm, av can NOT be dropped.
- Real run with `onnxruntime, hf_xet, httpx, httpcore, anyio, h11, fsspec, click, certifi, idna, filelock, flatbuffers, google.protobuf` blocked: `engine.load_model` + `transcribe_file(en.wav, timestamps=True)` → byte-identical to `tests/fixtures/golden/en-ts.txt`; none of the blocked modules loaded.
- Scratch copy + `[tool.uv] exclude-dependencies = ["onnxruntime", "hf-xet", "httpx", "fsspec", "click"]` → `uv lock` (uv 0.11.23) removes 7+3 packages, writes `[manifest] excludes = [...]`, keeps every remaining hash; `uv sync --frozen` OK; `pip-audit`, `bandit`, `pytest` still run; `find_spec` is `None` for all five. (filelock/certifi/idna must stay: pip-audit's cachecontrol/requests need them in the dev env.)
- Runtime set (`uv export --no-dev`): 24 packages today → 12 with the exclusions (faster-whisper, av, ctranslate2, numpy, pyyaml, huggingface-hub, filelock, packaging, tqdm, typing-extensions, tokenizers, colorama[win]).
- huggingface_hub `utils/_telemetry.py:31-32`: "Telemetry is also disabled in offline mode (`HF_HUB_OFFLINE=1`)".
- faster-whisper defaults: `beam_size=5, patience=1, repetition_penalty=1, vad_filter=False`.
- `uv sync --help` → `--system-certs [env: UV_SYSTEM_CERTS=]` exists (install.bat:17 valid).
- PyAV 18.1.0 (hls demuxer present): local file `evil.mp3` holding an HLS playlist → `InvalidDataError`, local listener got no connection. Positive control (`.m3u8`) also failed → inconclusive, see [AUDIT] A1.

## Refactor-first assessment

- None needed. Modules are already split by trust role (setup = network at install, models = pins, engine = transcription, app = GUI). Every candidate is local to 1-3 files; Stage 1 is config + lock only.

## Stage 1.1 — Exclude onnxruntime (unused Silero VAD)

- Focus: `pyproject.toml` (`[tool.uv]`, line 13-15), `uv.lock`, `tests/test_imports.py`, `SECURITY.md:28-32`.
- Change: `exclude-dependencies = ["onnxruntime"]` + 1-line comment (`# Silero VAD only; engine never enables vad_filter`). `uv lock && uv sync`.
- Add falsifier to `tests/test_imports.py`: parametrized `assert importlib.util.find_spec(module) is None` over an `EXCLUDED` list. Demonstrate it fails first: add the test, run it before `uv lock`/`uv sync` → red; after → green.
- Saves: onnxruntime (large native wheel), flatbuffers, protobuf — 3 runtime packages. Reviewer no longer asks "why is an ONNX runtime shipped?".
- Risk: a future faster-whisper upgrade that imports onnxruntime at module top fails loud (ImportError), never silently. The test catches re-introduction.
- Verify: `uv run pytest`, `uv run pytest -m slow` (models present), ruff, pyright; `uv lock --check` with the pinned uv (`uvx --from uv==0.12.19 uv lock --check`, or CI). Windows: release.yml `workflow_dispatch`.

## Stage 1.2 — Exclude the Hub's network stack

- Focus: same files as 1.1.
- Change: `exclude-dependencies` += `"hf-xet", "httpx", "fsspec", "click"`; comment `# Hub download/CLI stack; models load from a local path`. Extend `EXCLUDED`.
- `SECURITY.md:31-32`: replace "Importing faster_whisper itself still loads … huggingface_hub" with: huggingface_hub is imported but its HTTP client (httpx) and Xet downloader are not installed (`exclude-dependencies`, `tests/test_imports.py`), so it cannot download even if asked. Add as first bullet of the "runtime guarantee rests on" list.
- Saves: httpx, httpcore, h11, anyio, hf-xet (native Rust downloader), fsspec, click; certifi/idna leave the runtime set — 7 packages removed from the lock, runtime 21 → 12.
- Trust: turns "HF_HUB_OFFLINE is set" (env discipline) into "no HTTP client library besides stdlib exists in the runtime venv" (checkable with `uv tree --no-dev`).
- Risk: hub/tokenizers upgrade that imports httpx eagerly → ImportError at launch (fail-closed). Probe above covers import + model load + transcription on Linux only.
- Verify: as 1.1, plus release.yml `workflow_dispatch` on Windows (install.bat `uv sync --frozen --no-dev` + real-model test under the firewall).

## Stage 2 — Replace the stt-faster parity machinery with a real-model smoke test

- Focus: `tests/test_golden.py` → `tests/test_models.py`, delete `tests/fixtures/golden/*.txt` (4 files), `tests/fixtures/README.md`, `pyproject.toml:65`, `README.md:26`, `CLAUDE.md:15`, `.github/workflows/release.yml:9,38,41`, `transcribe_offline/engine.py:98`.
- `tests/test_models.py` (~18 lines, `@pytest.mark.slow`): parametrize `("Estonian", "et.wav", "Tartus")`, `("English", "en.wav", "Gettysburg")`; copy wav to `tmp_path`, `load_model` + `transcribe_file(timestamps=False)`, assert the word is in the output. No byte comparison, no CRLF normalisation, no cached-model helper.
- `tests/fixtures/README.md`: retitle "Test audio"; keep the source/license table + ffmpeg cut line; delete lines 10-21 (stt-faster regen recipe + regen rule).
- `pyproject.toml:65` marker → `"slow: needs models/ (real-model smoke test)"`; README/CLAUDE.md "golden parity" → "real-model smoke test"; release.yml job `install-and-parity` → `install-and-smoke` (and its `needs:`), step name line 38 likewise.
- `engine.py:98` comment → `# Platform newline (CRLF on Windows).` (drop the stt-faster reference).
- Keep the `slow` marker: `-m 'not slow'` keeps `uv run pytest` fast on a dev box that has `models/`; a skip-if-no-models would silently pass in CI.
- Saves: ~35 lines of test/fixture docs, 4 golden files, an external repo (stt-faster @ `3cfbae7`) the reviewer cannot check, and the "regenerate goldens when ctranslate2/av/tokenizers/numpy move" maintenance rule.
- Afterwards transcription correctness is guarded by: unit tests (format, timestamps, cancel, `.partial` cleanup, decode kwargs) + a per-language real-model check that the expected word appears, run on Windows with outbound firewall block in release.yml.
- Risk: token-level regressions (e.g. "Libravox" vs "LibriVox") no longer fail CI — accepted by the ruling.
- Verify: `uv run pytest`, `uv run pytest -m slow` (models present), ruff, pyright. Windows: release.yml `workflow_dispatch`.

## Stage 3 — One site for the HF env vars

- Focus: `transcribe_offline/__main__.py:3-9`, `transcribe_offline/engine.py:53`, `SECURITY.md:34`.
- Change: move `HF_HUB_DISABLE_TELEMETRY=1` next to `HF_HUB_OFFLINE=1` in `engine.load_model` (the only runtime import of faster_whisper: `engine.py:54`; the `engine.py:15` import is `TYPE_CHECKING`-only). `__main__.py` becomes docstring + `from transcribe_offline.app import main` + `main()`; the `# noqa: E402` goes.
- `SECURITY.md:34` → "set in `engine.load_model` immediately before the only runtime import of `faster_whisper`".
- Saves: ~6 lines, one duplicated guard, one noqa. Reviewer checks one place instead of reasoning about import order across two.
- Guard kept (not dropped): both vars still set, still before import, and the golden/smoke path already exercises exactly this site. Telemetry var is redundant with offline mode (hub docs) but kept as an explicit, 1-line "no telemetry" anchor.
- Risk: none found — `grep` shows no other runtime import of faster_whisper/huggingface_hub (ruff TID251 bans the latter).
- Verify: `uv run pytest` (test_imports allow-list still passes), ruff, pyright.

## Stage 4 — Drop the `Lang` indirection; one `MODELS_ROOT`

- Focus: `transcribe_offline/engine.py:8,20-29,48-49,86,95`, `transcribe_offline/app.py:20,35,135`, `transcribe_offline/models.py:3,28`, `transcribe_offline/setup.py:22`, tests using `engine.LANGUAGES`.
- Change: `LANGUAGES = {"Estonian": "et", "English": "en"}`; `code` doubles as the `models/` folder name (both fields are identical today). `load_model(models_root, code: str)`, `transcribe_file(..., language: str, ...)`, `run_job(..., language: str, ...)`. Remove `Lang` + the `dataclass` import from engine.
- `MODELS_ROOT = Path("models")` defined once in `models.py` (next to the pins it describes); `app.py:20` and `setup.py:22` import it. Update `models.py:28` comment ("Keys are the language code and the folder under models/").
- Saves: ~8 lines, one dataclass, one duplicated constant.
- Risk: none behavioural; pyright catches missed call sites.
- Verify: `uv run pytest`, `uv run pytest -m slow`, ruff, pyright.

Rulings (2026-09-27 qimpag round): D1 B, D2 B, D3 B, D4 A (keep tuned kwargs), D5 A (keep bandit), D6 C, A1 run probe, A2 write blind.

## Stage 4.1 — D1: drop the Desktop shortcut
- Focus: `install.bat:5,11,43-47`, delete `uninstall.bat`, README step 3, SECURITY.md "What it never does", CLAUDE.md invariant 3, release.yml refs.
- install.bat loses the PowerShell line + `APP_DIR`; README → "start `Transcribe.bat` (right-click → Send to → Desktop for a shortcut)"; invariant → "writes nothing outside its folder except transcripts".

## Stage 4.2 — D2: remove the "Open folder" button
- Focus: `app.py:110-113,177-180` (+ `last_saved`, `sys` import if unused), `pyproject.toml:37` banned-api message, SECURITY.md Explorer bullet + caveat → "no child processes at runtime".

## Stage 4.3 — D3: one log file, overwritten per launch
- `logging.FileHandler(LOG_FILE, mode="w", encoding="utf-8")`; drop `logging.handlers` import + its `tests/test_imports.py` allow-list entry; SECURITY.md:11 stays `logs\app.log`.

## Stage 4.4 — D6: `.gitattributes` → `.claude/ export-ignore`
- Verify: `git archive HEAD | tar -t` / zip listing has no `.claude/` (after commit).

## Stage 4.5 — A1: settle the PyAV local-file URL probe
- Scratch only: positive control `av.open("http://127.0.0.1:8765/x.m3u8")` must HIT the listener; then the same playlist as local `.mp3` path and as `open(path, "rb")`. No hit → one honest-scope line in SECURITY.md; hit → stop, user decision (file object vs document).

## Stage 4.6 — A2: newer-than diff replaces the 4-path denylist (release.yml:22-27)
- Timestamp before install.bat; fail if any file under `%USERPROFILE%`/`%TEMP%` newer than it lies outside the checkout/runner dirs (expected set empty after 4.1). Blind — validated on the first `workflow_dispatch`.

## Considered, rejected

- Derive `REQUIRED_FILES` from pin keys: drops the "every pin covers the mandatory set" guard (`tests/test_setup.py:23-27`).
- Drop hub/tokenizers/tqdm/av: top-level imports in faster_whisper (probe above).
- Drop the explicit `ssl.create_default_context()` (setup.py:36): redundant with urlopen's default, but "TLS verification is on" is exactly what a reviewer looks for.
- Drop `is_audio`/"All files" filter, fmt_time NaN guard, setup.main unused params, `LOG_EVERY` modulo trick: ≤3 lines each or user-visible.
- Drop `actions/cache` in release.yml: 3 GB per run; setup.py re-hashes every cached file, so a poisoned cache cannot inject a model.
- Reuse `.uv\uv.exe` instead of the second `setup-uv` in release.yml: the action is already trusted in ci.yml, so the trusted set does not shrink; adds env-var plumbing.
- Collapse the `os.spawn*`/`os.exec*` banned-api entries: ruff needs one entry per name.

## Stage 5 — Full verify + review

- `uv lock --check` (and with uv 0.12.19), `uv sync`, `uv run pytest`, `uv run pytest -m slow` (models present), `uv run ruff check . && uv run ruff format --check . && uv run pyright`.
- `uv tree --no-dev` shows none of the excluded packages; SECURITY.md line count claim (`SECURITY.md:4`, "under 500 lines") still true.
- Grep for stale refs: `stt-faster`, `golden`, `parity`, `Lang`, `model_dir`, `startfile`, `shortcut`, `uninstall`, `RotatingFileHandler`; `REQUIRED_FILES` usage unchanged.
- Windows: one release.yml `workflow_dispatch` run (install.bat end to end, outside-folder check, firewall + `pytest -m slow`).
- Code review in a fresh `code-reviewer` sub-agent over the whole plan range (`git diff <pre-Stage-1>..HEAD`), with SECURITY.md claims checked against the code.
