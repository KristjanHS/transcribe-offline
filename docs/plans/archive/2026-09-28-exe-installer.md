# v0.2.0: reputation-known native pins + small exe installer + local shortcut

Status: ✅ SHIPPED 2026-09-28 (code on main; `make release BUMP=minor` + the org-PC checklist below are owed by the user).

Why: on a managed Win11 PC, App Control blocked `av/_core.pyd` (av 18.1.0, cf. PyAV#2418) and the MOTW-tagged `.bat` files.
Background + checks: `smart-app-control.md` (same folder). Model: stt-faster (same PC, works).

## Rulings (user, 2026-09-28) — do not re-litigate

- Unsigned only: no certificate, no Store, no IT allow rules. One release: v0.2.0.
- Native pins = stt-faster v1.2.7 set: av 16.0.1, ctranslate2 4.6.2, numpy 2.3.5, tokenizers 0.22.1 (pyyaml 6.0.3 already equal).
- Installer = `Transcribe-Setup.exe`, C# on the in-box .NET Framework 4.8, fixed logic; pins read from `pins.txt` so the exe hash survives releases.
- `install.bat` stays as the documented fallback (Unblock zip → run it); it reads the same `pins.txt`.
- Both create `Transcribe.lnk` in the install root (never Desktop: invariant 3); `Transcribe.bat` is deleted.

## Stage 1 — pins

- `app/pyproject.toml` `[tool.uv] constraint-dependencies` = the four pins (comment: Windows App Control reputation, see this plan); `uv lock`.
- Falsifier: `uv lock --check`, `uv run pytest`, pip-audit as ci.yml runs it (clean on 2026-09-28).

## Stage 2 — `pins.txt` + install.bat

- Root `pins.txt`, `KEY=value` lines: `UV_VERSION`, `UV_SHA256` (zip), `UV_EXE_SHA256`, `PYTHON_VERSION` — values moved from install.bat.
- install.bat sets only those four keys from the file (never arbitrary `set %%A`); missing key → `:fail`.
- install.bat's last step writes `..\Transcribe.lnk` via `%SYS%\WindowsPowerShell\v1.0\powershell.exe -NoProfile -NonInteractive` + `WScript.Shell`.
- Shortcut: target `app\.venv\Scripts\pythonw.exe`, args `-m transcribe_offline`, WorkingDirectory `app\` (cwd makes the package importable).

## Stage 3 — `installer/Setup.cs` (≤ ~200 lines, C# 5: in-box `csc.exe` only)

- Same steps and env as install.bat: same UV_* vars set/cleared, TMP/TEMP in `app\.uv\tmp`, uv re-hash on every run, resume on re-run.
- Download via `%SystemRoot%\System32\curl.exe`, extract via `tar.exe` (same proxy/cert behaviour as the .bat); SHA-256 in-process.
- Console app; refuse with a clear message when `pins.txt` or `app\` is not beside the exe (e.g. run from inside the zip).
- Shortcut via `WScript.Shell` COM (`Type.GetTypeFromProgID` + `InvokeMember`), identical to Stage 2's; wait for Enter unless `CI` is set.
- Build: `C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe /target:exe /optimize /out:Transcribe-Setup.exe installer\Setup.cs`.

## Stage 4 — CI / release

- Windows job: rebuild the exe only if `installer/` changed since the newest release carrying it, else reuse that exe (port stt-faster `scripts/installer_reuse.sh`).
- install-and-smoke runs `Transcribe-Setup.exe` end to end, then `install.bat` (resume path), then the existing smoke + outside-folder checks; assert `Transcribe.lnk` exists.
- publish adds the exe into the zip under the `transcribe-offline-vX.Y.Z/` prefix, so it is covered by SHA256SUMS + attestation.
- Rebuilt exe → step-summary reminder to submit it at https://www.microsoft.com/en-us/wdsi/filesubmission (copy stt-faster's wording).
- `.gitattributes`: `installer/` export-ignore (source is not shipped; the exe is); update its zip-contents comment.

## Stage 5 — docs

- README Install: extract → double-click `Transcribe-Setup.exe` → start `Transcribe.lnk`; blocked exe → Unblock zip, run `install.bat`; moved folder → re-run setup.
- SECURITY.md: what the exe does (= install.bat), source path, how the shipped exe is proven (attestation, reuse rule).
- CLAUDE.md invariants 1–2: install-time network also in `installer/Setup.cs` + install.bat; uv pinned in `pins.txt`.
- `git mv` this plan to `docs/plans/archive/` at ship; the user runs `make release BUMP=minor`.

## Owed[USER] after release — org PC checklist (highest impact first)

1. Full transcription of an .m4a completes (av 16.0.1 loads; a later native module may still block).
2. `Transcribe-Setup.exe` from Downloads: runs, or blocked (then: Unblock zip → `install.bat` works).
3. `Transcribe.lnk` in the folder opens the GUI with no console window.
4. CodeIntegrity 3077 events: none new after the run.
