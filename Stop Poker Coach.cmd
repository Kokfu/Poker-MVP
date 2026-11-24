@echo off
rem Stops Poker Coach if its window was closed instead of pressing Enter.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop-coach.ps1"
pause
