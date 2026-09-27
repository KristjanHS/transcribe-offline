# Security architecture critique — TODO (needs fixing)

Status: **open** · Date: 2026-09-27 · Scope: everything shipped in the release zip (`install.bat`,
`Transcribe.bat`, `app/`) plus the CI/release pipeline that produces it.
Method: `security-best-practices` + `security-reviewer` skills, automated scans, and a manual read of
all ~490 lines of app code, both `.bat` files, both workflows, `SECURITY.md`, `README.md`.

## Executive summary

The design is unusually good for its size. Everything is hash-pinned, runtime imports have a
static ban, actions are SHA-pinned, and the release is attested. The weak spots are at the edges
the static checks cannot see:

1. **Native code the Python-level guards cannot see.** FFmpeg (PyAV 18.1.0 bundles FFmpeg 8.1.2)
   is built with network protocols (`tcp`, `udp`, `http`, `https`) and network demuxers (`sdp`,
   `rtp`, `rtsp`, `hls`, `dash`, `tee`). It picks the format by probing each file's content and runs
   on every file the user picks. The only proof it stays offline is one HLS test. `pytest-socket`
   in the release smoke test blocks Python sockets only, not native ones.
2. **The Tcl interpreter behind tkinter** can run `exec` and `socket`. Neither the TID251 ban nor
   `test_imports.py` covers it.
3. **The runtime invariants are never tested at runtime.** CI checks "nothing written outside the
   folder" only after `install.bat`, before the app ever runs. The smoke test runs in a dev
   environment, not the shipped one.
4. **The end-user trust chain starts from an unverified download.** README never tells users to
   check `SHA256SUMS` or the provenance attestation. Tags and releases are neither signed nor
   immutable.
5. **Transcripts can leave the machine** through OneDrive sync and Windows Error Reporting. This
   contradicts README's "Nothing is uploaded" and is not documented.

Every fix below has to be weighed against Invariant 4, *Minimal by default*. Each item has a
**Cost** line, meaning the extra lines a reviewer would have to read. Where a doc sentence is enough,
that is the recommended fix.

### Severity count

| Severity | Count |
|----------|-------|
| High     | 2 |
| Medium   | 9 |
| Low      | 13 |
| Info     | 4 |

### Automated scan results (2026-09-27)

| Tool | Result |
|------|--------|
| `bandit -r app/transcribe_offline` | clean |
| `semgrep p/python p/github-actions p/secrets` | clean (`--config=auto` refuses to run with metrics off) |
| `trivy fs app` (vuln/secret/misconfig) | `uv.lock`: 0 vulnerabilities |
| `gitleaks detect` | 2 hits: `generic-api-key` in `models.py` (commit `ee01edf`). **False positives:** these are the SHA-256 pins. See S10.4. |

---

## Angle 1 — Threat model & assurance claims

