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
   models), plus 1.3 GB of CUDA libraries on a PC with an NVIDIA GPU (GTX 16 / RTX series or newer, 4 GB+ memory, driver 528.33+),
   which then transcribes on the GPU, falling back to the CPU if the GPU fails. To stop using the GPU,
   delete `app\.venv\Lib\site-packages\nvidia` (setup puts it back when run again).
   Setup verifies every file against a pinned hash. If it stops, run it again to continue; it
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

## Install (Linux CLI)

No zip, no admin rights: you need `git` and [uv](https://docs.astral.sh/uv/) (x86-64 Linux).

```sh
git clone https://github.com/KristjanHS/transcribe-offline.git
cd transcribe-offline/app
uv sync --frozen --no-dev                     # locked, hash-checked libraries
.venv/bin/python -m transcribe_offline.setup  # pinned, SHA-256-verified models, about 3 GB
cd .. && ./transcribe -l et talk.mp3          # -l en for English; several files at once are fine
```

Each transcript is saved beside its audio as `.txt` and its path is printed; progress goes to stderr.
`--no-timestamps` gives plain text. Exit code 0 when every file was transcribed, 1 if any failed, 130 on
Ctrl+C (the unfinished transcript is removed). The same guard as on Windows blocks network, child
processes and writes outside the folder at runtime; `./transcribe` runs the app's own Python, never uv.

On an NVIDIA GPU (GTX 16 / RTX series or newer, 4 GB+ memory, driver 528.33+; WSL 2 works too) setup
also installs 1.3 GB of CUDA libraries and `./transcribe` uses the GPU, falling back to the CPU if it fails.
To stop using it, run `uv sync --frozen --no-dev` in `app/` (removes them; setup installs them again).

Unlike the Windows setup, uv keeps its download cache and the Python it installs in your home folder
(`~/.cache/uv`, `~/.local/share/uv`). **Upgrade:** `git pull`, then the `uv sync` and setup lines again
(setup keeps verified models). **Uninstall:** delete the folder (`uv cache clean` empties uv's cache).

### Without the setup script

`transcribe_offline.setup` is the only Python that touches the network or starts processes. To skip it,
replace the `uv sync` and setup lines above with these steps, which you can read as you run them:

1. GPU check (optional): `nvidia-smi --query-gpu=name,memory.total,driver_version,compute_cap --format=csv`.
   Use the GPU only if it shows 4000 MiB+ of memory, driver 528.33+ and compute capability 7.0+.
2. Libraries, in `app/`: `uv sync --frozen --no-dev`. On a capable GPU, add `--group gpu` (+1.3 GB).
3. Models: run this in `app/`. The first command only prints the URLs and SHA-256 hashes pinned in
   `transcribe_offline/models.py` (plain data, about 50 lines; read it first). `curl` downloads each file and
   `sha256sum -c` checks it; a file that fails the check is deleted, so run the loop again.

   ```sh
   .venv/bin/python -c 'from transcribe_offline.models import MODELS
   for lang, pin in MODELS.items():
       for name, sha in pin.files.items(): print(pin.url(name), f"models/{lang}/{name}", sha)' |
   while read -r url file sha; do
       curl -fL --create-dirs -o "$file" "$url"
       echo "$sha  $file" | sha256sum -c - || rm -f "$file"
   done
   ```

   Without running any Python, copy each URL and hash from `models.py` yourself: the file URL is
   `https://huggingface.co/<repo>/resolve/<commit>/<subfolder>/<name>` and it goes in `app/models/<et|en>/<name>`.
   You need all five files for each language; the app refuses to start a language with any missing.

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
