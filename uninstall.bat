@echo off
setlocal
powershell -NoProfile -Command "$l = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Transcribe (offline).lnk'; if (Test-Path -LiteralPath $l) { Remove-Item -LiteralPath $l }"
echo Desktop shortcut removed. To finish, close this window and delete this folder:
echo   %~dp0
pause
