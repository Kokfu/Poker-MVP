[CmdletBinding()]
param(
    [switch] $Status,
    [string] $JobsDirectory = (Join-Path $PSScriptRoot 'jobs'),
    [ValidateRange(1, 1440)] [int] $StaleAfterMinutes = 30
)

$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$jobs = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($JobsDirectory)
$resultDirectory = Join-Path $jobs 'agent-results'
$logPath = Join-Path $jobs 'agent.log'
$opponents = [ordered]@{ tight = 41000; equity = 44000; expert = 47000; range_expert = 50000 }
$sessions = 24
$handsPerSeat = 60

function Get-DiagnosticStatus([string] $Opponent, [int] $Offset) {
    $name = "nov26-$Opponent"
    $ledger = Join-Path $resultDirectory "$name.jsonl"
    $summary = Join-Path $resultDirectory "$name.summary.json"
    $records = @()
    $ledgerLastWrite = $null
    if (Test-Path -LiteralPath $ledger) {
        $contents = Get-Content -LiteralPath $ledger -Raw
        $ledgerLastWrite = [DateTimeOffset](Get-Item -LiteralPath $ledger).LastWriteTime
        # A process may still be writing the final line. Only consume lines
        # that already end in a newline.
        $lines = @([regex]::Matches([string]$contents, '(?m)^[^\r\n]+(?=\r?\n)') | ForEach-Object Value)
        if ($lines.Count -gt 0) {
            $header = ConvertFrom-Json -InputObject $lines[0]
            if ($header.agent -ne 'solver_adaptive' -or $header.opponent -ne $Opponent -or
                $header.configuration.pairs -ne $sessions -or $header.configuration.session_hands -ne $handsPerSeat -or
                $header.configuration.seed_offset -ne $Offset -or $header.configuration.seed_set -ne 'development' -or
                $header.configuration.big_blind -ne 100) {
                throw "The $name ledger parameters do not match the diagnostic."
            }
            for ($index = 1; $index -lt $lines.Count; $index++) {
                $record = ConvertFrom-Json -InputObject $lines[$index]
                $seed = 1000000 + $Offset + ($index - 1) * $handsPerSeat
                if ($index -gt $sessions -or $record.session -ne $index -or $record.seed -ne $seed -or
                    $record.hands_per_seat -ne $handsPerSeat) {
                    throw "The $name ledger has an unexpected session at line $($index + 1)."
                }
                $records += $record
            }
        }
    }

    $start = $null
    $attemptStart = $null
    $end = $null
    $exitCode = $null
    if (Test-Path -LiteralPath $logPath) {
        $safeName = [regex]::Escape($name)
        foreach ($line in Get-Content -LiteralPath $logPath) {
            if ($line -match "^(\S+) begin $safeName attempt \d+$") {
                $attemptStart = [DateTimeOffset]::Parse($Matches[1])
                if ($null -eq $start) { $start = $attemptStart }
                $end = $null
            } elseif ($line -match "^(\S+) end $safeName exit (-?\d+)$") {
                $end = [DateTimeOffset]::Parse($Matches[1])
                $exitCode = [int]$Matches[2]
            }
        }
    }
    $hands = $records.Count * $handsPerSeat * 2
    $net = ($records | ForEach-Object { $_.net_seat_a + $_.net_seat_b } | Measure-Object -Sum).Sum
    $illegalActions = ($records | Measure-Object -Property illegal_actions -Sum).Sum
    $engineFallbacks = ($records | Measure-Object -Property fallback_actions -Sum).Sum
    $dealMismatches = @($records | Where-Object { $_.deal_verified -ne $true }).Count
    $solverRecords = @($records | Where-Object { $null -ne $_.PSObject.Properties['solver_fallback_actions'] })
    $solverFallbacks = if ($solverRecords.Count -eq $records.Count) {
        ($solverRecords | Measure-Object -Property solver_fallback_actions -Sum).Sum
    } else { $null }
    $summaryStatus = 'Missing'
    if (Test-Path -LiteralPath $summary) {
        try {
            $result = Get-Content -LiteralPath $summary -Raw | ConvertFrom-Json
            $solverCoverageMatches = $result.solver_fallback_coverage_sessions -eq $solverRecords.Count -or
                ($null -eq $result.solver_fallback_coverage_sessions -and $solverRecords.Count -eq 0)
            $summaryStatus = if ($result.format_version -eq 1 -and $result.agent -eq 'solver_adaptive' -and
                $result.opponent -eq $Opponent -and $result.ledger -eq "$name.jsonl" -and
                $result.configuration.seed_offset -eq $Offset -and $result.configuration.seed_set -eq 'development' -and
                $result.configuration.pairs -eq $sessions -and $result.configuration.session_hands -eq $handsPerSeat -and
                $result.configuration.big_blind -eq 100 -and $result.sessions -eq $records.Count -and
                $result.hands -eq $hands -and $result.illegal_actions -eq $illegalActions -and
                $result.fallback_actions -eq $engineFallbacks -and $result.deal_mismatches -eq $dealMismatches -and
                $solverCoverageMatches -and $result.solver_fallback_actions -eq $solverFallbacks) { 'Confirmed' }
            else { 'Mismatch' }
        } catch {
            $summaryStatus = 'Unreadable'
        }
    }
    $now = [DateTimeOffset]::Now
    $remaining = $sessions - $records.Count
    $lastActivity = if ($ledgerLastWrite -gt $attemptStart) { $ledgerLastWrite } else { $attemptStart }
    $stale = $attemptStart -and !$end -and $remaining -gt 0 -and
        ($now - $lastActivity).TotalMinutes -ge $StaleAfterMinutes
    $referenceTime = if ($end) { $end } else { $now }
    $elapsed = if ($start) { ($referenceTime - $start).TotalSeconds } else { 0 }
    $rate = if ($elapsed -gt 0 -and $hands -gt 0) { $hands / $elapsed } else { 0 }
    $eta = if ($rate -gt 0 -and !$end -and !$stale -and $remaining -gt 0) {
        $now.AddSeconds((2 * $remaining * $handsPerSeat) / $rate)
    } else { $null }
    $state = if ($summaryStatus -eq 'Confirmed' -and $records.Count -eq $sessions) { 'Complete' }
    elseif ($end -and $exitCode -ne 0) { 'Failed' }
    elseif ($records.Count -eq $sessions -and $summaryStatus -ne 'Missing') { 'Unverified summary' }
    elseif ($records.Count -eq $sessions) { 'Ledger complete' }
    elseif ($end) { 'Incomplete' }
    elseif ($stale) { 'Stale' }
    elseif ($start) { 'Started' }
    else { 'Pending' }
    [pscustomobject]@{
        Opponent = $Opponent
        State = $state
        Sessions = $records.Count
        MissingSessions = $remaining
        Hands = $hands
        SummaryStatus = $summaryStatus
        BBPer100 = if ($hands) { [Math]::Round($net / $hands, 2) } else { $null }
        IllegalActions = $illegalActions
        EngineFallbacks = $engineFallbacks
        SolverFallbacks = $solverFallbacks
        SolverCoverage = "$($solverRecords.Count)/$($records.Count)"
        DealMismatches = $dealMismatches
        HandsPerMinute = [Math]::Round($rate * 60, 2)
        LedgerLastWrite = if ($ledgerLastWrite) { $ledgerLastWrite.ToString('yyyy-MM-dd HH:mm:ss zzz') } else { $null }
        EstimatedEnd = if ($eta) { $eta.ToString('yyyy-MM-dd HH:mm:ss zzz') } else { $null }
    }
}

