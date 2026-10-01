# transcribe-offline

[![Latest release](https://img.shields.io/github/v/release/KristjanHS/transcribe-offline?sort=semver&label=latest%20release)](https://github.com/KristjanHS/transcribe-offline/releases/latest)
[![Release date](https://img.shields.io/github/release-date/KristjanHS/transcribe-offline?label=released)](https://github.com/KristjanHS/transcribe-offline/releases/latest)

**[⬇ Download the latest release (Windows)](https://github.com/KristjanHS/transcribe-offline/releases/latest)** · [All releases](https://github.com/KristjanHS/transcribe-offline/releases)

Transcribe Estonian or English audio to text on your own computer. The app uploads nothing; after
installation it works with the network unplugged. See [SECURITY.md](SECURITY.md) for exactly what it does.
_(Developers: jump to [Development](#development).)_

## Install (Windows 10 1803+ / 11, no admin rights)

1. Open the [latest release](https://github.com/KristjanHS/transcribe-offline/releases/latest),
   download `transcribe-offline-vX.Y.Z.zip` under **Assets** and extract it to any folder.
   Don't use a OneDrive-synced folder (Desktop and Documents often are).
   Optional, before extracting: check that the zip is the one GitHub built with
   `gh attestation verify transcribe-offline-vX.Y.Z.zip -R KristjanHS/transcribe-offline`
   (without `gh`: compare PowerShell `Get-FileHash transcribe-offline-vX.Y.Z.zip` with `SHA256SUMS`).
2. Double-click `Transcribe-Setup.exe`. It downloads about 3.5 GB (uv, Python, libraries, two speech
   models), verifying every file against a pinned hash. If it stops, run it again to continue; it
   re-hashes uv and the models and downloads only what is missing or does not match.
   Windows may warn that it is unsigned (More info → Run anyway); that is expected.
   If Windows blocks it outright (Smart App Control or your organisation's App Control): delete the
   folder, right-click the zip → Properties → tick **Unblock** → OK, extract again and double-click
   `install.bat` instead. It does the same steps. Use `install.bat` too if your antivirus quarantines
   `Transcribe-Setup.exe`: it is a small unsigned exe that downloads and unpacks files, which heuristics
   can mistake for malware.
3. Start `Transcribe.bat` in the folder (make a shortcut to it on the Desktop if you like). After moving
   the folder, run the setup again.

With [Scoop](https://scoop.sh) instead (no SmartScreen prompt, since Scoop downloads without the browser's
Mark of the Web): `scoop install https://raw.githubusercontent.com/KristjanHS/transcribe-offline/main/scoop/transcribe-offline.json`
runs the same setup and adds a Start-menu shortcut; `scoop update transcribe-offline` keeps the downloaded models.

Pick audio files, choose the language, press Start. Each `.txt` is saved beside its audio file, so in a
OneDrive-synced or shared folder it is synced or shared too.

Known limit: proxies that require NTLM authentication may block the download.

**Upgrade:** the app never updates itself; security fixes come as a new release. Extract the
new zip to a new folder, optionally copy the old `app\models\` folder into the new `app\`, run
`Transcribe-Setup.exe`. **Uninstall:** delete the folder.

## License

MIT License - see [LICENSE](LICENSE).

---

## Development

_Everything below is for building or testing from source — not needed to [install the app](#install-windows-10-1803--11-no-admin-rights)._

Run these in `app/` (the Python project; the release zip ships only it, `Transcribe-Setup.exe` built from
`installer/Setup.cs`, `install.bat`, `pins.txt` and `LICENSE`).

- `uv sync` · `uv run python -m transcribe_offline` (runs on Linux too; needs `models/`)
- Models: `uv run python -m transcribe_offline.setup`
- Tests: `uv run pytest` (offline unit tests) · `uv run pytest -m slow` (real-model smoke test, needs `models/`)
- Lint/types: `uv run ruff check . && uv run ruff format --check . && uv run pyright`
