# transcribe-offline

Transcribe Estonian or English audio to text on your own computer. Nothing is uploaded; after
installation the app works with the network unplugged. See `SECURITY.md` for exactly what it does.

## Install (Windows 10 1803+ / 11, no admin rights)

1. Download `transcribe-offline-vX.Y.Z.zip` from the Releases page and extract it to any folder.
   Don't use a OneDrive-synced folder (Desktop and Documents often are).
2. Double-click `install.bat`. It downloads about 3.5 GB (uv, Python, libraries, two speech models),
   verifying every file against a pinned hash. If it stops, run it again to continue; files already
   verified are skipped.
3. Start `Transcribe.bat` in the folder (right-click → Send to → Desktop for a shortcut).

Pick audio files, choose the language, press Start. Each `.txt` is saved beside its audio file.

Known limit: proxies that require NTLM authentication may block the download.

**Upgrade:** extract the new zip to a new folder, optionally copy the old `models\` folder in, run
`install.bat`. **Uninstall:** delete the folder.

## Development

- `uv sync` · `uv run python -m transcribe_offline` (runs on Linux too; needs `models/`)
- Models: `uv run python -m transcribe_offline.setup`
- Tests: `uv run pytest` (offline unit tests) · `uv run pytest -m slow` (real-model smoke test, needs `models/`)
- Lint/types: `uv run ruff check . && uv run ruff format --check . && uv run pyright`
