@echo off
setlocal
cd /d "%~dp0app"
rem Installs into the app folder: pinned uv -> locked Python deps -> pinned, SHA-256-verified models.
rem Nothing is written outside this folder. No admin rights needed.

set "UV_VERSION=0.12.19"
set "UV_SHA256=6dbb02d79e419522f1c500f0adb1cddcff0cda7d59b0d66ea7f5e3b4a1b2f5f0"
set "UV_EXE_SHA256=f94eddb81f3addca6ef8f2361a70c3edde31adcbd1000a55fc6674306ae0b1e7"
set "SYS=%SystemRoot%\System32"
set "PYTHON_VERSION=3.12.14"

set "UV_CACHE_DIR=%CD%\.uv\cache"
set "UV_PYTHON_INSTALL_DIR=%CD%\.uv\python"
set "UV_PROJECT_ENVIRONMENT=%CD%\.venv"
set "UV_NO_CONFIG=1"
set "UV_PYTHON_PREFERENCE=only-managed"
set "UV_SYSTEM_CERTS=1"
rem Inherited settings that could redirect a download or its hashes are cleared.
for %%V in (UV_PYTHON_DOWNLOADS_JSON_URL UV_PYTHON_INSTALL_MIRROR UV_CONFIG_FILE UV_PROJECT UV_WORKING_DIR UV_INDEX UV_INDEX_URL UV_DEFAULT_INDEX UV_EXTRA_INDEX_URL UV_FIND_LINKS UV_INSECURE_HOST SSL_CERT_FILE SSL_CERT_DIR) do set "%%V="
rem uv takes a lock file in %TEMP%; keep that (and any other temp file) in this folder.
set "TMP=%CD%\.uv\tmp"
set "TEMP=%CD%\.uv\tmp"
if not exist ".uv\tmp" mkdir ".uv\tmp"
rem No python.exe in %USERPROFILE%\.local\bin, no HKCU registry entry.
set "UV_PYTHON_INSTALL_BIN=0"
set "UV_PYTHON_INSTALL_REGISTRY=0"

rem uv.exe is re-hashed on every run; a changed one is downloaded again.
if exist ".uv\uv.exe" call :uv_ok || del ".uv\uv.exe"
if not exist ".uv\uv.exe" (
    if not exist ".uv" mkdir ".uv"
    echo Downloading uv %UV_VERSION% ...
    "%SYS%\curl.exe" -fL -o ".uv\uv.zip" "https://github.com/astral-sh/uv/releases/download/%UV_VERSION%/uv-x86_64-pc-windows-msvc.zip" || goto :fail
    "%SYS%\certutil.exe" -hashfile ".uv\uv.zip" SHA256 | "%SYS%\findstr.exe" /i /x "%UV_SHA256%" >nul || (
        echo The uv download does not match the pinned SHA-256.
        echo Expected: %UV_SHA256%
        "%SYS%\certutil.exe" -hashfile ".uv\uv.zip" SHA256
        del ".uv\uv.zip"
        goto :fail
    )
    "%SYS%\tar.exe" -xf ".uv\uv.zip" -C ".uv" || goto :fail
    del ".uv\uv.zip"
    call :uv_ok || (
        echo The extracted uv.exe does not match the pinned SHA-256.
        goto :fail
    )
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

:uv_ok
"%SYS%\certutil.exe" -hashfile ".uv\uv.exe" SHA256 | "%SYS%\findstr.exe" /i /x "%UV_EXE_SHA256%" >nul
exit /b
