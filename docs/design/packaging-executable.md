# Étude — packaging en exécutable autonome du service de tri (T10.1, v2 volet 1)

> **Statut (13/11/2026)** : étude réalisée en séance (tâche T10.1, phase 10). Aucune
> implémentation en v1 — la v1 reste l'installation éditable (`pip install -e .`) + cron local.
> S'inscrit dans la **v2 à deux matérialisations** envisagée en D66 : (1) **exécutable autonome**
> sur poste de travail (cette note), (2) application déployée sur **Mistral Studio** (base :
> [conception-studio-apps.md](conception-studio-apps.md), conservé D63).
>
> **Statut (13/11/2026, fin de séance, D70)** : la décision de retenir la v2 (D69) est
> **suspendue** — à réévaluer, la piste paraît trop lourde pour le besoin. La v1 (CLI + cron local)
> reste la version de production. Cette note reste la base de l'étude si la v2 est relancée.

## 1. Objectif et périmètre (volet 1)

Produire un binaire utilisable sur un **poste Windows sans Python préinstallé** (utilisateur non
développeur), l'outil CLI étant lancé par **cron/timer** (run de tri périodique, run de
suppression T+24h D47). Hors périmètre : installeur « produit » avec auto-update, version GUI.

## 2. Fonctionnement de PyInstaller (précision utile)

- **Le build est unique** : la commande `pyinstaller …` analyse le graphe d'imports, collecte le
  bytecode, les bibliothèques natives et les données (via les hooks), et produit `dist/` **une
  fois pour toutes**. L'exécutable n'est **pas régénéré à chaque lancement**.
- **Mode `--onefile`** : un seul `.exe`, mais son bootloader **extrait le payload vers `%TEMP%` à
  chaque lancement** avant d'exécuter — c'est un coût de démarrage récurrent (défavorable pour un
  cron), pas une régénération du binaire.
- **Mode `--onedir`** : un dossier (exe + DLL + données) ; **aucune extraction au lancement**, donc
  démarrage rapide ; à distribuer sous forme de zip/dossier ou via un installeur.
- Les hooks `pyinstaller-hooks-contrib` couvrent `pydantic` et `googleapiclient` (métadonnées via
  `copy_metadata` + documents discovery JSON embarqués de la v2).

## 3. Options comparées (état 2026)

