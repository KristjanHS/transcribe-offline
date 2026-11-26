# transcribe-offline

Offline Estonian and English speech-to-text, small enough to audit.

[![CI](https://github.com/KristjanHS/transcribe-offline/actions/workflows/ci.yml/badge.svg)](https://github.com/KristjanHS/transcribe-offline/actions/workflows/ci.yml)
[![Latest release](https://img.shields.io/github/v/release/KristjanHS/transcribe-offline?sort=semver&label=latest%20release)](https://github.com/KristjanHS/transcribe-offline/releases/latest)
[![License](https://img.shields.io/github/license/KristjanHS/transcribe-offline)](LICENSE)

## Quick start

Windows 10 1803+ or 11, no admin rights:

1. Download `transcribe-offline-vX.Y.Z.zip` from the [latest release](https://github.com/KristjanHS/transcribe-offline/releases/latest)
   and extract it to a folder OneDrive doesn't sync.
2. Double-click `Transcribe-Setup.exe`, then start the `Transcribe.bat` that setup creates in the
   folder. Pick audio files, choose the language, press Start.

With [Scoop](https://scoop.sh), which skips the SmartScreen prompt:

```powershell
scoop install https://raw.githubusercontent.com/KristjanHS/transcribe-offline/main/scoop/transcribe-offline.json
```

Linux CLI (x86-64), with `git` and [uv](https://docs.astral.sh/uv/):

```sh
git clone https://github.com/KristjanHS/transcribe-offline.git
cd transcribe-offline/app
uv sync --frozen --no-dev                     # locked, hash-checked libraries
.venv/bin/python -m transcribe_offline.setup  # pinned, SHA-256-verified models, about 3 GB
cd .. && ./transcribe -l et talk.mp3          # -l en for English; several files at once are fine
```

The rest is in [docs/install.md](docs/install.md): verifying the zip, GPU requirements, what to do when
Windows or an antivirus blocks setup, upgrades, and a Linux install without the setup script.

## What it does

- Transcribes Estonian or English audio with two pinned Whisper models.
- Saves each transcript as a `.txt` file next to its audio file.
- On Windows it's a small GUI. On Linux, `./transcribe -l et|en <files>` exits with 0 when every file
  worked, 1 if any failed, and 130 on Ctrl+C.
- Runs on an NVIDIA GPU when setup finds one (compute capability 7.0+, such as GTX 16 or RTX, 4000 MiB+
  of memory, driver 528.33+). If the model fails to load on the GPU, or the first file fails there, the
  rest of the run uses the CPU. A native CUDA or cuDNN crash closes the app instead.
- Needs no network once installed.

## How it works

Install time and run time are split. Setup is the only code that goes online. It downloads uv, Python,
the locked libraries and the models, and checks uv, the libraries and the models against SHA-256 hashes
in the repo (`pins.txt`, `app/uv.lock`, `app/transcribe_offline/models.py`). For Python, `pins.txt` fixes
only the version; uv checks the download against the hashes built into it. The app itself runs under `guard.py`,
a Python audit hook (PEP 578) installed before anything else loads. It refuses sockets, child processes,
and writes anywhere except the app folder and next to the chosen audio. A ruff `TID251` ban rejects the
same imports at lint time in every module but `setup.py`, so a stray `socket` or `subprocess` import
fails CI before the hook would have to block it.
The hook only sees Python-level calls, not native code such as FFmpeg. [SECURITY.md](SECURITY.md) lists
what the app reads, writes and refuses. The flowchart and the design decisions, each with the alternative
it beat, are in [docs/architecture.md](docs/architecture.md).

## How it was built

Claude Code wrote most of the code from written plans, and I reviewed what it produced. Good thing, too.
Once the agent claimed that hiding Tcl's `exec` and `socket` commands had been "verified by unit
test", but `interp invokehidden` got around the hiding in one line. We dropped it and banned `.call` and
`.eval` in runtime modules. Windows took the longest to debug: App Control blocked PyAV 18's
`_core.pyd`, so the native wheels are pinned to versions that already ran on that PC. Bitdefender then
quarantined the installer, partly for starting `curl.exe` and `tar.exe`, so it now downloads and unzips
in managed C# code. These cases and three more, each with its diff, are in
[docs/how-it-was-built.md](docs/how-it-was-built.md). The workflow and agent setup are in
[claudeconf](https://github.com/KristjanHS/claudeconf).

Rewritten from the GUI path of [stt-faster](https://github.com/KristjanHS/stt-faster).

## Tests

```sh
uv --directory app run pytest
```

This runs the 51 test functions in `app/tests/` (a static count of `def test_`) with sockets disabled
(`--disable-socket` in `app/pyproject.toml`). `uv --directory app run pytest -m slow` adds the real-model
smoke test and needs `app/models/`.

CI runs on every push and pull request, and weekly so new advisories surface: ruff, pyright, bandit,
zizmor, pytest, pip-audit on the locked dependencies, and a compile of `installer/Setup.cs`. A release
also installs as a standard Windows user and fails if setup or the smoke test writes outside the folder.

## Limits

- Two languages, Estonian and English (the `MODELS` keys in `app/transcribe_offline/models.py`).
- Setup downloads about 3.5 GB once, plus 1.3 GB of CUDA libraries on an NVIDIA GPU. The models take 3.0 GB.
- Each file is decoded into memory whole: at least 230 MB of RAM per hour of audio, with no length cap.
- `Transcribe-Setup.exe` is unsigned, so SmartScreen warns and some antivirus tools quarantine it.
- Proxies that require NTLM authentication may block the setup download.

## License

MIT. See [LICENSE](LICENSE).

## Code signing policy

`Transcribe-Setup.exe` is not signed yet; an application to [SignPath Foundation](https://signpath.org)'s
free open-source code signing is in progress. Approvals will happen only for exes built by `release.yml` from this repository.

- Committers, reviewers and approvers: [KristjanHS](https://github.com/KristjanHS) (sole maintainer).
- Privacy: this program will not transfer any information to other networked systems unless specifically
  requested by the user or the person installing or operating it. Setup downloads from GitHub
  ([privacy](https://docs.github.com/site-policy/privacy-policies/github-general-privacy-statement)),
  Astral, for Python ([privacy](https://astral.sh/legal/privacy)),
  PyPI ([privacy](https://policies.python.org/pypi.org/Privacy-Notice/)) and Hugging Face
  ([privacy](https://huggingface.co/privacy)); the app itself makes no network connections.
