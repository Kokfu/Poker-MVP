# Stop Poker Coach if it was started with "Start Poker Coach.cmd" and its window was closed.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'coach-common.ps1')
Stop-CoachProcesses
