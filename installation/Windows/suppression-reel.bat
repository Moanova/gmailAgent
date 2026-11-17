@echo off
rem -------------------------------------------------------------------
rem Application  : gmailAgent
rem Script       : suppression-reel.bat
rem Version      : 1.0
rem Date         : 16-11-2026
rem Design       : TSC + Mistral Vibe
rem Build        : Mistral Vibe
rem -------------------------------------------------------------------
rem Run de suppression T+24h en mode REEL (corbeille uniquement, sur les
rem notifications deja traitees de plus de 24 h - jamais de suppression definitive).
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File "%~dp0\lancer.ps1" cli suppression --reel
pause
