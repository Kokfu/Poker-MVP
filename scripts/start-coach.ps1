<#
.SYNOPSIS
  Start Poker Coach for you and friends on the same Wi-Fi.

.DESCRIPTION
  Double-click "Start Poker Coach.cmd" in the project folder; it runs this script.
  - First run: creates the Python environment and installs the web packages.
  - Builds the frontend when its inputs change, serves it with the API, and
    prints the address for friends when Windows has a Private network.
  - Press Enter in the window to stop Coach. If the window was closed instead,
    run "Stop Poker Coach.cmd" (the next start also cleans up).

.PARAMETER NoBrowser
  Do not open the page in a browser.

.PARAMETER NoWait
  Start, print the addresses, and return without waiting (stop later with
  "Stop Poker Coach.cmd").

  Ports can be changed with the environment variables POKER_API_PORT (default
  8000) and POKER_WEB_PORT (default 5173).
#>
param([switch]$NoBrowser, [switch]$NoWait, [switch]$LoopbackOnly)

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

function Get-PortListener([int]$port) {
    $listeners = [Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners()
    return $listeners | Where-Object { $_.Port -eq $port } | Select-Object -First 1
}

function Get-PathDigest([string]$path) {
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $reader = [IO.File]::OpenRead($path)
        try { return [BitConverter]::ToString($sha.ComputeHash($reader)) }
        finally { $reader.Dispose() }
    } finally { $sha.Dispose() }
}

