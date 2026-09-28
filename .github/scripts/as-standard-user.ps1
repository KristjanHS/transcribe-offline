# Run a command as release.yml's standard user "tuser", in the current folder, and exit with its exit code.
# The runner image's own background tasks write to runneradmin's profile, so anything new in tuser's
# profile was written by our install. Output is shown when the command ends.
param([Parameter(Mandatory)][string]$File, [string]$Arguments = ' ')  # Start-Process rejects an empty one
$ErrorActionPreference = 'Stop'
# Creates tuser, or gives it a fresh password (14 characters: net user asks before setting a longer one).
$pw = 'Aa1!' + [Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(5))
net user tuser *> $null
if ($LASTEXITCODE) { net user tuser $pw /add | Out-Null } else { net user tuser $pw | Out-Null }
if ($LASTEXITCODE) { exit $LASTEXITCODE }
$cred = [pscredential]::new('tuser', (ConvertTo-SecureString $pw -AsPlainText -Force))
# The child inherits this environment: point its per-user folders at tuser's profile (once it exists).
$h = (Get-CimInstance Win32_UserProfile | Where-Object LocalPath -Like '*\tuser').LocalPath
if ($h) {
    $env:USERNAME = 'tuser'; $env:USERPROFILE = $h; $env:HOMEPATH = $h.Substring(2)
    $env:APPDATA = "$h\AppData\Roaming"; $env:LOCALAPPDATA = "$h\AppData\Local"
    $env:TEMP = $env:TMP = "$h\AppData\Local\Temp"
}
$io = "$env:RUNNER_TEMP\as-standard-user"
New-Item -ItemType File "$io.in" -Force | Out-Null  # an empty stdin, so no "Press Enter" can hang
$p = Start-Process $File $Arguments -Credential $cred -LoadUserProfile -WorkingDirectory $PWD -Wait -PassThru `
    -RedirectStandardInput "$io.in" -RedirectStandardOutput "$io.out" -RedirectStandardError "$io.err"
Get-Content "$io.out", "$io.err"
exit $p.ExitCode
