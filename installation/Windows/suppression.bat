@echo off
rem -------------------------------------------------------------------
rem Application  : gmailAgent
rem Script       : suppression.bat
rem Version      : 1.0
rem Date         : 16-11-2026
rem Design       : TSC + Mistral Vibe
rem Build        : Mistral Vibe
rem -------------------------------------------------------------------
rem Run de suppression T+24h en dry-run (corbeille uniquement, notifications
rem traitées de plus de 24 h). Ajouter --reel pour les écritures réelles.
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File "%~dp0\lancer.ps1" cli suppression
pause