if ($Status) {
    foreach ($match in $opponents.GetEnumerator()) { Get-DiagnosticStatus $match.Key $match.Value }
    return
}

New-Item -ItemType Directory -Force -Path $jobs | Out-Null
$planLock = [IO.File]::Open((Join-Path $jobs 'agent-diagnostic.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
$python = Join-Path $repo 'backend/.venv/Scripts/python.exe'
$env:OPENBLAS_NUM_THREADS = '1'
$env:OMP_NUM_THREADS = '1'
$env:MKL_NUM_THREADS = '1'
$env:COACH_DB_PATH = Join-Path $env:TEMP ('poker-agent-' + [guid]::NewGuid() + '.sqlite')
$anyFailed = $false
Push-Location (Join-Path $repo 'backend')
try {
    foreach ($match in $opponents.GetEnumerator()) {
        $name = "nov26-$($match.Key)"
        $progress = Get-DiagnosticStatus $match.Key $match.Value
        if ($progress.State -eq 'Complete') { continue }
        $options = @('-u', '-m', 'simulation.agent_cli', '--run', $name, '--opponent', $match.Key,
                     '--sessions', $sessions, '--session-hands', $handsPerSeat, '--seed-offset', $match.Value,
                     '--output-dir', $resultDirectory)
        for ($attempt = 1; $attempt -le 2; $attempt++) {
            Add-Content -LiteralPath $logPath -Value ('{0:o} begin {1} attempt {2}' -f (Get-Date), $name, $attempt)
            $resume = @()
            if (Test-Path -LiteralPath (Join-Path $resultDirectory "$name.jsonl")) { $resume = @('--resume') }
            & $python @options @resume *>> $logPath
            $exitCode = $LASTEXITCODE
            Add-Content -LiteralPath $logPath -Value ('{0:o} end {1} exit {2}' -f (Get-Date), $name, $exitCode)
            if ($exitCode -eq 0) { break }
        }
        if ($exitCode -ne 0) { $anyFailed = $true }
    }
} finally {
    Pop-Location
    $planLock.Dispose()
}
if ($anyFailed) { exit 1 }
