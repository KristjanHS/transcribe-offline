# SignPath Foundation application

Free code signing for `Transcribe-Setup.exe`. Plan: [plans/2026-11-24-signpath-signing.md](plans/2026-11-24-signpath-signing.md).
Form: https://signpath.org/apply · Terms: https://signpath.org/terms

Submitted 2026-11-24 with the values below; waiting for SignPath's reply.

## Form fields

| Field | Value |
|---|---|
| Project Name | `Transcribe Offline` (matches `AssemblyProduct` in `installer/Setup.cs`) |
| Repository URL | `https://github.com/KristjanHS/transcribe-offline` |
| Homepage URL | `https://github.com/KristjanHS/transcribe-offline` |
| Download URL | `https://github.com/KristjanHS/transcribe-offline/releases/latest` |
| Privacy Policy URL | `https://github.com/KristjanHS/transcribe-offline#code-signing-policy` |
| Wikipedia URL | empty |
| Tagline | `Offline speech-to-text for Estonian and English on your own Windows or Linux PC.` |
| Category | Audio |
| Maintainer Type | Individual maintainer(s) |
| Build System | GitHub Actions |
| First / Last Name, Email | the maintainer's |
| Company Name | empty |
| Primary Discovery Channel | AI / LLM tools |

### Description

> Transcribe Offline is a minimal speech-to-text app: a Windows GUI and a Linux CLI that transcribe Estonian or English audio with faster-whisper, on CPU or an NVIDIA GPU. After installation it makes no network connections, and the codebase is kept small so a security reviewer can read all of it. We'd sign Transcribe-Setup.exe, a small C# installer built from installer/Setup.cs by our GitHub Actions release workflow. It downloads uv, Python, the locked Python wheels and the models, and checks each against a pinned SHA-256 hash.

### Reputation

> A young project (first release 2026-09-27) with 10 releases so far and a winget submission under review (https://github.com/microsoft/winget-pkgs/pull/444805). Users need no admin rights; every download is pinned and hash-checked; release zips carry GitHub build-provenance attestations; SECURITY.md lists exactly what the app does on the network and on disk. The winget review asked for signing, which is why we're applying.

### Checkboxes

- Required: Code of Conduct + certificates issued in SignPath Foundation's name; storing and processing personal data.
- Optional: other communications from SignPath.

## After approval

SignPath invites the maintainer (account with MFA, project, signing policy); then plan slices 2–5.
