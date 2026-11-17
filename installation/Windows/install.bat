@echo off
rem -------------------------------------------------------------------
rem Application  : gmailAgent
rem Script       : install.bat
rem Version      : 1.0
rem Date         : 16-11-2026
rem Design       : TSC + Mistral Vibe
rem Build        : Mistral Vibe
rem -------------------------------------------------------------------
rem Point d'entree de l'installation, a lancer APRES avoir telecharge et
rem extrait le ZIP du depot (voir le guide) : installe Python si besoin,
rem cree le venv, installe le package en editable, copie les lanceurs a la
rem racine du projet, puis saisit les secrets (Credential Manager).
rem Double-cliquer sur ce fichier dans installation\Windows\.
rem Ce script n'existant que dans installation\Windows, la racine du projet
rem est toujours deux niveaux au-dessus.
powershell -ExecutionPolicy Bypass -File "%~dp0install.ps1"
pause
