# SESSIONS.md — Journal des séances

Journal des **actions, décisions et blocages** par séance. Utilisé pour la reprise de contexte (voir AGENTS.md, §1).

---

## Séance du 23/10/2026

### Contexte
Démarrage du projet **gmailAgent** : pipeline de tri de messagerie Gmail (classification, spam, suppression différée) orchestré en Python, conversations éphémères avec l'API Mistral.

### Actions réalisées

1. **Prise de connaissance du document de conception** initial (`docs/design/coneption.md`) et retour critique (faute de frappe dans le nom, dépendance à des scripts absents, gestion des doublons non spécifiée, absence de dimension rate limit, etc.).
2. **Réception des 8 scripts de référence** (`agent01a/01b/01c`, `agent02/02b`, `agent03a/03b/03c`), exemples de conception hors dépôt : pattern agent permanent (01x, 03x) et pattern conversation éphémère (02, 02b), fonctions de validation communes (`collecter_ids_reels`, `valider_synthese`, `extraire_json`).
3. **Réécriture complète de la spécification** (`docs/design/conception.md`) :
   - scénarios A (handoffs) et B (Workflows Studio) **écartés** ;
   - scénario retenu : **orchestration programmatique en Python** (orchestrateur séquentiel, checkpoints, idempotence par libellés, cron) ;
   - évaluation **agents permanents vs éphémères** : recommandation **conversations éphémères** pour le pipeline (configuration versionnée avec le code) ;
   - **contrats d'interface** définis (schémas JSON stricts par agent, enveloppe commune, modèles typés, allow-list d'outils, orchestrateur seul médiateur) ;
   - **gestion des doublons** : clé primaire `Message-ID` RFC 5322, clé secondaire SHA-256 (expéditeur/sujet/corps normalisés), dédoublonnage déterministe côté orchestrateur, libellé `Agent/doublon`, recalcul/validation des empreintes ;
   - **gestion des rate limits** : bornage 50 messages/run, backoff exponentiel + jitter (3 tentatives, base 2 s), garde-fou anti-boucle, cache `list_labels`, mode incrémental `history.list`, run de suppression séparé, plafonds de modèle, observabilité.
4. **Création du schéma Mermaid du workflow** (`docs/design/workflow.md`) : phases agentiques (bleu) vs programmatiques (vert), passages conditionnels ok/rejet, deux runs indépendants (tri + suppression T+1h) couplés par les libellés Gmail.
5. **Création du plan macro** (`docs/projet/plan-macro.md`) : 10 phases, principe du **registre de libellés** (`config/labels.yaml`, clés logiques vs libellés physiques), arborescence cible avec `src/` plat, précautions transverses (dry-run, validation systématique, corbeille uniquement, véracité).
6. **Création et adaptation de `AGENTS.md`** (méthode de travail) à partir du modèle openDataAgent :
   - étapes 5 (validation agent → En revue, **sans commit**) et 6 (validation utilisateur → rapatriement sur le poste de travail, test, Terminé, commit/push sur demande) distinctes ;
   - **3 tentatives** avant blocage (chiffre retenu) ;
   - références mortes supprimées, exemples adaptés à gmailAgent ;
   - ajouts spécifiques : **gestion des secrets** (§D), **mode dry-run** (§E), **qualité de code ruff/mypy/pytest** (§F), **gestion de l'environnement pyproject.toml** (§G) ;
   - **consigne de livraison** (§H) : branche `dev` unique, push direct sur demande, pas de PR ni de branche dédiée.
7. **Initialisation du kanban** (`docs/projet/kanban.md`) : 5 colonnes, puis découpage de la **phase 1 (Fondations)** en 6 tâches T1.1 à T1.6 (initialisation projet/pyproject, environnement et secrets, journalisation structurée, client Mistral + retry/backoff, registre de libellés configuration et résolution runtime).

### Décisions clés

