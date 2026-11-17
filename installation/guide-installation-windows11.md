# Guide d'installation — gmailAgent sur Windows 11

- **Version** : 1.6 - **Date** : 16-11-2026 - **Branche cible** : `main`
- **Public** : utilisatrut final (non développeur). **Aucun prérequis** : ni git, ni Python installés. Tout se fait par téléchargements et double-clics.

## 0. Avant de commencer - ce qu'on vous a fourni

1. Une **clé API Mistral** (créée sur [console.mistral.ai](https://console.mistral.ai)). Le modèle utilisé par défaut est `mistral-large-latest` (voir `config/settings.yaml`) ; la variable `MISTRAL_MODEL` permet de le changer.
2. Les **identifiants Google** `GOOGLE_CLIENT_ID` et `GOOGLE_CLIENT_SECRET` (fournis par l'administrateur du projet Google Cloud : API Gmail activée, écran de consentement OAuth « En production »). Ils ne serviront qu'au premier flux d'autorisation.
3. Le compte **Gmail** à traiter.

> **Sécurité** : ne transmettez jamais ces valeurs par e-mail ou messagerie.

## 1. Télécharger le projet

Le projet se télécharge sous forme d'archive ZIP de la branche **`main`** - git n'est ni installé ni nécessaire.

**Méthode 1 - via l'interface GitHub :**

1. Ouvrir [github.com/Moanova/gmailAgent](https://github.com/Moanova/gmailAgent).
2. En haut à gauche de la liste des fichiers, le sélecteur de branche affiche **« dev »** (branche par défaut du dépôt) → cliquer dessus → onglet **« Branches »** → choisir **`main`**.
3. Bouton vert **« <> Code »** → **« Download ZIP »** : le navigateur télécharge `gmailAgent-main.zip` (~1 Mo).

**Méthode 2 - URL directe** (à copier dans la barre d'adresse du navigateur) :

```
https://github.com/Moanova/gmailAgent/archive/refs/heads/main.zip
```

**Extraction** (commun aux deux méthodes) : clic droit sur le ZIP → **« Extraire tout… »** → choisir le dossier d'installation de votre choix (par exemple `C:\Users\Public\Documents`, ou vos `Documents` personnels) → renommer le dossier extrait `gmailAgent-main` en **`gmailAgent`**.

> Notez bien l'emplacement choisi : si vous déplacez le dossier plus tard, voir §7 (`recreer-venv.bat`).

## 2. Installer en un seul geste

Double-clic sur **`installation\Windows\install.bat`** dans le dossier extrait. Le script enchaîne automatiquement :

1. **Python** : installation de la **3.14** via `winget` (natif Windows 11) s'il est absent. Si un Python est déjà présent : version ≥ 3.14 → on continue sans rien changer ; version antérieure à 3.14 → question « monter en 3.14 [M] ou annuler [A] » ; version < 3.11 → refus (incompatible avec `pyproject.toml`).
2. **Environnement virtuel** `.venv` + `pip install -e .` (installation éditable obligatoire ; quelques minutes) + vérification `gmailagent --help`.
3. **Copie des lanceurs** à la racine du dossier projet : `tri.bat`, `tri-reel.bat`, `tri-reel-auto.bat`, `suppression.bat`, `init-oauth.bat`, `recreer-venv.bat`, `lancer.ps1`.
4. **Création du fichier `secrets.env`** (clés vides) à la racine du projet — à remplir ensuite avec le Bloc-notes, voir §2bis. Fichier local ignoré par git : aucun secret dans le dépôt.

> Pourquoi des `.bat` et pas des `.ps1` en direct : la stratégie d'exécution de Windows bloque les scripts PowerShell lancés par double-clic (« exécution de scripts désactivée »). Les `.bat` passent toujours ; ils appellent PowerShell avec `-ExecutionPolicy Bypass` **pour ce seul processus**, sans modifier aucun réglage du poste.

## 3. Autoriser l'accès à Gmail - une seule fois

Double-clic sur **`init-oauth.bat`** (à la racine du dossier projet) → le navigateur s'ouvre sur le consentement Google :

1. Choisir le compte Gmail concerné.
2. Si « application non vérifiée » apparaît : « Avancé » → « Continuer vers gmailAgent (non sécurisé) » - normal pour un usage personnel.
3. Accorder la permission demandée (lecture, libellés, corbeille - scope `gmail.modify`), puis « Continuer ».

Succès quand s'affiche : `refresh_token stocké dans data\gmail_token.json`. **À partir de ce moment, les identifiants Google (`client_id`/`client_secret`) sont lus automatiquement dans ce fichier** par `lancer.ps1` : plus besoin de les saisir, y compris en cas de ré-autorisation. Le fichier `data\gmail_token.json` est confidentiel (équivalent à un mot de passe) - ne jamais le partager.

## 4. Premier essai - dry-run (aucune modification dans Gmail)

Double-clic sur **`tri.bat`**. Par défaut, gmailAgent est en **dry-run** (règle de sécurité du projet) : il lit réellement la boîte, mais n'appose aucun libellé et ne met rien à la corbeille. Le rapport s'affiche dans la fenêtre noire ; le détail est journalisé dans `logs\gmailagent.log` (ouvrable avec le Bloc-notes).

## 5. Passage en réel

- **`tri-reel.bat`** : écritures réelles (apposition des libellés `Agent/*`) - commencer sur un petit volume de messages non lus.
- **`suppression.bat`** : run de suppression T+24h en dry-run ; corbeille uniquement, sur les notifications déjà traitées de plus de 24 h - jamais de suppression définitive.

## 6. Automatisation quotidienne (optionnel)

Ouvrir le **Planificateur de tâches** (`Win + R` → `taskschd.msc`) → « Créer une tâche de base » :

- Nom : `gmailAgent - tri quotidien`
- Déclencheur : **Quotidien**, heure choisie
- Action : « Démarrer un programme » → `...\gmailAgent\tri-reel-auto.bat` (chemin complet vers votre dossier d'installation)

> `tri-reel-auto.bat` est la variante **sans `pause`**, prévue pour l'exécution automatique (un `pause` bloquerait la tâche planifiée).

## 7. Si vous déplacez le dossier du projet : `recreer-venv.bat`

L'environnement virtuel `.venv` embarque des **chemins absolus** : si vous déplacez le dossier `gmailAgent`, le venv ne fonctionne plus. Dans ce cas : double-clic sur **`recreer-venv.bat`** (à la racine du projet) - il supprime `.venv` et le recrée à la nouvelle adresse (Python et secrets déjà en place : rien n'est re-demandé).

## 8. Mises à jour

Double-clic sur **`installation\Windows\bootstrap.bat`** : il retélécharge la branche `main` et recopie le code **en conservant** `.venv`, `data` et `logs`, puis réinstalle le package (`pip install -e .`). Alternative manuelle : refaire l'étape 1 (télécharger le ZIP) et remplacer le dossier, en conservant `.venv`, `data`, `logs`.

## 9. Dépannage

| Symptôme | Solution |
| --- | --- |
| « exécution de scripts désactivée » en lançant un `.ps1` | Toujours passer par les `.bat` (ils appellent PowerShell avec `-ExecutionPolicy Bypass` pour ce seul processus) |
| `winget` introuvable | Mettre à jour « App Installer » depuis le Microsoft Store, puis relancer `install.bat` |
| Python détecté mais version < 3.14 | Répondre `M` (montée de version en 3.14) ou `A` (annulation) à la question posée |
| « Variable d'environnement MISTRAL_API_KEY requise » | Relancer `configurer-secrets.ps1` (dans `installation\Windows\`) pour re-saisir les secrets |
| Échec du téléchargement (`curl`) | Vérifier la connexion ; en entreprise, définir `HTTP_PROXY` / `HTTPS_PROXY` avant de lancer |
| Le dossier projet a été déplacé | Double-clic sur `recreer-venv.bat` (voir §7) |
| Écran Google « app non vérifiée » | Normal : « Avancé » → « Continuer vers gmailAgent (non sécurisé) » |
| Windows bloque un fichier | « Informations complémentaires » → « Exécuter quand même » |
| Poste en « mode S » | Installer Python depuis le Microsoft Store à la place de `winget` |
| Besoin de rejouer/diagnostiquer l'installation | Le déroulement est journalisé sur la console (étapes horodatées) et dans `logs\installation.log` (transcript complet) |
| Erreurs de parsing PowerShell (accents bizarres, « terminateur manquant », « jeton inattendu ») | Les `.ps1` sont livrés en UTF-8 **avec BOM** + CRLF (lu correctement par Windows PowerShell 5.1) et les `.bat` en ASCII + CRLF. Ne pas rééditer les scripts à la main (un éditeur qui perd le BOM ou repasse en LF sans BOM provoque cette erreur) : re-télécharger le ZIP de `main` |

## 10. Règles de sécurité

- Les secrets (clé Mistral, identifiants Google) vivent **chiffrés** dans le Credential Manager Windows, liés à votre compte ; aucun secret en clair dans les fichiers du projet (`.env` et `data/` sont ignorés par git).
- Ne jamais partager `data\gmail_token.json`, la clé Mistral, ni les entrées `gmailAgent` du Gestionnaire d'identifiants.
- En cas de fuite suspectée : révoquer la clé sur [console.mistral.ai](https://console.mistral.ai), révoquer l'accès dans le compte Google (Sécurité → Gestion de l'accès tiers), supprimer les entrées `gmailAgent` dans le Gestionnaire d'identifiants Windows (Panneau de configuration → Identifiants), puis relancer `init-oauth.bat`.

---

Les scripts d'installation sont dans **`installation\Windows\`** : `install.bat` (1ère installation), `bootstrap.bat` (mises à jour), `recreer-venv.bat` (après déplacement du dossier), `lancer.ps1` + `configurer-secrets.ps1` (secrets), et les lanceurs copiés à la racine du projet.

---

## Annexe B — Créer le projet Google Cloud (API Gmail) - à faire par l'administrateur, une seule fois

Cette partie se fait dans la [console Google Cloud](https://console.cloud.google.com), avec le compte Google qui hébergera l'application. **Aucune facturation n'est requise** pour l'API Gmail en usage personnel. Résultat attendu : un `client_id` et un `client_secret`, à transmettre de façon sécurisée à l'utilisateur (ils seront saisis une fois via `configurer-secrets.ps1` - jamais par e-mail ou messagerie).

1. **Créer un projet** : en haut de la console, « Sélectionner un projet » → « Nouveau projet » → nom (ex. `gmailAgent`) → « Créer ».
2. **Activer l'API Gmail** : menu « API et services » → « Bibliothèque » → rechercher « Gmail API » → « Activer ».
3. **Écran de consentement OAuth** : « Google Auth Platform » → « Écran de consentement » → type d'utilisateur **« Externe »** → « Créer » → renseigner le nom de l'application (`gmailAgent`) et l'e-mail d'assistance → enregistrer. Puis **« Publier l'application »** pour passer le statut à **« En production »**.
   - « En production » est **obligatoire** : en « Testing », seuls les utilisateurs de test peuvent se connecter et le refresh token expire après 7 jours.
   - L'écran « application non vérifiée » affiché au consentement est normal (usage < 100 utilisateurs, scope `gmail.modify`) : le contourner par « Avancé » → « Continuer vers gmailAgent (non sécurisé) ».
4. **Créer les identifiants OAuth** : « Google Auth Platform » → « Clients » → « Créer un client » → type **« Application de bureau »** → nom → « Créer ». Copier le **`client_id`** et le **`client_secret`** affichés.
5. **Scopes** : définis dans le code (`installation/init_oauth.py`) : `https://www.googleapis.com/auth/gmail.modify` uniquement (lecture, libellés, corbeille). `gmail.send` est volontairement **exclu** (moindre privilège).

Côté utilisateur, le flux d'autorisation se termine par `init-oauth.bat` → `data\gmail_token.json` (permissions 600). En « En production », le refresh token n'a **pas d'expiration calendaire** ; il est invalidé en cas de révocation, 6 mois d'inactivité, changement de mot de passe Google (scopes Gmail) ou plafond d'environ 50 tokens actifs par compte/client. Dans ce cas : supprimer `data\gmail_token.json` (`init_oauth.py` refuse de se relancer sinon) et relancer `init-oauth.bat` - les identifiants Google proviennent alors du Credential Manager (saisis à l'installation) ou de l'ancien token encore présent (lus automatiquement par `lancer.ps1`).
