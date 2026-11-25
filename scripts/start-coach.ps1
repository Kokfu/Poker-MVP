<#
.SYNOPSIS
  Start Poker Coach for you and friends on the same Wi-Fi.

.DESCRIPTION
  Double-click "Start Poker Coach.cmd" in the project folder; it runs this script.
  - First run: creates the Python environment and installs the web packages.
  - Starts the backend on this computer only (127.0.0.1) and the web page on
    your local network, then opens the page and prints the address for friends.
  - Press Enter in the window to stop both. If the window was closed instead,
    run "Stop Poker Coach.cmd" (the next start also cleans up).

.PARAMETER NoBrowser
  Do not open the page in a browser.

.PARAMETER NoWait
  Start, print the addresses, and return without waiting (stop later with
  "Stop Poker Coach.cmd").

  Ports can be changed with the environment variables POKER_API_PORT (default
  8000) and POKER_WEB_PORT (default 5173).
#>
param([switch]$NoBrowser, [switch]$NoWait)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'coach-common.ps1')

$ApiPort = if ($env:POKER_API_PORT) { [int]$env:POKER_API_PORT } else { 8000 }
$WebPort = if ($env:POKER_WEB_PORT) { [int]$env:POKER_WEB_PORT } else { 5173 }

function Write-Step($text) { Write-Host "  - $text" -ForegroundColor DarkGray }

function Stop-WithMessage($text) {
    Write-Host ""
    Write-Host $text -ForegroundColor Red
    exit 1
}

function Get-PortOwner([int]$port) {
    $listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $listener) { return $null }
    $process = Get-Process -Id $listener.OwningProcess -ErrorAction SilentlyContinue
    if ($process) { return "$($process.ProcessName) (process $($process.Id))" }
    return "process $($listener.OwningProcess)"
}

function Wait-ForUrl([string]$url, [int]$seconds) {
    $deadline = (Get-Date).AddSeconds($seconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 3
            if ($response.StatusCode -eq 200) { return $true }
        } catch { Start-Sleep -Milliseconds 500 }
    }
    return $false
}

function Get-LanAddress {
    $config = Get-NetIPConfiguration -ErrorAction SilentlyContinue |
        Where-Object { $_.IPv4DefaultGateway -and $_.NetAdapter.Status -eq 'Up' } |
        Select-Object -First 1
    if ($config) { return @($config.IPv4Address)[0].IPAddress }
    return $null
}

Write-Host ""
Write-Host "Poker Coach" -ForegroundColor Green
Write-Host ""

# Clean up anything a previous start left running (window closed instead of Enter).
Stop-CoachProcesses -Quiet

# ---- First-run setup -------------------------------------------------------
if (-not (Test-Path $CoachPython)) {
    Write-Step "First run: creating the Python environment (one-time, a few minutes)"
    $py = Get-Command py.exe -ErrorAction SilentlyContinue
    if (-not $py) { Stop-WithMessage "Python 3.11 is not installed. Install it from https://www.python.org/downloads/ (tick 'Add python.exe to PATH'), then run this again." }
    & py.exe -3.11 -m venv (Join-Path $CoachBackend '.venv')
    if ($LASTEXITCODE -ne 0) { Stop-WithMessage "Could not create the Python environment. Is Python 3.11 installed? (py -3.11 --version)" }
}
& $CoachPython -c "import fastapi, uvicorn, eval7, treys, numpy" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Step "Installing Python packages (one-time)"
    & $CoachPython -m pip install --disable-pip-version-check -q -r (Join-Path $CoachBackend 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { Stop-WithMessage "Installing the Python packages failed. Check your internet connection and try again." }
}

$npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
if (-not $npm) { Stop-WithMessage "Node.js is not installed. Install the LTS version from https://nodejs.org/, then run this again." }
if (-not (Test-Path (Join-Path $CoachFrontend 'node_modules'))) {
    Write-Step "Installing web packages (one-time)"
    Push-Location $CoachFrontend
    try { & npm.cmd install --no-audit --no-fund } finally { Pop-Location }
    if ($LASTEXITCODE -ne 0) { Stop-WithMessage "Installing the web packages failed. Check your internet connection and try again." }
}

# ---- Ports -----------------------------------------------------------------
foreach ($port in @($ApiPort, $WebPort)) {
    $owner = Get-PortOwner $port
    if ($owner) {
        Stop-WithMessage ("Port $port is already in use by $owner.`n" +
            "Poker Coach may already be running: try http://localhost:$WebPort`n" +
            "Otherwise close that program, or pick other ports (set POKER_API_PORT / POKER_WEB_PORT).")
    }
}

# ---- Start -----------------------------------------------------------------
New-Item -ItemType Directory -Force -Path $CoachRunDir | Out-Null
$log = @{
    apiOut = Join-Path $CoachRunDir 'backend.log'; apiErr = Join-Path $CoachRunDir 'backend-errors.log'
    webOut = Join-Path $CoachRunDir 'web.log';     webErr = Join-Path $CoachRunDir 'web-errors.log'
}

