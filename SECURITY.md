# Security

transcribe-offline turns audio files into `.txt` transcripts on the user's own CPU. The whole app is
654 lines of Python in `app/transcribe_offline/` (`wc -l` of its `.py` files) plus the installer
(`installer/Setup.cs`, 181 lines, built into `Transcribe-Setup.exe`) and its fallback `install.bat`,
written to be read in full.

## What it does

- Reads the audio files the user picks. Each is decoded into memory whole (at least 230 MB per hour of
  audio); there is no size or duration limit.
- Writes `<name>.txt` beside each one (`<name> (2).txt` if that exists), via a transient
  `<name>.txt.partial` beside it that is renamed on success and deleted on cancel or failure.
  A hard kill (power loss, Task Manager, a native crash) can leave the `.partial` file behind.
- The `.txt` goes wherever the audio is, including cloud-synced folders (OneDrive) and network
  shares, and gets that folder's permissions.
- Writes `logs\app.log` inside the app folder, overwritten on each launch. It can
  contain audio file names.

## What it never does

Our code never opens a network connection or starts a child process at runtime, and writes nothing
outside its folder except the transcripts. No telemetry, no auto-update, no admin rights, no registry
writes by the app itself (the Windows file dialog records recent folders, as for any app), no services
or scheduled tasks. Native libraries (FFmpeg, CTranslate2, tokenizers), Tcl and Windows itself are
outside what our code controls; see the threat model below.

Windows Error Reporting may send a crash report, which can hold audio or transcript data, to
Microsoft. Admins can stop that with the WER group policy (`Disabled` or `DontSendAdditionalData`).

## Threat model

| Threat | Control | Verified by |
|--------|---------|-------------|
| Crafted audio file attacks FFmpeg | `engine.decode_audio`: `file` protocol only, 8 demuxers, audio-codec allow-list (FFmpeg's decoder whitelist, applied before any decoder runs) | unit tests |
| A memory-corruption bug in FFmpeg or CTranslate2 | none: no sandbox, the app runs with the user's rights (accepted risk) | not verified |
| Our code opens a socket, starts a process or writes outside its folder | import ban (`TID251`, `test_imports.py`); runtime audit hook `guard.py` | static checks, unit tests, release smoke test |
| Native code (FFmpeg, CTranslate2, Tcl) opens a socket | FFmpeg `file` protocol only; our code never passes Tcl text (no `.call`/`.eval`). The audit hook cannot see native code | Tcl: `test_imports.py`; FFmpeg, CTranslate2: not verified |
| Install or app writes outside the folder | `Transcribe-Setup.exe` / `install.bat` point uv's cache, Python and temp files at `app\`; `guard.py` at runtime | release CI: install, then smoke test, then a check of the user profile, `%TEMP%` and uv's HKCU key |
| Tampered download at install time | SHA-256 pins (table below) | `test_setup.py`; release CI runs `Transcribe-Setup.exe`, then `install.bat` |
| Tampered release zip | provenance attestation | the user (README install step 1) |
| Transcript leaves the machine (OneDrive, share, WER) | none in the app; user's folder choice, admin WER policy | not verified |
| Known vulnerability in a pinned dependency | weekly `pip-audit` in CI; new release (see Updates) | CI; native parts manual |

## Honest scope of the import ban

Ruff rule `TID251` (config in `app/pyproject.toml`) forbids our code from importing `socket`, `urllib`,
`http`, `subprocess`, `huggingface_hub`, `ctypes` or calling `os.system`/`popen`/`startfile`/`spawn*`/
`exec*`, everywhere except `app/transcribe_offline/setup.py` (install time). `app/tests/test_imports.py` parses
the runtime modules (`__init__`, `__main__`, `app`, `engine`, `guard`, `models`; not `setup.py`) and fails if any
static import is outside an explicit allow-list, if anything but `WhisperModel` is imported from
`faster_whisper`, or if `__import__`, `importlib`, `eval`, `exec` or `call` (Tcl) appear by name. Both are static
checks of our source only: they don't cover indirect access (e.g. `getattr`) or what imported libraries
do. Importing `faster_whisper` itself still loads `socket`, `ssl`, `subprocess` and `huggingface_hub`
into the process. The runtime guarantee therefore rests on:

- huggingface_hub's HTTP client (`httpx`) and Xet downloader not being installed
  (`[tool.uv] exclude-dependencies`, checked by `app/tests/test_imports.py`), so it cannot download even
  if asked;
- `HF_HUB_OFFLINE=1` being set when the package is imported (`transcribe_offline/__init__.py`), before
  anything imports `faster_whisper`;
- every model loading from a local folder path;
- `engine.load_model` refusing to start if any of the five required model files is missing, so
  faster-whisper never falls back to downloading a tokenizer;
- FFmpeg opening only local files, with the demuxer and codec allow-lists in `engine.py`;
- `guard.py`, a Python audit hook that `__main__` installs first: it refuses socket creation, DNS lookups,
  child processes, and writes, renames and removes outside the app folder or the chosen audio's
  folder. It sees Python calls only, not native code (FFmpeg, CTranslate2, Tcl);
- the "disconnect the network" check below.

## Network egress (install time only)

| Host | What | Pin |
|------|------|-----|
| github.com → release-assets.githubusercontent.com | uv 0.12.19 zip | SHA-256 in `pins.txt` |
| github.com (python-build-standalone, via uv) | Python 3.12.14 | uv's embedded hash table |
| pypi.org / files.pythonhosted.org | wheels | `app/uv.lock` hashes (`uv sync --frozen`) |
| huggingface.co → us.aws.cdn.hf.co (`model.bin`) | models | commit + SHA-256 per file in `app/transcribe_offline/models.py` |

Redirect hosts as observed with `curl -sI`; the hashes, not the hosts, are the integrity anchor.
python-build-standalone's CDN host is whatever github.com redirects to (unverified until the first
Windows run). `Transcribe-Setup.exe` and `install.bat` clear inherited `UV_*` and `SSL_CERT_*`
variables that could redirect a download.

