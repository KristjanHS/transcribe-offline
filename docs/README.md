# Where things live

## App (`app/`, a uv project)

- [`transcribe_offline/__init__.py`](../app/transcribe_offline/__init__.py): sets `HF_HUB_OFFLINE` before faster-whisper can load the Hub client, and defines the app folder.
- [`transcribe_offline/__main__.py`](../app/transcribe_offline/__main__.py): installs the guard, then opens the GUI, or the CLI when given arguments.
- [`transcribe_offline/guard.py`](../app/transcribe_offline/guard.py): audit hook that refuses network, child processes and writes outside the allowed folders.
- [`transcribe_offline/app.py`](../app/transcribe_offline/app.py): Tkinter GUI with file picker, language choice, progress and cancel.
- [`transcribe_offline/cli.py`](../app/transcribe_offline/cli.py): Linux command line, `-l et|en`, exit codes 0, 1 and 130.
- [`transcribe_offline/job.py`](../app/transcribe_offline/job.py): the worker thread the GUI and CLI share, including the CPU fallback when CUDA fails.
- [`transcribe_offline/engine.py`](../app/transcribe_offline/engine.py): model loading, PyAV decoding behind the format and codec whitelist, `.txt` writing.
- [`transcribe_offline/models.py`](../app/transcribe_offline/models.py): model repos, commits and SHA-256 hashes.
- [`transcribe_offline/setup.py`](../app/transcribe_offline/setup.py): install-time GPU check and model download; the one module allowed network and processes.
- [`tests/`](../app/tests): offline pytest suite, plus a real-model smoke test marked `slow`.

## Install and packaging

- [`installer/`](../installer): `Setup.cs`, the source of `Transcribe-Setup.exe`, and its manifest.
- [`install.bat`](../install.bat): the fallback installer; same steps as the exe.
- [`pins.txt`](../pins.txt): uv version and hashes and the Python version, read by both installers.
- [`transcribe`](../transcribe): Linux launcher for the CLI.
- [`scoop/`](../scoop): Scoop manifest, installable by URL.
- [`.github/winget/`](../.github/winget): winget manifests for submission to microsoft/winget-pkgs.

The release zip holds `app/`, `Transcribe-Setup.exe` (compiled from `installer/Setup.cs`), `install.bat`,
`pins.txt` and `LICENSE`.

## CI

- [`.github/workflows/ci.yml`](../.github/workflows/ci.yml): lint, types, security scanners, tests, `pip-audit` and a compile of `Setup.cs`, on every push, pull request and weekly.
- [`.github/workflows/release.yml`](../.github/workflows/release.yml): builds or reuses the exe, installs as a standard Windows user, runs the smoke test, publishes the zip.
- [`.github/scripts/`](../.github/scripts): helpers for those workflows, and `winget-sandbox-test.ps1`, which installs the winget package in a fresh Windows Sandbox.

## Docs

- [`SECURITY.md`](../SECURITY.md): what the app reads, writes and refuses, and what that rests on.
- [`docs/install.md`](install.md): full install, upgrade and uninstall steps for Windows and Linux.
- [`docs/architecture.md`](architecture.md): flowchart and design decisions.
- [`docs/how-it-was-built.md`](how-it-was-built.md): five trails from plan to merged diff, with what review changed.
- [`CLAUDE.md`](../CLAUDE.md): the invariants a change must keep, written for coding agents.

## Plans (`docs/plans/archive/`)

- [Minimal app design](plans/archive/2026-09-27-transcribe-offline-minimal-app-design.md): scope, first decisions and parity with stt-faster.
- [Security critique](plans/archive/2026-09-27-security-critique-todo.md): an eight-angle security review and its fixes.
- [Reviewer-trust simplification](plans/archive/2026-09-27-reviewer-trust-simplification.md): cuts to what a reviewer must read or trust.
- [Exe installer](plans/archive/2026-09-28-exe-installer.md): pinned native wheels, `Transcribe-Setup.exe` and `pins.txt`.
- [App Control](plans/archive/smart-app-control.md): App Control blocking setup and transcription on a managed Windows 11 PC.
- [Trust without a certificate](plans/archive/2026-10-01-trust-without-certificate.md): fixed exe hash, Scoop and winget.
- [GPU support](plans/archive/2026-10-07-gpu-support.md): NVIDIA detection at install, CPU fallback at run time.

## Working from source

Run these in `app/`:

```sh
uv sync
uv run python -m transcribe_offline.setup   # models, about 3 GB
uv run python -m transcribe_offline         # GUI; runs on Linux too
uv run pytest                               # add -m slow for the real-model smoke test
uv run ruff check . && uv run ruff format --check . && uv run pyright
```

To test the winget package in Windows Sandbox, from the repo root in a PowerShell that is not
elevated: `powershell -ExecutionPolicy Bypass -File .github\scripts\winget-sandbox-test.ps1`. The
script's header lists what it changes on the PC.
