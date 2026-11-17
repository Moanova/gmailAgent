# -------------------------------------------------------------------
# Application  : gmailAgent
# Script       : lancer.ps1
# Version      : 1.2
# Date         : 16-11-2026
# Design       : TSC + Mistral Vibe
# Build        : Mistral Vibe
# -------------------------------------------------------------------
# Lance par les .bat (tri.bat, tri-reel.bat, ...) a la racine du projet.
# 1. Lit secrets.env (fichier local, ignore par git) et peuple les
#    variables d'environnement du processus (le projet ne lit que os.environ).
# 2. Si data\gmail_token.json existe, ses client_id / client_secret priment
#    (option A : valorisation dynamique depuis le token).
# 3. Execute gmailagent (mode cli) ou installation\init_oauth.py (mode oauth).
# Usage : lancer.ps1 [-Mode cli|oauth] [args...]
param(
    [string]$Mode = "cli",
    [Parameter(ValueFromRemainingArguments=$true)][string[]]$Args
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# 1. Secrets depuis secrets.env -> variables d'environnement du processus
$fichierSecrets = Join-Path $PSScriptRoot "secrets.env"
if (Test-Path $fichierSecrets) {
    foreach ($ligne in Get-Content $fichierSecrets) {
        $l = $ligne.Trim()
        if ($l -and -not $l.StartsWith("#") -and $l -match "^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$") {
            [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2].Trim(), "Process")
        }
    }
} else {
    Write-Warning "secrets.env introuvable - lancer installation\Windows\configurer-secrets.ps1, puis remplir le fichier avec le Bloc-notes"
}

# 2. Option A : le token Gmail existant prime pour les identifiants Google
$token = Join-Path $PSScriptRoot "data\gmail_token.json"
if (Test-Path $token) {
    $t = Get-Content $token -Raw | ConvertFrom-Json
    if ($t.client_id)     { [Environment]::SetEnvironmentVariable("GOOGLE_CLIENT_ID",     $t.client_id,     "Process") }
    if ($t.client_secret) { [Environment]::SetEnvironmentVariable("GOOGLE_CLIENT_SECRET", $t.client_secret, "Process") }
}

# 3. Execution
if ($Mode -eq "oauth") {
    & (Join-Path $PSScriptRoot ".venv\Scripts\python.exe") (Join-Path $PSScriptRoot "installation\init_oauth.py")
} else {
    & (Join-Path $PSScriptRoot ".venv\Scripts\gmailagent.exe") @Args
}
exit $LASTEXITCODE
