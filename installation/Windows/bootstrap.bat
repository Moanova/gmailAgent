@echo off
rem -------------------------------------------------------------------
rem Application  : gmailAgent
rem Script       : bootstrap.bat
rem Version      : 1.1
rem Date         : 16-11-2026
rem Design       : TSC + Mistral Vibe
rem Build        : Mistral Vibe
rem -------------------------------------------------------------------
rem MISE À JOUR du projet (branche BRANCHE) sans git : télécharge l'archive
rem ZIP depuis GitHub et recopie le code sur le dossier projet (racine =
rem 2 niveaux au-dessus de ce script), en conservant .venv, data et logs.
rem À lancer depuis installation\Windows\ du projet déjà installé.
rem Le premier téléchargement se fait manuellement (voir le guide / README).
setlocal
set "BRANCHE=main"
if not "%~1"=="" goto :suite
rem Premier passage : on se relance depuis %TEMP% (le dossier projet va être modifié en place)
copy "%~f0" "%TEMP%\ga-bootstrap.bat" >nul
"%TEMP%\ga-bootstrap.bat" "%~dp0..\.."
exit /b
:suite
set "PROJET=%~1"
cd /d "%PROJET%" || (echo ERREUR : dossier projet introuvable : "%PROJET%" && pause & exit /b 1)
set "URL=https://github.com/Moanova/gmailAgent/archive/refs/heads/%BRANCHE%.zip"
set "ZIP=%TEMP%\gmailAgent-%BRANCHE%.zip"
set "TMP=%TEMP%\gmailAgent-extract"
echo [1/3] Téléchargement de la branche %BRANCHE% depuis GitHub...
curl -L --fail -o "%ZIP%" "%URL%" || (echo ERREUR : téléchargement impossible (connexion, proxy ?) && pause & exit /b 1)
echo [2/3] Extraction...
rmdir /s /q "%TMP%" 2>nul
mkdir "%TMP%"
tar -xf "%ZIP%" -C "%TMP%" || (echo ERREUR : extraction du ZIP && pause & exit /b 1)
for /d %%D in ("%TMP%\*") do set "SRC=%%D"
if not exist "%SRC%\pyproject.toml" (echo ERREUR : archive invalide (pyproject.toml absent) && pause & exit /b 1)
echo [3/3] Mise à jour du code dans "%CD%" (.venv, data, logs conservés)...
robocopy "%SRC%" "%CD%" /E /XD .venv data logs /NFL /NDL /NJH /NJS >nul
if %errorlevel% GTR 7 (echo ERREUR : copie du code (robocopy) && pause & exit /b 1)
echo Code mis à jour.
rem Réinstallation éditable (pyproject.toml peut avoir changé) + lanceurs à jour
powershell -ExecutionPolicy Bypass -File "%CD%\installation\Windows\install.ps1" -SansPython -SansSecrets
pause
