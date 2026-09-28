# App Control blocks install and transcription on a managed Windows 11 PC

Status: open. The checks below must run on the org PC before any code change.

## Observed (org PC, release v0.1.1)

- `install.bat` / `Transcribe.bat` blocked (Mark of the Web); Unblock fixed both.
- Start fails: `DLL load failed while importing _core: An Application Control policy has blocked this file`.
- Same PC runs stt-faster (unsigned PyInstaller setup exe → uv → uv Python + venv, launched via a local `.lnk`).
- stt-faster v1.2.7 pins av 16.0.1 / numpy 2.3.5 / ctranslate2 4.6.2 / tokenizers 0.22.1; we pin av 18.1.0 / 2.5.3 / 4.8.2 / 0.23.2.
- PyAV 18.1.0 blocked by SAC upstream: https://github.com/PyAV-Org/PyAV/issues/2418

## Rulings (user, 2026-09-28)

- Unsigned only: no paid certificate, no waiting weeks for a cert or reputation build-up.
- Self-service: org IT will not add allow rules or deploy via Intune; no Store (MSIX).

## Checks to run on the org PC (decide the path)

0. Gate: Windows Security → App & browser control → Smart App Control state; policy name in the newest CodeIntegrity 3077 event.
   `Get-WinEvent -LogName 'Microsoft-Windows-CodeIntegrity/Operational' -MaxEvents 50 | ? Id -eq 3077 | fl TimeCreated, Message`
1. Installer trust: `fsutil file queryEA "<stt-faster install>\…\site-packages\av\_core*.pyd"` lists `$KERNEL.SMARTLOCKER.ORIGINCLAIM`?
2. Version reputation: in `app\`, `.uv\uv.exe pip install --python .venv\Scripts\python.exe av==16.0.1`, then Start a transcription (`install.bat` re-run restores the pins).

| Check 1 | Check 2 | Path |
|---|---|---|
| any | pass | **A**: pin reputable versions + launch via a locally created `.lnk` |
| pass | fail | **B**: reputable setup exe that runs uv (stt-faster pattern) |
| fail | fail | No unsigned path found; reopen this plan |

## Path A (if chosen)

- Pin av (and any other blocked wheel) to the stt-faster-proven versions; set `exclude-newer` to a date ≥60 days back on each bump.
- `install.bat` creates a Desktop `.lnk` to `pythonw.exe -m transcribe_offline`; drop `Transcribe.bat`; README: Unblock the zip before extracting.
- Falsifier: a full transcription on the org PC after a clean install (Python stops at the first blocked import, so later modules may still block).

## Path B (if chosen)

- The setup exe bakes in its install logic; never a generic "run the script beside me" launcher (that launders trust).
- Reuse the exe hash across releases (stt-faster `scripts/installer_reuse.sh`); a rebuild restarts reputation at zero.
