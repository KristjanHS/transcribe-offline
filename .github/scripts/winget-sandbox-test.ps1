# Install the winget package in a fresh Windows Sandbox and run transcribe-offline-setup in it, as winget-pkgs
# reviewers do. The script exits with the exit code of transcribe-offline-setup (0 = installed).
# Run it on the Windows host after enabling Windows Sandbox:
#   powershell -ExecutionPolicy Bypass -File <repo>\.github\scripts\winget-sandbox-test.ps1 [-Ref <commit>]
# Without -Ref it tests the manifests in .github\winget next to this script. With -Ref it fetches the manifests
# committed at that commit on GitHub, for example an earlier version to check that a bug still shows there.
# The Sandbox window stays open afterwards. The next run closes it.
param([string]$Ref, [int]$Minutes = 60)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

# The winget-pkgs maintainers' test script, pinned by commit and SHA-256.
$sandboxTestUrl = 'https://raw.githubusercontent.com/microsoft/winget-pkgs/9cb4b0c09a1a664d07cd8945bd9bad125f9f6cc8/Tools/SandboxTest.ps1'
$sandboxTestSha256 = 'F28470A689069D652C0159A16A77A68729E8BD29673141BDBD6C21C79196C228'
$names = 'KristjanHS.TranscribeOffline.yaml', 'KristjanHS.TranscribeOffline.installer.yaml',
    'KristjanHS.TranscribeOffline.locale.en-US.yaml'

$work = Join-Path $env:TEMP 'transcribe-offline-winget-test'
Remove-Item $work -Recurse -Force -ErrorAction SilentlyContinue
$staged = New-Item -ItemType Directory (Join-Path $work 'manifest')
foreach ($name in $names) {
    $to = Join-Path $staged $name
    if ($Ref) {
        Invoke-WebRequest -UseBasicParsing "https://raw.githubusercontent.com/KristjanHS/transcribe-offline/$Ref/.github/winget/$name" -OutFile $to
    } else {
        Copy-Item (Join-Path $PSScriptRoot "..\winget\$name") $to
    }
}
# SandboxTest.ps1 shows the folder name as the manifest's name.
$version = (Select-String -Path (Join-Path $staged $names[0]) -Pattern '^PackageVersion:\s*(\S+)').Matches[0].Groups[1].Value
$manifest = Rename-Item $staged $version -PassThru

$sandboxTest = Join-Path $work 'SandboxTest.ps1'
Invoke-WebRequest -UseBasicParsing $sandboxTestUrl -OutFile $sandboxTest
if ((Get-FileHash $sandboxTest -Algorithm SHA256).Hash -ne $sandboxTestSha256) { throw "SHA-256 mismatch: $sandboxTestUrl" }

# CI makes Transcribe-Setup.exe exit without waiting for Enter.
$inSandbox = { $env:CI = '1'; transcribe-offline-setup 2>&1 | Out-Host; exit $LASTEXITCODE }
& $sandboxTest $manifest.FullName $inSandbox -MapFolder $work -Unattended $Minutes
if ($LASTEXITCODE) { throw "SandboxTest.ps1 failed with exit code $LASTEXITCODE" }

$results = Join-Path $env:LOCALAPPDATA 'Packages\Microsoft.DesktopAppInstaller_8wekyb3d8bbwe\SandboxTest\Results'
$metadata = Get-Content (Join-Path $results 'metadata.json') -Raw | ConvertFrom-Json
Write-Host "winget install exit code: $($metadata.InstallExitCodeHex)"
Write-Host "transcribe-offline-setup $version exit code: $($metadata.ScriptExitCode)"
# A failed install leaves no transcribe-offline-setup, and a command that is not found leaves exit code 0.
$code = $metadata.ScriptExitCode
if ($metadata.InstallExitCode -or (-not $metadata.ScriptSucceeded -and -not $code)) { $code = 1 }
exit $code