| Outil | Principe | Points forts | Points faibles |
| --- | --- | --- | --- |
| **PyInstaller** 6.22.x (onefile / onedir) | Interpréteur CPython gelé + bytecode + natifs | Standard de facto ; hooks prêts (pydantic, googleapiclient) ; build simple et reproductible | onefile = extraction à chaque run ; binaire volumineux ; faux positifs AV (bootloader connu) ; pas de signature intégrée |
| **Nuitka** 4.x | Compilation Python → C → binaire natif | Démarrage ~0,06–0,08 s ; exécution 2–4× plus rapide ; binaire natif « propre » | Build 5–15 min avec compilateur C (MSVC/MinGW) ; `--include-package`/anti-bloat requis ; licence Apache 2.0 (+ option commerciale) |
| **cx_Freeze** 8.x | Même mécanisme que PyInstaller, config déclarative | Léger ; démarrage onedir ~0,5 s | Communauté plus petite ; inclusions manuelles ; macOS M1 capricieux |
| **Briefcase** (BeeWare) | Installeur natif (MSI/WiX sous Windows, DMG, AppImage) + auto-update | Vrai installeur, icône, mise à jour ; **gratuit et open-source (licence BSD)** — pertinent pour un projet GUI | Surdimensionné pour un CLI ; config plus lourde |
| **PyOxidizer** | Interpréteur embarqué (Rust) | Contrôle total du binaire | Projet en maintenance ralentie — écarté |
| **zipapp / shiv / pex + python-build-standalone (`uv`)** | Archive + interpréteur autonome distribué | Un seul fichier, rapide à produire | Ne répond pas seul à « sans Python » (il faut embarquer l'interpréteur, ~50 Mo) — piste « arborescence + venv + `.bat` » déjà documentée |

## 4. Contraintes propres au projet

- **Dépendances lourdes** : `google-api-python-client` v2 embarque 200+ documents discovery (+50 Mo),
  plus `pydantic` (pydantic-core compilé), `mistralai`, `httpx`, `structlog`, `pyyaml`, `google-auth`
  → bundle volumineux quel que soit l'outil.
- **Cron/timer** → démarrages fréquents et courts : le **démarrage rapide est prioritaire** → écarter
  `--onefile` pour l'usage cron.
- **Point dur** : `RACINE_PROJET = Path(__file__).resolve().parents[2]` (`src/gmailagent/core_config.py`)
  résout `config/`, `data/`, `logs/` relativement au fichier source — absent d'un binaire figé.
  **À recoder** : résolution depuis le répertoire de l'exécutable (ou cwd), avec tests ; `config/`
  (labels.yaml + settings.yaml) **externe et éditable à côté du binaire**, défauts embarqués en repli.
- **Invariants à préserver** : secrets via `os.environ` uniquement (règle D — jamais embarqués) ;
  token OAuth Gmail dans `data/` hors binaire (permissions 600) ; dry-run par défaut (règle E) ;
  idempotence par libellés ; corbeille uniquement (`TRASH`).
- **Entrées** : `gmailagent.cli:main` + `__main__.py` ; lanceur `.bat` pour le cron.
- **Windows** : SmartScreen sur exe non signé (prévoir une signature de code si distribution au-delà
  d'un usage perso) ; faux positifs AV sur le bootloader PyInstaller (mitigations : onedir, rebuild
  du bootloader, soumission aux éditeurs AV).
- **Build reproductible** : venv propre, dépendances épinglées, script de build dans le groupe `dev`,
  test sur un poste Windows « nu ».

## 5. Recommandation

**PyInstaller en mode `onedir`** + config externe à côté du binaire + lanceur `.bat` : meilleur
compromis (hooks prêts pour les dépendances, démarrage rapide, dossier patchable, taille
maîtrisée). **Nuitka** en alternative si le temps de démarrage devient critique (build plus lourd).
**Briefcase** réservé à une distribution « produit » avec MSI et auto-update (gratuit, BSD — utile
pour un projet GUI). `onefile` écarté pour un usage cron. PyOxidizer écarté (maintenance ralentie).

## 6. Plan de réalisation si la v2 est retenue

1. Recoder la résolution des chemins (`RACINE_PROJET` → répertoire de l'exe / cwd ; config externe
   avec repli sur les défauts embarqués) + tests unitaires dédiés.
2. Script de build (groupe `dev`) + fichier `.spec` PyInstaller (entrée `gmailagent.cli:main`,
   hidden-imports `googleapiclient`/`pydantic`, datas = `config/` par défaut).
3. Build `onedir`, smoke sur poste Windows nu : `--help`, `tri` en dry-run, `suppression` en
   dry-run.
4. Lanceur `.bat` + doc d'installation (variables d'environnement `MISTRAL_API_KEY`,
   `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` ; provisioning du token via `scripts/init_oauth.py`).
5. Validation : rejouer TU/TI (aucun changement fonctionnel attendu), dry-run réel puis petit
   périmètre `--reel` (règle E).

## 7. Risques

- Taille du bundle (google-api-python-client) ; AV / SmartScreen ; chemins cassés (point dur) ;
  token OAuth à provisionner sur le poste cible ; pas d'auto-update en onedir (remplacement manuel
  du dossier).

## 8. Plan détaillé PyInstaller (ajout séance du 13/11/2026)

### 8.1 Prérequis
- Build **sur Windows** (PyInstaller ne cross-compile pas) : poste de dev ou runner Windows.
- venv propre : `pip install -e ".[dev]"` + `pyinstaller` ajouté au groupe `dev` de `pyproject.toml`
  (dépendance de build, jamais en runtime).