Trust chain: release zip (provenance attestation; the exe inside also carries the attestation of the
run that compiled it) → uv zip hash → uv's Python hashes → lock wheel
hashes → model hashes. `SHA256SUMS` sits in the same release as the zip, so it catches corruption, not
tampering. The project itself is never built (`[tool.uv] package = false`), so no unpinned build
backend is fetched. Each setup run re-hashes `uv.exe` and every model file and downloads
again any that do not match; it does not re-check the installed Python or wheels.

Releases also ship `sbom.cdx.json` (CycloneDX list of the locked Python packages), covered by
`SHA256SUMS` and the attestation.

`Transcribe-Setup.exe`, `install.bat` and the Python executables are unsigned. Windows may warn before
running them, and AppLocker/WDAC default rules may block programs in a user folder. The exe is rebuilt
only when `installer/` changes, so its hash (and Windows reputation) stays the same across releases;
`gh attestation verify Transcribe-Setup.exe -R KristjanHS/transcribe-offline` names the run that compiled
it. `av`, `ctranslate2`, `numpy` and `tokenizers` are held at versions Windows App Control already
trusts (`constraint-dependencies` in `app/pyproject.toml`). For an allow-list: `uv.exe`'s SHA-256 is
`UV_EXE_SHA256` in `pins.txt`; hash the Python executables under `app\.uv\python\` and
`app\.venv\Scripts\` after install. Windows itself logs .NET and PowerShell runs under
`%LOCALAPPDATA%\Microsoft\` (`CLR_v4.0\UsageLogs`, `Windows\PowerShell`); the release CI allows only those.

## Updates

Installs never update themselves: Python, FFmpeg and every other pinned part stay as they are until
you install a new release. Security updates are a new release. A high-severity issue in a runtime
dependency gets a new release within 14 days.

`pip-audit` sees PyPI advisories only. Before each release the maintainer checks the upstream
advisories of the native parts: uv and CPython (pins in `pins.txt`), FFmpeg 8.0 (bundled in `av` 16.0.1), CTranslate2 and
tokenizers (versions in `app/uv.lock`).

## Verify it yourself (~15 min)

1. Read `installer/Setup.cs` (`install.bat` does the same steps).
2. In `app/` of a git clone, run `uv lock --check`.
3. Run `uv run ruff check .` and `uv run pytest tests/test_imports.py` — they pass only if the runtime
   modules' static imports stay inside the ban and the allow-list. To see them bite, add
   `import subprocess` to `engine.py` and run both again.
4. Install, disconnect the network, transcribe a file — it works.
5. Check the model hashes:
   - `model.bin`: compare with the LFS SHA-256 Hugging Face shows for the pinned commit.
   - The small files: `sha256sum` them after downloading from `resolve/<pinned commit>/…`.

Secret scanners such as gitleaks flag the SHA-256 pins in `models.py` as API keys; they are hashes.

## Reporting a vulnerability

Use GitHub private vulnerability reporting on this repository (Security → Report a vulnerability).
