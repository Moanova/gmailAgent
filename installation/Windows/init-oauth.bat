@echo off
rem -------------------------------------------------------------------
rem Application  : gmailAgent
rem Script       : init-oauth.bat
rem Version      : 1.0
rem Date         : 16-11-2026
rem Design       : TSC + Mistral Vibe
rem Build        : Mistral Vibe
rem -------------------------------------------------------------------
rem Premier flux OAuth Gmail (UNE SEULE FOIS) : ouvre le consentement Google
rem dans le navigateur et ecrit data\gmail_token.json (permissions 600).
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File "%~dp0\lancer.ps1" oauth
pause
