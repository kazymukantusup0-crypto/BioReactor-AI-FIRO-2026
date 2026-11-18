# BioReactor AI — update the code on the Raspberry Pi from this laptop, WITHOUT internet (no git pull on the Pi).
#
#   powershell -ExecutionPolicy Bypass -File scripts\deploy_to_pi.ps1            finds the Pi by itself
#   powershell -ExecutionPolicy Bypass -File scripts\deploy_to_pi.ps1 -PiHost 10.42.0.1
#
# 1. finds the Pi: direct cable 192.168.50.2 -> its Wi-Fi 10.42.0.1 -> bioreactor.local (SSH key ~/.ssh/id_ed25519_bioreactor)
# 2. copies every file of raspberry/ that is not ignored by git (as it is on this laptop, with uncommitted edits) into
#    ~/BioReactor_AI/raspberry on the Pi (the Pi's .venv stays), plus a stamp «commit, time»
# 3. runs /usr/local/sbin/bioreactor-deploy on the Pi (sudo without password, installed by install.sh): the bridge code
#    goes to /opt/bioreactor-pi and the service restarts
# 4. waits for /health and checks that the Pi runs exactly this stamp
# Network scripts, the systemd unit and the config are copied but NOT applied (they need «sudo ./install.sh» or
# «sudo ./setup_network.sh ...» on the Pi — printed at the end when they changed).
param([string]$PiHost = "")

# Continue: in PowerShell 5.1 a native program writing to stderr (ssh, git) must not abort the script; exit codes are checked by hand
$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
$Key = Join-Path $env:USERPROFILE ".ssh\id_ed25519_bioreactor"
$SshOpts = @("-i", $Key, "-o", "BatchMode=yes", "-o", "ConnectTimeout=4", "-o", "StrictHostKeyChecking=accept-new")

function Invoke-Pi([string]$PiAddress, [string]$Command) {
    $out = & ssh @SshOpts "bio@$PiAddress" $Command 2>&1
    return @{ Code = $LASTEXITCODE; Text = (($out | ForEach-Object { "$_" }) -join "`n").Trim() }   # stderr lines as plain text
}

# 1. where is the Pi
$candidates = if ($PiHost) { @($PiHost) } else { @("192.168.50.2", "10.42.0.1", "bioreactor.local") }
$pi = $null
foreach ($candidate in $candidates) {
    Write-Host "looking for the Pi at $candidate ..."
    if ((Invoke-Pi $candidate "echo ok").Text -eq "ok") { $pi = $candidate; break }
}
if (-not $pi) { Write-Host "Pi not found (cable 192.168.50.2, Wi-Fi 10.42.0.1, bioreactor.local)." -ForegroundColor Red; exit 1 }
Write-Host "Pi: $pi" -ForegroundColor Green

# 2. pack raspberry/ (files git knows, current content) + stamp
$commit = (& git -C $Repo rev-parse --short HEAD).Trim()
$dirty = (& git -C $Repo status --porcelain -- raspberry) -ne $null
$stamp = "$commit$(if ($dirty) { '+local-edits' }) $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
$files = & git -C $Repo ls-files --cached --others --exclude-standard -- raspberry | Where-Object { Test-Path (Join-Path $Repo $_) }
$tmp = Join-Path $env:TEMP "bioreactor-deploy"
New-Item -ItemType Directory -Force $tmp | Out-Null
$list = Join-Path $tmp "files.txt"
$tar = Join-Path $tmp "raspberry.tar"
[IO.File]::WriteAllLines($list, [string[]]$files)
Push-Location $Repo
try { & tar.exe -cf $tar -T $list } finally { Pop-Location }
if ($LASTEXITCODE -ne 0) { Write-Host "tar failed" -ForegroundColor Red; exit 1 }
$before = (Invoke-Pi $pi "cd ~/BioReactor_AI/raspberry 2>/dev/null && sha256sum install.sh bioreactor-pi.service setup_network.sh wifi/* 2>/dev/null").Text
Write-Host "copying $($files.Count) files ($stamp) ..."
& scp @SshOpts -q $tar "bio@${pi}:/tmp/bioreactor-deploy.tar"
if ($LASTEXITCODE -ne 0) { Write-Host "copy failed" -ForegroundColor Red; exit 1 }
$r = Invoke-Pi $pi "mkdir -p ~/BioReactor_AI && tar -xf /tmp/bioreactor-deploy.tar -C ~/BioReactor_AI && rm -f /tmp/bioreactor-deploy.tar && echo '$stamp' > ~/BioReactor_AI/raspberry/DEPLOYED && chmod +x ~/BioReactor_AI/raspberry/*.sh ~/BioReactor_AI/raspberry/wifi/*.sh && echo copied"
if ($r.Text -notmatch "copied") { Write-Host "unpack failed: $($r.Text)" -ForegroundColor Red; exit 1 }
$after = (Invoke-Pi $pi "cd ~/BioReactor_AI/raspberry && sha256sum install.sh bioreactor-pi.service setup_network.sh wifi/* 2>/dev/null").Text

# 3. bridge code -> /opt, restart
$r = Invoke-Pi $pi "sudo -n /usr/local/sbin/bioreactor-deploy"
if ($r.Code -ne 0) {
    Write-Host "The Pi has no deploy helper yet (or it failed): $($r.Text)" -ForegroundColor Yellow
    Write-Host "Once, in a terminal:  ssh -t bio@$pi `"cd ~/BioReactor_AI/raspberry && sudo ./install.sh`"" -ForegroundColor Yellow
    exit 1
}
Write-Host $r.Text

# 4. /health with this stamp
$ok = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 1
    try {
        $h = Invoke-RestMethod -Uri "http://${pi}:8780/health" -TimeoutSec 3
        # the new code answers, and the Arduino (it resets when the port opens: ~3 s) is on line again
        if ($h.ok -and $h.deployed -eq $stamp -and $h.arduino_ok) { $ok = $true; break }
        if ($h.ok -and $h.deployed -eq $stamp -and $i -ge 25) { $ok = $true; break }
    } catch { }
}
if (-not $ok) { Write-Host "/health did not answer with the new code in 30 s: journalctl -u bioreactor-pi -n 30" -ForegroundColor Red; exit 1 }
Write-Host ("/health OK: deployed {0}, Arduino {1} ({2}, {3})" -f $h.deployed, $(if ($h.arduino_ok) { "on line" } else { "NOT on line" }), $h.port, $h.firmware) -ForegroundColor Green
if ($before -ne $after) {
    Write-Host "Network scripts / unit changed: they are copied but not applied. Apply when needed, with the cable connected:" -ForegroundColor Yellow
    Write-Host "  ssh -t bio@$pi `"cd ~/BioReactor_AI/raspberry && sudo ./install.sh && sudo ./setup_network.sh always`"" -ForegroundColor Yellow
}
exit 0