### 8.2 Étapes de build
1. **Script d'entrée** `scripts/pyinstaller_entry.py` (PyInstaller prend un script, pas un point
   d'entrée pyproject) : `from gmailagent.cli import main` + `raise SystemExit(main())`.
2. **Spec versionné** `scripts/gmailagent.spec` : `Analysis([...], pathex=['src'],
   datas=[('config', 'config')]` (défauts embarqués en repli), `hiddenimports=[...]`,
   `excludes=['tkinter', 'PyQt5', ...]` ; **`onefile=False`** (onedir — décision §5), `console=True`,
   `name='gmailagent'`. UPX désactivé.
3. **Script de build** `scripts/build_exe.py` : nettoyage `build/`/`dist/` puis
   `pyinstaller scripts/gmailagent.spec --clean --noconfirm --distpath dist --workpath build`.
4. **Config externe éditable** déposée à côté du dossier `dist/gmailagent/` (modèle, limites,
   libellés) ; **lanceur** `gmailagent.bat` (`"%~dp0gmailagent\gmailagent.exe" %*`) pour le cron.
5. **Distribution** : zip du dossier onedir ; signature de code optionnelle (certificat payant)
   contre SmartScreen.

### 8.3 Changement de code (point dur) et impact sur le CLI actuel
- Recoder `RACINE_PROJET` (`core_config.py`) : `getattr(sys, "frozen", False)` → base =
  `Path(sys.executable).resolve().parent` (onedir), priorité à une variable d'env
  `GMAILAGENT_HOME` si définie ; sinon comportement actuel inchangé
  (`Path(__file__).resolve().parents[2]`). En mode figé : `config/` externe d'abord, défauts
  embarqués (`sys._MEIPASS`) en repli ; `data/` (token, checkpoints) et `logs/` à côté de l'exe.
- **Impact sur l'exécution CLI actuelle (venv, commande `gmailagent`) : aucun.** En exécution
  normale `sys.frozen` est absent → `RACINE_PROJET` identique à aujourd'hui ; l'override
  `GMAILAGENT_HOME` est optionnel et inactif par défaut ; la résolution de `config/` est inchangée
  (`test_settings_du_depot_charges` reste vert). La branche figée n'est active que dans le binaire,
  couverte par des TU dédiés (mock de `sys.frozen`).

### 8.4 Pièges dépendances
- `google-api-python-client` v2 : documents discovery embarqués (+50 Mo) + métadonnées lues à
  l'exécution → prévoir `--collect-data googleapiclient` / `--collect-all googleapiclient` dans le
  spec (hooks hooks-contrib couvrent `googleapiclient.model`) et **tester `migrate-labels` dans le
  binaire** (construit le service Gmail).
- `pydantic`/`pydantic-core` (wheel Rust compilée) : OK via l'analyse binaire + hook pydantic ;
  contrôler `build/*/warn-*.txt` (hidden imports manquants, ex. `email_validator` optionnel).
- Taille ~100–200 Mo (discovery docs) ; élaguer les documents d'API inutilisés seulement après
  mesure (risque de casser `discovery.build`).

