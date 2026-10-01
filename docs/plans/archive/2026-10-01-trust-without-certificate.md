# Trust without a code-signing certificate

Status: ✅ SHIPPED 2026-10-01 (Stages 1–3 on main; winget submission waits for v0.2.6)

Goal: fewer "Windows protected your PC" prompts for Transcribe-Setup.exe without buying a certificate.
SmartScreen reputation is per file hash and builds only from clean downloads (no consumer submission
route: https://learn.microsoft.com/windows/apps/package-and-deploy/smartscreen-reputation). Package
managers download without Mark of the Web, so their users never see the prompt.

## Stage 1 — freeze the exe hash, winget-ready installer (edits already in the working tree)

- `installer/Setup.cs`: resolve the exe's real folder through symlinks (winget starts portables via
  `%LOCALAPPDATA%\Microsoft\WinGet\Links`); print the install folder in the Done line.
- `.github/workflows/release.yml`: smoke test launches the exe through a symlink; rebuilt-exe reminder
  states the reputation facts instead of the (non-existent) submission route.
- `.claude/rules/installer-hash.md`: path-gated rule — edits under `installer/` reset reputation.
- `.github/winget/*.yaml`: zip + portable manifests for v0.2.6 (first exe with symlink support);
  SHA-256 placeholder filled from the v0.2.6 `SHA256SUMS` before the winget-pkgs PR.
- Verify: `uv --directory app run zizmor --offline <repo>/.github`; C# compiles only in CI (`ci.yml`).
- Commit.

## Stage 2 — Scoop manifest, installable by URL (no moderation)

- `scoop/transcribe-offline.json`: `url` = v0.2.5 release zip, `hash` from `SHA256SUMS`,
  `extract_dir` = the zip's version folder, `installer.script` runs `Transcribe-Setup.exe` with `CI=1`
  (skips the Enter prompt), `shortcuts` → `Transcribe.bat`, `persist` `app\models` across upgrades,
  `checkver` github + `autoupdate` with `hash.url` = the release's `SHA256SUMS`.
- README install section: `scoop install https://raw.githubusercontent.com/KristjanHS/transcribe-offline/main/scoop/transcribe-offline.json`
  as an alternative that skips the SmartScreen prompt.
- Verify: `python3 -m json.tool scoop/transcribe-offline.json`.
- Commit.

## Stage 3 — review

- `code-reviewer` subagent over the two commits: symlink path resolution (`\\?\` and UNC prefixes),
  release.yml symlink step runs as tuser, manifests' field names against winget schema 1.12.0 and
  Scoop's manifest schema.

## Deferred / user-owned

- After tagging v0.2.6: fill `InstallerSha256`, submit `.github/winget/` to microsoft/winget-pkgs
  (`wingetcreate submit`); then add `winget install KristjanHS.TranscribeOffline` to README.
- Options needing a decision, not code: Microsoft Store (only route Microsoft says removes the prompt;
  needs MSIX), Artifact Signing (~$10/month, individuals accepted; EV no longer bypasses SmartScreen),
  SignPath Foundation (free OSS signing). Smart App Control blocks unsigned files regardless; only these fix it.
