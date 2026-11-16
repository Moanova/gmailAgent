@echo off
rem -------------------------------------------------------------------
rem Application  : gmailAgent
rem Script       : bootstrap.bat
rem Version      : 1.0
rem Date         : 16-11-2026
rem Design       : TSC + Mistral Vibe
rem Build        : Mistral Vibe
rem -------------------------------------------------------------------
rem Récupère la branche BRANCHE de gmailAgent depuis GitHub (archive ZIP,
rem sans git installé), installe le projet dans le dossier DEST, puis lance
rem installation\Windows\install.ps1 (Python + venv + dépendances + secrets).
rem Premier lancement : copier ce fichier (Bloc-notes, type "Tous les fichiers")
rem n'importe où (ex. Bureau) puis double-cliquer. Mises à jour : relancer le
rem bootstrap.bat du dépôt.
setlocal
set "BRANCHE=main"
set "URL=https://github.com/Moanova/gmailAgent/archive/refs/heads/%BRANCHE%.zip"
set "ZIP=%TEMP%\gmailAgent-%BRANCHE%.zip"
set "TMP=%TEMP%\gmailAgent-extract"

rem Destination : C:\Users\Public\Documents si accessible en écriture, sinon Documents perso
set "DEST="
echo x > "C:\Users\Public\Documents\.ga_test" 2>nul
if exist "C:\Users\Public\Documents\.ga_test" (
  del "C:\Users\Public\Documents\.ga_test"
  set "DEST=C:\Users\Public\Documents\gmailAgent"
) else (
  set "DEST=%USERPROFILE%\Documents\gmailAgent"
)
echo Dossier d'installation : "%DEST%"

echo [1/4] Téléchargement de la branche %BRANCHE% depuis GitHub...
curl -L --fail -o "%ZIP%" "%URL%" || (echo ERREUR : téléchargement impossible (connexion, proxy ?) && pause & exit /b 1)

echo [2/4] Extraction...
rmdir /s /q "%TMP%" 2>nul
mkdir "%TMP%"
tar -xf "%ZIP%" -C "%TMP%" || (echo ERREUR : extraction du ZIP && pause & exit /b 1)
for /d %%D in ("%TMP%\*") do set "SRC=%%D"
if not exist "%SRC%\pyproject.toml" (echo ERREUR : archive invalide (pyproject.toml absent) && pause & exit /b 1)

echo [3/4] Installation dans "%DEST%"...
if exist "%DEST%" (
  rem Mise à jour : on conserve le venv, les données, les logs et les lanceurs personnels
  if exist "%DEST%.old" rmdir /s /q "%DEST%.old"
  move "%DEST%" "%DEST%.old" >nul
  move "%SRC%" "%DEST%"
  if exist "%DEST%.old\.venv" move "%DEST%.old\.venv" "%DEST%\" >nul
  if exist "%DEST%.old\data"  move "%DEST%.old\data"  "%DEST%\" >nul
  if exist "%DEST%.old\logs"  move "%DEST%.old\logs"  "%DEST%\" >nul
  for %%F in ("%DEST%.old\*.bat") do move "%%F" "%DEST%\" >nul
  for %%F in ("%DEST%.old\*.ps1") do move "%%F" "%DEST%\" >nul
  rmdir /s /q "%DEST%.old"
  echo Mise à jour effectuée (.venv, data, logs et lanceurs conservés).
) else (
  move "%SRC%" "%DEST%"
  echo Projet installé dans "%DEST%".
)

echo [4/4] Installation (Python, venv, dépendances, lanceurs, secrets)...
powershell -ExecutionPolicy Bypass -File "%DEST%\installation\Windows\install.ps1"
pause
