# Guide d'installation — gmailAgent sur Windows 11 (poste neuf)

- **Version** : 1.0 — **Date** : 16-11-2026 — **Branche cible** : `main`
- **Public** : utilisatrice non technique. **Objectif** : installer et faire tourner gmailAgent sans compétence technique, sans git, sans Python préinstallé.

## 0. Avant de commencer — ce qu'on vous a fourni

1. Une **clé API Mistral** (créée sur [console.mistral.ai](https://console.mistral.ai)). Le modèle utilisé par défaut est `mistral-large-latest` (voir `config/settings.yaml`) ; la variable `MISTRAL_MODEL` permet de le changer.
2. Les **identifiants Google** `GOOGLE_CLIENT_ID` et `GOOGLE_CLIENT_SECRET` (fournis par l'administrateur du projet Google Cloud : API Gmail activée, écran de consentement OAuth « En production »). Ils ne serviront qu'au premier flux d'autorisation.
3. Le compte **Gmail** à traiter.

> **Sécurité** : ne transmettez jamais ces valeurs par e-mail ou messagerie.

## 1. Tout installer en un seul geste

Tous les scripts d'installation vivent dans le dépôt, dossier **`installation\Windows\`**. Pour le tout premier lancement (le dépôt n'étant pas encore sur le poste), copiez le contenu de **l'annexe A** dans un fichier `bootstrap.bat` (Bloc-notes → « Enregistrer sous… » → type **« Tous les fichiers (*.*) »**, sinon le fichier s'appellera `bootstrap.bat.txt` et ne fonctionnera pas), placé par exemple sur le Bureau, puis **double-cliquez** dessus.

Le script enchaîne automatiquement :

1. **Choix du dossier d'installation** : `C:\Users\Public\Documents\gmailAgent` s'il est accessible en écriture, sinon `Documents\gmailAgent` de l'utilisateur courant.
2. **Téléchargement de la branche `main` depuis GitHub** (archive ZIP, ~1 Mo — git n'est ni installé ni nécessaire ; `curl` et `tar` sont natifs à Windows 11).
3. **Python** : installation de la **3.14** via `winget` (natif Windows 11) s'il est absent. Si un Python est déjà présent : version ≥ 3.14 → on continue sans rien changer ; version antérieure à 3.14 → question « monter en 3.14 [M] ou annuler [A] » ; version < 3.11 → refus (incompatible avec `pyproject.toml`).
4. **Environnement virtuel** `.venv` + `pip install -e .` (installation éditable obligatoire ; quelques minutes) + vérification `gmailagent --help`.
5. **Copie des lanceurs** à la racine du dossier d'installation : `tri.bat`, `tri-reel.bat`, `tri-reel-auto.bat`, `suppression.bat`, `init-oauth.bat`, `lancer.ps1` (sans écraser une version existante).
6. **Saisie des 3 secrets** (affichage masqué), stockés **chiffrés dans le Credential Manager Windows** et liés à votre compte. Aucun secret n'est écrit en clair dans un fichier du projet.

> Pourquoi des `.bat` et pas des `.ps1` en direct : la stratégie d'exécution de Windows bloque les scripts PowerShell lancés par double-clic (« exécution de scripts désactivée »). Les `.bat` passent toujours ; ils appellent PowerShell avec `-ExecutionPolicy Bypass` **pour ce seul processus**, sans modifier aucun réglage du poste.

## 2. Autoriser l'accès à Gmail — une seule fois

Double-clic sur **`init-oauth.bat`** (à la racine du dossier d'installation) → le navigateur s'ouvre sur le consentement Google :

1. Choisir le compte Gmail concerné.
2. Si « application non vérifiée » apparaît : « Avancé » → « Continuer vers gmailAgent (non sécurisé) » — normal pour un usage personnel.
3. Accorder la permission demandée (lecture, libellés, corbeille — scope `gmail.modify`), puis « Continuer ».

Succès quand s'affiche : `refresh_token stocké dans data\gmail_token.json`. **À partir de ce moment, les identifiants Google (`client_id`/`client_secret`) sont lus automatiquement dans ce fichier** par `lancer.ps1` : plus besoin de les saisir, y compris en cas de ré-autorisation. Le fichier `data\gmail_token.json` est confidentiel (équivalent à un mot de passe) — ne jamais le partager.

## 3. Premier essai — dry-run (aucune modification dans Gmail)

Double-clic sur **`tri.bat`**. Par défaut, gmailAgent est en **dry-run** (règle de sécurité du projet) : il lit réellement la boîte, mais n'appose aucun libellé et ne met rien à la corbeille. Le rapport s'affiche dans la fenêtre noire ; le détail est journalisé dans `logs\gmailagent.log` (ouvrable avec le Bloc-notes).

## 4. Passage en réel

- **`tri-reel.bat`** : écritures réelles (apposition des libellés `Agent/*`) — commencer sur un petit volume de messages non lus.
- **`suppression.bat`** : run de suppression T+24h en dry-run ; corbeille uniquement, sur les notifications déjà traitées de plus de 24 h — jamais de suppression définitive.

## 5. Automatisation quotidienne (optionnel)

Ouvrir le **Planificateur de tâches** (`Win + R` → `taskschd.msc`) → « Créer une tâche de base » :

- Nom : `gmailAgent - tri quotidien`
- Déclencheur : **Quotidien**, heure choisie
- Action : « Démarrer un programme » → `...\gmailAgent\tri-reel-auto.bat` (chemin complet vers le dossier d'installation)

> `tri-reel-auto.bat` est la variante **sans `pause`**, prévue pour l'exécution automatique (un `pause` bloquerait la tâche planifiée).

## 6. Mises à jour

Reprendre le `bootstrap.bat` du dépôt (`installation\Windows\bootstrap.bat`) et double-cliquer : il retélécharge la branche `main` et remplace le code **en conservant** `.venv`, `data`, `logs` et vos lanceurs personnels (`*.bat`, `*.ps1` à la racine). Si `pyproject.toml` a changé, relancer ensuite dans un terminal du dossier : `.\.venv\Scripts\pip.exe install -e .`

## 7. Dépannage

| Symptôme | Solution |
| --- | --- |
| « exécution de scripts désactivée » en lançant un `.ps1` | Toujours passer par les `.bat` (ils appellent PowerShell avec `-ExecutionPolicy Bypass` pour ce seul processus) |
| `winget` introuvable | Mettre à jour « App Installer » depuis le Microsoft Store, puis relancer `bootstrap.bat` |
| Python détecté mais version < 3.14 | Répondre `M` (montée de version en 3.14) ou `A` (annulation) à la question posée |
| « Variable d'environnement MISTRAL_API_KEY requise » | Relancer `configurer-secrets.ps1` (à la racine du projet) pour re-saisir les secrets |
| Échec du téléchargement (`curl`) | Vérifier la connexion ; en entreprise, définir `HTTP_PROXY` / `HTTPS_PROXY` avant de lancer |
| Le dossier projet a été déplacé | Supprimer `.venv` et relancer `bootstrap.bat` (le venv embarque des chemins absolus) |
| Écran Google « app non vérifiée » | Normal : « Avancé » → « Continuer vers gmailAgent (non sécurisé) » |
| Windows bloque un fichier | « Informations complémentaires » → « Exécuter quand même » |
| Poste en « mode S » | Installer Python depuis le Microsoft Store à la place de `winget` |

## 8. Règles de sécurité

- Les secrets (clé Mistral, identifiants Google) vivent **chiffrés** dans le Credential Manager Windows, liés à votre compte ; aucun secret en clair dans les fichiers du projet (`.env` et `data/` sont ignorés par git).
- Ne jamais partager `data\gmail_token.json`, la clé Mistral, ni les entrées `gmailAgent` du Gestionnaire d'identifiants.
- En cas de fuite suspectée : révoquer la clé sur [console.mistral.ai](https://console.mistral.ai), révoquer l'accès dans le compte Google (Sécurité → Gestion de l'accès tiers), supprimer les entrées `gmailAgent` dans le Gestionnaire d'identifiants Windows (Panneau de configuration → Identifiants), puis relancer `init-oauth.bat`.

## Annexe A — `bootstrap.bat` (à copier-coller pour le tout premier lancement)

```bat
@echo off
setlocal
set "BRANCHE=main"
set "URL=https://github.com/Moanova/gmailAgent/archive/refs/heads/%BRANCHE%.zip"
set "ZIP=%TEMP%\gmailAgent-%BRANCHE%.zip"
set "TMP=%TEMP%\gmailAgent-extract"
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
curl -L --fail -o "%ZIP%" "%URL%" || (echo ERREUR : téléchargement impossible && pause & exit /b 1)
echo [2/4] Extraction...
rmdir /s /q "%TMP%" 2>nul
mkdir "%TMP%"
tar -xf "%ZIP%" -C "%TMP%" || (echo ERREUR : extraction du ZIP && pause & exit /b 1)
for /d %%D in ("%TMP%\*") do set "SRC=%%D"
if not exist "%SRC%\pyproject.toml" (echo ERREUR : archive invalide && pause & exit /b 1)
echo [3/4] Installation dans "%DEST%"...
if exist "%DEST%" (
  if exist "%DEST%.old" rmdir /s /q "%DEST%.old"
  move "%DEST%" "%DEST%.old" >nul
  move "%SRC%" "%DEST%"
  if exist "%DEST%.old\.venv" move "%DEST%.old\.venv" "%DEST%\" >nul
  if exist "%DEST%.old\data"  move "%DEST%.old\data"  "%DEST%\" >nul
  if exist "%DEST%.old\logs"  move "%DEST%.old\logs"  "%DEST%\" >nul
  for %%F in ("%DEST%.old\*.bat") do move "%%F" "%DEST%\" >nul
  for %%F in ("%DEST%.old\*.ps1") do move "%%F" "%DEST%\" >nul
  rmdir /s /q "%DEST%.old"
  echo Mise à jour effectuée.
) else (
  move "%SRC%" "%DEST%"
  echo Projet installé dans "%DEST%".
)
echo [4/4] Installation (Python, venv, dépendances, lanceurs, secrets)...
powershell -ExecutionPolicy Bypass -File "%DEST%\installation\Windows\install.ps1"
pause
```

Les autres scripts (`install.ps1`, `configurer-secrets.ps1`, `lancer.ps1`, `tri.bat`, `tri-reel.bat`, `tri-reel-auto.bat`, `suppression.bat`, `init-oauth.bat`) sont dans **`installation\Windows\`** du dépôt.
