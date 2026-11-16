# -------------------------------------------------------------------
# Application  : gmailAgent
# Script       : lancer.ps1
# Version      : 1.0
# Date         : 16-11-2026
# Design       : TSC + Mistral Vibe
# Build        : Mistral Vibe
# -------------------------------------------------------------------
# Lancé par les .bat (tri.bat, tri-reel.bat, ...) à la racine du projet.
# 1. Lit les secrets du Credential Manager et peuple les variables
#    d'environnement du processus (le projet ne lit que os.environ, règle D).
# 2. Si data\gmail_token.json existe, ses client_id / client_secret priment
#    sur le vault (option A : valorisation dynamique depuis le token).
# 3. Exécute gmailagent (mode cli) ou scripts\init_oauth.py (mode oauth).
# Usage : lancer.ps1 [-Mode cli|oauth] [args...]
param(
    [string]$Mode = "cli",
    [Parameter(ValueFromRemainingArguments=$true)][string[]]$Args
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# 1. Secrets depuis le Credential Manager
[Windows.Security.Credentials.PasswordVault,Windows.Security.Credentials,ContentType=WindowsRuntime] | Out-Null
$vault = New-Object Windows.Security.Credentials.PasswordVault
foreach ($nom in @("MISTRAL_API_KEY","GOOGLE_CLIENT_ID","GOOGLE_CLIENT_SECRET")) {
    try {
        $c = $vault.Retrieve("gmailAgent", $nom); $c.RetrievePassword()
        [Environment]::SetEnvironmentVariable($nom, $c.Password, "Process")
    } catch { Write-Warning "$nom absent du Credential Manager — relancer configurer-secrets.ps1" }
}

# 2. Option A : le token Gmail existant prime pour les identifiants Google
$token = Join-Path $PSScriptRoot "data\gmail_token.json"
if (Test-Path $token) {
    $t = Get-Content $token -Raw | ConvertFrom-Json
    if ($t.client_id)     { [Environment]::SetEnvironmentVariable("GOOGLE_CLIENT_ID",     $t.client_id,     "Process") }
    if ($t.client_secret) { [Environment]::SetEnvironmentVariable("GOOGLE_CLIENT_SECRET", $t.client_secret, "Process") }
}

# 3. Exécution
if ($Mode -eq "oauth") {
    & (Join-Path $PSScriptRoot ".venv\Scripts\python.exe") (Join-Path $PSScriptRoot "scripts\init_oauth.py")
} else {
    & (Join-Path $PSScriptRoot ".venv\Scripts\gmailagent.exe") @Args
}
exit $LASTEXITCODE
