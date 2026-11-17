# -------------------------------------------------------------------
# Application  : gmailAgent
# Script       : configurer-secrets.ps1
# Version      : 1.2
# Date         : 16-11-2026
# Design       : TSC + Mistral Vibe
# Build        : Mistral Vibe
# -------------------------------------------------------------------
# Cree le fichier secrets.env (cles vides) a la racine du projet s'il
# n'existe pas. L'utilisateur le remplit ensuite avec le Bloc-notes
# (voir le guide, section "Remplir les secrets"). secrets.env est ignore
# par git (*.env) : aucun secret dans le depot. lancer.ps1 lit ce fichier
# et injecte les valeurs dans os.environ (le pipeline ne lit que os.environ).
$ErrorActionPreference = "Stop"
$Racine = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$fichier = Join-Path $Racine "secrets.env"
if (Test-Path $fichier) {
    Write-Host "secrets.env existe deja : $fichier"
    Write-Host "Pour modifier les secrets : ouvrir ce fichier avec le Bloc-notes, mettre a jour, enregistrer."
    exit 0
}
$contenu = @"
# Secrets gmailAgent - a remplir avec le Bloc-notes, puis enregistrer (Ctrl+S).
# Format : NOM=valeur  (pas d'espace autour du =, guillemets inutiles).
# Ne jamais partager ni commiter ce fichier (ignore par git).
# Cle API Mistral (obligatoire pour chaque run) :
MISTRAL_API_KEY=
# Identifiants Google OAuth (utiles si data\gmail_token.json est absent :
# premier flux OAuth ou re-autorisation) :
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
"@
$contenu | Out-File -FilePath $fichier -Encoding utf8
Write-Host "Fichier cree : $fichier"
Write-Host "Ouvrez-le avec le Bloc-notes, remplissez les 3 valeurs, enregistrez."
Write-Host "Puis : init-oauth.bat (1er flux Gmail), tri.bat (dry-run), tri-reel.bat (reel)."
