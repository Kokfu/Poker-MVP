# Shared paths and process cleanup for start-coach.ps1 and stop-coach.ps1.

$CoachRoot = Split-Path -Parent $PSScriptRoot
$CoachBackend = Join-Path $CoachRoot 'backend'
$CoachFrontend = Join-Path $CoachRoot 'frontend'
$CoachPython = Join-Path $CoachBackend '.venv\Scripts\python.exe'
$CoachRunDir = Join-Path $CoachRoot '.run'
$CoachPidFile = Join-Path $CoachRunDir 'pids.json'

function Stop-CoachProcesses([switch]$Quiet) {
    # Stops only the processes this launcher started (recorded in .run\pids.json),
    # together with their child processes, never other programs on the same ports.
    if (-not (Test-Path $CoachPidFile)) {
        if (-not $Quiet) { Write-Host "Poker Coach is not running (nothing was started by the launcher)." }
        return
    }
    $recorded = Get-Content $CoachPidFile -Raw | ConvertFrom-Json
    $stopped = 0
    foreach ($id in @($recorded.api, $recorded.web)) {
        if (-not $id) { continue }
        $process = Get-Process -Id $id -ErrorAction SilentlyContinue
        if ($process -and $process.ProcessName -in @('python', 'cmd', 'node')) {
            & taskkill.exe /PID $id /T /F 2>$null | Out-Null
            $stopped++
        }
    }
    Remove-Item $CoachPidFile -Force -ErrorAction SilentlyContinue
    if (-not $Quiet) {
        if ($stopped) { Write-Host "Poker Coach stopped." } else { Write-Host "Poker Coach was not running." }
    }
}
