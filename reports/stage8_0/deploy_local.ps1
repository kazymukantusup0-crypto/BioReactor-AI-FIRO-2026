# One-time reviewed deployment record for the former PID 21888; not a launcher.
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$expectedDatabase = Join-Path $projectRoot 'data/market/market.sqlite3'
$health = Invoke-RestMethod -Uri 'http://127.0.0.1:8765/health'
if ([IO.Path]::GetFullPath($health.database) -ne [IO.Path]::GetFullPath($expectedDatabase)) { throw 'Unexpected production database; server left untouched' }
$previousProcess = Get-CimInstance Win32_Process -Filter 'ProcessId=21888'
if (-not $previousProcess -or $previousProcess.CommandLine -notmatch 'main\.py dashboard --port 8765 --no-browser --no-scheduler') { throw 'Recorded server PID does not match the expected command; server left untouched' }
$audit = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'preservation.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not $audit.all_protected_files_unchanged -or $audit.active_leases.Count -ne 0) { throw 'Preservation or active-work guard failed' }
$pythonPath = $previousProcess.ExecutablePath
Stop-Process -Id $previousProcess.ProcessId
$env:BIOREACTOR_MARKET_DB = $expectedDatabase
$env:BIOREACTOR_RESEARCH_ONLINE = '0'
$env:PYTHONUTF8 = '1'
$serverProcess = Start-Process -FilePath $pythonPath -ArgumentList @('main.py','dashboard','--port','8765','--no-browser','--no-scheduler') -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $projectRoot 'data/runtime/dashboard_v8_0.stdout.log') -RedirectStandardError (Join-Path $projectRoot 'data/runtime/dashboard_v8_0.stderr.log')
Set-Content -LiteralPath (Join-Path $projectRoot 'data/runtime/dashboard_v8_0.pid') -Value $serverProcess.Id -Encoding UTF8
$ready = $false
for ($attempt=0; $attempt -lt 60; $attempt++) {
    try { $newHealth = Invoke-RestMethod -Uri 'http://127.0.0.1:8765/health'; if ($newHealth.database -eq $expectedDatabase) { $ready=$true; break } } catch {}
    Start-Sleep -Milliseconds 250
}
if (-not $ready) { throw 'Updated server did not become healthy; inspect v8 runtime logs' }
$catalog = Invoke-RestMethod -Uri 'http://127.0.0.1:8765/api/advisor/catalog'
if ($catalog.approved_profile_count -ne 6) { throw 'Updated catalog not served' }
$body = @{ request=@{ components=@(@{id='probe';material='cattle_manure';quantity=1000;unit='g'}) };target_unit='kg'} | ConvertTo-Json -Depth 5
$conversion = Invoke-RestMethod -Uri 'http://127.0.0.1:8765/api/advisor/convert' -Method Post -ContentType 'application/json' -Body $body
if ($conversion.conversions[0].value.low -ne 1) { throw 'Real production conversion HTTP failed' }
$page = Invoke-WebRequest -Uri 'http://127.0.0.1:8765/dashboard/' -UseBasicParsing
$record = @{version='8.0';pid=$serverProcess.Id;database=$newHealth.database;scheduler_enabled=$newHealth.scheduler_enabled;approved_profile_count=$catalog.approved_profile_count;http_status=[int]$page.StatusCode;conversion_http_passed=$true;url='http://127.0.0.1:8765/dashboard/#/chat'}
$record | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'production_server.json') -Encoding UTF8
$record | ConvertTo-Json -Depth 4
Start-Process -FilePath 'C:/Program Files/Google/Chrome/Application/chrome.exe' -ArgumentList @('--new-window','http://127.0.0.1:8765/dashboard/#/chat')
