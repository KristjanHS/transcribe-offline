@echo off
setlocal
cd /d "%~dp0app"
rem Installs into the app folder: pinned uv -> locked Python deps -> pinned, SHA-256-verified models.
rem Nothing is written outside this folder. No admin rights needed.

set "UV_VERSION=0.12.19"
set "UV_SHA256=6dbb02d79e419522f1c500f0adb1cddcff0cda7d59b0d66ea7f5e3b4a1b2f5f0"
set "PYTHON_VERSION=3.12.14"

set "UV_CACHE_DIR=%CD%\.uv\cache"
set "UV_PYTHON_INSTALL_DIR=%CD%\.uv\python"
set "UV_PROJECT_ENVIRONMENT=%CD%\.venv"
set "UV_NO_CONFIG=1"
set "UV_PYTHON_PREFERENCE=only-managed"
set "UV_SYSTEM_CERTS=1"
rem uv takes a lock file in %TEMP%; keep that (and any other temp file) in this folder.
set "TMP=%CD%\.uv\tmp"
set "TEMP=%CD%\.uv\tmp"
if not exist ".uv\tmp" mkdir ".uv\tmp"
rem No python.exe in %USERPROFILE%\.local\bin, no HKCU registry entry.
set "UV_PYTHON_INSTALL_BIN=0"
set "UV_PYTHON_INSTALL_REGISTRY=0"

if not exist ".uv\uv.exe" (
    if not exist ".uv" mkdir ".uv"
    echo Downloading uv %UV_VERSION% ...
    curl.exe -fL -o ".uv\uv.zip" "https://github.com/astral-sh/uv/releases/download/%UV_VERSION%/uv-x86_64-pc-windows-msvc.zip" || goto :fail
    certutil -hashfile ".uv\uv.zip" SHA256 | findstr /i /x "%UV_SHA256%" >nul || (
        echo The uv download does not match the pinned SHA-256.
        echo Expected: %UV_SHA256%
        certutil -hashfile ".uv\uv.zip" SHA256
        del ".uv\uv.zip"
        goto :fail
    )
    tar -xf ".uv\uv.zip" -C ".uv" || goto :fail
    del ".uv\uv.zip"
)

echo Installing Python %PYTHON_VERSION% and the locked dependencies ...
".uv\uv.exe" sync --frozen --no-dev --python %PYTHON_VERSION% || goto :fail

echo Downloading and verifying the models (about 3 GB) ...
".venv\Scripts\python.exe" -m transcribe_offline.setup || goto :fail

echo.
echo Done. Start the app with Transcribe.bat.
if not defined CI pause
exit /b 0

:fail
echo.
echo Installation failed - see the message above. Running install.bat again resumes.
if not defined CI pause
exit /b 1
