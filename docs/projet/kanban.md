# Projet gmailAgent

Ce document suit l'avancement des tâches pour l'implémentation du projet **gmailAgent**. Il est organisé en **5 colonnes** :
- **À faire** : Tâches non commencées.
- **En cours** : Tâches en cours d'implémentation.
- **En revue** : Tâches prêtes pour une revue ou des tests (validation agent effectuée, en attente de validation utilisateur).
- **Terminé** : Tâches validées par l'utilisateur (après test sur son poste de travail).
- **Annulé** : Tâches abandonnées (remplacées par une solution existante ou rendues inutiles).

> Nota de traçabilité : les identifiants de tâches (T1.1, T2.1, etc.) renvoient aux phases du [plan macro](plan-macro.md) et sont conservés inchangés pour la traçabilité avec `tests/plan_tests.md`, `docs/tasks/` et `SESSIONS.md`.

---

# Tableau du kanban

## À faire
T1.3
T1.4
T1.5
T1.6
T2.1
T2.2
T2.3
T2.4

## En cours

## En revue
T1.2


## Terminé
T1.1


## Annulé


---

# Description des tâches

> Tâches triées par ordre numérique d'identifiant. L'état d'avancement de chaque tâche est indiqué dans le tableau ci-dessus. Les tâches T1.x correspondent à la **phase 1 (Fondations)** du [plan macro](plan-macro.md) (critère de sortie : package installable, configuration validée au démarrage) ; les tâches T2.x à la **phase 2 (Contrats)** (critère de sortie : tout échange inter-étapes typé et testé).

## T1.1 — Fondations : Initialisation du projet
Créer la structure des dossiers (`src/`, `tests/unit/`, `config/`, `docs/tasks/`) et le fichier `pyproject.toml` (dépendances : `mistralai`, `pydantic`, `httpx`, `structlog`, `pyyaml` ; dépendances dev : `pytest`, `ruff`, `mypy`). Vérifier `pip install -e .[dev]`.

## T1.2 — Fondations : Environnement et secrets
Créer `.env.example` (template documenté, notamment `MISTRAL_API_KEY`) ; vérifier que `.env` et ses variantes sont ignorés par `.gitignore` (règle D de AGENTS.md) ; chargement des variables d'environnement au démarrage.

## T1.3 — Fondations : Journalisation structurée
Configurer `structlog` dans `src/journalisation.py` : sortie console + fichier, niveaux, contexte (`run_id`, étape). *(Module ajouté à l'arborescence du plan macro.)*

## T1.4 — Fondations : Client Mistral commun et retry/backoff
Créer `src/client.py` : instanciation unique du client Mistral (timeout HTTP 300 s) et wrapper de retry — 3 tentatives, backoff exponentiel (base 2 s) avec jitter, sur les erreurs 429/5xx de l'API Mistral. *(Module ajouté à l'arborescence du plan macro.)*

## T1.5 — Fondations : Registre de libellés — configuration
Créer `config/labels.yaml` (clés logiques → libellés physiques, préfixe `Agent/`) et `src/config.py` (chargement + validation du registre au démarrage ; échec propre si une clé est manquante).

## T1.6 — Fondations : Registre de libellés — résolution runtime
Créer `src/labels.py` : résolution clé logique → `labelId` via `list_labels` (mis en cache par run), création du libellé via `create_label` s'il est absent, échec propre sinon. *(La migration ancien → nouveau libellé relève de la phase 3, commande CLI `migrate-labels`.)*

## T2.1 — Contrats : Modèles Pydantic et enveloppe
Créer `src/contracts.py` : modèles Pydantic `MessageClasse`, `SyntheseEtape`, `RapportFinal` et enveloppe commune `meta` (`run_id`, `etape`, `agent`, `timestamp`). Typage strict (pas de `Any` non justifié) ; la sérialisation JSON alimente les checkpoints et le rapport final.

## T2.2 — Contrats : Schémas JSON dynamiques des agents
Dans `src/contracts.py`, construire les schémas JSON stricts (`strict: true`, `additionalProperties: false`) des trois agents (classification, spam, suppression), avec les `enum` de catégorie et d'urgence construits dynamiquement à partir du registre de libellés (`config/labels.yaml`) — jamais de nom de libellé physique en dur.

## T2.3 — Contrats : Validation programmatique
Créer `src/validation.py` : fonctions reprises des scripts de référence — `collecter_ids_reels` (identifiants réellement manipulés par les outils), `valider_synthese` (cohérence, authenticité, complétude), `extraire_json` (extraction robuste du premier objet JSON bien formé). Appliquées par l'orchestrateur à chaque synthèse d'étape.

## T2.4 — Contrats : Tests unitaires
Créer `tests/unit/test_contracts.py` et `tests/unit/test_validation.py` : validation des modèles (champs requis, enums dynamiques issus du registre), sérialisation/désérialisation, rejet des synthèses incohérentes (statut échec avec messages, IDs inconnus, JSON malformé). *(La phase 9 initialisera `tests/plan_tests.md` et couvrira l'ensemble du pipeline : fixtures de conversations mockées, mode dry-run, CI.)*