- [ ] **S1.1 (Medium) No written threat model; the claims outrun what is enforced.**
  `SECURITY.md:13-17` states absolutes ("no network access at runtime", "no child processes at
  runtime", "no writes outside its folder"). Only some of them are enforced, and only statically.
  Nothing names the assets (audio, transcripts), the actors (a malicious audio file, whoever
  controls the release, local malware, the cloud-sync client) or the trust boundaries (the user's
  file → FFmpeg; the internet → the installer; GitHub → the zip).
  **Fix:** add a short `## Threat model` table to `SECURITY.md`: threat → control → how it is
  verified (static / CI / manual / *not verified*). Rows that come out *not verified* feed the
  items below.
  **Cost:** ~15 doc lines.
- [ ] **S1.2 (Low) Soften or qualify the absolutes until they are tested.** Say "our code never …"
  for what the ban covers. For native deps (FFmpeg, CTranslate2, tokenizers), Tcl and Windows
  itself (WER, the file-dialog MRU), point to S1.1's table.
  **Cost:** wording only.

## Angle 2 — Untrusted input: media parsing (FFmpeg / PyAV)

The attacker's easiest route in is a crafted audio file that the user is persuaded to transcribe
(an email attachment, a shared folder).

- [ ] **S2.1 (High) FFmpeg runs with every format and codec, and picks the format from the file's
  content.** `engine.is_audio` (`engine.py:30-31`) checks only the extension, so it is not a
  security boundary. faster-whisper calls `av.open(input_file, mode="r", metadata_errors="ignore")`
  (`faster_whisper/audio.py:46`) with no `format`, `format_whitelist` or `codec_whitelist`. A
  `.mp3` can therefore be decoded by any of the 417 demuxers and hundreds of decoders compiled
  into PyAV's FFmpeg 8.1.2. That native attack surface has a steady CVE rate, and it runs with the
  user's full rights.
  **Fix:** decode in `engine.py` and pass the waveform to `model.transcribe(ndarray)`. Open with
  `av.open(path, options={"protocol_whitelist": "file", "format_whitelist": "<the ~9 demuxers for
  AUDIO_EXTENSIONS>"})` and a matching codec whitelist. This also closes S3.1.
  **Cost:** ~20 lines, plus `av` added to the `test_imports.py` allow-list.
  **Falsifier:** a test that feeds a `.wav`-named file with SDP, ffconcat or DASH content and
  asserts it is rejected. Show that it fails first without the whitelist.
- [ ] **S2.2 (Low) Resource exhaustion.** faster-whisper decodes the whole file into float32
  memory: about 230 MB per hour of audio. A crafted file or a very long recording can exhaust RAM
  or run for hours, and there is no limit on duration or size. The impact is only a local
  self-DoS.
  **Fix:** refuse above a documented duration, for example 12 h (from `info.duration` or the
  container), or document the limit.
  **Cost:** ~3 lines, or 1 doc line.
- [ ] **S2.3 (Info) No dedicated way to track FFmpeg CVEs.** See S10.1.

## Angle 3 — Runtime network isolation (Invariant 1)

- [ ] **S3.1 (High, unverified) FFmpeg can reach the network and runtime egress is not
  constrained.** A probe on 2026-09-27 showed the bundled FFmpeg attempts `udp://` opens (the
  sandbox returned `PermissionError`, not "protocol not found"). `tcp/http/https` are also present,
  as are the `sdp`/`rtp`/`rtsp`/`hls`/`dash` demuxers. `av.open` on a local path leaves
  `protocol_whitelist` unset. Nested opens are held back only by per-demuxer defaults, and
  `SECURITY.md:39-40` records a test of the HLS default only. Content probing can still select SDP
  and DASH. Whether any of them can open a network URL from a local file is **not established.**
  **Fix:** S2.1's `protocol_whitelist=file` closes it whatever the demuxer defaults are.
  **Falsifier (do before claiming either way):** on a machine with network, open a crafted `.wav`
  holding an SDP body that points at `rtp://127.0.0.1:<port>`. Also try a DASH MPD pointing at
  `http://127.0.0.1:<port>`. Listen on the port. A connection means High is confirmed.
- [ ] **S3.2 (Medium) The release smoke test's "network blocked" is Python-only.**
  `release.yml:39` says "network blocked by pytest-socket". pytest-socket patches
  `socket.socket` and cannot see FFmpeg's, CTranslate2's or Tcl's native sockets.
  **Fix:** run the smoke step with the runner firewalled. On `windows-latest`,
  `New-NetFirewallRule -Direction Outbound -Action Block` for the Python executable, or block all
  outbound after the install step. Or rename the step so it does not over-claim.
  **Cost:** ~3 YAML lines.
- [ ] **S3.3 (Low) The offline env vars are set late and are process-global.** `engine.py:44-45`
  sets `HF_HUB_OFFLINE` just before import. That works, but a future import of
  `faster_whisper`/`huggingface_hub` elsewhere (a new module, a test helper) would come before it.
  **Fix:** set both vars at the top of `__main__.py`, before any other import, and assert
  `huggingface_hub.constants.HF_HUB_OFFLINE` after load in the slow test.
  **Cost:** 2 lines.

## Angle 4 — Process capability confinement & least privilege

- [ ] **S4.1 (Medium) tkinter's Tcl interpreter is a way around the import ban.** `import tkinter`
  is allow-listed (`test_imports.py:21`). The Tcl interpreter behind it has `exec` (spawn
  processes), `socket` (network) and `open "|cmd"`. `root.tk.call("exec", …)` or
  `root.call("socket", …)` passes both TID251 and the AST test. `DYNAMIC` (`test_imports.py:28`)
  catches `.eval` but not `.call`. Today this is a code-review blind spot rather than something
  exploitable, but it undermines the claim "the import ban proves no child processes/network".
  **Fix:** (a) right after `tk.Tk()`, hide the dangerous commands:
  `for c in ("exec", "socket", "open", "load"): root.tk.call("interp", "hide", "", c)`. Check first
  that `open` is not used internally by ttk or filedialog; `exec` and `socket` are safe to hide.
  And/or (b) have the AST test reject `.call(` whose first string argument is in that set. And/or
  (c) add it to "Honest scope" in `SECURITY.md`.
  **Cost:** 2 lines (a), ~4 lines (b), or 1 doc line (c).
- [ ] **S4.2 (Medium) Nothing is enforced at runtime.** Every "never" is a static property of our
  source. `sys.addaudithook` (PEP 578, cannot be removed once installed) can raise on
  `socket.connect`, `socket.getaddrinfo`, `subprocess.Popen`, `os.system`, `os.startfile`,
  `os.exec`, `os.spawn`, `ctypes.dlopen`, and on `open` in write mode outside the install folder or
  the chosen audio folders. That would turn the Python half of Invariants 1 and 3 into a runtime
  guarantee. It still would not cover native code; see S2.1 and S3.1.
  **Fix:** a ~15-line hook installed first thing in `__main__.py`, plus a unit test showing that it
  raises. Add `sys` to the allow-list.
  **Cost:** ~15 lines, and it is the highest-maturity option.
- [ ] **S4.3 (Low) No OS-level confinement.** The app runs at medium integrity with the user's full
  file-system and network rights. A memory-corruption bug in FFmpeg (S2.1) gets everything the
  user has. AppContainer or a low-integrity child process would need admin rights or process
  spawning, which conflicts with the "no child processes" invariant.
  **Fix:** record it as an accepted risk in the threat model (S1.1). S2.1's whitelists are the
  practical mitigation.

## Angle 5 — File-system integrity (output writes, Invariant 3)

- [ ] **S5.1 (Medium) The transcript write can overwrite files; check-then-act race.**
  `unique_destination` (`engine.py:66-72`) checks `exists()`, then writing starts minutes later.
  `open(partial, "w")` (`engine.py:91`) truncates any existing `<name>.txt.partial` and follows a
  symlink or junction planted at that name. `partial.replace(dest)` (`engine.py:98`) silently
  overwrites a `dest` that appeared during the run: a second app instance, a sync client, or a
  hostile writer on a shared or SMB folder.
  **Fix:** `open(partial, "x", …)` (O_EXCL: refuses existing files and symlinks) and
  `partial.rename(dest)` (Windows rename does not overwrite). On `FileExistsError`, pick the next
  `unique_destination`. Guard the `except` cleanup so it deletes only a `.partial` **we** created.
  **Cost:** ~6 lines.
  **Falsifier:** tests that pre-create `dest` after `unique_destination` returns, and pre-create the
  `.partial`, then assert neither is clobbered. Run them against the current code first to show
  they fail.
- [ ] **S5.2 (Low) Paths depend on the working directory.** `MODELS_ROOT = Path("models")`
  (`models.py:6`) and `LOG_FILE = Path("logs")/…` (`app.py:19`) resolve against the CWD, which
  only `Transcribe.bat:3` sets. Started any other way (a shortcut with a different "Start in",
  `python -m` from elsewhere), the app loads `models/` from and writes `logs/` into an arbitrary
  directory. That is model planting from an attacker-chosen CWD, and a log written outside the
  folder.
  **Fix:** anchor both to `Path(__file__).resolve().parents[1]`.
  **Cost:** 2 lines.
- [ ] **S5.3 (Low) A hard kill leaves `.partial` files.** `except BaseException` does not run on
  power loss, task-kill or a native crash in FFmpeg or CTranslate2. A partial transcript stays
  beside the audio.
  **Fix:** document it in `SECURITY.md` "What it does". Optionally sweep for stale
  `<name>.txt.partial` for the chosen files at start (only files matching our naming).
  **Cost:** 1 doc line.

## Angle 6 — Data confidentiality & privacy

- [ ] **S6.1 (Medium) Transcripts can be uploaded by the OS, which contradicts README's "Nothing is
  uploaded".** `README.md:8` claims nothing is uploaded, and `README.md:16` warns against OneDrive
  only for the install folder. The transcript lands **beside the audio**
  (`engine.py:67`). If the audio is on Desktop or Documents, which OneDrive usually syncs, or on a
  network share, the plaintext transcript is uploaded or shared at once, often with wider access
  than the user expects.
  **Fix:** one README and SECURITY.md sentence: "the `.txt` goes where the audio is, including
  cloud-synced folders". Optionally make "Save to…" the first-run default. That would be a feature,
  so it needs a decision under Invariant 4.
- [ ] **S6.2 (Medium) Windows Error Reporting may upload crash dumps holding audio and transcript
  data.** A native crash in FFmpeg, CTranslate2 or Tcl in `pythonw.exe` can produce a WER report,
  and depending on policy it may include heap memory sent to Microsoft. This is runtime egress
  outside the app's control and is not mentioned in `SECURITY.md`. Excluding the app per user
  needs an HKCU registry write, which Invariant 3 forbids.
  **Fix:** document it in "What it never does" and in the threat model, with the admin-side
  control: the `DontSendAdditionalData` / `Disabled` WER policy via GPO.
- [ ] **S6.3 (Low) The log records sensitive file names and full paths.**
  `log.exception("Transcription failed: %s", audio)` (`app.py:64`) writes the full path, which
  often names a person or patient. `app.log` persists until the next launch. Exception text can
  also include paths from FFmpeg.
  **Fix:** log `audio.name` or an index instead of the full path, or state in `SECURITY.md` that the
  log holds file paths.
  **Cost:** 1 line.
- [ ] **S6.4 (Info) Recent-folder MRU.** `show_folder` (`app.py:199-206`) and `choose` add entries
  to the Windows common-dialog MRU in HKCU. This is already disclosed (`SECURITY.md:16`); keep the
  disclosure.
- [ ] **S6.5 (Info) Transcripts inherit the folder's ACL.** This is by design. Mention it together
  with S6.1.

## Angle 7 — Install-time supply chain & integrity at rest

- [ ] **S7.1 (Medium) Once installed, nothing is verified again.** `install.bat:25` skips download
  and verification when `.uv\uv.exe` exists. Only the zip was ever hashed, never the extracted
  exe. At runtime, `load_model` (`engine.py:38-48`) checks that the model files **exist**, not
  their SHA-256. The whole install tree (uv.exe, `.venv`, `models/`) is user-writable by design.
  User-level malware, or a corrupted disk, can therefore swap in a model (parsed by native
  CTranslate2 and tokenizers code) or a binary, and neither re-running `install.bat` nor launching
  the app notices. Local malware already owns the user, so the realistic gain is catching
  corruption and giving a clear re-verify path.
  **Fix:** (a) have `install.bat` re-hash `uv.exe` against a pinned exe hash as well as the zip
  hash. (b) `setup.py` already re-hashes the models on every run; document "re-run `install.bat`
  to re-verify everything". (c) Optionally add a "Verify installation" command that also runs
  `uv sync --frozen --check` or re-hashes `.venv` against RECORD files.
  **Cost:** 2 bat lines plus a doc line.
- [ ] **S7.2 (Low) `install.bat` finds its tools through the CWD and PATH.** `curl.exe`,
  `certutil`, `findstr` and `tar` (`install.bat:28-36`) are resolved by cmd.exe, which searches
  the **current directory** (`app\`) before PATH. The hash check depends on `certutil` and
  `findstr` telling the truth.
  **Fix:** call `%SystemRoot%\System32\curl.exe`, `…\certutil.exe`, `…\findstr.exe` and
  `…\tar.exe` explicitly.
  **Cost:** 4 edited lines.
- [ ] **S7.3 (Low) `UV_*` environment variables inherited from the user's environment can change
  the trust chain.** `UV_NO_CONFIG=1` (`install.bat:14`) disables config **files** only.
  Environment variables such as `UV_PYTHON_DOWNLOADS_JSON_URL` (which replaces the download
  metadata, hashes included), `UV_PYTHON_INSTALL_MIRROR`, `UV_INDEX_URL`, `UV_INSECURE_HOST` and
  `SSL_CERT_FILE` still apply. The pin chain in `SECURITY.md:56` ("uv zip hash → uv's Python
  hashes") holds only if `UV_PYTHON_DOWNLOADS_JSON_URL` is unset.
  **Fix:** `set "UV_PYTHON_DOWNLOADS_JSON_URL="` (and the others) near `install.bat:14`, or list
  the assumption in `SECURITY.md`.
  **Cost:** ~4 lines.
- [ ] **S7.4 (Low) CPython 3.12.14 and FFmpeg are frozen until the next release.** There is no
  update path except a new zip, and old installs never learn that they are stale.
  **Fix:** document the "security updates = new release" policy and a cadence (see S10.2).

## Angle 8 — Release & distribution integrity (end-user trust root)

- [ ] **S8.1 (Medium) Users are never told to verify the zip.** The trust chain in
  `SECURITY.md:56` starts at the uv hash inside `install.bat`, which comes **from the zip**.
  README install step 1 (`README.md:14-15`) is "download … extract". `SHA256SUMS` sits in the same
  release, so it only catches corruption, not tampering. The provenance attestation made in
  `release.yml:59-61` is never mentioned to users.
  **Fix:** add an optional verification step to README:
  `gh attestation verify transcribe-offline-vX.Y.Z.zip -R KristjanHS/transcribe-offline`, plus a
  PowerShell `Get-FileHash` line for people without `gh`.
  **Cost:** 3 doc lines.
- [ ] **S8.2 (Medium) Releases are mutable and tags are unsigned.** An attacker with the
  maintainer's GitHub session, or a leaked token with `contents:write`, can replace release
  assets or push a `v*` tag. `release.yml` triggers on any `v*` tag push (`release.yml:3-4`).
  `Makefile:16` makes lightweight, unsigned tags and pushes straight to `main`.
  **Fix (repo settings, zero code):** enable GitHub **immutable releases**. Add a tag ruleset that
  restricts `v*` creation and deletion to the maintainer. Add a branch ruleset on `main`
  (no force-push, no deletion). Require 2FA with a hardware key. Optionally `git tag -s` in the
  Makefile, and put the maintainer's signing key fingerprint in `SECURITY.md`.
- [ ] **S8.3 (Low) Unsigned `.bat` files and SmartScreen.** Explorer carries the Mark-of-the-Web
  onto the extracted `.bat` files, and the unsigned Python binaries in a user-writable folder are
  what AppLocker and WDAC default rules block. Enterprise security teams will ask.
  **Fix:** document the expected SmartScreen prompt. Publish the SHA-256 of each executable that
  runs (uv.exe, python/pythonw.exe) so admins can allow-list them. Authenticode signing is a later
  maturity step.

## Angle 9 — CI/CD pipeline security

Already good: SHA-pinned actions, `persist-credentials: false`, `contents: read` by default, the
write permissions granted only to the `publish` job, `--verify-tag`, and the release-time model
cache re-verified by `setup.py`'s hashes, so cache poisoning cannot land an unverified model.

- [ ] **S9.1 (Medium) The runtime invariants are not tested in CI.** The outside-folder check
  (`release.yml:22-33`) runs **after `install.bat`, before the app runs**. What the app does at
  runtime, such as Tcl, huggingface_hub or ctranslate2 creating `~\.cache\…` or writing
  `%APPDATA%`, is never checked. The smoke test (`release.yml:34-41`) also runs in a
  `setup-uv` + `uv sync --frozen` **dev** environment (dev deps, a different uv cache in the
  profile), not the `.venv` that `install.bat` built and that ships.
  **Fix:** run the slow smoke test with `app\.venv\Scripts\python.exe -m pytest …` from the
  installed tree (pytest has to be present; either install `--group dev` into a copy, or run a tiny
  non-pytest smoke script). Then repeat the outside-folder check **after** it, with the network
  blocked (S3.2).
  **Cost:** ~10 YAML lines.
- [ ] **S9.2 (Low) There is no workflow linter.**
  **Fix:** add `zizmor` (GitHub Actions security linter) to `ci.yml`, as a pinned dev dependency
  or `uvx zizmor==<pin> .github`.
  **Cost:** 1 line.
- [ ] **S9.3 (Low) The `publish` job has no environment protection.** A tag push publishes with no
  human gate.
  **Fix:** a `release` environment with a required reviewer (the maintainer) and deployment
  restricted to `v*` tags. This complements S8.2.
  **Cost:** 1 YAML line plus repo settings.

## Angle 10 — Vulnerability & dependency lifecycle

- [ ] **S10.1 (Medium) `pip-audit` cannot see the native components that carry the risk.**
  `ci.yml:32-36` audits PyPI advisories. Bundled FFmpeg 8.1.2 (in `av`), CTranslate2's C++,
  tokenizers' Rust, python-build-standalone CPython 3.12.14 and `uv.exe` are tracked under their
  own CVE feeds, not as PyPI advisories. `trivy fs` also reported 0 against `uv.lock` alone.
  **Fix:** write down the list of native components and their upstream versions (below) and check
  it on each release. Optionally run `trivy`/`grype` on the installed `.venv` in `release.yml`.
- [ ] **S10.2 (Medium) Audits run only when code changes.** `pip-audit` runs on push and PR only.
  A CVE published against a pinned version is not noticed until the next commit. There is no
  Dependabot or Renovate for `uv.lock`, the actions, or the uv and Python pins in `install.bat`.
  **Fix:** add `schedule: - cron: "0 6 * * 1"` to `ci.yml` (weekly), and Dependabot for
  `github-actions` plus `uv`. Record a patch-release SLA in `SECURITY.md`, for example "high-sev
  in a runtime dep → release within 14 days".
  **Cost:** ~10 lines.
- [ ] **S10.3 (Low) No SBOM is published.** Reviewers and enterprise intake want one.
  **Fix:** in `publish`, `uv export --frozen --no-dev --format cyclonedx1.5 > sbom.cdx.json` (or
  generate it with `cyclonedx-py` from `requirements.txt`), attach it to the release and attest it.
  **Cost:** ~3 YAML lines.
- [ ] **S10.4 (Info) gitleaks false positives.** The SHA-256 pins in `models.py:38-58` match
  `generic-api-key`, so a future secret-scan gate would fail on them.
  **Fix:** add a `.gitleaks.toml` allowlist for `models.py` hex-64 values when a gitleaks gate is
  added. Not before, per Invariant 4.
- [ ] **S10.5 (Low) The runtime installs more than it uses.** `huggingface-hub`, `filelock`,
  `pyyaml`, `tqdm`, `packaging` and `colorama` are in the runtime set but only needed for download
  paths faster-whisper never takes here. `exclude-dependencies` already strips the HTTP stack.
  **Fix:** check whether `huggingface-hub` can be excluded too, i.e. whether faster-whisper
  imports it lazily only for `download_model`. If `test_faster_whisper_imports_without_excluded_dependencies`
  still passes with it excluded, a whole network-capable package leaves the runtime.
  **Cost:** 1 line.

Runtime components to track (S10.1): CPython 3.12.14 (python-build-standalone) · uv 0.12.19 ·
faster-whisper 1.2.1 · ctranslate2 4.8.2 · av 18.1.0 / FFmpeg 8.1.2 · tokenizers 0.23.2 ·
numpy 2.5.3 · huggingface-hub 1.33.0 · Tcl/Tk (bundled with CPython).

---

## Suggested order

Pick again after each item lands; the order is not fixed.

1. **S3.1 falsifier → S2.1.** Decode with the protocol and format whitelists. This settles both
   High items and replaces an unverified doc claim with a test.
2. **S5.1.** O_EXCL plus a non-clobbering rename. Small, testable, and a real data-loss path.
3. **S8.1 + S8.2.** Mostly repo settings and README lines; they protect every future user.
4. **S4.1 (a) + S4.2.** Hide Tcl exec/socket and add the runtime audit hook. This is the
   highest-maturity move, turning the static claims into runtime ones.
5. **S9.1 + S3.2.** Test the shipped environment, firewalled, and check for outside writes after
   it runs.
6. **S6.1 + S6.2 + S1.1.** Doc-only honesty fixes: OneDrive, WER, and the threat-model table.
7. The Low and Info items, as capacity allows.
