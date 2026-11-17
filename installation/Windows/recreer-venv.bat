@echo off
rem -------------------------------------------------------------------
rem Application  : gmailAgent
rem Script       : recreer-venv.bat
rem Version      : 1.0
rem Date         : 16-11-2026
rem Design       : TSC + Mistral Vibe
rem Build        : Mistral Vibe
rem -------------------------------------------------------------------
rem Recree l'environnement virtuel (.venv) : a utiliser si le dossier du
rem projet a ete DEPLACE (le venv embarque des chemins absolus et casserait).
rem Double-clic sur le recreer-venv.bat situe a la racine du projet.
rem Python et secrets deja en place : rien n'est re-demande.
set "RACINE=%~dp0"
if not exist "%~dp0\pyproject.toml" set "RACINE=%~dp0..\.."
cd /d "%RACINE%"
if exist ".venv" rmdir /s /q ".venv"
echo Recreation du venv dans "%CD%"...
powershell -ExecutionPolicy Bypass -File "%RACINE%\installation\Windows\install.ps1" -SansPython -SansSecrets
pause
