# -------------------------------------------------------------------
# Application  : gmailAgent
# Script       : install.ps1
# Version      : 1.0
# Date         : 16-11-2026
# Design       : TSC + Mistral Vibe
# Build        : Mistral Vibe
# -------------------------------------------------------------------
# Appelé par bootstrap.bat. Racine du projet = 2 niveaux au-dessus de ce
# script (installation\Windows). Installe Python (cible 3.14, min 3.11) via
# winget si besoin, crée le venv, installe le package en éditable, copie les
# lanceurs à la racine du projet, puis lance la saisie des secrets.
$ErrorActionPreference = "Stop"
$Racine = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $Racine
Write-Host "Racine du projet : $Racine"

$VersionCible = [version]"3.14"   # 3.14.3 validée en conditions réelles
$VersionMin   = [version]"3.11"   # exigence de pyproject.toml

function Get-Python {
    $candidats = @()
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) { $candidats += $py.Source }
    $pyExe = Get-Command python -ErrorAction SilentlyContinue
    # Le stub "python.exe" du Microsoft Store (WindowsApps) ouvre le Store au lieu de répondre : on l'ignore
    if ($pyExe -and $pyExe.Source -notlike "*\Microsoft\WindowsApps\*") { $candidats += $pyExe.Source }
    foreach ($exe in $candidats) {
        try {
            $out = & $exe --version 2>&1 | Out-String
            if ($out -match "Python (\d+)\.(\d+)\.(\d+)") {
                return @{ Exe = $exe; Version = [version]"$($Matches[1]).$($Matches[2]).$($Matches[3])" }
            }
        } catch { }
    }
    return $null
}

function Install-PythonCible {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "winget introuvable : mettre à jour 'App Installer' depuis le Microsoft Store, puis relancer."
    }
    winget install --id "Python.Python.$($VersionCible.Major).$($VersionCible.Minor)" -e --scope user `
        --accept-source-agreements --accept-package-agreements
    # Le PATH modifié par l'installeur n'est visible que dans les nouveaux processus : on le rafraîchit
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "User") + ";" +
                [Environment]::GetEnvironmentVariable("Path", "Machine")
}

$python = Get-Python
if ($null -eq $python) {
    Write-Host "Aucun Python détecté : installation de Python $VersionCible via winget..."
    Install-PythonCible
    $python = Get-Python
    if ($null -eq $python) { throw "Python introuvable après l'installation winget." }
}
elseif ($python.Version -lt $VersionCible) {
    Write-Host "Python $($python.Version) détecté ($($python.Exe)) — antérieur à la cible $VersionCible."
    $choix = Read-Host "Monter en $VersionCible [M] ou annuler l'installation [A] ?"
    if ($choix -match "^[Aa]") { Write-Host "Installation annulée à la demande de l'utilisateur."; exit 1 }
    Install-PythonCible
    $python = Get-Python
}
else {
    Write-Host "Python $($python.Version) détecté ($($python.Exe)) — conforme à la cible $VersionCible, aucun changement."
}
if ($python.Version -lt $VersionMin) {
    throw "Python $($python.Version) insuffisant : >= $VersionMin requis (pyproject.toml)."
}
Write-Host "Python retenu pour le venv : $($python.Version)"

# Environnement virtuel + installation éditable du projet (le -e est obligatoire)
& $python.Exe -m venv .venv
.\.venv\Scripts\pip.exe install -e .
.\.venv\Scripts\gmailagent.exe --help   # vérification (aucun secret requis pour --help)

# Lanceurs copiés à la racine du projet, sans écraser une version existante
$dossier = Join-Path $Racine "installation\Windows"
foreach ($f in @("lancer.ps1","tri.bat","tri-reel.bat","tri-reel-auto.bat","suppression.bat","init-oauth.bat")) {
    $cible = Join-Path $Racine $f
    if (-not (Test-Path $cible)) { Copy-Item (Join-Path $dossier $f) $cible }
}

# Saisie unique des secrets -> Credential Manager Windows (chiffré, lié au compte)
powershell -ExecutionPolicy Bypass -File (Join-Path $dossier "configurer-secrets.ps1")

Write-Host "Installation terminée."
Write-Host "  1) Double-clic sur init-oauth.bat   (autoriser Gmail, une seule fois)"
Write-Host "  2) Double-clic sur tri.bat           (premier essai en dry-run)"
Write-Host "  3) Double-clic sur tri-reel.bat      (écritures réelles, petit périmètre d'abord)"