| # | Décision | Justification |
| --- | --- | --- |
| D1 | Scénarios A (handoffs) et B (Workflows Studio) écartés | A : pas de reprise sur incident, état partiel possible. B : Public Preview, orchestration externe au code. Remplacés par orchestration Python + checkpoints + cron. |
| D2 | Conversations éphémères retenues pour le pipeline | Configuration (prompt, outils, schéma) versionnée avec le code, reproductible, sans cycle create/delete. Agents permanents réservés à un usage manuel depuis Studio. |
| D3 | Préfixe `Agent/` généralisé pour tous les libellés de coordination | Lisibilité dans Gmail, namespace réservé, évolution possible via le registre. |
| D4 | Libellés évolutifs via registre `config/labels.yaml` | Clés logiques stables côté code, libellés physiques changeants côté Gmail ; renommage sans migration de code ; outil `migrate-labels` prévu (phase 3). |
| D5 | Arborescence `src/` plat (pas de package imbriqué) | Projet de scripts CLI, pas une bibliothèque installable. |
| D6 | Dédoublonnage en code Python, pas par le LLM | Comparaison déterministe, reproductible, testable, sans coût en tokens. |
| D7 | Livraison sur `dev`, sans PR ni branches dédiées | Méthode de travail choisie par le concepteur. `main` alimentée uniquement par le concepteur. |
| D8 | 3 tentatives avant blocage (règle d'arrêt des tests) | Chiffre retenu après correction de l'incohérence 3/4 dans le modèle AGENTS.md. |

### Blocages

Aucun.

### État en fin de séance

- Branche `dev` à jour sur origin (dernier commit : `ac6c3e2`) ; `main` inchangé (`51f9074`) ; branche `vibe/conception-doc-208312` supprimée (contenu fusionné dans `dev`).
- Livrables documentaires : `docs/design/conception.md`, `docs/design/workflow.md`, `docs/projet/plan-macro.md`, `docs/projet/kanban.md` (phase 1 découpée), `AGENTS.md`, `SESSIONS.md`.
- Kanban : 6 tâches en « À faire » (T1.1–T1.6), aucune en cours.
- Prochaines étapes pressenties : découpage de la phase 2 (Contrats) en tâches T2.x, puis implémentation de T1.1.

---

## Séance du 26/10/2026

### Contexte
Reprise du projet **gmailAgent** après la séance du 23/10/2026. Objectif de la séance : poursuivre l'initialisation du kanban à partir du [plan macro](docs/projet/plan-macro.md). La phase 1 (Fondations) était déjà découpée en T1.1–T1.6 ; il restait à découper la **phase 2 (Contrats)** — c'était la prochaine étape pressentie en fin de séance précédente.

### Actions réalisées

1. **Reprise de contexte** : passage sur la branche `dev` (à jour sur origin, dernier commit `9807970`), lecture de `AGENTS.md`, `docs/design/conception.md`, `docs/design/workflow.md`, `docs/projet/plan-macro.md`, `docs/projet/kanban.md` et `SESSIONS.md`.
2. **Découpage de la phase 2 (Contrats)** du plan macro en 4 tâches, ajoutées en « À faire » dans `docs/projet/kanban.md` :
   - **T2.1** — modèles Pydantic (`MessageClasse`, `SyntheseEtape`, `RapportFinal`) et enveloppe `meta` dans `src/contracts.py` ;
   - **T2.2** — schémas JSON stricts des 3 agents, `enum` construits dynamiquement depuis le registre de libellés (jamais de nom de libellé physique en dur) ;
   - **T2.3** — `src/validation.py` : `collecter_ids_reels`, `valider_synthese`, `extraire_json` (fonctions reprises des scripts de référence) ;
   - **T2.4** — tests unitaires des contrats et de la validation dans `tests/unit/`.
3. **Implémentation de la tâche T1.1** (Fondations : Initialisation du projet) :
   - création de l'arborescence (`src/`, `tests/unit/`, `tests/integration/`, `config/`, `docs/tasks/` avec `.gitkeep`) ;
   - création de `pyproject.toml` (setuptools, dépendances runtime + extra `dev`, src plat via `py-modules`, config ruff/mypy/pytest) ;
   - vérification : `pip install -e ".[dev]"` OK, `ruff check src tests` OK, `mypy src` et `pytest tests/unit` sans erreur (aucun module/test à ce stade, comme attendu) ;
   - kanban : T1.1 déplacée en « En cours » puis « En revue » (validation agent effectuée, en attente de validation utilisateur) ;
   - fichier de suivi : `docs/tasks/T1.1_initialisation_projet.md`.
4. **Itération sur T1.1 lors de la validation utilisateur** : `mypy src` échouait
   sur le poste local (124 erreurs) car mypy analyse les scripts de référence
   (`src/agent0*.py`) présents sur le disque, bien qu'ils soient ignorés par git
   (ruff respecte `.gitignore`, mypy non). Correction : ajout d'un `exclude`
   dans `[tool.mypy]` (`agent0\d[a-c]?\.py`). Revérifié : mypy propre avec ou
   sans les scripts présents localement.
### Décisions clés

| # | Décision | Justification |
| --- | --- | --- |
| D9 | Phase 2 découpée en 4 tâches T2.1–T2.4 | La sortie de phase (« tout échange inter-étapes typé et testé ») se traduit en : modèles + enveloppe, schémas JSON dynamiques, validation programmatique, tests unitaires. |
| D10 | Les schémas JSON dynamiques restent dans `src/contracts.py` | Conformément à l'arborescence du plan macro (« pydantic + schémas JSON dynamiques ») ; `src/prompts.py` se chargera des textes de prompts dans une phase ultérieure. |
| D11 | T2.4 (tests des contrats) en phase 2, pas en phase 9 | Le critère de sortie de la phase 2 exige des contrats testés ; la phase 9 (Tests) portera sur l'ensemble du pipeline (fixtures de conversations mockées, mode dry-run, CI). |

### Blocages

Aucun.

### État en fin de séance

- Branche `dev` : dernier commit poussé `fb59864` (T1.1) ; itération mypy (exclude des scripts de référence) et mises à jour documentaires en local, en attente de commit/push sur demande explicite (règle C de AGENTS.md).
- Kanban : **T1.1 validée par l'utilisateur et déplacée en « Terminé »** ; **T1.2 validée par l'utilisateur et déplacée en « Terminé »** ; **T1.3 validée par l'utilisateur et déplacée en « Terminé »** ; **T1.4 validée par l'utilisateur et déplacée en « Terminé »** ; **T1.5 validée par l'utilisateur et déplacée en « Terminé »** (validation groupée au rapatriement du projet sur le poste) ; **T1.6 implémentée et poussée (commit `52eedf1`)** ; **T1.7 ajoutée en « À faire »** (pré-requis OAuth Gmail — configuration côté Google Cloud, câblage en phase 3) ; 5 tâches en « À faire » (T1.7, T2.1–T2.4).
- L'itération mypy de T1.1 (exclude des scripts de référence) reste en local, non commitée (décision utilisateur : « inutile de faire un commit pour si peu ») ; elle sera embarquée dans le prochain commit demandé.
- **Investigation mistralai 3.5.0** (suite au doute utilisateur, résolu) : le wheel 3.x de PyPI (3.0.0 à 3.5.0, généré par hatchling) ne contient **pas** de `mistralai/__init__.py` racine — le package est un **namespace package** (`__file__ = None`), donc `from mistralai import Mistral` échoue en environnement pur. La 1.9.11 (générée par Speakeasy) contient bien ce fichier. **Découverte clé** : le poste de l'utilisateur (projet openDataAgent, Python 3.14) échoue aussi sur `mistralai.client` à cause d'un **masquage stdlib** (`mistralai/client/types/__init__.py` masque le module `types` → `ImportError: cannot import name 'GenericAlias' from 'types'`). openDataAgent contourne les deux problèmes par un **import tolérant** (`try: from mistralai import Mistral / except ImportError: from mistralai.client import Mistral`) — ce n'est pas un lazy import, c'est un fallback. **Décision pour gmailAgent** : pas de pattern tolérant (il casse `mypy --strict` : `Module "mistralai" has no attribute "Mistral"` [attr-defined], testé) ; import direct via `from mistralai.client import Mistral` et `from mistralai.client.errors import SDKError` — chemin présent et fonctionnel dans les deux familles de versions, mypy-propre et runtime-vérifié sur 3.5.0. Dépendance : `mistralai>=3.5` (rétabli après épinglage temporaire à 1.9.11). **Attention environnement** : le dossier `mistralai/client/types/` peut masquer le module stdlib `types` si le venv est mal isolé — à surveiller sur le poste Windows (Python 3.14).

---

## Séance du 27/10/2026

### Contexte
Reprise du projet **gmailAgent**. L'utilisateur confirme que T1.7 (pré-requis OAuth Gmail) n'est pas un pré-requis de la phase 2 — il relève de la phase 3 (câblage Gmail). Décision de commencer directement par **T2.1 (Contrats : modèles Pydantic et enveloppe)**.

### Actions réalisées

1. **Reprise de contexte** : branche `dev` à jour (`63025a2`), lecture de `AGENTS.md`, `docs/design/conception.md`, `docs/design/workflow.md`, `docs/projet/plan-macro.md`, `docs/projet/kanban.md`, `SESSIONS.md`, et des modules existants (`src/config.py`, `src/labels.py`, `src/journalisation.py`, `src/client.py`, `src/env.py`).
2. **T2.1 déplacée en « En cours »** dans le kanban ; fichier de suivi `docs/tasks/T2.1_contrats_pydantic.md` créé avec le plan détaillé.
3. **Implémentation de T2.1** :
   - `src/contracts.py` créé : `Meta` (enveloppe commune : `run_id: UUID`, `etape`, `agent`, `timestamp` UTC par défaut), `MessageLu`, `MessageClasse` (+ `categorie` pattern clé logique, `urgence` Literal, `message_id_rfc` normalisé, `empreinte` SHA-256 hexa), `SyntheseClassification` / `SyntheseSpam` / `SyntheseSuppression` (statut Literal par agent, `erreur: str | None`, `meta`), `SyntheseEtape` (union), `RapportFinal`. `extra="forbid"` sur tous les modèles (aligné avec `additionalProperties: false` des schémas stricts de T2.2).
   - `pyproject.toml` : `py-modules += "contracts"`.
   - Itération ruff : UP017 corrigé (`datetime.UTC` au lieu de `timezone.utc`).
   - Règles de non-contradiction (cohérence statut/messages/erreur) volontairement hors des modèles → `valider_synthese` (T2.3).
4. **Vérification (étape 4 de AGENTS.md)** :
   - `ruff check src tests` : OK.
   - `mypy src` : OK (`Success: no issues found in 6 source files`, strict).
   - `python -m pytest tests/unit -v` : 0 test collecté (attendu — tests en T2.4, décision D11).
   - Smoke : round-trip JSON (`model_dump(mode="json")` → `model_validate`) sur les 3 synthèses + `RapportFinal` ; rejets conformes (champ interdit, `urgence="critique"`, `empreinte` hors pattern, `statut` hors enum). Note : le premier smoke a échoué sur un artefact du test (`model_copy(update=...)` ne revalide pas en Pydantic v2) ; corrigé via `model_validate` — les modèles étaient corrects.
5. **T2.1 déplacée en « En revue »** (validation agent effectuée, en attente de validation utilisateur). Fichier de suivi mis à jour. **Aucun commit** (règle C de AGENTS.md).

### Décisions clés

| # | Décision | Justification |
| --- | --- | --- |
| D12 | T2.1 lancée avant T1.7 | T1.7 (OAuth Gmail) est un pré-requis de la phase 3 (câblage `googleapiclient`), pas de la phase 2 (Contrats). |
| D13 | `categorie` typée `str` avec pattern clé logique en T2.1 | L'enum dynamique sera construit en T2.2 depuis `config/labels.yaml` ; jamais de libellé physique en dur dans les contrats. |
| D14 | Non-contradiction hors des modèles Pydantic | Cohérence sémantique (statut/messages/erreur) → `valider_synthese` (T2.3), pas contrainte de schéma. |

### Blocages

Aucun.

### État en fin de séance

- Branche `dev` : modifications non commitées (`src/contracts.py`, `pyproject.toml`, `docs/projet/kanban.md`, `docs/tasks/T2.1_contrats_pydantic.md`, `SESSIONS.md`) — en attente de commit/push sur demande explicite (règle C).
- Kanban : **T2.1 en « En revue »** ; **T1.6 en « En revue »** (en attente de validation utilisateur) ; 4 tâches en « À faire » (T1.7, T2.2, T2.3, T2.4).
- Prochaine étape pressentie : validation utilisateur de T2.1 (et T1.6), puis **T2.2** (schémas JSON dynamiques des agents).

---

## Séance du 27/10/2026 (suite) — T2.2

### Contexte
Poursuite de la phase 2 (Contrats) après T2.1. Implémentation de **T2.2 (schémas JSON dynamiques des agents)**.

### Actions réalisées

1. **Recherche technique préalable** : inspection du SDK `mistralai` 3.5 installé
   (`ResponseFormat`/`JSONSchema` : forme `{"type": "json_schema", "json_schema": {"name", "schema", "strict"}}`,
   passage via `completion_args.response_format` dans les conversations éphémères) ;
   lecture de `mistralai.extra.utils._pydantic_helper.rec_strict_json_schema`
   (force `additionalProperties: false` sur tous les objets) ; consultation de la
   doc Mistral (Custom Structured Outputs) et de retours communautaires
   (pydantic-ai#4762, client-python#633). Décision : **ne pas utiliser** le helper
   SDK `response_format_from_pydantic_model` (pas de contrôle sur les enums
   dynamiques ni l'exclusion de `meta`) — construction manuelle des schémas.
2. **T2.2 déplacée en « En cours »** ; fichier de suivi
   `docs/tasks/T2.2_schemas_json_dynamiques.md` créé avec le plan détaillé.
3. **Implémentation dans `src/contracts.py`** :
   - Constantes `AGENT_*`, `_MODELES_PAR_AGENT`, `_ENUM_URGENCES`, `_ENUM_STATUTS` ;
     `AgentInconnuError`.
   - `_schema_payload(cls, exclure=("meta",))` : deep-copy du schéma Pydantic,
     retrait de `meta`, nettoyage des `$defs` orphelins.
   - `_enum_categories(registre)` + `_injecter_enums_agent` : injection des enums
     dynamiques (`statut` par agent, `categorie` depuis le registre, `urgence`
     fixe) — navigation via le `$ref` de `messages.items` pour la classification.
   - `schema_agent(agent, registre=None)` (registre par défaut via `charger_registre()`).
   - `response_format_agent(agent, registre=None)` : enveloppe SDK prête pour
     `completion_args.response_format`.
4. **Vérification** :
   - `ruff check src tests` : OK. `mypy src` : OK (strict, 6 fichiers).
   - `pytest tests/unit` : 0 test (attendu — T2.4).
   - Smoke 7 groupes : structure (`additionalProperties: false` partout, `meta`
     exclu, `$ref` résolus, `$defs` sans orphelins), enums dynamiques, aucun
     libellé physique en dur, forme SDK, round-trip Pydantic (payload + `meta`
     injecté), rejet libellé physique par le pattern, `AgentInconnuError`.
     Tous OK. (Première version du smoke échouait sur une confusion clé logique
     vs libellé physique dans l'assertion — le code était correct.)
5. **T2.2 déplacée en « En revue »**. Aucun commit (règle C).

### Décisions clés

| # | Décision | Justification |
| --- | --- | --- |
| D15 | Schéma agent = payload sans `meta` ; `meta` injecté par l'orchestrateur | Le LLM ne connaît pas `run_id`/`timestamp` ; l'enveloppe complète (conception §2.4.2) est reconstituée côté orchestrateur avant validation Pydantic. |
| D16 | Construction manuelle des schémas (pas le helper SDK `response_format_from_pydantic_model`) | Le helper applique `rec_strict_json_schema` sans contrôle sur les enums dynamiques ni l'exclusion de `meta`. |
| D17 | `erreur` dans `required` avec `anyOf [string, null]` | Émulation du nullable (pattern Pydantic `Optional[str]`) ; le LLM produit explicitement `"erreur": null`. |

### Blocages

Aucun.

### État en fin de séance

- Branche `dev` : modifications non commitées (T2.1 + T2.2 + doc) — en attente de commit/push sur demande explicite.
- Kanban : **T2.1 et T2.2 en « En revue »** ; **T1.6 en « En revue »** ; 3 tâches en « À faire » (T1.7, T2.3, T2.4).
- Prochaine étape pressentie : validation utilisateur de T2.1/T2.2, puis **T2.3** (validation programmatique : `collecter_ids_reels`, `valider_synthese`, `extraire_json`).

---

## Séance du 27/10/2026 (suite) — T2.3

### Contexte
Poursuite de la phase 2 (Contrats). Implémentation de **T2.3 (validation programmatique)**.

### Actions réalisées

1. **Vérification SDK** : `ToolExecutionEntry.arguments` est `str` (JSON),
   `FunctionCallEntry.arguments` est `dict`, `entry.type` ∈ `{"tool.execution",
   "function.call", "message.output", ...}` — confirmé par construction de
   fixtures avec les vrais modèles SDK.
2. **T2.3 déplacée en « En cours »** ; fichier de suivi
   `docs/tasks/T2.3_validation_programmatique.md` créé.
3. **Implémentation de `src/validation.py`** :
   - `extraire_json` : extraction robuste du premier objet JSON bien formé
     (accolades imbriquées, chaînes échappées).
   - `collecter_ids_reels` : parcours des entrées `tool.execution` /
     `function.call`, parse des arguments, collecte des champs d'IDs
     (`threadId`, `thread_id`, `messageId`, `message_id`, `id`).
   - `valider_synthese` : 6 contrôles (C1 non-contradiction statut/messages,
     C2 aucun_message cohérent, C3 complétude, C4 authenticité des IDs,
     C5 cohérence count/ids, C6 empreintes présentes) — rejet avec motif
     explicite via `SyntheseInvalideError`.
   - `construire_synthese` (bonus) : sélection du modèle par agent + injection
     de `meta` + `model_validate` (pont orchestrateur entre le payload LLM et
     les contrats T2.1/T2.2).
   - `pyproject.toml` : `py-modules += "validation"`.
   - Itération ruff : I001 (tri des imports).
4. **Vérification** :
   - `ruff check src tests` : OK. `mypy src` : OK (strict, 7 fichiers).
   - `pytest tests/unit` : 0 test (attendu — T2.4).
   - Smoke 6 groupes (avec vrais modèles SDK) : `extraire_json` (noyé,
     imbriqué, échappé, rejets), `collecter_ids_reels` (str + dict, str/list,
     entrées ignorées, arguments tronqués), 5 cas valides, 10 cas de rejet
     C1–C5, agent inconnu, champ interdit (Pydantic). Tous OK.
   - Note : première exécution du smoke a échoué sur une erreur du script de
     test lui-même (argument `label` manquant dans `rejet_attendu`) — le code
     était correct.
5. **T2.3 déplacée en « En revue »**. Aucun commit (règle C).

### Décisions clés

| # | Décision | Justification |
| --- | --- | --- |
| D18 | `construire_synthese` ajouté à T2.3 (hors périmètre initial du kanban) | Pont nécessaire entre le payload LLM (schéma T2.2) et les modèles Pydantic (T2.1) ; sans lui, l'orchestrateur devrait réimplémenter la sélection du modèle + injection de `meta`. |
| D19 | `_CHAMPS_IDS` en constante module (allow-list configurable) | Les noms exacts de champs d'arguments Gmail (`threadId` vs `id`, `messageId` vs `message_id`) seront confirmés au premier appel réel (phase 3+) ; la liste couvre les variantes usuelles. |

### Blocages

Aucun.

### État en fin de séance

- Branche `dev` : modifications non commitées (T2.1 + T2.2 + T2.3 + doc).
- Kanban : **T2.1, T2.2, T2.3 en « En revue »** ; **T1.6 en « En revue »** ; 2 tâches en « À faire » (T1.7, T2.4).
- **Phase 2 (Contrats) : T2.1–T2.3 terminées côté agent, T2.4 (tests unitaires) reste** — c'est le critère de sortie de la phase (« tout échange inter-étapes typé et testé »).
- Prochaine étape : **T2.4** (tests unitaires `test_contracts.py` + `test_validation.py`) pour clôturer la phase 2.

---

## Séance du 27/10/2026 (suite) — T2.4 et clôture de la phase 2

### Contexte
Dernière tâche de la **phase 2 (Contrats)** : **T2.4 (tests unitaires)** couvrant T2.1 (modèles), T2.2 (schémas dynamiques) et T2.3 (validation). L'utilisateur demande ensuite un commit et un push sur `dev`.

### Actions réalisées

1. **T2.4 déplacée en « En cours »** ; fichier de suivi `docs/tasks/T2.4_tests_unitaires.md` créé.
2. **Implémentation des tests unitaires** :
   - `tests/unit/conftest.py` : fixtures communes (`meta`, `meta_fixe`, `registre`,
     `message_lu`, `message_classe`).
   - `tests/unit/test_contracts.py` (52 tests) : modèles T2.1 (Meta, MessageLu,
     MessageClasse, 3 synthèses, RapportFinal — champs requis, patterns, enums,
     round-trip JSON, rejets) + schémas T2.2 (`additionalProperties: false`
     partout, `meta` exclu, `$ref` résolus, enums dynamiques, aucun libellé
     physique en dur, forme SDK `response_format_agent`).
   - `tests/unit/test_validation.py` (39 tests) : `extraire_json` (6),
     `collecter_ids_reels` (11, avec vrais modèles SDK `ToolExecutionEntry` /
     `FunctionCallEntry` / `MessageOutputEntry`), `valider_synthese` cas valides
     (5) + rejets C1–C6 (12, C6 via `model_construct`), `construire_synthese`
     (4), test cross-module (1).
   - Itération ruff : F401 (imports `AGENT_SPAM`/`AGENT_SUPPRESSION` inutilisés).
3. **Vérification** :
   - `ruff check src tests` : OK. `mypy src` : OK (strict, 7 fichiers).
   - `python -m pytest tests/unit -v` : **91 passed in 0.53s**
     (test_contracts : 52, test_validation : 39).
4. **T2.4 déplacée en « En revue »** ; fichiers de suivi et SESSIONS.md mis à jour.
5. **Commit et push sur `dev`** (demande explicite utilisateur, règle C levée) :
   - `feat(T2.1-T2.4): contrats, schémas dynamiques, validation et tests unitaires (phase 2)`
   - `docs(projet): kanban, suivi de tâches T2.1-T2.4 et journal de séance`

### Décisions clés

| # | Décision | Justification |
| --- | --- | --- |
| D20 | T2.4 couvre T2.1 + T2.2 + T2.3 en deux fichiers de tests | Le critère de sortie de la phase 2 est « tout échange inter-étapes typé et testé » (D11) ; les tests unitaires sont regroupés par module testé. |
| D21 | C6 testé via `model_construct` (bypass Pydantic) | Le validateur défensif `_valider_empreintes` ne peut pas être atteint avec un modèle validé normalement (le pattern Pydantic rejette d'abord) ; `model_construct` permet de tester la couche de validation indépendamment. |

### Blocages

Aucun.

### État en fin de séance

- **Phase 2 (Contrats) clôturée côté agent** : T2.1–T2.4 en « En revue » (critère de sortie : tout échange inter-étapes typé et testé — 91 TU passent).
- Branche `dev` : commits poussés (voir `git log`).
- Kanban : 4 tâches en « En revue » (T1.6, T2.1, T2.2, T2.3, T2.4 — en attente de validation utilisateur) ; 1 tâche en « À faire » (T1.7).
- Prochaine étape pressentie : validation utilisateur des tâches en revue, puis **phase 3 (Orchestrateur squelette)** ou **T1.7 (pré-requis OAuth Gmail)** selon la priorité de l'utilisateur.

---

## Séance du 02/11/2026

### Contexte
Reprise après exécution de la partie B de T1.7 sur le poste utilisateur : déplacement du projet dans une nouvelle arborescence, recréation du venv, `python scripts/init_oauth.py` mené à bout, `data/gmail_token.json` renseigné (permissions 600, `data/` ignoré par git). Application Google confirmée « En production » ; `ruff check src tests`, `mypy src` et `python -m pytest tests/unit -v` passent sur le poste (91 TU).

### Actions réalisées

1. **Diagnostic T1.7 partie B** : `ModuleNotFoundError: No module named 'google'` → cause environnementale, pas un bug du dépôt : venv non recréé après déplacement du projet, et dépendances `google-auth` / `google-auth-oauthlib` ajoutées à `pyproject.toml` seulement au commit `63025a2`. Procédure communiquée : supprimer l'ancien venv, `python -m venv .venv`, `.\.venv\Scripts\activate`, `pip install -e ".[dev]"`.
2. **Écran « app non vérifiée »** : confirmé attendu et acceptable (kanban T1.7 partie A — usage perso < 100 utilisateurs, scope `gmail.modify` sensible non restreint) : passage par « Avancé » → « Continuer vers … (non sécurisé) », aucune vérification Google requise. Condition de durabilité du refresh token rappelée : statut « En production » (confirmé par l'utilisateur).
3. **Kanban mis à jour** (sur demande explicite ; **aucun commit**, demande utilisateur) : T1.6, T1.7 et T2.1–T2.4 déplacées vers « Terminé » ; découpage de la phase 3 ajouté en « À faire » (T3.1–T3.4) avec descriptions.

### Décisions clés

| # | Décision | Justification |
| --- | --- | --- |
| D22 | Phase 3 découpée en T3.1 (client Gmail concret + câblage OAuth), T3.2 (cycle de run, checkpoints, idempotence), T3.3 (CLI `tri`/`suppression`/`migrate-labels` + dry-run), T3.4 (run vide de bout en bout) | Reprend le contenu de la phase 3 du plan macro ; le câblage `googleapiclient` (pré-requis T1.7, décision D12) en tête ; dry-run dès la phase 3 (précaution transverse §5). |
| D23 | `google-api-python-client` sera ajouté en T3.1 | Le kanban T1.7 le mentionnait « déjà déclaré », mais `pyproject.toml` ne contient que `google-auth` et `google-auth-oauthlib` ; le câblage SDK relève bien de la phase 3. |

### Blocages

Aucun.

### État en fin de séance

- Kanban : **Terminé** = T1.1–T1.7, T2.1–T2.4 ; **À faire** = T3.1–T3.4 (phase 3, Orchestrateur squelette) ; « En cours » et « En revue » vides.
- Aucun commit effectué (demande explicite de l'utilisateur : pas de commit intermédiaire).
- Prochaine étape : démarrer **T3.1** sur demande explicite de l'utilisateur.

---

## Séance du 02/11/2026 (suite) — T3.1

### Contexte
Début de la phase 3 (Orchestrateur squelette) sur demande explicite de l'utilisateur. Tâche lancée : **T3.1** (client Gmail concret).

### Actions réalisées

1. **Implémentation T3.1** :
   - `pyproject.toml` : ajout de `google-api-python-client`, de `gmail` dans `py-modules`, override mypy `googleapiclient.*` ;
   - `src/gmail.py` (créé) : `charger_credentials` (contrat T1.7, `Credentials.from_authorized_user_info`), `ClientGmailAPI` (protocole `ClientGmail` de `labels.py` + `search_threads` / `get_thread` / `modifier_libelles` / `corbeille`), dry-run des écritures (règle E), garde-fou anti-boucle (`PLAFOND_LECTURES = 100`), fabrique `nouveau_client` typée contre le protocole ;
   - `tests/unit/test_gmail.py` (créé, 17 tests) : faux service googleapiclient, mappage/filtrage, dry-run (écritures non exécutées), plafond, recharge du token (fichier OK / absent / non JSON / non objet), construction via `build` mocké.
2. **Vérification** : `ruff check src tests` OK ; `mypy src` OK (strict, 8 fichiers — 1 itération : `cast` + `type: ignore[no-untyped-call]` sur `from_authorized_user_info`) ; `python -m pytest tests/unit -q` : **108 passed**.
3. **Kanban** : T3.1 déplacée « En cours » → « En revue » ; fichier de suivi `docs/tasks/T3.1_client_gmail_concret.md` créé. **Aucun commit** (règle C — pas de demande explicite).

### Décisions clés

| # | Décision | Justification |
| --- | --- | --- |
| D24 | Le client concret vit dans `src/gmail.py` (complète l'arborescence cible du plan macro) et satisfait le protocole `ClientGmail` de `labels.py` | Le découplage protocole/implémentation (T1.6) permet de mocker Gmail dans les tests sans dépendre de googleapiclient. |
| D25 | Dry-run au niveau client (écritures journalisées, non exécutées), en plus du dry-run du `ResolveurLibelles` | Règle E : aucun appel d'écriture Gmail en dry-run, à tous les niveaux. |

### Blocages

Aucun.

### État en fin de séance

- Kanban : **En revue** = T3.1 (en attente de validation utilisateur) ; **À faire** = T3.2–T3.4.
- Branche `dev` : aucun commit (règle C).
- Prochaine étape : validation utilisateur de T3.1, puis **T3.2** (orchestrateur squelette) sur demande explicite.

---

## Séance du 02/11/2026 (suite) — validation T3.1, puis T3.2

### Contexte
Validation utilisateur de T3.1 (ruff/mypy/pytest OK sur le poste), puis lancement de T3.2 sur demande explicite, avec commit + push autorisés (règle C levée pour cette séance).

### Actions réalisées

1. **Validation T3.1 (étape 6)** : kanban — T3.1 « En revue » → « Terminé » ; board Miro « gmailAgent » synchronisé (15 lignes : T1.1–T3.1 « Fait », T3.2–T3.4 « À faire ») ; `docs/tasks/T3.1_client_gmail_concret.md` complété.
2. **Plan T3.2** (étape 2) puis **implémentation T3.2** :
   - `src/orchestrator.py` (créé) : `Checkpoint` Pydantic + persistance JSON `data/checkpoints/<run_id>.json`, reprise sur incident, `requete_non_lus` (idempotence depuis le registre, clé `suivi.traite`), `lancer_run_tri` étapes 0–7 (stubs phases 4/5/6, dry-run par défaut, rejet → rapport `echec_partiel` persisté + arrêt propre) ;
   - `src/client.py` : `avec_retry` généralisé (prédicat `erreur_retentable` : `SDKError` + `HttpError` 429/5xx) ;
   - `pyproject.toml` : `py-modules += orchestrator` ;
   - `tests/unit/test_orchestrator.py` (créé, 13 tests).
3. **Vérification** : `ruff check src tests` OK (1 itération : 4 lignes > 100 car.) ; `mypy src` OK (strict, 9 fichiers) ; `python -m pytest tests/unit -q` : **121 passed**.
4. **Kanban** : T3.2 « En cours » → « En revue » ; fichier de suivi `docs/tasks/T3.2_orchestrateur_squelette.md` à jour.
5. **Commit et push sur `dev`** : `feat(T3.2)` + `docs(projet)`.

### Décisions clés

| # | Décision | Justification |
| --- | --- | --- |
| D26 | Le squelette T3.2 ne fait aucun appel Mistral (stubs agentiques) | Critère de sortie phase 3 : « un run vide qui tourne de bout en bout » ; pas besoin de `MISTRAL_API_KEY` pour T3.2–T3.4. |
| D27 | `lancer_run_tri` avec dépendances injectables et `dry_run=True` par défaut | Tests unitaires sans token Gmail ni écriture hors tmp ; règle E (aucune écriture Gmail en dry-run). |
| D28 | Rejet = exception relancée après persistance d'un rapport `echec_partiel` avec `etape_fautive` | workflow.md : le rejet est journalisé avec son motif et le run s'arrête ; une synthèse rejetée n'est jamais restituée. |

### Blocages

Aucun.

### État en fin de séance

- Kanban : **Terminé** = T1.1–T1.7, T2.1–T2.4, T3.1 ; **En revue** = T3.2 (attente validation utilisateur) ; **À faire** = T3.3, T3.4.
- Branche `dev` : commits `feat(T3.2)` + `docs(projet)` poussés.
- Prochaine étape : validation utilisateur de T3.2 sur le poste (dry-run réel), puis **T3.3** (CLI + dry-run) sur demande explicite.

---

## Séance du 02/11/2026 (suite) — validation T3.2, plans T3.3/T3.4

### Contexte
Validation utilisateur de T3.2 : ruff/mypy/pytest OK sur le poste + smoke test dry-run réel réussi (checkpoint `2332efc2-…` : 8 étapes validées, `statut_global: "succes"`).

### Actions réalisées

1. **Validation T3.2 (étape 6)** : kanban — T3.2 « En revue » → « Terminé » ; `docs/tasks/T3.2_orchestrateur_squelette.md` complété (validation utilisateur) ; board Miro « gmailAgent » : T3.2 → « Fait ».
2. **Plans T3.3 et T3.4 établis** (étape 2) : `docs/tasks/T3.3_cli_dry_run.md` (CLI argparse `tri`/`suppression`/`migrate-labels`, dry-run par défaut + `--reel`, `[project.scripts]`) et `docs/tasks/T3.4_run_vide_bout_en_bout.md` (tests d'intégration mockés + validation dry-run réelle — critère de sortie phase 3).
3. Aucun commit (règle C — pas de demande explicite pour ces changements de doc).

### Blocages

Aucun.

### État en fin de séance

- Kanban : **Terminé** = T1.1–T1.7, T2.1–T2.4, T3.1, T3.2 ; **À faire** = T3.3, T3.4 ; « En cours »/« En revue » vides.
- Branche `dev` : dernier push `8469a9a` ; modifications doc non commitées.
- Prochaine étape : implémenter **T3.3** sur demande explicite de l'utilisateur.

---

## Séance du 02/11/2026 (suite) — T3.3

### Contexte
Validation utilisateur de T3.2 (smoke test dry-run réel : `succes`). Lancement de T3.3 (CLI + dry-run) sur demande explicite, avec commit + push autorisés.

### Actions réalisées

1. **Validation T3.2 (étape 6)** : kanban T3.2 → « Terminé » ; board Miro T3.2 → « Fait » ; plans T3.3/T3.4 écrits (`docs/tasks/T3.3_cli_dry_run.md`, `T3.4_run_vide_bout_en_bout.md`).
2. **Implémentation T3.3** :
   - `src/cli.py` (créé) : sous-commandes `tri` / `suppression` (stub phase 7) / `migrate-labels ANCIEN NOUVEAU` ; **dry-run par défaut**, `--reel` pour les écritures (accepté avant ou après la sous-commande) ; rapport `RapportFinal` affiché en JSON ; registre validé au démarrage, secrets via `os.environ` uniquement ;
   - `pyproject.toml` : `[project.scripts] gmailagent = "cli:main"`, `py-modules += cli` ;
   - `tests/unit/test_cli.py` (créé, 11 tests) : parsing, dry-run par défaut, `tri` → `lancer_run_tri`, `migrate-labels` dry-run vs `--reel`, libellé inconnu.
3. **Vérification** : `ruff check src tests` OK ; `mypy src` OK (strict, 10 fichiers) ; `pytest tests/unit -q` : **132 passed** (1 itération : bug argparse `--reel` après sous-commande, résolu avec `default=argparse.SUPPRESS`) ; `gmailagent --help` OK.
4. **Kanban** : T3.3 « En cours » → « En revue » ; fichier de suivi à jour.
5. **Commit et push sur `dev`** : `feat(T3.3)` + `docs(projet)`.

### Décisions clés

| # | Décision | Justification |
| --- | --- | --- |
| D29 | Dry-run par défaut côté CLI (`--reel` pour les écritures) | Règle E : aucune écriture Gmail sans validation dry-run préalable ; le run de tri phase 3 ne fait de toute façon que des lectures + création de libellés. |
| D30 | `--reel` accepté avant ET après la sous-commande | UX argparse (parser parent + SUPPRESS côté sous-commande pour ne pas écraser la valeur). |

### Blocages

Aucun.

### État en fin de séance

- Kanban : **Terminé** = T1.1–T1.7, T2.1–T2.4, T3.1, T3.2 ; **En revue** = T3.3 ; **À faire** = T3.4.
- Branche `dev` : commits `feat(T3.3)` + `docs(projet)` poussés.
- Prochaine étape : validation utilisateur de T3.3 sur le poste, puis **T3.4** (run vide de bout en bout) sur demande explicite.

---

## Séance du 02/11/2026 (suite) — validation T3.3

### Contexte
Validation utilisateur de T3.3 (ruff/mypy/pytest OK sur le poste). Question utilisateur sur la commande `gmailagent` (hors venv, hors racine du projet) — réponses vérifiées empiriquement : point d'entrée embarque le python du venv (shebang), chemins projet par défaut résolus en absolu via `__file__` (registre, token, checkpoints), seul `LOG_FILE` par défaut (`logs/gmailagent.log`) est relatif au cwd.

### Actions réalisées

1. **Validation T3.3 (étape 6)** : kanban — T3.3 « En revue » → « Terminé » ; `docs/tasks/T3.3_cli_dry_run.md` complété ; board Miro « gmailAgent » : T3.3 → « Fait ».
2. Aucun commit (règle C — pas de demande explicite pour ces changements de doc).

### Blocages

Aucun.

### État en fin de séance

- Kanban : **Terminé** = T1.1–T1.7, T2.1–T2.4, T3.1–T3.3 ; **À faire** = T3.4 ; « En cours »/« En revue » vides.
- Branche `dev` : dernier push `24ff7c2` ; modifications doc non commitées.
- Prochaine étape : **T3.4** (run vide de bout en bout : tests d'intégration mockés + validation dry-run réelle) sur demande explicite.

---

## Séance du 02/11/2026 (suite) — T3.4

### Contexte
Validation utilisateur de T3.3 (ruff/mypy/pytest OK sur le poste). Questions sur la commande `gmailagent` (hors venv / hors racine) — réponses vérifiées : point d'entrée avec shebang du venv (chemin complet OK sans activation), chemins projet par défaut en absolu via `__file__`, seul `LOG_FILE` par défaut relatif au cwd. Lancement de T3.4 sur demande explicite, avec commit + push autorisés.

### Actions réalisées

1. **Validation T3.3 (étape 6)** : kanban T3.3 → « Terminé » ; board Miro T3.3 → « Fait ».
2. **Implémentation T3.4** : `tests/integration/test_run_vide.py` (créé, 5 tests) — pile réelle CLI/orchestrateur/`ClientGmailAPI` avec faux service googleapiclient : run `tri` complet en dry-run (8 étapes, checkpoint, lectures seules), idempotence (2 runs, même run_id), reprise sur crash (checkpoint partiel), `migrate-labels` dry-run (aucune écriture) vs `--reel` (création libellé + 4 modify). Aucun changement `src/`.
3. **Vérification** : `ruff check src tests` OK (1 itération : 1 ligne > 100 car.) ; `mypy src` OK (strict, 10 fichiers) ; `python -m pytest tests -q` : **137 passed** (132 unit + 5 intégration).
4. **Kanban** : T3.4 « En cours » → « En revue » ; fichier de suivi à jour (validation dry-run réelle restant à faire côté utilisateur, étape 6).
5. **Commit et push sur `dev`** : `test(T3.4)` + `docs(projet)`.

### Décisions clés

| # | Décision | Justification |
| --- | --- | --- |
| D31 | T3.4 = tests d'intégration uniquement (aucun changement src/) | Le squelette (T3.2) et la CLI (T3.3) couvrent déjà le comportement ; T3.4 prouve le critère de sortie phase 3 « un run vide qui tourne de bout en bout » avec Gmail mocké, avant validation dry-run réelle côté utilisateur. |

### Blocages

Aucun.

### État en fin de séance

- Kanban : **Terminé** = T1.1–T1.7, T2.1–T2.4, T3.1–T3.3 ; **En revue** = T3.4 ; **À faire** = phase 4+ (agents).
- Branche `dev` : commits `test(T3.4)` + `docs(projet)` poussés.
- Prochaine étape : validation utilisateur de T3.4 en dry-run réel (`gmailagent tri`), puis clôture de la phase 3 et passage à la **phase 5 (agent classification)** selon l'ordre du plan macro (5 avant 4).

---

## Séance du 02/11/2026 (suite) — validation T3.4, passage à la phase 4

### Contexte
L'utilisateur valide T3.4 (le mécanisme d'idempotence fonctionne : 2e run avec le même `--run-id` journalise « reprise sur incident »). Questions de conception traitées : `--run-id` accepte tout UUID (forme canonique normalisée, rejet des chaînes invalides, pas de traversal de chemin) ; journalisation = fichier unique `logs/gmailagent.log` en append, sans rotation ni purge (décision : laisser en l'état pour l'instant).

### Actions réalisées

1. **Validation T3.4 (étape 6)** : kanban T3.4 → « Terminé » (phase 3 clôturée) ; `docs/tasks/T3.4_run_vide_bout_en_bout.md` complété ; board Miro : T3.4 → « Fait ».
2. **Découpage phase 4 (Agent spam) ajouté au kanban** en « À faire » : T4.1 (prompts + contrats d'outils), T4.2 (runner conversation éphémère `src/agents.py`), T4.3 (branchement étapes 1–2 dans l'orchestrateur), T4.4 (tests + validation de bout en bout). Plans écrits dans `docs/tasks/T4.*.md`.
3. Aucun commit (règle C — pas de demande explicite pour ces changements de doc).

### Décisions clés

| # | Décision | Justification |
| --- | --- | --- |
| D32 | Phase 4 (agent spam) lancée avant la phase 5 (classification), sur choix explicite de l'utilisateur | Écart volontaire à l'ordre du plan macro §4 (5 avant 4, pour valider les contrats sur l'agent le plus représentatif) ; l'utilisateur a choisi la phase 4. |
| D33 | Journalisation : fichier unique append-only `logs/gmailagent.log`, sans rotation ni purge | Tel qu'implémenté (`journalisation.py` FileHandler mode append) ; corrélation par run via le contexte `run_id`. Rotation éventuelle à voir en phase 10. |

### Blocages

Aucun.

### État en fin de séance

- Kanban : **Terminé** = T1.1–T1.7, T2.1–T2.4, T3.1–T3.4 (phase 3 clôturée) ; **À faire** = T4.1–T4.4 (phase 4, Agent spam) ; « En cours »/« En revue » vides.
- Branche `dev` : dernier push `93d8a16` ; modifications doc non commitées.
- Prochaine étape : implémenter **T4.1** sur demande explicite de l'utilisateur.

---

## Séance du 02/11/2026 (suite) — retour à l'ordre initial, plan de la phase 5

### Contexte
L'utilisateur reprend l'ordre initial du plan macro §4 : **phase 5 (classification) avant phase 4 (spam)** (décision D32 révolue). Plan de la phase 5 demandé.

### Actions réalisées

1. **Kanban** : T5.1–T5.5 ajoutés en « À faire » (prioritaires, listés avant T4.1–T4.4 conservés en backlog) avec descriptions + note d'ordre ; plans écrits dans `docs/tasks/T5.*.md`.
2. **Board Miro** : cartes T5.1–T5.5 ajoutées (« À faire », priorité Haute) ; T4.x annotées « après T5.x » ; correction d'un doublon de carte T3.2 (les deux cartes passées en « Fait »).
3. Aucun commit (règle C — pas de demande explicite pour ces changements de doc).

### Décisions clés

| # | Décision | Justification |
| --- | --- | --- |
| D34 | Ordre initial du plan macro §4 restauré : phase 5 (classification) avant phase 4 (spam) | La classification est l'agent le plus représentatif du pattern commun : elle valide les contrats et la validation programmatique (C1–C6 + recalcul des empreintes) avant leur réutilisation par le spam. D32 révolue. |
| D35 | Le runner de conversation éphémère (`src/agents.py`, T5.2) est paramétré par agent et mutualisé ; la phase 4 ne fera plus que le prompt spam + le branchement orchestrateur | Évite la duplication ; les plans T4.2/T4.3 seront révisés en conséquence lors de la phase 4. |

### Blocages

Aucun.

### État en fin de séance

- Kanban : **Terminé** = T1.1–T1.7, T2.1–T2.4, T3.1–T3.4 ; **À faire** = T5.1–T5.5 (prioritaires) puis T4.1–T4.4.
- Branche `dev` : dernier push `93d8a16` ; modifications doc non commitées.
- Prochaine étape : implémenter **T5.1** sur demande explicite de l'utilisateur.

---

## Séance du 02/11/2026 (suite) — phase 5 (T5.1–T5.5)

### Contexte
Ordre initial restauré (D34) : phase 5 (classification) avant phase 4. Implémentation en chaîne T5.1→T5.5 sur demande explicite, commit+push unique en fin de phase si tout est vert.

### Actions réalisées

1. **T5.1** : `src/prompts.py` (créé) — `OUTILS_GMAIL` (allow-list : search_threads, get_thread, get_message, label_message, list_labels) + `prompt_classification` (enums injectés depuis le registre, règles de véracité, déclaration message_id_rfc/empreinte) ; 5 TU. `py-modules += prompts`.
2. **T5.2** : `src/agents.py` (créé) — `lancer_conversation(agent, requete, meta, …)` : conversation éphémère (Mistral `chat.complete`, `avec_retry`, temperature 0.0, max_tokens 1500, response_format strict via `response_format_agent`), boucle tool-calls bornée (garde-fou 50), `executer_outil` vers `ClientGmailAPI` (dry-run = écritures journalisées), puis `extraire_json` → `construire_synthese` → `valider_synthese` (C1–C6) avec `collecter_ids_reels`. Itérations : conversion des tool-calls reçus en `ToolCall` requête (`_vers_tool_call`), gardes mypy (message optionnel, contenu non-str). 8 TU.
3. **T5.3** : `src/dedup.py` (créé) — normalisations (Message-ID, sujet Re/Fwd/Tr, corps base64/quoted-printable/HTML→texte) + `empreinte_sha256` + `empreinte_message` (recalcul depuis une sortie réelle get_thread/get_message, multipart text/plain préféré). 11 TU.
4. **T5.4** : `src/orchestrator.py` — étapes 3–4 réelles : `_lancer_classification` (requête d'idempotence `is:unread -label:"…"`), `_recalculer_empreintes` (rejet C6 si écart — `get_message` ajouté à `src/gmail.py`), `_appliquer_libelles_classification` (catégorie + `suivi.traite`, dry-run par défaut), synthèse dans le checkpoint, rapport avec `synthese_classification`. Dépendances injectables (client_api/client_mistral/conversation) ; résolution Mistral paresseuse. 4 TU (+ mise à jour des TU/TI existants).
5. **T5.5** : `tests/integration/test_agent_classification.py` (créé, 5 tests) — classification ok → libellés posés (réel) / aucune écriture (dry-run) ; empreinte erronée → rejet C6 ; boîte vide → `aucun_message` ; idempotence (agent non rappelé). Itération : ajout de `get_message` à l'allow-list (l'authenticité C3 exige que chaque id de la synthèse provienne d'un argument d'outil).
6. **Vérification** : `ruff check src tests` OK ; `mypy src` OK (strict, 13 fichiers) ; `python -m pytest tests -q` : **172 passed** (137 + 35).
7. **Kanban** : T5.1–T5.5 → « En revue » ; T4.1–T4.4 restent « À faire ». Fichiers de suivi T5.* cochés. Board Miro : T5.1–T5.5 ajoutés « En revue ».
8. **Commit et push sur `dev`** : `feat(T5.1-T5.5)` + `docs(projet)`.

### Décisions clés

| # | Décision | Justification |
| --- | --- | --- |
| D35 | Runner mutualisé paramétré par agent (T5.2), réutilisé en phase 4 | Évite la duplication ; phase 4 = prompt spam + branchement orchestrateur. |
| D36 | `get_message` ajouté à l'allow-list des outils Gmail | C3 (authenticité) : chaque id de la synthèse doit provenir d'un argument d'outil réel ; get_thread ne fournit que le threadId. |
| D37 | Empreintes recalculées par l'orchestrateur via `dedup.empreinte_message` sur `get_message` (rejet C6 si écart) | Conception §3 : règle de véracité sur les clés de dédoublonnage. |

### Blocages

Aucun (3 itérations max respectées à chaque tâche).

### État en fin de séance

- Kanban : **En revue** = T5.1–T5.5 (attente validation utilisateur) ; **À faire** = T4.1–T4.4.
- Branche `dev` : commits `feat(T5.1-T5.5)` + `docs(projet)` poussés.
- Prochaine étape : validation utilisateur de la phase 5 en dry-run réel (`MISTRAL_API_KEY` exportée, `gmailagent tri`), puis **phase 4 (agent spam)**.

---

## Séance du 02/11/2026 (suite) — incidents phase 5 + tâche T3.5

### Contexte
Itérations de validation dry-run réelle de la phase 5 (classification). Quatre incidents réels corrigés et poussés : ToolCall vs ToolExecutionEntry (8cdaf27), payload message nu (eb94d57), prompt trop gros 704k>262k -> aperçus bornés (a0bf854), run_id double CLI/orchestrateur + garde complétude threads (2b3a26c), garde complétude messages (fcdf369), plafond 3 tentatives de synthèse (bfc084d), max_tokens 4000 (81542a8), distinction id Gmail vs message_id_rfc + bornage 25 threads/run (6712704). 183→185 tests.

### Actions réalisées

1. **Question de conception** : la conception (§2.6, §4.1, §2.7) prévoit la planification **externe** (cron/timer, phase 10) et le bornage par run avec reprise au run suivant — pas de boucle interne. Réponse communiquée.
2. **Tâche T3.5 ajoutée au kanban** (« À faire ») : option `gmailagent tri --tout` (boucle de runs jusqu'à épuisement des non lus, plafond de runs, run_id distincts, dry-run par défaut) — alternative ponctuelle au cron pour vider un retard. Plan dans `docs/tasks/T3.5_option_tout.md`.
3. **Conception mise à jour** (`docs/design/conception.md`) : §2.6 (rattrapage volumineux, option `--tout` prévue T3.5) et §4.1 (bornage implémenté à 25 threads/run, référence à `--tout`).
4. Aucun commit (règle C — pas de demande explicite).

### Décisions clés

| # | Décision | Justification |
| --- | --- | --- |
| D38 | Le nom retenu est `--tout` ; la boucle de rattrapage est une option, pas le mode par défaut | Le design retenu mise sur le cron externe (§2.7 « planification externe, sans moteur de workflow ») ; `--tout` n'est qu'une alternative ponctuelle, bornée (plafond de runs). |
| D39 | Bornage implémenté à 25 threads/run (`MAX_THREADS_PAR_RUN`), max_tokens plafonné à 4000 | Ne pas faire croître max_tokens indéfiniment ; la pagination inter-runs absorbe le volume (réponse à la question utilisateur). |

### Blocages

Aucun.

### État en fin de séance

- Kanban : **En revue** = T5.1–T5.5 ; **À faire** = T4.1–T4.4, T3.5.
- Branche `dev` : dernier push `6712704` ; modifications doc (kanban, conception, T3.5, SESSIONS) non commitées.
- Prochaine étape : retest dry-run de la phase 5 avec les correctifs, puis validation ou **phase 4 (agent spam)**.

---

## Séance du 02/11/2026 (suite) — validation phase 5

### Contexte
Dernier correctif poussé : C3 accepte aussi les ids présents dans les résultats d'outils (fffea69). Retest utilisateur : `gmailagent tri` terminé en **succes**, checkpoint avec **13 messages / 12 fils** (run `7e2337c1-71a6-4281-ad89-1aab17c4466b`).

### Actions réalisées

1. **Validation phase 5 (étape 6)** : kanban — T5.1–T5.5 « En revue » → **« Terminé »** (critère de sortie atteint : étapes 3–4 opérationnelles en dry-run réel) ; fichiers de suivi T5.* complétés (validation 02/11/2026) ; board Miro : T5.1–T5.5 → « Fait ».
2. Aucun commit (règle C — pas de demande explicite pour ces changements de doc).

### Décisions clés

| # | Décision | Justification |
| --- | --- | --- |
| D40 | C3 élargi aux ids des résultats d'outils (pas seulement les arguments) | Un message lu via le résultat de get_thread est réellement manipulé ; rejet C3 sinon (faux positif constaté sur un thread à 2 messages). |

### Blocages

Aucun.

### État en fin de séance

- Kanban : **Terminé** = T1.1–T1.7, T2.1–T2.4, T3.1–T3.4, T5.1–T5.5 (phases 1, 2, 3 et 5) ; **À faire** = T4.1–T4.4 (phase 4, agent spam), T3.5 (option --tout).
- Branche `dev` : dernier push `fffea69` ; modifications doc non commitées.
- Prochaine étape : **phase 4 (agent spam)** — T4.1 sur demande explicite.

---

## Séance du 02/11/2026 (suite) — validation T3.1 et plan T3.2

### Contexte
L'utilisateur valide T3.1 sur son poste (`git pull`, `pip install -e ".[dev]"`, puis `ruff`, `mypy`, `pytest` OK) et demande le passage en « Terminé » + le plan d'implémentation de T3.2.

### Actions réalisées

1. **Validation T3.1 (étape 6)** : kanban — T3.1 déplacée « En revue » → **« Terminé »** ; `docs/tasks/T3.1_client_gmail_concret.md` complété (validation utilisateur 02/11/2026). **Aucun nouveau commit** (règle C — pas de demande explicite pour ces seuls changements de doc).
2. **Plan T3.2 établi** (étape 2) : `docs/tasks/T3.2_orchestrateur_squelette.md` créé — sous-tâches (checkpoints JSON + reprise sur incident, requête d'idempotence depuis le registre, cycle de run étapes 0–7 avec stubs agentiques, retry HTTP Gmail, tests unitaires), fichiers prévus (`src/orchestrator.py`, `src/client.py`, `pyproject.toml`, `tests/unit/test_orchestrator.py`), vérifications ruff/mypy/pytest.
3. **Board Miro « gmailAgent »** : état du kanban reporté (T3.1 → Terminé).

### Décisions clés

| # | Décision | Justification |
| --- | --- | --- |
| D26 | Le squelette T3.2 ne fait aucun appel Mistral (stubs agentiques) : le run vide ne requiert pas `MISTRAL_API_KEY` | Critère de sortie phase 3 : « un run vide qui tourne de bout en bout » ; les phases agentiques arrivent en phases 4/5. |

### Blocages

Aucun.

### État en fin de séance

- Kanban : **Terminé** = T1.1–T1.7, T2.1–T2.4, T3.1 ; **À faire** = T3.2–T3.4 ; « En cours »/« En revue » vides.
- Branche `dev` : commits `d8ccfd8` + `dd97034` poussés ; modifications doc (kanban/SESSIONS/suivi) non commitées en attente.
- Prochaine étape : implémenter **T3.2** sur demande explicite de l'utilisateur.

---

## Séance du 03/11/2026 — T4.1 (prompt agent spam)

### Contexte
Reprise du projet **gmailAgent**. Phase 5 (classification) validée (T5.1–T5.5 en « Terminé ») ; la phase en cours est la **phase 4 (agent spam)**. Plan détaillé de T4.1 établi sur demande, puis implémentation lancée sur demande explicite.

### Actions réalisées

1. **Reprise de contexte** : branche `dev` à jour (`aca36a8`), lecture de `AGENTS.md`, `docs/projet/kanban.md`, `docs/projet/plan-macro.md`, `SESSIONS.md`, `docs/tasks/T4.1_prompts_contrats_outils.md`, `src/prompts.py`, `src/contracts.py`, `src/config.py`, `tests/unit/test_prompts.py`.
2. **Plan T4.1 établi (étape 2)** : constat — `OUTILS_GMAIL` (allow-list 5 outils) déjà livré en T5.1 et testé ; schéma strict `SyntheseSpam` + enum `deplaces`/`aucun_message`/`echec_technique` déjà construits (T2.2) et testés (T2.4). Périmètre réel : `prompt_spam(registre)` + tests unitaires.
3. **Kanban** : T4.1 déplacée « À faire » → « En cours ».
4. **Implémentation** : `prompt_spam(registre)` ajouté dans `src/prompts.py` — rôle conservatoire (dossier spam `in:spam`, ne retenir que les messages dont la légitimité est certaine ; en cas de doute, laisser en spam) ; véracité (lecture de chaque thread via `get_thread` avant synthèse) ; clés logiques `suivi.valide-spam`/`suivi.traite` injectées depuis le registre (aucun libellé `Agent/` en dur) ; consigne de ne modifier aucun libellé soi-même (l'orchestrateur appose en T4.3) ; ni envoi ni suppression (corbeille interdite) ; sortie = unique objet JSON racine conforme au schéma strict `SyntheseSpam`.
5. **Tests** : `TestPromptSpam` (5 tests) dans `tests/unit/test_prompts.py` — clés de suivi depuis le registre, aucun libellé physique en dur, conservatisme/véracité/statuts, pas de libellisation par l'agent, objet JSON unique à la racine.
6. **Vérifications (étape 4, 1ère tentative)** : `ruff check src tests` OK ; `mypy src` OK (strict, 13 fichiers) ; `python -m pytest tests -q` : **191 passed** (dont 12 dans `test_prompts.py`).
7. **Kanban** : T4.1 « En cours » → « En revue » (validation agent, étape 5) ; fichier de suivi `docs/tasks/T4.1_prompts_contrats_outils.md` mis à jour. **Aucun commit** (règle C — pas de demande explicite).

### Décisions clés

| # | Décision | Justification |
| --- | --- | --- |
| D41 | T4.1 se réduit au prompt spam + tests ; `OUTILS_GMAIL` réutilisé tel quel (livré en T5.1) | Allow-list identique pour les deux agents (moindre privilège) ; aucun besoin spécifique au spam. |

### Blocages

Aucun.

### État en fin de séance

- Kanban : **En revue** = T4.1 ; **À faire** = T4.2–T4.4, T3.5 ; « En cours » vide.
- Branche `dev` : modifications non commitées (`src/prompts.py`, `tests/unit/test_prompts.py`, `docs/projet/kanban.md`, `docs/tasks/T4.1_prompts_contrats_outils.md`, `SESSIONS.md`) — en attente de commit/push sur demande explicite (règle C).
- Prochaine étape : validation utilisateur de T4.1 (étape 6), puis **T4.2** (dispatch `AGENT_SPAM` dans `_prompt_systeme`, `src/agents.py`) sur demande explicite.

---

## Séance du 03/11/2026 (suite) — T4.2 (branchement agent spam dans le runner)

### Contexte
Poursuite de la phase 4 (agent spam) après T4.1 (prompt spam, « En revue »). Plan de T4.2 établi sur demande (révision D35 : le runner générique `lancer_conversation(agent, ...)` est déjà livré en T5.2), puis implémentation lancée sur demande explicite.

### Actions réalisées

1. **Kanban** : T4.2 déplacée « À faire » → « En cours ».
2. **Implémentation dans `src/agents.py`** :
   - `_prompt_systeme` : branche `AGENT_SPAM` → `prompt_spam(registre)` (T4.1) ; `AGENT_SUPPRESSION` lève encore `AgentInconnuError` (phase 7) ;
   - garde de complétude « messages lus non classés » désormais conditionnée à `AGENT_CLASSIFICATION` : pour le spam, un message lu mais laissé en spam ne figure pas dans la synthèse (conservatisme du prompt T4.1) ; la garde threads (tout thread retourné lu via `get_thread`) reste active pour tous les agents.
3. **Tests** (`tests/unit/test_agents.py`, 7 nouveaux) : sélection du prompt spam + `response_format` `SyntheseSpam` ; conversation spam complète mockée (`deplaces`) ; `aucun_message` ; message lu non retenu accepté pour le spam ; garde threads active pour le spam (refus puis acceptation) ; rejet C3 (id non manipulé) ; suppression toujours sans prompt.
4. **Vérifications (étape 4, 1ère tentative)** : `ruff check src tests` OK ; `mypy src` OK (strict, 13 fichiers) ; `python -m pytest tests -q` : **198 passed** (7 nouveaux, tous verts).
5. **Kanban** : T4.2 « En cours » → « En revue » (étape 5) ; fichier de suivi `docs/tasks/T4.2_runner_conversation_ephemere.md` révisé (constat D35). **Aucun commit** (règle C).

### Décisions clés

| # | Décision | Justification |
| --- | --- | --- |
| D42 | Garde « messages lus non classés » réservée à la classification | Pour le spam, un message lu mais non retenu (laissé en spam) est légitime — le prompt T4.1 impose de ne rien mentionner en cas de doute ; la garde threads suffit. |

### Blocages

Aucun.

### État en fin de séance

- Kanban : **En revue** = T4.1, T4.2 ; **À faire** = T4.3, T4.4, T3.5 ; « En cours » vide.
- Branche `dev` : modifications non commitées (`src/agents.py`, `tests/unit/test_agents.py`, `docs/projet/kanban.md`, `docs/tasks/T4.1_*.md`, `docs/tasks/T4.2_*.md`, `SESSIONS.md`) — en attente de commit/push sur demande explicite (règle C).
- Prochaine étape : validation utilisateur de T4.1/T4.2 (étape 6), puis **T4.3** (branchement des étapes 1–2 dans `src/orchestrator.py` : requête `in:spam`, apposition `suivi.valide-spam`/`suivi.traite`, checkpoint) sur demande explicite.

---

## Séance du 03/11/2026 (suite) — T4.3 (étapes 1–2 spam dans l'orchestrateur)

### Contexte
Poursuite de la phase 4 (agent spam) : T4.1/T4.2 en « En revue ». Plan de T4.3 établi sur demande, implémentation lancée sur demande explicite. Rappel : un **stub** = fonction provisoire à la bonne signature mais au comportement factice (ici : validation de checkpoint sans appel agent).

### Actions réalisées

1. **Kanban** : T4.3 déplacée « À faire » → « En cours ».
2. **Implémentation dans `src/orchestrator.py`** :
   - `_lancer_spam(...)` : miroir de `_lancer_classification` (dépendances injectables `client_api`/`client_mistral`/`conversation`), `Meta(etape="lecture_spam", agent=AGENT_SPAM)`, requête `in:spam`, via `lancer_conversation(AGENT_SPAM, ...)` ;
   - `_appliquer_libelles_spam(...)` : si statut `deplaces`, appose `suivi.valide-spam` + `suivi.traite` + INBOX et retire SPAM par message (`api.modifier_libelles`, dry-run journalisé, règle E ; jamais de corbeille). Constantes `REQUETE_SPAM="in:spam"`, `LABEL_SPAM="SPAM"`, `LABEL_INBOX="INBOX"` (ids système API, hors registre `Agent/`) ;
   - stubs `lecture_spam`/`validation_spam` remplacés : synthèse spam persistée (`checkpoint.syntheses["spam"]`), validation C1–C3 déjà faite dans `lancer_conversation`, rejet → arrêt propre `echec_partiel`/`etape_fautive="lecture_spam"` (chemin existant) ; `synthese_spam` renseigné dans le `RapportFinal` ; docstrings mises à jour.
3. **Tests** :
   - `tests/unit/test_orchestrator.py` : `TestEtapes12Spam` (4 tests) — `deplaces` → `modifier_libelles` avec `ajouter=[L_valspam, L_traite, INBOX]`, `retirer=[SPAM]` (réel) / aucune écriture (dry-run) ; rejet → `echec_partiel` ; reprise sans rappeler l'agent spam ; `syntheses["spam"]` persistée. `_conversation_classifiee` dispatchée (spam → conversation vide) ; `test_reprise_ne_rappelle_pas_lagent` ajusté (2 appels : spam + classification).
   - `tests/integration/test_agent_classification.py` : faux service filtre `in:spam` (`liste_threads_spam`, vide par défaut) + libellé `Agent/valide-spam` ; `_scenario_spam_vide()` préfixé aux scénarios (étape spam réelle avant la classification).
4. **Vérifications (étape 4, 1ère tentative)** : `ruff check src tests` OK ; `mypy src` OK (strict, 13 fichiers) ; `python -m pytest tests -q` : **202 passed** (4 nouveaux, tous verts).
5. **Kanban** : T4.3 « En cours » → « En revue » (étape 5) ; fichier de suivi `docs/tasks/T4.3_orchestrateur_etapes_1_2.md` mis à jour. **Aucun commit** (règle C).

### Décisions clés

| # | Décision | Justification |
| --- | --- | --- |
| D43 | Replacer depuis le spam = retirer SPAM + ajouter INBOX (+ `suivi.valide-spam`, `suivi.traite`) | SPAM/INBOX sont des ids système stables de l'API Gmail, hors registre `Agent/` ; la corbeille reste interdite ici. |

### Blocages

Aucun.

### État en fin de séance

- Kanban : **En revue** = T4.1, T4.2, T4.3 ; **À faire** = T4.4, T3.5 ; « En cours » vide.
- Branche `dev` : modifications non commitées (T4.1+T4.2+T4.3 : `src/prompts.py`, `src/agents.py`, `src/orchestrator.py`, tests, docs) — en attente de commit/push sur demande explicite (règle C).
- Prochaine étape : validation utilisateur de T4.1–T4.3 (étape 6), puis **T4.4** (TI spam de bout en bout + validation dry-run réelle sur la boîte) sur demande explicite. Critère de sortie phase 4 alors atteint : étapes 1–2 opérationnelles.

---

## Séance du 03/11/2026 (suite) — T4.4 (TI spam de bout en bout)

### Contexte
Dernière tâche de la **phase 4 (agent spam)** : T4.1–T4.3 en « En revue ». Plan de T4.4 établi sur demande, implémentation lancée sur demande explicite.

### Actions réalisées

1. **Kanban** : T4.4 déplacée « À faire » → « En cours ».
2. **Nouveau TI `tests/integration/test_agent_spam.py`** (5 tests, pile réelle orchestrateur → `lancer_conversation` avec faux Mistral scénarisé + faux service googleapiclient filtrant `in:spam`) :
   - `deplaces` valide en réel → `messages.modify` avec `ajouter=[L_valspam, L_traite, INBOX]`, `retirer=[SPAM]` ; `syntheses["spam"]` au checkpoint ; 8 étapes validées dans l'ordre (spam avant classification) ;
   - `deplaces` en dry-run → aucune écriture (`modify` non appelé) ;
   - synthèse rejetée (C3, id non manipulé) → `SyntheseInvalideError`, rapport `echec_partiel`, `etape_fautive="lecture_spam"` ;
   - boîte spam vide → `aucun_message`, run `succes` ;
   - idempotence : 2 runs même `run_id` → agent spam non rappelé (aucun appel Mistral au 2e run).
   - **Aucun changement `src/`** (T4.4 = tests + docs, comme prévu).
3. **Vérifications (étape 4, 1ère tentative)** : `ruff check src tests` OK ; `mypy src` OK (strict, 13 fichiers) ; `python -m pytest tests -q` : **207 passed** (5 nouveaux, 5/5 verts).
4. **Kanban** : T4.4 « En cours » → « En revue » (étape 5) ; fichier de suivi `docs/tasks/T4.4_tests_validation_bout_en_bout.md` mis à jour. **Aucun commit** (règle C).

### Décisions clés

Aucune nouvelle (D41–D43 appliquées).

### Blocages

Aucun.

### État en fin de séance

- Kanban : **En revue** = T4.1–T4.4 (phase 4 complète côté code/tests) ; **À faire** = T3.5 ; « En cours » vide.
- Branche `dev` : modifications non commitées (T4.1–T4.4 : `src/prompts.py`, `src/agents.py`, `src/orchestrator.py`, `tests/integration/test_agent_spam.py` nouveau, autres tests, docs) — en attente de commit/push sur demande explicite (règle C).
- Reste pour clôturer la phase 4 (étape 6, règle E, poste utilisateur) : validation dry-run réelle (`MISTRAL_API_KEY` exporté, `gmailagent tri`) puis petit périmètre réel (`--reel` sur quelques spams évidents) → T4.1–T4.4 « Terminé ».
- Prochaine tâche ensuite : **T3.5** (option `gmailagent tri --tout`), puis découpage de la **phase 6 (dédoublonnage)**.

---

## Séance du 03/11/2026 (suite) — README

### Contexte
Question utilisateur : les options de `gmailagent` sont-elles documentées dans un README ? Constat : aucun `README.md` n'existait sur `dev`. Création d'un README à la racine sur demande explicite.

### Actions réalisées

1. **Création de `README.md`** (racine) : présentation, prérequis (Python ≥ 3.11, `MISTRAL_API_KEY`, `data/gmail_token.json` via `scripts/init_oauth.py`), installation (`pip install -e ".[dev]"`), usage CLI complet (`tri [--run-id UUID] [--reel]`, `suppression [--reel]` stub phase 7, `migrate-labels ANCIEN NOUVEAU [--reel]`, `--reel` avant/après sous-commande, dry-run par défaut règle E, note `--tout` prévu mais non implémenté T3.5), tests/qualité (`ruff`, `mypy`, `pytest`), liens vers la doc projet, consigne branche `dev`.
2. **Vérifications** : `ruff check src tests` OK ; `mypy src` OK ; `python -m pytest tests -q` : **207 passed** (inchangé — doc seule).
3. **Aucun commit** (règle C — pas de demande explicite pour ce changement).

### Blocages

Aucun.

### État en fin de séance

- `README.md` non commité, en attente de commit/push sur demande explicite.
- Branche `dev` : dernier push `6174cb7` (T4.1–T4.4).

---

## Séance du 03/11/2026 (suite) — correctif reprise sur incident (discriminateur `agent`)

### Contexte
Validation utilisateur de la phase 4 en dry-run réel. Incident réseau + relance avec `--run-id` : le run repris a terminé en `echec_partiel` à `validation_spam` avec `synthese_spam: null` dans le rapport. Diagnostic confirmé en local : au rechargement du checkpoint, l'union `SyntheseEtape` désérialisait une synthèse spam `aucun_message` (messages vides, statut commun) en `SyntheseClassification` → `isinstance(..., SyntheseSpam)` False → `CheckpointError`. L'agent spam avait répondu `aucun_message` (conservatisme — le message douteux laissé en spam), ce qui déclenchait le bug à la reprise si le crash était survenu entre `lecture_spam` et `validation_spam`.

### Actions réalisées

1. **Correctif dans `src/contracts.py`** : champ racine `agent: Literal[...] = ...` ajouté aux 3 modèles de synthèse (constantes `AGENT_*` passées en `Final`) ; `SyntheseEtape = Annotated[Union[...], Field(discriminator="agent")]` ; `_schema_payload` exclut désormais `("meta", "agent")` du schéma JSON strict (le LLM ne voit pas le champ). `src/validation.py` : `construire_synthese` injecte `agent` dans le payload validé.
2. **Tests** (3 nouveaux) : `test_schema_exclut_meta_et_agent` et `test_union_discriminee_par_agent` (test_contracts) ; `test_reprise_crash_entre_lecture_et_validation_spam` (test_orchestrator — checkpoint avec `lecture_spam` validée + spam `aucun_message`, reprise → `succes`, `synthese_spam` non null).
3. **Vérifications** : `ruff check src tests` OK ; `mypy src` OK (strict, 13 fichiers — littéraux directs dans `Literal[...]` après 1 itération mypy `Final`) ; `python -m pytest tests -q` : **210 passed**. Repro manuel : `aucun_message` rechargé en `SyntheseSpam` (avant : `SyntheseClassification`).
4. **Commit + push sur `dev`** sur demande explicite.

### Décisions clés

| # | Décision | Justification |
| --- | --- | --- |
| D44 | Discriminateur `agent` (champ racine Literal) sur l'union `SyntheseEtape`, exclu du schéma JSON strict | Rechargement de checkpoint non ambigu quel que soit le statut ; le schéma exposé au LLM est inchangé. **Rétrocompatibilité** : les checkpoints antérieurs (sans champ `agent`) sont illisibles → ignorés, le run repart de zéro — sans danger (idempotence par libellés Gmail). |

### Blocages

Aucun.

### État en fin de séance

- Branche `dev` : correctif poussé (voir commit ci-dessus).
- À retester côté utilisateur : relancer `gmailagent tri --run-id <run_id interrompu>` → plus de `CheckpointError`, rapport `succes` avec `synthese_spam` renseigné.

---

## Séance du 03/11/2026 (suite) — validation phase 4, clôture de séance

### Contexte
Retest utilisateur après correctif D44 : `synthese_spam` correctement renseigné (`aucun_message`), run `succes`, 12 non lus de la boîte de réception bien classifiés. Un message légitime abusivement classé en spam par Gmail (resté non lu) n'a pas été retenu par l'agent spam (conservatisme — légitimité non certaine) : comportement attendu, à réévaluer sur de vrais spams ultérieurs. L'utilisateur valide l'ensemble de la phase 4.

### Actions réalisées

1. **Retest du correctif D44** : confirmé — plus de `CheckpointError` à la reprise `--run-id`, rapport `succes` avec `synthese_spam` renseigné.
2. **Kanban (étape 6)** : T4.1, T4.2, T4.3, T4.4 déplacées « En revue » → **« Terminé »** (phase 4 clôturée : étapes 1–2 opérationnelles). Fichiers de suivi T4.1–T4.4 cochés + section Validation (03/11/2026).
3. **Board Miro « gmailAgent »** : cartes T4.1–T4.4 → « Fait ».
4. **Aucun commit** (règle C — pas de demande explicite pour ces changements de doc).

### Décisions clés

| # | Décision | Justification |
| --- | --- | --- |
| D45 | Phase 4 validée avec un spam `aucun_message` (faux négatif conservatoire accepté) | Le conservatisme du prompt spam privilégie l'absence de faux positifs (vrais spams replacés) ; les faux négatifs restent corrigeables manuellement. Comportement à réévaluer sur de vrais spams. |

### Blocages

Aucun.

### État en fin de séance

- Kanban : **Terminé** = T1.1–T1.7, T2.1–T2.4, T3.1–T3.4, T4.1–T4.4, T5.1–T5.5 (phases 1, 2, 3, 4 et 5) ; **À faire** = T3.5 ; « En cours »/« En revue » vides.
- Branche `dev` : derniers pushs `111032e` (fix D44) + `c40b31f` (docs) ; modifications doc de validation non commitées (kanban, suivis T4.x, SESSIONS) — en attente de commit/push sur demande explicite (règle C).
- Prochaine séance : **T3.5** (option `gmailagent tri --tout`) ou découpage de la **phase 6 (dédoublonnage, étape 5)** — au choix de l'utilisateur.

---

## Séance du 04/11/2026 — décision D46 : phase 6 en option post-v1

### Contexte
Reprise du projet **gmailAgent** après validation des phases 4 et 5. Questionnement sur la
justification de la phase 6 (dédoublonnage) : l'utilisateur confirme que les originaux
restent sur leurs serveurs d'origine (laposte.net, orange.fr) et en local (Thunderbird) ;
un doublon intra-Gmail n'apparaît que si un même message RFC entre dans Gmail par deux
chemins (ex. re-routé depuis deux messageries). Décision de passer directement à la phase 7
pour la v1, la phase 6 restant documentée comme option post-v1.

### Actions réalisées

1. **Reprise de contexte** : branche `dev` à jour (`eb6a659`), lecture de `AGENTS.md`,
   `docs/projet/plan-macro.md`, `docs/projet/kanban.md`, `docs/design/conception.md`,
   `docs/design/workflow.md`, `SESSIONS.md`, `README.md`, `src/orchestrator.py`.
2. **Modifications (aucun commit, règle C)** :
   - `docs/projet/plan-macro.md` : phase 6 annotée « option post-v1 » (§3) ; ordre v1 =
     7 → 8 → 9 → 10, phase 6 insérée après (§4), avec rappel des fondations déjà en place ;
   - `docs/design/conception.md` : §3 coiffée d'une note de statut v1 ; tableau §2.2
     (étape 5 = no-op en v1, libellé posé post-v1) ; §2.2 run de suppression (clause
     `Agent/doublon` inerte en v1) ; §1.2 (libellé `Agent/doublon` non posé en v1) ;
   - `docs/design/workflow.md` : nœud A5, tableau du run principal (étape 5), tableau du run
     de suppression (clause inerte en v1) et paragraphe de couplage ;
   - `docs/projet/kanban.md` : note — phase 6 reportée post-v1, aucune tâche T6.x, prochaine
     phase à découper = phase 7 (T7.x) ;
   - `README.md` : présentation, ligne `suppression`, référence aux décisions D1…D46 ;
   - `src/orchestrator.py` : docstring du module + log du stub de l'étape 5
     (« option post-v1, decision D46 »).
3. **Conservés tels quels** (fondations de la phase 6, réutilisées post-v1) : `src/dedup.py`
   et `tests/unit/test_dedup.py` (T5.3), contrôle C6 `_recalculer_empreintes`
   (`src/orchestrator.py`), champs `message_id_rfc`/`empreinte` de `MessageClasse` et
   `nb_doublons` de `RapportFinal` (`src/contracts.py`), déclaration d'empreinte dans le
   prompt classification (`src/prompts.py`), `suivi.doublon` dans `config/labels.yaml`,
   tests associés. Le stub de l'étape 5 (`src/orchestrator.py`) valide l'étape sans rien
   faire : `nb_doublons=0` dans le rapport en v1.

### Décisions clés

| # | Décision | Justification |
| --- | --- | --- |
| D46 | Phase 6 (dédoublonnage) conservée comme option post-v1 : v1 = phases 1–5 + 7–10 ; étape 5 = stub no-op (`nb_doublons=0`), clause `Agent/doublon` du run de suppression inerte en v1 | Tant qu'un même message n'entre pas deux fois dans Gmail, aucun doublon intra-Gmail ; la phase 6 reste un calcul déterministe local et réversible, reportée pour livrer la v1 plus tôt. Fondations (T5.3, C6) déjà en place pour la reprise. |

### Blocages

Aucun.

### État en fin de séance

- Kanban : inchangé (**À faire** = T3.5 ; phases 1–5 en « Terminé ») + note D46 (phase 6
  reportée post-v1, prochaine phase = 7).
- Branche `dev` : modifications non commitées (6 documents + `src/orchestrator.py`) — en
  attente de commit/push sur demande explicite (règle C).
- Prochaine étape : découpage de la **phase 7 (Agent suppression)** en tâches T7.x sur
  demande explicite (T3.5 à choix avant ou après).

---

## Séance du 04/11/2026 (suite) — découpage de la phase 7 (T7.1–T7.4)

### Contexte
Après la décision D46 (phase 6 en option post-v1), découpage de la **phase 7 (Agent suppression)** en tâches, sur demande explicite. Constats préalables : schéma strict `SyntheseSuppression` déjà construit (T2.2 — statuts `supprimes`/`aucun_message`/`echec_technique`, champs `count`/`ids`) ; runner générique `lancer_conversation` paramétré par agent (D35) mais `AGENT_SUPPRESSION` lève encore `AgentInconnuError` dans `_prompt_systeme` ; requête de suppression déjà construite depuis le registre dans `src/cli.py` (`_requete_suppression`, clause `doublon` inerte en v1, D46) ; `ClientGmailAPI.corbeille` + wrapper dry-run (règle E) en place ; commande CLI `suppression` encore un stub.

### Actions réalisées

1. **Kanban** : T7.1–T7.4 ajoutées en « À faire » (avant T3.5) ; note d'en-tête mise à jour (phase 7 découpée, T3.5 à choix avant/après) ; descriptions détaillées en fin de document :
   - **T7.1** — prompt `prompt_suppression(registre)` dans `src/prompts.py` (corbeille uniquement via `TRASH` + outil `label_message`, schéma strict `SyntheseSuppression`, allow-list `OUTILS_GMAIL` réutilisée D41, libellés depuis le registre) + tests `test_prompts.py` ;
   - **T7.2** — branche `AGENT_SUPPRESSION` dans `_prompt_systeme` (`src/agents.py`), runner D35 réutilisé tel quel, garde de complétude `count == len(ids)` + C3 + tests `test_agents.py` ;
   - **T7.3** — `lancer_run_suppression` dans `src/orchestrator.py` (run séparé, checkpoints propres, requête depuis le registre, validation C1–C3 + complétude, rejet → `echec_partiel`, reprise `--run-id`, idempotence `older_than:1h`) et remplacement du stub `_cmd_suppression` dans `src/cli.py` (dry-run par défaut, règle E) + tests `test_orchestrator.py`/`test_cli.py` ;
   - **T7.4** — TI `tests/integration/test_agent_suppression.py` de bout en bout (TRASH réel/journalisé, `aucun_message`, rejet C3, idempotence 2 runs) + validation dry-run réelle puis petit périmètre réel. Critère de sortie phase 7 : pipeline complet.
2. **Aucun changement de code** ; aucun commit (règle C).

### Décisions clés

Aucune nouvelle (D35, D41, D46 appliquées).

### Blocages

Aucun.

### État en fin de séance

- Kanban : **À faire** = T7.1, T7.2, T7.3, T7.4, T3.5 ; phases 1–5 en « Terminé » ; phase 6 reportée post-v1 (D46).
- Branche `dev` : modifications doc non commitées (kanban, SESSIONS, + celles de la séance D46) — en attente de commit/push sur demande explicite (règle C).
- Prochaine étape : **T7.1** (prompt agent suppression) sur demande explicite.

---

## Séance du 04/11/2026 (suite) — commit D46 + plan T7.1

### Contexte
Demande explicite : commit/push des changements en cours (D46 + découpage phase 7), puis
établissement du plan d'implémentation de la tâche T7.1.

### Actions réalisées

1. **Vérifications avant commit** : `ruff check src tests` OK, `mypy src` OK (strict,
   13 fichiers), `pytest tests -q` : **210 passed** ; `git status` : seuls les 7 fichiers
   prévus modifiés, aucun secret (.env/data) dans le diff.
2. **Commit + push sur `dev`** (demande explicite, règles C/H) : commit `015d6d1`
   « docs(projet): D46 phase 6 en option post-v1 + découpage phase 7 (T7.1–T7.4) »
   (7 fichiers, +132/−18) — poussé : `eb6a659..015d6d1 dev -> dev`.
3. **Plan T7.1 établi** (étape 2) : `docs/tasks/T7.1_prompt_suppression.md` créé — constats
   préalables (schéma strict `SyntheseSuppression` déjà construit T2.2, allow-list
   `OUTILS_GMAIL` réutilisée D41, `TRASH` id système hors registre comme D43, requête
   CLI déjà depuis le registre) et plan : `prompt_suppression(registre)` dans
   `src/prompts.py` (run T+1h, véracité, corbeille uniquement via `TRASH`+`label_message`,
   statuts `supprimes`/`aucun_message`/`echec_technique` avec `count`/`ids`, JSON unique à
   la racine) + `TestPromptSuppression` (~6 tests) dans `tests/unit/test_prompts.py`.
4. **Kanban** : T7.1 « À faire » → **« En cours »**.

### Décisions clés

Aucune nouvelle (D35, D41, D43, D46 appliquées).

### Blocages

Aucun.

### État en fin de séance

- Branche `dev` à jour sur origin : `015d6d1`.
- Modifications non commitées : `docs/tasks/T7.1_prompt_suppression.md` (nouveau), kanban
  (T7.1 → En cours), `SESSIONS.md` — en attente de commit/push sur demande explicite (règle C).
- Prochaine étape : **implémentation de T7.1** (prompt suppression + tests) sur demande
  explicite, puis vérifications ruff/mypy/pytest et kanban → « En revue ».

---

## Séance du 04/11/2026 (suite) — T7.1 implémentée (prompt suppression)

### Contexte
Implémentation de la tâche **T7.1** (étape 3) sur demande explicite, selon le plan établi
dans `docs/tasks/T7.1_prompt_suppression.md`.

### Actions réalisées

1. `src/prompts.py` : ajout de `prompt_suppression(registre)` — run de suppression T+1h
   (requête fournie par l'orchestrateur ; clés `suivi.traite`/`suivi.doublon` injectées depuis
   le registre, clause `doublon` inerte en v1 D46) ; véracité (lecture de chaque thread via
   `search_threads`/`get_thread`/`get_message` avant synthèse) ; **corbeille uniquement**
   via `TRASH` + `label_message` (JAMAIS de suppression définitive, ni envoi) ; statuts
   `supprimes`/`aucun_message`/`echec_technique` avec `count == len(ids)` si `supprimes` ;
   sortie = unique objet JSON racine (`statut`, `count`, `ids`). Aucun libellé physique en
   dur ; schéma strict `SyntheseSuppression` inchangé (déjà construit T2.2) ; allow-list
   `OUTILS_GMAIL` réutilisée telle quelle (D41).
2. `tests/unit/test_prompts.py` : `TestPromptSuppression` (6 tests) — clés logiques depuis le
   registre, aucun `Agent/` en dur, statuts/champs/requête `older_than:1h`, corbeille
   uniquement, `count == len(ids)`, JSON unique à la racine.
3. **Vérifications (étape 4, 1ère tentative)** : `ruff check src tests` OK ; `mypy src` OK
   (strict, 13 fichiers) ; `pytest tests -q` : **216 passed** (6 nouveaux, tous verts).
4. **Validation agent (étape 5)** : kanban T7.1 « En cours » → **« En revue »** ; fichier de
   suivi T7.1 coché. **Aucun commit** (règle C).

### Décisions clés

Aucune nouvelle (D41, D43, D46 appliquées).

### Blocages

Aucun.

### État en fin de séance

- Kanban : **En revue** = T7.1 ; **À faire** = T7.2, T7.3, T7.4, T3.5 ; « En cours » vide.
- Branche `dev` : modifications non commitées (`src/prompts.py`, `tests/unit/test_prompts.py`,
  kanban, `docs/tasks/T7.1_prompt_suppression.md`, `SESSIONS.md`) — en attente de commit/push
  sur demande explicite (règle C).
- Prochaine étape : validation utilisateur de T7.1 (étape 6), puis **T7.2** (branchement
  `AGENT_SUPPRESSION` dans `_prompt_systeme`, `src/agents.py`) sur demande explicite.

---

## Séance du 04/11/2026 (suite) — plan T7.2 (branchement runner suppression)

### Contexte
Poursuite des tâches de la phase 7 avant validation utilisateur (décision utilisateur de
faire T7.2–T7.4 d'abord). Plan d'implémentation de **T7.2** établi sur demande explicite.

### Actions réalisées

1. **Constats préalables** (code) : `_prompt_systeme` (`src/agents.py:221-226`) lève
   `AgentInconnuError` pour `AGENT_SUPPRESSION` ; runner générique `lancer_conversation`
   déjà paramétré par agent (D35) ; `valider_synthese` gère déjà `SyntheseSuppression`
   (validation.py : non-contradiction, complétude `count == len(ids)`, authenticité C3) ;
   gardes existantes : threads non lus (tous agents), messages lus non classés
   (classification seule, D42) ; test `test_suppression_toujours_sans_prompt` à faire évoluer.
2. **Plan T7.2** : `docs/tasks/T7.2_branchement_runner_suppression.md` créé — branche
   `AGENT_SUPPRESSION` → `prompt_suppression(registre)` dans `_prompt_systeme` (T7.1) +
   nouvelle garde de complétude action (tout message passé à la corbeille via
   `label_message`/`TRASH` doit figurer dans `ids` de la synthèse `supprimes`, et
   réciproquement ; refus + retry, plafond `MAX_TENTATIVES_SYNTHESE`) + ~6 tests dans
   `tests/unit/test_agents.py` (prompt sélectionné, conversation `supprimes` mockée avec
   schéma `SyntheseSuppression`, `aucun_message`, rejet C3, garde action, garde threads).
3. **Kanban** : T7.2 « À faire » → **« En cours »** (T7.1 reste « En revue »).
4. Aucun changement de code ; aucun commit (règle C).

### Décisions clés

Aucune nouvelle (D35, D42, D46 appliquées).

### Blocages

Aucun.

### État en fin de séance

- Kanban : **En revue** = T7.1 ; **En cours** = T7.2 ; **À faire** = T7.3, T7.4, T3.5.
- Branche `dev` : non commité (`docs/tasks/T7.2_*.md` nouveau, kanban, SESSIONS, + T7.1
  en attente) — en attente de commit/push sur demande explicite (règle C).
- Prochaine étape : **implémentation de T7.2** sur demande explicite.

---

## Séance du 04/11/2026 (suite) — T7.2 implémentée (branchement runner suppression)

### Contexte
Implémentation de la tâche **T7.2** (étape 3) sur demande explicite, selon le plan
`docs/tasks/T7.2_branchement_runner_suppression.md`.

### Actions réalisées

1. `src/agents.py` :
   - `_prompt_systeme` : branche `AGENT_SUPPRESSION` → `prompt_suppression(registre)` (T7.1) ;
     le runner générique `lancer_conversation` est sinon inchangé (D35) ;
   - nouvelle **garde de complétude action** : collecte des `messageId` des appels
     `label_message` avec `TRASH` dans `addLabelIds` (`ids_corbeille`, constante
     `LABEL_TRASH`) ; pour `AGENT_SUPPRESSION`, la synthèse doit satisfaire
     `set(ids) == ids_corbeille` si `statut == "supprimes"`, et `ids_corbeille` vide sinon —
     écart → refus + retry (plafond `MAX_TENTATIVES_SYNTHESE`, puis abandon propre
     `SyntheseInvalideError` « abandon du run »). C1–C3 restent appliqués avant
     (`valider_synthese` gère déjà `SyntheseSuppression`) ; garde threads active pour tous
     les agents, garde « messages lus non classés » toujours réservée à la classification
     (D42).
2. `tests/unit/test_agents.py` : `TestPromptAgents.test_prompt_suppression_selectionne`
   (remplace `test_suppression_toujours_sans_prompt`) + `TestConversationSuppression`
   (6 tests) — conversation `supprimes` complète mockée (schéma `SyntheseSuppression`,
   requête dans le message utilisateur, `messages.modify` non appelé en dry-run),
   `aucun_message`, rejet C3 (id non manipulé), garde action (écart corbeille/ids → refus
   puis accepté après correction), abandon après écarts persistants
   (`2 + MAX_TENTATIVES_SYNTHESE + 1` appels), garde threads active pour la suppression.
3. **Vérifications (étape 4, 1ère tentative)** : `ruff check src tests` OK ; `mypy src` OK
   (strict, 13 fichiers) ; `pytest tests -q` : **222 passed** (6 nouveaux, tous verts).
4. **Validation agent (étape 5)** : kanban T7.2 « En cours » → **« En revue »** ; fichier de
   suivi T7.2 coché. **Aucun commit** (règle C).

### Décisions clés

Aucune nouvelle (D35, D42, D46 appliquées).

### Blocages

Aucun.

### État en fin de séance

- Kanban : **En revue** = T7.1, T7.2 ; **À faire** = T7.3, T7.4, T3.5 ; « En cours » vide.
- Branche `dev` : modifications non commitées (`src/agents.py`, `tests/unit/test_agents.py`,
  kanban, suivis T7.1/T7.2, SESSIONS, + T7.1) — en attente de commit/push sur demande
  explicite (règle C).
- Prochaine étape : **T7.3** (run de suppression dans l'orchestrateur + CLI) — plan à
  établir sur demande explicite.

---

## Séance du 04/11/2026 (suite) — plan T7.3 (run de suppression : orchestrateur + CLI)

### Contexte
Poursuite de la phase 7. Plan d'implémentation de **T7.3** établi sur demande explicite.

### Actions réalisées

1. **Constats préalables** (code) : pattern `lancer_run_tri` à miroir dans
   `src/orchestrator.py` (checkpoints, injections `client`/`client_api`/`client_mistral`/
   `conversation`, `ResolveurLibelles`, rapport `echec_partiel` + `etape_fautive`) ;
   `_requete_suppression` déjà construit depuis le registre dans `src/cli.py` (clause
   `doublon` inerte en v1, D46) ; `_cmd_suppression` encore un stub ; `--run-id` seulement
   sur `tri` ; `RapportFinal` sans champ `synthese_suppression` ; runner suppression
   opérationnel (T7.2) avec C1–C3 + garde action ; `ClientGmailAPI.modifier_libelles` /
   `corbeille` avec wrapper dry-run (règle E) ; test `test_suppression_stub_sans_ecriture`
   à faire évoluer.
2. **Plan T7.3** : `docs/tasks/T7.3_run_suppression_orchestrateur_cli.md` créé —
   `lancer_run_suppression` dans `src/orchestrator.py` (miroir de `lancer_run_tri` :
   étapes demarrage → lecture_suppression → validation_suppression → rapport → fin,
   checkpoints propres, reprise `--run-id`, rejet → `echec_partiel`), nouvelle
   `requete_suppression(registre, resolveur)` (libellés résolus/créés via le resolveur,
   jamais en dur), `_lancer_suppression` (modèle `_lancer_classification`),
   `RapportFinal.synthese_suppression` (champ optionnel, rétro-compatible),
   `src/cli.py` (`_cmd_suppression` réel + `--run-id` sur `suppression`), TU
   (`TestRunSuppression` + évolution du test CLI stub), README. L'agent applique TRASH
   lui-même via `label_message` (journalisé en dry-run) — l'orchestrateur ne fait que
   valider/checkpointer. Idempotence par la requête `older_than:1h` + exclusion corbeille.
3. **Kanban** : T7.3 « À faire » → **« En cours »** (T7.1, T7.2 restent « En revue »).
4. Aucun changement de code ; aucun commit (règle C).

### Décisions clés

Aucune nouvelle (D35, D42, D46 appliquées).

### Blocages

Aucun.

### État en fin de séance

- Kanban : **En revue** = T7.1, T7.2 ; **En cours** = T7.3 ; **À faire** = T7.4, T3.5.
- Branche `dev` : non commité (suivi T7.3 nouveau, kanban, SESSIONS, + T7.1/T7.2 en
  attente) — en attente de commit/push sur demande explicite (règle C).
- Prochaine étape : **implémentation de T7.3** sur demande explicite.

---

## Séance du 04/11/2026 (suite) — T7.3 implémentée (run de suppression : orchestrateur + CLI)

### Contexte
Implémentation de la tâche **T7.3** (étape 3) sur demande explicite, selon le plan
`docs/tasks/T7.3_run_suppression_orchestrateur_cli.md`.

### Actions réalisées

1. `src/orchestrator.py` :
   - `requete_suppression(registre, resolveur)` — requête `label:"<traité>" older_than:1h`
     + `label:"<doublon>"` (clause inerte en v1, D46), libellés résolus/créés via le
     resolveur depuis le registre, jamais en dur (constante `CLE_DOUBLON` ajoutée) ;
   - `_lancer_suppression` (modèle `_lancer_classification`, agent `AGENT_SUPPRESSION`,
     `Meta(etape="lecture_suppression")`) ;
   - `lancer_run_suppression(...)` — miroir de `lancer_run_tri` : étapes `demarrage` →
     `lecture_suppression` → `validation_suppression` → `rapport` → `fin`, checkpoints
     propres, reprise `--run-id`, rejet → `echec_partiel` + `etape_fautive` + checkpoint
     persisté + relance. L'agent applique `TRASH` lui-même via `label_message`
     (journalisé en dry-run, règle E) ; l'orchestrateur ne fait que valider/checkpointer.
2. `src/contracts.py` : `RapportFinal.synthese_suppression: SyntheseSuppression | None =
   None` (rétro-compatible checkpoints).
3. `src/cli.py` : `_cmd_suppression(args, run_id)` réel (appelle `lancer_run_suppression`,
   imprime le rapport JSON, code retour selon `statut_global`), `--run-id` ajouté à la
   sous-commande `suppression`, stub `_requete_suppression` supprimé (construction
   unique dans l'orchestrateur), docstring à jour, imports nettoyés.
4. Tests : `test_orchestrator.py` — `TestRequeteSuppression` (requête depuis le registre)
   + `TestRunSuppression` (bout en bout `supprimes` avec étapes/checkpoint/rapport,
   `aucun_message`, reprise sans rappel de l'agent (1 appel), rejet → `echec_partiel`
   + `etape_fautive="lecture_suppression"`) ; `test_cli.py` — `test_suppression_dry_run_par_defaut`
   / `test_suppression_reel` (monkeypatch `lancer_run_suppression`), `test_run_id_suppression`,
   suppression de l'ancien test stub et de `TestRequeteSuppression` (déplacé côté orchestrateur).
5. `README.md` : ligne `gmailagent suppression` (plus un stub, `[--run-id UUID] [--reel]`).
6. **Vérifications (étape 4, 2 tentatives — 1ʳᵉ : 2 imports inutilisés, corrigés)** :
   `ruff check src tests` OK ; `mypy src` OK (strict, 13 fichiers) ; `pytest tests -q` :
   **228 passed** (+6 nets, tous verts).
7. **Validation agent (étape 5)** : kanban T7.3 « En cours » → **« En revue »** ; fichier de
   suivi T7.3 coché. **Aucun commit** (règle C).

### Décisions clés

Aucune nouvelle (D35, D42, D46 appliquées).

### Blocages

Aucun.

### État en fin de séance

- Kanban : **En revue** = T7.1, T7.2, T7.3 ; **À faire** = T7.4, T3.5 ; « En cours » vide.
- Branche `dev` : modifications non commitées (T7.1–T7.3 : `src/prompts.py`, `src/agents.py`,
  `src/orchestrator.py`, `src/contracts.py`, `src/cli.py`, tests, README, kanban, suivis,
  SESSIONS) — en attente de commit/push sur demande explicite (règle C).
- Prochaine étape : **T7.4** (TI bout en bout `tests/integration/test_agent_suppression.py`
  + validation dry-run réelle) — plan à établir sur demande explicite.

---

## Séance du 04/11/2026 (suite) — T7.4 implémentée (TI suppression) + commit/push phase 7

### Contexte
Implémentation directe de **T7.4** sur demande explicite, puis commit/push demandé
explicitement (règle C levée pour ce commit). La validation utilisateur (dry-run réel +
petit périmètre réel) sera faite ensuite par l'utilisateur (étape 6).

### Actions réalisées

1. **TI `tests/integration/test_agent_suppression.py`** (6 tests, pile réelle
   `lancer_run_suppression` → `lancer_conversation`, faux Mistral scénarisé + faux service
   googleapiclient filtrant la requête `older_than:1h`) : TRASH posé en réel
   (`messages.modify addLabelIds=["TRASH"]`, schéma `SyntheseSuppression`, étapes
   checkpointees, requête passée à `threads.list`) ; dry-run sans aucune écriture ; rejet C3
   → `echec_partiel` + `etape_fautive="lecture_suppression"` ; garde de complétude action
   (écart corbeille/ids → refus puis accepté) ; `aucun_message` ; idempotence (2 runs, même
   `run_id`, agent non rappelé).
2. **Vérifications (étape 4, 3 tentatives — 1ʳᵉ : E501, 2ᵉ : attribut `messages` du faux
   service masquant sa méthode `messages()`, corrigés)** : `ruff check src tests` OK ;
   `mypy src` OK (strict, 13 fichiers) ; `pytest tests -q` : **234 passed** (6 nouveaux TI).
3. **Validation agent (étape 5)** : kanban T7.4 → **« En revue »** (T7.1–T7.4 toutes en
   « En revue ») ; `docs/tasks/T7.4_tests_validation_bout_en_bout.md` créé et coché.
4. **Commit + push sur `dev`** (demande explicite) : voir commit ci-dessous — tout le travail
   T7.1–T7.4 (code + tests + docs) est embarqué.

### Décisions clés

Aucune nouvelle (D35, D42, D46 appliquées).

### Blocages

Aucun.

### État en fin de séance

- Kanban : **En revue** = T7.1, T7.2, T7.3, T7.4 (phase 7 complète côté code/tests) ;
  **À faire** = T3.5 ; « En cours » vide. Phase 6 reportée post-v1 (D46).
- Branche `dev` : poussée (commit phase 7).
- Reste pour clôturer la phase 7 (étape 6, règle E) : validation utilisateur — dry-run réel
  `gmailagent suppression` sur la boîte, puis petit périmètre réel `--reel` — puis
  T7.1–T7.4 → « Terminé » et commit/push des docs de validation sur demande.

---

## Séance du 04/11/2026 (suite) — décision D47 : périmètre et délai de la suppression

### Contexte
Questionnement utilisateur sur la base de sélection de l'agent de suppression (test réel
rendu `aucun_message`). Constats : (1) bug de syntaxe — la requête
`label:"Agent/traité" older_than:1h label:"Agent/doublon"` combine les deux libellés en
**AND** côté Gmail, donc inerte en v1 (aucun `Agent/doublon`, D46) ; (2) aucun garde-fou
sur l'état lu ni sur la catégorie — un message `a-repondre` traité serait éligible ;
(3) le libellé UNREAD n'est jamais retiré par le pipeline. Réponses utilisateur : UNREAD
conservé volontairement (action utilisateur) ; **seule la catégorie `Agent/notification`
est éligible** ; **délai de grâce porté à 24 h** (fonctionnement actuel basé sur la date du
message conservé) ; corbeille uniquement conservé. Correction du AND → OR incluse.

### Actions réalisées

1. **Code** :
   - `src/orchestrator.py` : `requete_suppression` →
     `label:"<traité>" label:"<notification>" older_than:24h OR label:"<doublon>"`
     (constantes `CLE_NOTIFICATION = "classification.notification"`,
     `DELAI_GRACE_SUPPRESSION = "24h"`) — correction du AND→OR + notification seule
     éligible + 24 h ;
   - `src/prompts.py` : `prompt_suppression` — rôle T+24h, requête fournie (notification
     seule éligible, D47, ne JAMAIS trash `classification.a-repondre`/`information`,
     UNREAD jamais retiré), clés logiques injectées depuis le registre ;
   - `src/cli.py` : aide « run de suppression T+24h (notifications uniquement, corbeille) ».
2. **Tests** : `TestRequeteSuppression` (requête exacte, `older_than:24h`, `Agent/notification`,
   `older_than:1h` absent) ; `TestPromptSuppression` (+`test_categorie_notification_seule_eligible`,
   T+24h/older_than:24h) ; constantes `REQUETE_SUPPRESSION` mises à jour (TU agents + TI) ;
   TI : libellé `Agent/notification` servi, assertion `older_than:24h` + `Agent/notification`
   dans la requête.
3. **Docs** : `conception.md` (tableau agents, §2.2 run séparé T+24h + requête OR +
   notification seule éligible + UNREAD jamais retiré, §2.6 idempotence/planification,
   §3 délai 24 h, §4 lissage T+24h) ; `workflow.md` (sous-graphe T+24h, délai 24 h, ligne
   requête) ; `plan-macro.md` (phase 7, §5 précautions) ; `kanban.md` (note phase 7, T7.1,
   T7.3, T7.4) ; `README.md` (ligne `suppression`) ; suivis T3.3/T7.1/T7.3/T7.4.
4. **Vérifications** : `ruff check src tests` OK ; `mypy src` OK (strict, 13 fichiers) ;
   `pytest tests -q` : **235 passed** (+1 test). **Aucun commit** (règle C — pas de demande).

### Décisions clés

| # | Décision | Justification |
| --- | --- | --- |
| D47 | Suppression : requête `label:"Agent/traité" label:"Agent/notification" older_than:24h OR label:"Agent/doublon"` — seule la catégorie `notification` est éligible ; délai de grâce 24 h (date du message, fonctionnement conservé) ; UNREAD jamais retiré par le pipeline (action utilisateur) ; corbeille uniquement conservé. Corrige le bug AND→OR (la clause `doublon`, inerte en v1, rendait la requête vide). | Ne pas risquer de mettre à la corbeille des messages non lus ou auxquels il faut répondre ; 24 h de grâce au lieu d'1 h ; un message déjà en corbeille n'est plus sélectionné (idempotence). |

### Blocages

Aucun.

### État en fin de séance

- Kanban : inchangé (**En revue** = T7.1–T7.4 ; **À faire** = T3.5).
- Branche `dev` : modifications D47 non commitées (code + tests + docs) — en attente de
  commit/push sur demande explicite (règle C). Dernier push : `91577eb`.
- Validation utilisateur en attente : dry-run réel `gmailagent suppression` (vérifier que
  seules les notifications traitées > 24 h sont sélectionnées), puis petit périmètre réel.

---

## Séance du 04/11/2026 (suite) — découpage de la phase 8 (T8.1–T8.3)

### Contexte
La phase 7 (T7.1–T7.4) est maintenue en « En revue » en attendant le test de suppression à
T+24h (délai de grâce, D47) — décision utilisateur. Passage à la **phase 8 (Rapport et
restitution)** : découpage en tâches demandé. Constat : `RapportFinal` existe déjà
(synthèses + `nb_doublons` + statut), le CLI imprime le JSON + une ligne de statut, mais
il n'existe ni module `src/report.py` (emplacement prévu par le plan macro §2), ni résumé
agrégé (`resume`).

### Actions réalisées

1. **Kanban** : T8.1–T8.3 ajoutées en « À faire » (avant T3.5) ; note d'en-tête : phase 8
   découpée (critère de sortie : étape 6 opérationnelle — rapport final JSON + résumé
   console), phase 7 maintenue en « En revue » (test T+24h, D47) ; descriptions détaillées :
   - **T8.1** — contrat : modèle `ResumeRun` (comptes par catégorie/urgence, spam, doublons,
     corbeille, statut) + `RapportFinal.resume` (rétro-compatible) + TU contrats ;
   - **T8.2** — `src/report.py` nouveau (`aggreger` déterministe, `formater_console`),
     branchement étape 6 de `lancer_run_tri`/`lancer_run_suppression`, restitution console
     dans `cli.py` (`_cmd_tri`, `_cmd_suppression`) + TU ;
   - **T8.3** — TU/TI (rapport avec `resume` cohérent, rejet → étape fautive, boîtes vides)
     + validation dry-run réelle. Critère de sortie phase 8 : étape 6 opérationnelle.
2. Aucun changement de code ; aucun commit (règle C).

### Décisions clés

Aucune nouvelle (D46, D47 appliquées).

### Blocages

Aucun.

### État en fin de séance

- Kanban : **En revue** = T7.1–T7.4 (attente test T+24h, D47) ; **À faire** = T8.1, T8.2, T8.3, T3.5.
- Branche `dev` : à jour sur origin (`dad0edb`) ; kanban + SESSIONS non commités — en
  attente de commit/push sur demande explicite (règle C).
- Prochaine étape : plan détaillé puis implémentation de **T8.1** sur demande explicite.

---

## Séance du 04/11/2026 (suite) — plan T8.1 (contrat du résumé agrégé)

### Contexte
Phase 8 (Rapport et restitution). Plan d'implémentation de **T8.1** établi sur demande
explicite. Constats : `RapportFinal` existe (synthèses + `nb_doublons` + statut,
`extra="forbid"`) — un champ optionnel `resume` y est rétro-compatible ; `MessageClasse`
a `categorie` (pattern clé logique) et `urgence` (Literal haute/moyenne/basse) ; style
de tests `test_contracts.py` (classe par modèle, round-trip, rejets) ; `contracts` déjà
dans `py-modules`.

### Actions réalisées

1. **Plan T8.1** : `docs/tasks/T8.1_contrat_resume_agrege.md` créé — modèle `ResumeRun`
   (`extra="forbid"`) : `par_categorie` (clés logiques validées par pattern, valeurs
   `ge=0`), `par_urgence` (haute/moyenne/basse), `spam_deplaces`, `doublons` (0 en v1, D46),
   `corbeille` (ge=0) ; `RapportFinal.resume: ResumeRun | None = None` (rétro-compatible
   checkpoints) + tests `TestResumeRun`/`TestRapportFinal` (round-trip, rejets, rétro-compat).
2. **Kanban** : T8.1 « À faire » → **« En cours »** (T7.1–T7.4 restent « En revue »).
3. Aucun changement de code ; aucun commit (règle C).

### Décisions clés

Aucune nouvelle (D46, D47 appliquées).

### Blocages

Aucun.

### État en fin de séance

- Kanban : **En cours** = T8.1 ; **En revue** = T7.1–T7.4 ; **À faire** = T8.2, T8.3, T3.5.
- Branche `dev` : à jour sur origin (`dad0edb`) ; suivi T8.1 + kanban + SESSIONS non
  commités — en attente de commit/push sur demande explicite (règle C).
- Prochaine étape : **implémentation de T8.1** sur demande explicite.

---

## Séance du 04/11/2026 (suite) — T8.1 implémentée (contrat du résumé agrégé)

### Contexte
Implémentation de **T8.1** (étape 3) sur demande explicite, selon
`docs/tasks/T8.1_contrat_resume_agrege.md`.

### Actions réalisées

1. `src/contracts.py` : modèle `ResumeRun` (`extra="forbid"`) — `par_categorie` (clés
   logiques validées par `_PATTERN_CLE_LOGIQUE` via `field_validator`, valeurs `ge=0`),
   `par_urgence` (clés validées contre `Urgence`, valeurs `ge=0`), `spam_deplaces`,
   `doublons` (0 en v1, D46), `corbeille` (ge=0) ; + `RapportFinal.resume:
   ResumeRun | None = None` — rétro-compatible avec les checkpoints existants.
2. `tests/unit/test_contracts.py` : `TestResumeRun` (6 tests : construction minimale,
   valeurs négatives rejetées, champ interdit rejeté, clé de catégorie invalide, urgence
   invalide, round-trip JSON) + 2 tests `TestRapportFinal` (`resume` absent par défaut =
   rétro-compat, `resume` renseigné → round-trip).
3. **Vérifications (étape 4, 1ère tentative)** : `ruff check src tests` OK ; `mypy src` OK
   (strict, 13 fichiers) ; `pytest tests -q` : **243 passed** (+8, tous verts).
4. **Validation agent (étape 5)** : kanban T8.1 « En cours » → **« En revue »** ; suivi T8.1
   coché. **Aucun commit** (règle C).

### Décisions clés

Aucune nouvelle (D46, D47 appliquées).

### Blocages

Aucun.

### État en fin de séance

- Kanban : **En revue** = T7.1–T7.4, T8.1 ; **À faire** = T8.2, T8.3, T3.5 ; « En cours » vide.
- Branche `dev` : non commité (`src/contracts.py`, `tests/unit/test_contracts.py`, kanban,
  suivi T8.1, SESSIONS) — en attente de commit/push sur demande explicite (règle C).
  Dernier push : `dad0edb`.
- Prochaine étape : plan puis implémentation de **T8.2** (`src/report.py` + étape 6 +
  restitution console CLI) sur demande explicite.

---

## Séance du 04/11/2026 (suite) — plan T8.2 (report.py : agrégation + restitution)

### Contexte
Phase 8. Plan d'implémentation de **T8.2** établi sur demande explicite. Constats :
`ResumeRun` + `RapportFinal.resume` livrés en T8.1 ; les étapes `ETAPE_RAPPORT` de
`lancer_run_tri`/`lancer_run_suppression` construisent déjà le `RapportFinal` ;
`py-modules` à compléter (`report`) ; CLI imprime JSON + ligne de statut.

### Actions réalisées

1. **Plan T8.2** : `docs/tasks/T8.2_report_agregation_restitution.md` créé —
   `src/report.py` nouveau : `aggreger(syntheses, nb_doublons) -> ResumeRun` (déterministe :
   classification → par_categorie/par_urgence, spam deplaces → spam_deplaces, suppression
   supprimes → corbeille, doublons = nb_doublons) et `formater_console(rapport) -> str`
   (résumé lisible, statut + étape fautive si rejet, aucun libellé physique en dur) ;
   `pyproject.toml` += "report" ; orchestrateur : étape `ETAPE_RAPPORT` des deux runs avec
   `resume=aggreger(...)` ; `cli.py` : `_cmd_tri`/`_cmd_suppression` impriment le résumé
   console après le JSON ; TU (`test_report.py` nouveau + orchestrateur + CLI).
2. **Kanban** : T8.2 « À faire » → **« En cours »** (T7.1–T7.4, T8.1 restent « En revue »).
3. Aucun changement de code ; aucun commit (règle C).

### Décisions clés

Aucune nouvelle (D46, D47 appliquées).

### Blocages

Aucun.

### État en fin de séance

- Kanban : **En cours** = T8.2 ; **En revue** = T7.1–T7.4, T8.1 ; **À faire** = T8.3, T3.5.
- Branche `dev` : suivi T8.2 + kanban + SESSIONS non commités — en attente de commit/push
  sur demande explicite (règle C). Dernier push : `dad0edb`.
- Prochaine étape : **implémentation de T8.2** sur demande explicite.

---

## Séance du 04/11/2026 (suite) — T8.2 implémentée (report.py : agrégation + restitution console)

### Contexte
Implémentation de **T8.2** (étape 3) sur demande explicite, selon
`docs/tasks/T8.2_report_agregation_restitution.md`.

### Actions réalisées

1. `src/report.py` (nouveau, `py-modules += "report"`) : `aggreger(syntheses,
   nb_doublons) -> ResumeRun` (déterministe : classification → par_categorie/par_urgence,
   spam `deplaces` → spam_deplaces, suppression `supprimes` → corbeille, doublons) ;
   `formater_console(rapport) -> str` (résumé lisible : statut + étape fautive si rejet,
   spam/classés par catégorie et urgence/corbeille/doublons — clés logiques uniquement,
   aucun `Agent/` en dur).
2. `src/orchestrator.py` : étape `ETAPE_RAPPORT` de `lancer_run_tri` et
   `lancer_run_suppression` → `resume=aggreger(checkpoint.syntheses, nb_doublons=0)`.
3. `src/cli.py` : `_cmd_tri` / `_cmd_suppression` impriment `formater_console(rapport)`
   après le JSON (ligne `run <id> terminé : <statut>` conservée).
4. Tests : `tests/unit/test_report.py` (8 tests : aggreger tri complet/aucun_message/
   suppression/echec, formater succes/echec_partiel/sans resume/corbeille, pas de `Agent/`
   en dur) ; `test_orchestrator.py` `TestResumeRapport` (2 tests : resume des deux runs) ;
   `test_cli.py` `TestResumeConsole` (2 tests : résumé affiché pour `tri` et `suppression`).
5. **Vérifications (étape 4, 2 tentatives — 1ʳᵉ : E501 sur une signature, corrigé)** :
   `ruff check src tests` OK ; `mypy src` OK (strict, 14 fichiers) ; `pytest tests -q` :
   **255 passed** (+12, tous verts).
6. **Validation agent (étape 5)** : kanban T8.2 « En cours » → **« En revue »** ; suivi T8.2
   coché. **Aucun commit** (règle C).

### Décisions clés

Aucune nouvelle (D46, D47 appliquées).

### Blocages

Aucun.

### État en fin de séance

- Kanban : **En revue** = T7.1–T7.4, T8.1, T8.2 ; **À faire** = T8.3, T3.5 ; « En cours » vide.
- Branche `dev` : non commité (T8.1+T8.2 : `src/contracts.py`, `src/report.py`,
  `src/orchestrator.py`, `src/cli.py`, `pyproject.toml`, tests, kanban, suivis, SESSIONS) —
  en attente de commit/push sur demande explicite (règle C). Dernier push : `dad0edb`.
- Prochaine étape : **T8.3** (TU/TI de bout en bout du rapport + validation dry-run réelle)
  sur demande explicite.

---

## Séance du 04/11/2026 (suite) — T8.3 implémentée + commit/push phase 8

### Contexte
Implémentation directe de **T8.3** sur demande explicite, puis commit/push demandé
explicitement (règle C levée pour ce commit). Validation utilisateur (dry-run réel) à faire
ensuite par l'utilisateur (étape 6).

### Actions réalisées

1. **TI complétés** (assertions `resume` dans les rapports) : `test_agent_classification.py`
   (`par_categorie == {"classification.a-repondre": 1}`, `par_urgence == {"haute": 1}` ;
   boîte vide → resume à zéro) ; `test_agent_spam.py` (`spam_deplaces == 1`,
   `par_categorie == {}`) ; `test_agent_suppression.py` (`corbeille == 1`).
2. **Vérifications (étape 4, 1ère tentative)** : `ruff check src tests` OK ; `mypy src` OK
   (strict, 14 fichiers) ; `pytest tests -q` : **255 passed**.
3. **Validation agent (étape 5)** : kanban T8.3 → **« En revue »** (phase 8 complète côté
   code/tests : T8.1–T8.3) ; `docs/tasks/T8.3_tests_validation_bout_en_bout.md` créé et coché.
4. **Commit + push sur `dev`** (demande explicite) : voir commit ci-dessous — T8.1–T8.3
   embarqués.

### Décisions clés

Aucune nouvelle (D46, D47 appliquées).

### Blocages

Aucun.

### État en fin de séance

- Kanban : **En revue** = T7.1–T7.4 (attente test suppression T+24h, D47), T8.1, T8.2, T8.3 ;
  **À faire** = T3.5 ; « En cours » vide. Phase 6 reportée post-v1 (D46).
- Branche `dev` : poussée (commit phase 8).
- Validation utilisateur en attente : dry-run réel `gmailagent tri` (vérifier JSON + résumé
  console) et `gmailagent suppression` (dry-run), puis T8.1–T8.3 → « Terminé » sur demande.

---

## Séance du 04/11/2026 (suite) — journalisation : bornes de run dans gmailagent.log

### Contexte
Demande utilisateur (modification mineure) : `logs/gmailagent.log` est unique pour toutes
les exécutions ; introduire une séparation lisible. Variante retenue après discussion :
conserver le fichier unique et encadrer chaque run par une ligne d'en-tête et une ligne de
pied de page horodatées (plutôt que des fichiers par run).

### Actions réalisées

1. `src/journalisation.py` : `configurer(run_id)` émet désormais une ligne
   `evenement="debut_run"` (le `run_id` est déjà lié via contextvars, timestamp ISO déjà
   présent) ; nouvelle fonction `marquer_fin_run(statut)` émettant
   `evenement="fin_run", statut=...`.
2. `src/cli.py` : `marquer_fin_run(rapport.statut_global)` appelé en fin de `_cmd_tri` et
   `_cmd_suppression`.
3. Test : `tests/unit/test_journalisation.py` (nouveau) — en-tête `debut_run` en première
   ligne avec `run_id` + timestamp, pied `fin_run` avec `statut` en dernière ligne, lignes
   de run au milieu.
4. `README.md` : note sur les bornes de run filtrables (`jq select(.evenement==...)`).
5. **Vérifications (2 tentatives — 1ʳᵉ : E741 variable `l`, renommée)** : `ruff check src
   tests` OK ; `mypy src` OK (strict, 14 fichiers) ; `pytest tests -q` : **256 passed** (+1).
6. **Commit + push sur `dev`** (demande explicite) : voir commit ci-dessous.

### Décisions clés

Aucune nouvelle (D46, D47 appliquées).

### Blocages

Aucun.

### État en fin de séance

- Kanban : inchangé (**En revue** = T7.1–T7.4, T8.1–T8.3 ; **À faire** = T3.5).
- Branche `dev` : poussée (commit bornes de run).

---

## Séance du 04/11/2026 (suite) — T9.1 : plan de tests + critères d'acceptation (CI écartée, D48)

### Contexte
Phase 9 (Tests). Question utilisateur sur la logique d'un plan de test rédigé après les
tests : réponse — le plan amont était distribué (plan macro + critères par tâche au
kanban, tests écrits par phase avec le code) ; le document de phase 9 est une
consolidation/traçabilité + audit de couverture honnête. La CI (GitHub Actions) est
écartée sur décision utilisateur : projet réduit, commandes de qualité lancées
manuellement.

### Actions réalisées

1. **Kanban** : T9.1 inscrite (plan de tests consolidé + critères d'acceptation ; CI
   écartée D48), passée « En cours » puis **« En revue »** ; note d'en-tête phase 9.
2. **`tests/plan_tests.md`** (nouveau) : conventions (fixtures mockées, aucun appel
   réseau, dry-run, secrets, commandes de qualité manuelles), recensement fidèle par
   fichier — 235 TU + 21 TI = 256 tests (vérifié par `pytest --collect-only`) — mapping
   fichier ↔ tâches ↔ critères, couverture par critère transverse, hors-périmètre
   (validation réelle manuelle, règle E ; phase 6 post-v1 D46).
3. **`docs/test/acceptation.md`** (nouveau) : critères de sortie par phase avec état de
   validation au 04/11/2026 (phases 1–5 validées ; 6 = option post-v1 D46 ; 7 = code/tests
   ✔, validation réelle en attente du délai 24 h D47 ; 8 = code/tests ✔ + dry-run réel
   constaté ; 9 = ce document ; 10 = hors périmètre v1) + critères transverses (règle E,
   corbeille uniquement, UNREAD jamais retiré D47, registre, véracité C1–C6, idempotence,
   qualité ruff/mypy/pytest 256 tests).
4. **Vérifications** : décompte doc conforme (`pytest --collect-only` : 235 + 21 = 256) ;
   `pytest tests -q` : **256 passed**. **Aucun commit** (règle C — pas de demande).

### Décisions clés

| # | Décision | Justification |
| --- | --- | --- |
| D48 | CI (GitHub Actions) écartée : commandes de qualité (`ruff`, `mypy`, `pytest`) lancées manuellement | Projet réduit, mono-développeur ; la CI n'apporte pas de valeur ici. Phase 9 = doc de test seule (T9.1). |

### Blocages

Aucun.

### État en fin de séance

- Kanban : **En revue** = T7.1–T7.4 (attente T+24h, D47), T8.1–T8.3, T9.1 ; **À faire** = T3.5.
- Branche `dev` : non commité (`tests/plan_tests.md`, `docs/test/acceptation.md`, kanban,
  SESSIONS) — en attente de commit/push sur demande explicite (règle C). Dernier push :
  `a109d61`.