function Test-BuiltCoach([string]$directory, [string]$manifest) {
    $files = @(Get-Content -LiteralPath $manifest -ErrorAction SilentlyContinue)
    if ('index.html' -notin $files -or 'service-worker.js' -notin $files) { return $false }
    foreach ($file in $files) {
        if (-not (Test-Path -LiteralPath (Join-Path $directory $file) -PathType Leaf)) { return $false }
    }
    return $true
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
    param($profiles)
    if ($LoopbackOnly -or -not (Get-Command Get-NetIPConfiguration -ErrorAction SilentlyContinue)) { return $null }
    foreach ($profile in $profiles) {
        if ($profile.NetworkCategory -ne 'Private') { continue }
        $config = Get-NetIPConfiguration -InterfaceIndex $profile.InterfaceIndex -ErrorAction SilentlyContinue
        if ($config -and $config.IPv4DefaultGateway -and $config.NetAdapter.Status -eq 'Up') {
            return @($config.IPv4Address)[0].IPAddress
        }
    }
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
New-Item -ItemType Directory -Force -Path $CoachRunDir | Out-Null
$installStamp = Join-Path $CoachRunDir 'frontend-install.sha256'
$buildStamp = Join-Path $CoachRunDir 'frontend-build.sha256'
$buildManifest = Join-Path $CoachRunDir 'frontend-built-files.txt'
$dist = Join-Path $CoachFrontend 'dist'
$lockHash = Get-PathDigest (Join-Path $CoachFrontend 'package-lock.json')
$installed = Get-Content -LiteralPath $installStamp -ErrorAction SilentlyContinue
if (-not (Test-Path (Join-Path $CoachFrontend 'node_modules/.bin/vite.cmd')) -or $installed -ne $lockHash) {
    Write-Step "Installing locked web packages"
    Push-Location $CoachFrontend
    try { & npm.cmd ci --prefer-offline --no-audit --no-fund } finally { Pop-Location }
    if ($LASTEXITCODE -ne 0) { Stop-WithMessage "Installing the web packages failed. Check your internet connection and try again." }
    Set-Content -LiteralPath $installStamp -Value $lockHash
}
$buildInputs = @(
    Get-ChildItem -LiteralPath (Join-Path $CoachFrontend 'src'), (Join-Path $CoachFrontend 'public') -File -Recurse
    Get-ChildItem -LiteralPath $CoachFrontend -Filter 'tsconfig*.json' -File
    Get-Item -LiteralPath @('index.html', 'package.json', 'package-lock.json', 'vite.config.ts', 'pwa-build.mjs').ForEach({
        Join-Path $CoachFrontend $_
    })
)
$stamp = ($buildInputs | Sort-Object FullName | ForEach-Object { Get-PathDigest $_.FullName }) -join ':'
$built = Get-Content -LiteralPath $buildStamp -ErrorAction SilentlyContinue
if ($built -ne $stamp -or -not (Test-BuiltCoach $dist $buildManifest)) {
    Write-Step "Building Poker Coach"
    Push-Location $CoachFrontend
    try { & npm.cmd run build } finally { Pop-Location }
    if ($LASTEXITCODE -ne 0) { Stop-WithMessage "The Poker Coach web build failed." }
    $prefixLength = $dist.Length + 1
    Get-ChildItem -LiteralPath $dist -File -Recurse | Sort-Object FullName |
        ForEach-Object { $_.FullName.Substring($prefixLength) } |
        Set-Content -LiteralPath $buildManifest -Encoding UTF8
    Set-Content -LiteralPath $buildStamp -Value $stamp
}

# ---- Ports -----------------------------------------------------------------
foreach ($port in @($ApiPort, $WebPort)) {
    $listener = Get-PortListener $port
    if ($listener) {
        Stop-WithMessage ("Port $port is already in use at $listener.`n" +
            "Poker Coach may already be running: try http://localhost:$WebPort`n" +
            "Otherwise close that program, or pick other ports (set POKER_API_PORT / POKER_WEB_PORT).")
    }
}

# ---- Start -----------------------------------------------------------------
$log = @{
    apiOut = Join-Path $CoachRunDir 'backend.log'; apiErr = Join-Path $CoachRunDir 'backend-errors.log'
}

$profiles = if (-not $LoopbackOnly) {
    # The .cmd can inherit a PowerShell 7 module path from its caller.
    foreach ($module in @('NetConnection', 'NetTCPIP')) {
        $manifest = Join-Path $PSHOME "Modules/$module/$module.psd1"
        if (Test-Path -LiteralPath $manifest) { Import-Module -Name $manifest -ErrorAction SilentlyContinue }
    }
    if (Get-Command Get-NetConnectionProfile -ErrorAction SilentlyContinue) {
        @(Get-NetConnectionProfile -ErrorAction SilentlyContinue)
    }
}
$lan = Get-LanAddress $profiles
$share = [bool]$lan
$publicNetwork = $profiles |
    Where-Object { $_.NetworkCategory -eq 'Public' -and $_.IPv4Connectivity -ne 'NoTraffic' } |
    Select-Object -First 1

$coachArguments = @('-m', 'coach.launcher', '--api-port', "$ApiPort", '--web-port', "$WebPort")
if ($share) { $coachArguments += @('--lan', $lan) }
Write-Step "Serving the built Coach page and API (web port $WebPort)"
$api = Start-Process -FilePath $CoachPython -WorkingDirectory $CoachBackend -WindowStyle Hidden -PassThru `
    -ArgumentList $coachArguments -RedirectStandardOutput $log.apiOut -RedirectStandardError $log.apiErr

@{ api = $api.Id; apiPort = $ApiPort; webPort = $WebPort; started = (Get-Date).ToString('s') } |
    ConvertTo-Json | Set-Content -Path $CoachPidFile -Encoding UTF8

$ok = (Wait-ForUrl "http://127.0.0.1:$ApiPort/api/health" 90) -and (Wait-ForUrl "http://127.0.0.1:$WebPort/" 60) -and
      (Wait-ForUrl "http://127.0.0.1:$WebPort/api/health" 15)
if (-not $ok -or $api.HasExited) {
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
} elseif ($LoopbackOnly) {
    Write-Host "  Loopback-only mode is enabled."
} elseif ($publicNetwork) {
    Write-Host "  Not shared: Windows marks the network '$($publicNetwork.Name)' as Public, so only this computer can use it." -ForegroundColor Yellow
    Write-Host "  On your own home Wi-Fi, switch it to Private and start again:" -ForegroundColor Yellow
    Write-Host "  Settings > Network & internet > Wi-Fi > $($publicNetwork.Name) > Network profile type > Private." -ForegroundColor Yellow
} else {
    Write-Host "  No network connection found, so only this computer can use it." -ForegroundColor Yellow
}
Write-Host ""
Write-Host "  Notes:" -ForegroundColor DarkGray
Write-Host "  - If Windows Firewall asks, allow Python on Private networks only." -ForegroundColor DarkGray
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
