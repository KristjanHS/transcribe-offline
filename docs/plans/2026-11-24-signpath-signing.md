# Sign Transcribe-Setup.exe via SignPath Foundation

Conditions: https://signpath.org/terms · Apply: https://signpath.org/apply · CI: https://docs.signpath.io/trusted-build-systems/github

## Slices

1. [USER] Turn on MFA on GitHub (and on SignPath once invited), then submit https://signpath.org/apply:
   repo https://github.com/KristjanHS/transcribe-offline, MIT, artifact `Transcribe-Setup.exe` (release.yml, `installer/Setup.cs`).
2. On approval: replace README §Code signing policy's "in progress" with "Free code signing provided by
   [SignPath.io](https://about.signpath.io), certificate by [SignPath Foundation](https://signpath.org)".
3. On approval: in `release.yml` add `SignPath/github-action-submit-signing-request` after the exe build (secret
   `SIGNPATH_API_TOKEN`; organization-id, project-slug, signing-policy-slug from SignPath); pin it by SHA.
4. Make `.github/scripts/setup-exe-reuse.sh` reuse the signed exe; signing = new hash, so ship it once with
   the next batched `installer/` change (`.claude/rules/installer-hash.md`).
5. Bump `.github/winget/` to the first signed release and reply on microsoft/winget-pkgs PR #444805.

## Watch

- Each release needs a manual approval in SignPath; SignPath metadata check: product name `Transcribe Offline`.
- Sign only our exe: uv, Python and the NVIDIA wheels are third-party downloads, never repackaged.
