@echo off
rem -------------------------------------------------------------------
rem Application  : gmailAgent
rem Script       : tri-reel.bat
rem Version      : 1.0
rem Date         : 16-11-2026
rem Design       : TSC + Mistral Vibe
rem Build        : Mistral Vibe
rem -------------------------------------------------------------------
rem Run de tri en mode reel (ecritures Gmail : libelles Agent/*).
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File "%~dp0\lancer.ps1" cli tri --reel
pause