Write-Step "Starting the Coach engine (port $ApiPort, this computer only)"
# Vite is the public LAN entry point. The API uses its socket peer for
# practice creation limits instead of an address carried in HTTP headers.
$api = Start-Process -FilePath $CoachPython -WorkingDirectory $CoachBackend -WindowStyle Hidden -PassThru `
    -ArgumentList @('-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', "$ApiPort", '--no-proxy-headers') `
    -RedirectStandardOutput $log.apiOut -RedirectStandardError $log.apiErr

# Share the page on the network only when Windows marks this network Private (home/work).
# On a Public network (cafe, hotspot) the page stays on this computer.
$lan = Get-LanAddress
$netProfile = Get-NetConnectionProfile -ErrorAction SilentlyContinue | Where-Object { $_.IPv4Connectivity -ne 'NoTraffic' } | Select-Object -First 1
$publicNetwork = $netProfile -and $netProfile.NetworkCategory -eq 'Public'
$share = $lan -and -not $publicNetwork
$webHost = if ($share) { '0.0.0.0' } else { '127.0.0.1' }

# The web page proxies /api to the engine, so friends never talk to the engine directly.
$env:API_PROXY = "http://127.0.0.1:$ApiPort"
Write-Step ("Starting the web page (port $WebPort, " + $(if ($share) { 'visible on your network)' } else { 'this computer only)' }))
$vite = Join-Path $CoachFrontend 'node_modules\.bin\vite.cmd'
$web = Start-Process -FilePath 'cmd.exe' -WorkingDirectory $CoachFrontend -WindowStyle Hidden -PassThru `
    -ArgumentList @('/c', "`"$vite`"", '--host', $webHost, '--port', "$WebPort", '--strictPort') `
    -RedirectStandardOutput $log.webOut -RedirectStandardError $log.webErr

@{ api = $api.Id; web = $web.Id; apiPort = $ApiPort; webPort = $WebPort; started = (Get-Date).ToString('s') } |
    ConvertTo-Json | Set-Content -Path $CoachPidFile -Encoding UTF8

$ok = (Wait-ForUrl "http://127.0.0.1:$ApiPort/api/health" 90) -and (Wait-ForUrl "http://127.0.0.1:$WebPort/" 60) -and
      (Wait-ForUrl "http://127.0.0.1:$WebPort/api/health" 15)
if (-not $ok) {
    Write-Host ""
    Write-Host "Poker Coach did not start. Last log lines:" -ForegroundColor Red
    foreach ($file in $log.Values) {
        if ((Test-Path $file) -and (Get-Item $file).Length -gt 0) {
            Write-Host "--- $(Split-Path $file -Leaf)" -ForegroundColor DarkGray
            Get-Content $file -Tail 15
        }
    }
    Stop-CoachProcesses -Quiet
    exit 1
}

# ---- Ready -----------------------------------------------------------------
Write-Host ""
Write-Host "  Poker Coach is running." -ForegroundColor Green
Write-Host ""
Write-Host "  On this computer:          http://localhost:$WebPort"
if ($share) {
    Write-Host "  Friends on the same Wi-Fi: " -NoNewline
    Write-Host "http://${lan}:$WebPort" -ForegroundColor Cyan
} elseif ($publicNetwork) {
    Write-Host "  Not shared: Windows marks the network '$($netProfile.Name)' as Public, so only this computer can use it." -ForegroundColor Yellow
    Write-Host "  On your own home Wi-Fi, switch it to Private and start again:" -ForegroundColor Yellow
    Write-Host "  Settings > Network & internet > Wi-Fi > $($netProfile.Name) > Network profile type > Private." -ForegroundColor Yellow
} else {
    Write-Host "  No network connection found, so only this computer can use it." -ForegroundColor Yellow
}
Write-Host ""
Write-Host "  Notes:" -ForegroundColor DarkGray
Write-Host "  - The first time, Windows may ask whether Node.js can use the network: allow Private networks." -ForegroundColor DarkGray
Write-Host "  - Everyone shares one saved-hands file, and anyone who can open the page can delete saved hands." -ForegroundColor DarkGray
Write-Host "    Only share the address on a network you trust (home Wi-Fi, not public hotspots)." -ForegroundColor DarkGray
Write-Host "  - Logs: $CoachRunDir" -ForegroundColor DarkGray
Write-Host ""

if (-not $NoBrowser) { Start-Process "http://localhost:$WebPort" }

if ($NoWait) {
    Write-Host "  Running in the background. Stop it with 'Stop Poker Coach.cmd'."
    exit 0
}

try {
    Read-Host "  Press Enter to stop Poker Coach" | Out-Null
} finally {
    Write-Host "  Stopping..." -ForegroundColor DarkGray
    Stop-CoachProcesses -Quiet
    Write-Host "  Stopped." -ForegroundColor DarkGray
}