### 8.5 Validation (si v2 retenue)
1. `ruff check src tests`, `mypy src`, `pytest tests -q` — aucun changement fonctionnel attendu.
2. Build, puis smoke sur **poste Windows nu** (sans Python) : `gmailagent.exe --help`, `tri` en
   dry-run (vérifier : config externe lue, `data/checkpoints` + `logs/` créés à côté de l'exe).
3. Dry-run réel (`MISTRAL_API_KEY` exportée), puis petit périmètre `--reel` (règle E) sur `tri`,
   `suppression`, `migrate-labels`.

### 8.6 Portabilité du binaire (réponse séance)
Oui : le dossier onedir embarque l'interpréteur CPython — **distribuable tel quel sur tout poste
Windows 10/11 x86_64, sans Python préinstallé**, modulo :
- variables d'environnement à définir (`setx`) : `MISTRAL_API_KEY`, `GOOGLE_CLIENT_ID`,
  `GOOGLE_CLIENT_SECRET` (règle D — jamais dans le binaire) ;
- provisioning du token OAuth : `scripts/init_oauth.py` (navigateur) une fois sur le poste cible,
  ou copie de `data/gmail_token.json` (ACL 600) ;
- dossier de l'exe **accessible en écriture** (`data/`, `logs/`, checkpoints) ;
- `config/` externe éditable à côté de l'exe ;
- avertissement SmartScreen si exe non signé (certificat optionnel) ; faux positifs AV possibles
  sur le bootloader PyInstaller (mitigations : onedir, rebuild du bootloader, soumission aux
  éditeurs AV).

## 8.7 SmartScreen, signature de code et faux positifs AV (Q/R séance du 13/11/2026)

- **SmartScreen** = filtre de **réputation** de Microsoft Defender (pas un verdict viral) : au
  lancement d'un exe téléchargé d'Internet (marqué « Mark-of-the-Web »), Windows interroge le
  service de réputation de Microsoft (hash du fichier, certificat de signature, éditeur). Exe non
  signé ou hash inconnu → avertissement « Windows protected your PC » (« Exécuter quand même »
  caché derrière « Informations complémentaires »). Un fichier copié hors navigateur (USB, etc.)
  n'a pas la marque web → pas d'écran.
- **Certificat de signature de code nécessaire uniquement si l'on distribue à d'autres
  utilisateurs** : il évite l'avertissement, remplace « Unknown publisher » par l'identité vérifiée,
  et satisfait les politiques entreprise (AppLocker/EDR bloquent les non signés). **Inutile pour un
  usage perso sur sa propre machine.** Options : certificat OV auprès d'une CA du Microsoft Trusted
  Root Program (~100 €/an) — l'EV n'apporte plus de réputation SmartScreen instantanée depuis 2024 ;
  ou **Azure Artifact Signing** (ex-Trusted Signing, ~9,99 $/mois, HSM managé, sans token physique,
  intégrable au CI) recommandé par Microsoft hors Store. Signer **chaque release avec la même
  identité + horodatage** : la réputation s'accumule sur le certificat, pas sur chaque hash.
  Même signé, un premier build peut avertir tant que la réputation s'établit (en entreprise :
  soumission via le portail Microsoft Security Intelligence).
- **Faux positifs AV** : l'antivirus signale l'exe comme malveillant (`Trojan:Win32/Wacatac.B!ml`,
  `BehavesLike.Win64.Dropper`, `!ml`…) alors qu'il est sain. Cause : le bootloader PyInstaller —
  surtout en `--onefile` (extraction vers `%TEMP%` = comportement de « dropper ») — est connu des
  éditeurs AV car des malwares l'utilisent aussi ; heuristiques comportementales + réputation du
  bootloader partagé. Conséquence : fichier en quarantaine/supprimé au téléchargement ou au premier
  lancement. Mitigations : `onedir` + `--noupx`, recompiler le bootloader depuis la source (hash
  unique), signer le code (réduit fortement les détections), renseigner les métadonnées du fichier
  (version, éditeur, icône), soumettre le faux positif aux éditeurs via leurs portails (vérifier
  d'abord sur VirusTotal), exclusion Defender en local pour un usage perso.

## 9. Références

- [PyInstaller 6.22.3 — docs](https://pyinstaller.org/en/stable/) (hooks, *When Things Go Wrong*)
- [pyinstaller-hooks-contrib](https://github.com/pyinstaller/pyinstaller-hooks-contrib) (hooks pydantic, googleapiclient)
- [Nuitka](https://nuitka.net/), [cx_Freeze](https://cx-freeze.readthedocs.io/), [Briefcase / BeeWare](https://beeWare.org/briefcase/) (gratuit, licence BSD), PyOxidizer, python-build-standalone / `uv`
- Volet 2 (Mistral Studio) : [conception-studio-apps.md](conception-studio-apps.md) (D63/D66)
