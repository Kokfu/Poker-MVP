@echo off
rem Double-click to start Poker Coach for you and friends on the same Wi-Fi.
title Poker Coach
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-coach.ps1" %*
if errorlevel 1 pause
