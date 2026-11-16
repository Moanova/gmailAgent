# -------------------------------------------------------------------
# Application  : gmailAgent
# Script       : configurer-secrets.ps1
# Version      : 1.0
# Date         : 16-11-2026
# Design       : TSC + Mistral Vibe
# Build        : Mistral Vibe
# -------------------------------------------------------------------
# Saisie unique (masquée) des secrets, stockés chiffrés dans le Credential
# Manager Windows (PasswordVault, lié au compte). Le projet ne lit que
# os.environ (règle D) : lancer.ps1 peuple ces variables au lancement.
# GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET ne servent que si
# data\gmail_token.json est absent (1er flux OAuth / ré-autorisation) ;
# ensuite, lancer.ps1 les lit directement dans le token.
[Windows.Security.Credentials.PasswordVault,Windows.Security.Credentials,ContentType=WindowsRuntime] | Out-Null
$vault = New-Object Windows.Security.Credentials.PasswordVault
foreach ($nom in @("MISTRAL_API_KEY","GOOGLE_CLIENT_ID","GOOGLE_CLIENT_SECRET")) {
    $sec = Read-Host "Valeur de $nom (affichage masqué)" -AsSecureString
    $clair = [Runtime.InteropServices.Marshal]::PtrToStringBSTR(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec))
    try { $vault.Remove("gmailAgent", $nom) } catch { }
    $vault.Add((New-Object Windows.Security.Credentials.PasswordCredential("gmailAgent", $nom, $clair)))
    Write-Host "$nom enregistré dans le Credential Manager."
}
Write-Host "Terminé. Ne transmettez jamais ces valeurs (e-mail, messagerie, fichier partagé)."
