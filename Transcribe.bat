@echo off
rem The working directory is what makes the (never installed) transcribe_offline package importable.
cd /d "%~dp0app"
start "" ".venv\Scripts\pythonw.exe" -m transcribe_offline
