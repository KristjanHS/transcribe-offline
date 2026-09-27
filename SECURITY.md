# Security

transcribe-offline turns audio files into `.txt` transcripts on the user's own CPU. The whole app is
under 500 lines of Python in `transcribe_offline/` plus three `.bat` files, written to be read in full.

## What it does

- Reads the audio files the user picks.
- Writes `<name>.txt` beside each one (`<name> (2).txt` if that exists), via a transient
  `<name>.txt.partial` beside it that is renamed on success and deleted on cancel or failure.
- Writes `logs\app.log` inside the app folder.
- Opens Explorer on the output folder via `os.startfile`, only when "Open folder" is clicked
  (`transcribe_offline/app.py`, the one line carrying `noqa: ... TID251`).

## What it never does

No network access at runtime, no telemetry, no auto-update, no admin rights, no registry writes by the
app itself (the Windows file dialog records recent folders, as for any app), no services or scheduled
tasks, no child processes at runtime (other than that one Explorer call), and no writes outside its
folder except the Desktop shortcut and the transcripts.

## Honest scope of the import ban

Ruff rule `TID251` (config in `pyproject.toml`) forbids our code from importing `socket`, `urllib`,
`http`, `subprocess`, `huggingface_hub`, `ctypes` or calling `os.system`/`popen`/`startfile`/`spawn*`/
`exec*`, everywhere except `transcribe_offline/setup.py` (install time). `tests/test_imports.py` parses
the runtime modules (`__init__`, `__main__`, `app`, `engine`, `models`; not `setup.py`) and fails if any
static import is outside an explicit allow-list, if anything but `WhisperModel` is imported from
`faster_whisper`, or if `__import__`, `importlib`, `eval` or `exec` appear by name. Both are static
checks of our source only: they don't cover indirect access (e.g. `getattr`) or what imported libraries
do. Importing `faster_whisper` itself still loads `socket`, `subprocess`, `http` and `huggingface_hub`
into the process. The runtime guarantee therefore rests on:

- `HF_HUB_OFFLINE=1` being set before `faster_whisper` is imported (`engine.load_model`, `__main__.py`);
- every model loading from a local folder path;
- `engine.load_model` refusing to start if any of the five required model files is missing, so
  faster-whisper never falls back to downloading a tokenizer;
- the "disconnect the network" check below.

## Network egress (install time only)

| Host | What | Pin |
|------|------|-----|
| github.com → release-assets.githubusercontent.com | uv 0.12.19 zip | SHA-256 in `install.bat` |
| github.com (python-build-standalone, via uv) | Python 3.12.14 | uv's embedded hash table |
| pypi.org / files.pythonhosted.org | wheels | `uv.lock` hashes (`uv sync --frozen`) |
| huggingface.co → us.aws.cdn.hf.co (`model.bin`) | models | commit + SHA-256 per file in `transcribe_offline/models.py` |

Redirect hosts as observed with `curl -sI`; the hashes, not the hosts, are the integrity anchor.
python-build-standalone's CDN host is whatever github.com redirects to (unverified until the first
Windows run).

Trust chain: uv zip hash → uv's Python hashes → lock wheel hashes → model hashes. The project itself is
never built (`[tool.uv] package = false`), so no unpinned build backend is fetched.

## Verify it yourself (~15 min)

1. Read `install.bat`.
2. Run `uv lock --check`.
3. Run `uv run ruff check .` and `uv run pytest tests/test_imports.py` — they pass only if the runtime
   modules' static imports stay inside the ban and the allow-list. To see them bite, add
   `import subprocess` to `engine.py` and run both again.
4. Install, disconnect the network, transcribe a file — it works.
5. Check the model hashes:
   - `model.bin`: compare with the LFS SHA-256 Hugging Face shows for the pinned commit.
   - The small files: `sha256sum` them after downloading from `resolve/<pinned commit>/…`.

## Reporting a vulnerability

Use GitHub private vulnerability reporting on this repository (Security → Report a vulnerability).
