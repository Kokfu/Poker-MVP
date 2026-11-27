# Shared paths and process cleanup for start-coach.ps1 and stop-coach.ps1.

$CoachRoot = Split-Path -Parent $PSScriptRoot
$CoachBackend = Join-Path $CoachRoot 'backend'
$CoachFrontend = Join-Path $CoachRoot 'frontend'
$CoachPython = Join-Path $CoachBackend '.venv\Scripts\python.exe'
$CoachRunDir = if ($env:POKER_COACH_RUN_DIR) { $env:POKER_COACH_RUN_DIR } else { Join-Path $CoachRoot '.run' }
$CoachPidFile = Join-Path $CoachRunDir 'pids.json'

function Test-CoachProcess($process, [string]$role, $recorded) {
    if ($role -eq 'api' -and $process.ProcessName -ne 'python') { return $false }
    if ($role -eq 'web' -and $process.ProcessName -ne 'cmd') { return $false }

    try { $started = $process.StartTime } catch { return $false }
    $recordedTicks = $recorded."${role}StartedUtcTicks"
    if ($null -ne $recordedTicks) {
        return $started.ToUniversalTime().Ticks -eq $recordedTicks
    }

    # Older launchers recorded one local timestamp for both processes.
    # Also verify the repo-specific original command before stopping either.
    $legacyStart = [datetime]::MinValue
    if (-not [datetime]::TryParse([string]$recorded.started, [ref]$legacyStart)) { return $false }
    $age = ($legacyStart - $started).TotalSeconds
    if ($age -lt -1 -or $age -gt 10) { return $false }
    $instance = Get-CimInstance Win32_Process -Filter "ProcessId = $($process.Id)" -ErrorAction SilentlyContinue
    $command = [string]$instance.CommandLine
    if ($role -eq 'api') {
        return $command.IndexOf($CoachPython, [StringComparison]::OrdinalIgnoreCase) -ge 0 -and
            $command -match '\s-m\s+(coach\.launcher|uvicorn\s+main:app)\s'
    }
    $vite = Join-Path $CoachFrontend 'node_modules\.bin\vite.cmd'
    return $command.IndexOf($vite, [StringComparison]::OrdinalIgnoreCase) -ge 0
}

function Stop-CoachProcesses([switch]$Quiet) {
    # Stops only the processes this launcher started (recorded in .run\pids.json),
    # together with their child processes, never other programs on the same ports.
    if (-not (Test-Path $CoachPidFile)) {
        if (-not $Quiet) { Write-Host "Poker Coach is not running (nothing was started by the launcher)." }
        return
    }
    $recorded = Get-Content $CoachPidFile -Raw | ConvertFrom-Json
    $stopped = 0
    foreach ($role in @('api', 'web')) {
        $id = $recorded.$role
        if (-not $id) { continue }
        $process = Get-Process -Id $id -ErrorAction SilentlyContinue
        if ($process -and (Test-CoachProcess $process $role $recorded)) {
            & taskkill.exe /PID $id /T /F 2>$null | Out-Null
            $stopped++
        }
    }
    Remove-Item $CoachPidFile -Force -ErrorAction SilentlyContinue
    if (-not $Quiet) {
        if ($stopped) { Write-Host "Poker Coach stopped." } else { Write-Host "Poker Coach was not running." }
    }
}
