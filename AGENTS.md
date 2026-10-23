# Guide pour les Agents (AGENTS.md)

Ce fichier décrit la **méthode de travail** à suivre pour contribuer au projet **gmailAgent**.
Il est automatiquement chargé à chaque séance, mais **aucune action structurante n'est déclenchée sans demande explicite** de l'utilisateur.

---

## **1. Reprise de contexte à chaque séance**
### **Étapes automatiques (sans initiative de l'agent)**
À chaque début de séance, l'agent **recharge automatiquement** les fichiers clés suivants pour reprendre le contexte :
1. **`docs/design/conception.md`** : schéma de conception du pipeline (agents, contrats, doublons, rate limits).
2. **`docs/design/workflow.md`** : workflow général (schéma Mermaid, phases agentiques et programmatiques).
3. **`docs/projet/plan-macro.md`** : plan macro (10 phases de développement).
4. **`docs/architecture/*.md`** : contrats d'interface et invariants (créés en phase 2).
5. **`tests/plan_tests.md`** : plan de tests associés aux tâches.
6. **`docs/test/acceptation.md`** : critères d'acceptation des réalisations.
7. **`SESSIONS.md`** : **actions, décisions et blocages** des séances précédentes.
8. **`docs/projet/kanban.md`** : tableau des tâches.

### **Étapes à suivre (sur initiative de l'utilisateur)**
1. **Vérifier les derniers commits** (si modifications hors session).
   - Exemple de demande :
     ```markdown
     Peux-tu lister les 5 derniers commits pour voir les changements récents ?
     ```
2. **Demander un résumé du contexte** :
   - Exemple de demande :
     ```markdown
     Peux-tu me faire un résumé des tâches en cours et des décisions de conception clés ?
     ```

---

## **2. Workflow par tâche**

### **Étape 1 : Choix de la tâche (sur initiative de l'utilisateur)**
- **Action** : Identifier **la tâche explicitement demandée par l'utilisateur** dans `kanban.md` et la déplacer dans le bon paragraphe (« À faire », « En cours », « En revue », « Terminé »).
  - *L'agent ne choisit **jamais** automatiquement une tâche prioritaire, mais peut proposer une évaluation des priorités si l'utilisateur le demande.*
- **Vérification** : S'assurer que ses dépendances sont terminées et vérifier s'il y a des dépendances éventuelles avec d'autres tâches.
- **Exemple de demande** :
  ```markdown
  Peux-tu préparer le travail sur la tâche T1.1 du kanban ?
  ```
- **Exemple de proposition de priorisation (sur demande)** :
  ```markdown
  Quelles tâches me recommandes-tu de prioriser dans le kanban ?
  ```

### **Étape 2 : Planification (sur initiative de l'utilisateur)**
- **Actions** :
  1. Lire les spécifications associées à la tâche dans les sources suivantes :
     - `docs/architecture/<nom_contrat>.md` (ex : `agent_classification.md`).
     - `docs/projet/plan-macro.md` (pour les choix de conception macroscopiques).
     - `tests/plan_tests.md` (pour les tests associés).
     - `SESSIONS.md` (pour les décisions passées).
  2. Établir un **plan détaillé** avec :
     - Sous-tâches (ex : « Créer les modèles Pydantic pour `SyntheseEtape` »).
     - Fichiers à modifier (ex : `src/contracts.py`).
     - Tests associés (ex : TU-01 à TU-05 dans `plan_tests.md`).
- **Exemple de demande** :
  ```markdown
  Peux-tu établir un plan détaillé pour la tâche T2.1 ?
  ```

