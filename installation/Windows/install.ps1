# -------------------------------------------------------------------
# Application  : gmailAgent
# Script       : install.ps1
# Version      : 1.3
# Date         : 16-11-2026
# Design       : TSC + Mistral Vibe
# Build        : Mistral Vibe
# -------------------------------------------------------------------
# Appele par install.bat (1ere installation) ou bootstrap.bat /
# recreer-venv.bat (mise a jour, venv recree). Racine du projet = 2 niveaux
# au-dessus de ce script (installation\Windows).
#   -SansPython  : ne propose pas d'installer/monter Python (utilise la version detectee)
#   -SansSecrets : ne relance pas la saisie des secrets
# Journalisation : console (etapes horodgees) + transcript dans logs\installation.log
# (logs/ est ignore par git et conserve lors des mises a jour).
param([switch]$SansPython, [switch]$SansSecrets)
$ErrorActionPreference = "Stop"

$Racine = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $Racine

New-Item -ItemType Directory -Force -Path (Join-Path $Racine "logs") | Out-Null
Start-Transcript -Path (Join-Path $Racine "logs\installation.log") -Append -ErrorAction SilentlyContinue | Out-Null
function Write-Etape([string]$msg) { Write-Host ("[{0:HH:mm:ss}] {1}" -f (Get-Date), $msg) }

try {
    Write-Etape "Racine du projet : $Racine"

    $VersionCible = [version]"3.14"   # 3.14.3 validee en conditions reelles
    $VersionMin   = [version]"3.11"   # exigence de pyproject.toml

    function Get-Python {
        $candidats = @()
        $py = Get-Command py -ErrorAction SilentlyContinue
        if ($py) { $candidats += $py.Source }
        $pyExe = Get-Command python -ErrorAction SilentlyContinue
        # Le stub "python.exe" du Microsoft Store (WindowsApps) ouvre le Store au lieu de repondre : on l'ignore
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
            throw "winget introuvable : mettre a jour 'App Installer' depuis le Microsoft Store, puis relancer."
        }
        winget install --id "Python.Python.$($VersionCible.Major).$($VersionCible.Minor)" -e --scope user `
            --accept-source-agreements --accept-package-agreements
        # Le PATH modifie par l'installeur n'est visible que dans les nouveaux processus : on le rafraichit
        $env:Path = [Environment]::GetEnvironmentVariable("Path", "User") + ";" +
                    [Environment]::GetEnvironmentVariable("Path", "Machine")
    }

    Write-Etape "Detection de Python..."
    $python = Get-Python
    if ($null -eq $python) {
        if ($SansPython) { throw "Aucun Python detecte (requis pour creer le venv) - relancer sans -SansPython." }
        Write-Etape "Aucun Python detecte : installation de Python $VersionCible via winget..."
        Install-PythonCible
        $python = Get-Python
        if ($null -eq $python) { throw "Python introuvable apres l'installation winget." }
    }
    elseif ($python.Version -lt $VersionCible) {
        if (-not $SansPython) {
            Write-Etape "Python $($python.Version) detecte ($($python.Exe)) - anterieur a la cible $VersionCible."
            $choix = Read-Host "Monter en $VersionCible [M] ou annuler l'installation [A] ?"
            if ($choix -match "^[Aa]") { Write-Etape "Installation annulee a la demande de l'utilisateur."; exit 1 }
            Install-PythonCible
            $python = Get-Python
        }
        else {
            Write-Etape "Python $($python.Version) retenu tel quel (-SansPython)."
        }
    }
    else {
        Write-Etape "Python $($python.Version) detecte ($($python.Exe)) - conforme a la cible $VersionCible, aucun changement."
    }
    if ($python.Version -lt $VersionMin) {
        throw "Python $($python.Version) insuffisant : >= $VersionMin requis (pyproject.toml)."
    }
    Write-Etape "Python retenu pour le venv : $($python.Version)"

    # Environnement virtuel + installation editable du projet (le -e est obligatoire)
    Write-Etape "Creation du venv .venv..."
    & $python.Exe -m venv .venv
    Write-Etape "Installation du package (pip install -e .) - peut prendre quelques minutes..."
    .\.venv\Scripts\pip.exe install -e .
    .\.venv\Scripts\gmailagent.exe --help   # verification (aucun secret requis pour --help)
    Write-Etape "Package installe, smoke test gmailagent --help OK."

    # Lanceurs copies a la racine du projet, sans ecraser une version existante
    $dossier = Join-Path $Racine "installation\Windows"
    foreach ($f in @("lancer.ps1","tri.bat","tri-reel.bat","tri-reel-auto.bat","suppression.bat","init-oauth.bat","recreer-venv.bat")) {
        $cible = Join-Path $Racine $f
        if (-not (Test-Path $cible)) { Copy-Item (Join-Path $dossier $f) $cible }
    }
    Write-Etape "Lanceurs copies a la racine du projet."

    # Creation de secrets.env (cles vides) ; l'utilisateur le remplit avec le Bloc-notes
    if (-not $SansSecrets) {
        Write-Etape "Creation de secrets.env (a remplir avec le Bloc-notes)..."
        powershell -ExecutionPolicy Bypass -File (Join-Path $dossier "configurer-secrets.ps1")
    }

    Write-Etape "Installation terminee."
    Write-Etape "  1) Double-clic sur init-oauth.bat   (autoriser Gmail, une seule fois)"
    Write-Etape "  2) Double-clic sur tri.bat           (premier essai en dry-run)"
    Write-Etape "  3) Double-clic sur tri-reel.bat      (ecritures reelles, petit perimetre d'abord)"
}
finally {
    Stop-Transcript -ErrorAction SilentlyContinue | Out-Null
    Write-Host "Journal de l'installation : logs\installation.log"
}