### **Étape 3 : Implémentation (sur initiative de l'utilisateur)**
- **Actions** :
  1. Coder la fonctionnalité en respectant les **invariants** du projet (moindre privilège, véracité, corbeille uniquement, contrats stricts).
  2. Coder les **tests associés** (unitaires et/ou d'intégration).
- **Exemple de demande** :
  ```markdown
  Peux-tu implémenter la tâche T2.1 en suivant le plan établi ?
  ```

### **Étape 4 : Tests et itérations (sur initiative de l'agent à la suite de l'étape 3)**
- **Actions** :
  1. Lancer les vérifications : `ruff check`, `mypy`, puis `pytest`.
     - Exemple de commandes :
       ```bash
       ruff check src tests
       mypy src
       python -m pytest tests/unit/test_contracts.py -v
       ```
  2. **Itérer en cas d'échec** :
     - **1ère tentative** : Corriger directement.
     - **2ème tentative** : Vérifier les hypothèses et corriger.
     - **3ème tentative** : **Arrêter** et documenter le blocage.
- **Règle d'arrêt** : Si un test échoue à la troisième tentative, créer une entrée dans [`BLOCKERS.md`](BLOCKERS.md) et passer à une autre tâche.

### **Étape 5 : Validation agent (sur initiative de l'agent à la suite de l'étape 4)**
- **Actions** :
  1. Valider que tous les tests passent, que `ruff` et `mypy` sont propres, et que les critères d'acceptation sont respectés.
  2. Mettre à jour `docs/projet/kanban.md` (déplacer la tâche en **En revue**).
  - *Pas de commit à cette étape : la validation utilisateur (étape 6) intervient d'abord.*

### **Étape 6 : Validation utilisateur (sur initiative de l'utilisateur)**
- **Actions** :
  1. L'utilisateur **rapatrie le code sur son poste de travail** et le teste en conditions réelles (ou en mode dry-run).
  2. L'utilisateur valide que tous les tests passent et que les critères d'acceptation sont respectés.
  3. L'utilisateur demande le déplacement de la tâche en **Terminé** dans `docs/projet/kanban.md`.
  4. L'utilisateur demande explicitement le commit et le push.
- **Exemple de demande** :
  ```markdown
  Peux-tu valider la tâche T2.1 et la déplacer en Terminé dans le kanban ?
  Peux-tu faire un commit et pousser les changements sur la branche dev ?
  ```

---

## **3. Règles supplémentaires**

### **A. Documentation systématique (sur initiative de l'agent et éventuelle initiative complémentaire de l'utilisateur)**
- Pour chaque tâche, créer un **fichier de suivi** dans `docs/tasks/` (ex : `T2.1_contrats_pydantic.md`).
  ```markdown
  # Tâche T2.1 : Modèles Pydantic

  ## Statut
  - [X] Implémentation
  - [ ] Tests unitaires
  - [ ] Tests d'intégration

  ## Fichiers modifiés
  - `src/contracts.py`

  ## Blocages
  - Aucun.
  ```
- **Exemple de demande** :
  ```markdown
  Peux-tu créer un fichier de suivi pour la tâche T2.1 dans `docs/tasks/` ?
  ```

### **B. Gestion des blocages (sur initiative de l'agent à l'issue de l'étape 4)**
- Si une tâche est bloquée :
  1. Créer une entrée dans [`BLOCKERS.md`](BLOCKERS.md) :
     ```markdown
     # Blocages

     ## T2.1 : Modèles Pydantic
     - **Problème** : Le test TU-03 échoue car le schéma JSON n'est pas accepté par l'API.
     - **Tentatives** : 3/3.
     - **Proposition** : Vérifier la compatibilité `json_schema.strict` avec le SDK Mistral.
     ```
  2. Passer à une autre tâche.
- **Exemple de demande** :
  ```markdown
  Peux-tu documenter ce blocage dans `BLOCKERS.md` et passer à une autre tâche ?
  ```

### **C. Gestion des changements (sur initiative de l'utilisateur à l'issue de l'étape 5 ou durant l'étape 6)**
- Ne jamais faire un commit, ni pousser un changement dans le repository sans demande explicite de l'utilisateur.

### **D. Gestion des secrets (spécifique gmailAgent)**
- **Jamais de secret dans le code ni dans les commits** : la clé `MISTRAL_API_KEY` et les credentials du connecteur Gmail vivent exclusivement dans les variables d'environnement.
- Le fichier `.env` (et toute variante `.env.*`) est ignoré par git (vérifié dans `.gitignore`) : ne jamais forcer son ajout (`git add -f` interdit).
- Les secrets sont injectés par l'environnement au runtime ; les scripts et l'orchestrateur lisent `os.environ` uniquement.
- En cas de fuite suspectée (commit accidentel) : révoquer la clé côté Mistral / Google immédiatement, puis purger l'historique si nécessaire.

### **E. Mode dry-run (spécifique gmailAgent)**
- Toute tâche qui ajoute une **écriture vers Gmail** (apposition de libellé, corbeille) doit supporter un mode **dry-run** : exécution complète du pipeline sans aucun appel d'écriture (les appels d'écriture sont journalisés au lieu d'être exécutés).
- La tâche n'est déplacée en **En revue** (étape 5) que si le dry-run a été exécuté et validé.
- La validation en conditions réelles (étape 6) s'effectue d'abord en dry-run sur le poste de l'utilisateur, puis sur un petit périmètre réel (quelques messages).

### **F. Qualité de code (spécifique gmailAgent)**
- Lint : `ruff check src tests` (à exécuter avant chaque commit).
- Typage : `mypy src` (les contrats pydantic et les modules `src/` sont typés ; pas de `Any` non justifié).
- Tests : `python -m pytest tests/unit -v` (unitaires), `tests/integration` lorsque disponible.
- Les trois commandes font partie de la validation agent (étape 5).

### **G. Gestion de l'environnement (spécifique gmailAgent)**
- Le projet est géré par `pyproject.toml` (dépendances : `mistralai`, `pydantic`, `httpx`, `structlog`, `pyyaml` ; dev : `pytest`, `ruff`, `mypy`).
- Environnement virtuel dédié (`venv/` ou `.venv/`, ignoré par git) ; installation : `pip install -e .[dev]`.
- Le client Mistral commun est instancié une seule fois (avec timeout HTTP explicite de 300 s).

### **H. Consigne de livraison (spécifique gmailAgent)**
- **Branche de travail unique : `dev`.** Tout le code est poussé directement sur `dev`.
- **Pas de pull request, pas de branche dédiée** par tâche : pas de branche `feature/*`, pas de PR.
- Le commit et le push interviennent **uniquement sur demande explicite** de l'utilisateur (règle C), sur la branche `dev`.
- La branche `main` n'est alimentée que par l'utilisateur (merge depuis `dev` à sa demande).

---

## **4. Actions ponctuelles (hors workflow)**
Les actions suivantes peuvent être demandées en séance **sans être référencées dans ce fichier** :
- **Analyse/Revue** :
  ```markdown
  Peux-tu analyser la cohérence entre `src/validation.py` et `docs/architecture/agent_classification.md` ?
  ```
- **Corrections ponctuelles** :
  ```markdown
  Peux-tu corriger cette erreur de typage dans `src/contracts.py` ?
  ```
- **Génération de documentation** :
  ```markdown
  Peux-tu générer un exemple de synthèse pour l'agent classification ?
  ```
- **Autres demandes** :
  ```markdown
  Peux-tu me proposer une évaluation des priorités dans le kanban ?
  ```

---

## **5. Résumé des fichiers clés**
| Fichier                  | Rôle                                                                                            |
|--------------------------|-------------------------------------------------------------------------------------------------|
| `SESSIONS.md`            | Journal des **actions, décisions et blocages** par séance. Utilisé pour la reprise de contexte. |
| `docs/projet/kanban.md`  | Suivi des tâches (À faire → En cours → En revue → Terminé).                                     |
| `docs/projet/plan-macro.md` | Plan macro : 10 phases de développement du pipeline.                                        |
| `docs/design/conception.md` | Spécification générale du pipeline.                                                          |
| `docs/design/workflow.md` | Workflow général (schéma Mermaid).                                                             |
| `docs/architecture/*.md` | Contrats d'interface et invariants par agent.                                                   |
| `tests/plan_tests.md`    | Plan de tests (TU, TI) et couverture des critères d'acceptabilité.                              |
| `docs/tasks/`            | Suivi détaillé par tâche (optionnel).                                                           |
| `BLOCKERS.md`            | Liste des **blocages non résolus** (documentés après 3 échecs de test).                         |
