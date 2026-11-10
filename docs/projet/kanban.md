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
T9.6
T9.7
T9.8
T9.9

## En cours

## En revue

## Terminé
T1.1
T1.2
T1.3
T1.4
T1.5
T1.6
T1.7
T2.1
T2.2
T2.3
T2.4
T3.1
T3.2
T3.3
T3.4
T3.5
T4.1
T4.2
T4.3
T4.4
T5.1
T5.2
T5.3
T5.4
T5.5
T7.1
T7.2
T7.3
T7.4
T8.1
T8.2
T8.3
T9.1
T9.2
T9.3
T9.4
T9.5


## Annulé


---

# Description des tâches

> Tâches triées par ordre numérique d'identifiant. L'état d'avancement de chaque tâche est indiqué dans le tableau ci-dessus. Les tâches T1.x correspondent à la **phase 1 (Fondations)** du [plan macro](plan-macro.md) (critère de sortie : package installable, configuration validée au démarrage ; T1.7 documente le pré-requis OAuth Gmail, câblage en phase 3) ; les tâches T2.x à la **phase 2 (Contrats)** (critère de sortie : tout échange inter-étapes typé et testé) ; les tâches T3.x à la **phase 3 (Orchestrateur squelette)** (critère de sortie : un run vide qui tourne de bout en bout, dry-run sans aucun appel d'écriture Gmail) ; les tâches T4.x à la **phase 4 (Agent spam)** (critère de sortie : étapes 1–2 opérationnelles — lecture spam, validation, apposition `Agent/valide-spam`) ; les tâches T5.x à la **phase 5 (Agent classification)** (critère de sortie : étapes 3–4 opérationnelles — lecture non lus, validation IDs + empreintes recalculées, apposition catégorie + `Agent/traité`) ; les tâches T7.x à la **phase 7 (Agent suppression)** (critère de sortie : pipeline complet — run de suppression T+24h séparé, corbeille uniquement, notifications seules éligibles (D47)) ; les tâches T8.x à la **phase 8 (Rapport et restitution)** (critère de sortie : étape 6 opérationnelle — rapport final JSON + résumé console). **Ordre de priorité : T5.x avant T4.x** (plan macro §4 — décision D34). La **phase 6 (dédoublonnage) est reportée post-v1** (décision D46) : aucune tâche T6.x n'est créée pour l'instant, l'étape 5 du run reste un stub no-op en v1 ; T3.5 (`--tout`) passe à choix avant ou après la phase 7. La **phase 7 (T7.1–T7.4) est passée en « Terminé »** le 10/11/2026 sur décision utilisateur (test de suppression à T+24h, délai de grâce D47, à valider en conditions réelles). La **phase 9 (Tests)** se réduit à la tâche T9.1 : plan de tests consolidé (`tests/plan_tests.md`) + critères d'acceptation (`docs/test/acceptation.md`) — la CI (GitHub Actions) est écartée sur décision utilisateur (D48 : projet réduit, commandes de qualité lancées manuellement). **T9.2** est un correctif de robustesse rattaché à cette phase (incident réel 10/11/2026) : erreurs d'outils renvoyées au modèle dans le runner au lieu d'interrompre le run. **T9.3** poursuit sur le 2e volet du même incident : synthèse invalide rebouclée vers le modèle + `message_id_rfc` normalisé. **T9.4** rend cohérentes les bornes du run (cap de recherche dérivé du budget d'appels via le nouveau paramètre `marge_appels_reprise`, budget explicite donné au modèle) ; **T9.5** (analyse des axes de simplification) est **Terminé** — note de synthèse `docs/design/simplification.md`, toutes les simplifications approuvées (D60) ; **T9.6** reprend ses conclusions à implémenter plus tard (simplifications + idempotence du spam) ; **T9.7/T9.8** en sont les volets codés (validation classification en une passe ; unification des mécanismes de refus dans le runner) ; **T9.9** : remise à plat de l'arborescence et des documents du projet (lisibilité humaine).

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

## T1.7 — Fondations : Pré-requis OAuth Gmail (configuration + script one-shot)
**Partie A — configuration côté Google Cloud (à réaliser par l'utilisateur, avant la phase 3) :**
1. Créer un projet Google Cloud ([console.cloud.google.com](https://console.cloud.google.com)), activer l'**API Gmail** (API et services > Bibliothèque).
2. Configurer l'**écran de consentement OAuth** (Google Auth Platform > Écran de consentement) : type utilisateur **Externe**, puis **« Publier l'application »** (statut « En production ») — **obligatoire** : en « Testing », le refresh token expire après 7 jours. Sans vérification Google (usage perso < 100 utilisateurs), l'écran « app non vérifiée » s'affiche au consentement : acceptable. Scopes : `gmail.modify` uniquement (lecture, libellés, corbeille) ; `gmail.send` **exclu** (moindre privilège).
3. Créer les identifiants (Google Auth Platform > **Clients** > Créer un client > **Application de bureau**) → `client_id` + `client_secret` à renseigner dans `.env` (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` — `.env` ignoré par git).

**Partie B — premier flux d'autorisation (une seule fois, manuel) :**
Exécuter `python scripts/init_oauth.py` (script one-shot livré) : ouvre le consentement Google dans le navigateur (`access_type=offline`, `prompt=consent` → le code d'autorisation `?code=...` n'apparaît que dans l'URL de redirection, il est échangé automatiquement et **n'intervient jamais dans les appels API**), échange le code contre `access_token` (1 h) + `refresh_token` (long terme), et stocke le résultat dans `data/gmail_token.json` (permissions 600, dossier `data/` ignoré par git). Garde-fous : échec propre si variables manquantes, si le fichier existe déjà, ou si aucun refresh token n'est reçu. Le fichier produit est rechargeable via `Credentials.from_authorized_user_info` (contrat avec la phase 3).

**Workflow ensuite (automatique, à chaque run)** : l'orchestrateur charge `data/gmail_token.json`, présente l'`access_token` à l'API Gmail (`Authorization: Bearer ...`), et le renouvelle toutes les heures via `grant_type=refresh_token` (`google-auth` gère le rafraîchissement). Le refresh token n'a **pas d'expiration calendaire** en « En production » ; il est invalidé si : révocation par l'utilisateur, 6 mois d'inactivité, changement de mot de passe Google (scopes Gmail), ou plafond ~50 tokens actifs par compte/client. En cas d'invalidation → retour à la Partie B.

**Hors périmètre** : le câblage `googleapiclient` (`google-api-python-client`, `google-auth`, `google-auth-oauthlib` — dépendances déjà déclarées) relève de la phase 3.

## T2.1 — Contrats : Modèles Pydantic et enveloppe
Créer `src/contracts.py` : modèles Pydantic `MessageClasse`, `SyntheseEtape`, `RapportFinal` et enveloppe commune `meta` (`run_id`, `etape`, `agent`, `timestamp`). Typage strict (pas de `Any` non justifié) ; la sérialisation JSON alimente les checkpoints et le rapport final.

## T2.2 — Contrats : Schémas JSON dynamiques des agents
Dans `src/contracts.py`, construire les schémas JSON stricts (`strict: true`, `additionalProperties: false`) des trois agents (classification, spam, suppression), avec les `enum` de catégorie et d'urgence construits dynamiquement à partir du registre de libellés (`config/labels.yaml`) — jamais de nom de libellé physique en dur.

## T2.3 — Contrats : Validation programmatique
Créer `src/validation.py` : fonctions reprises des scripts de référence — `collecter_ids_reels` (identifiants réellement manipulés par les outils), `valider_synthese` (cohérence, authenticité, complétude), `extraire_json` (extraction robuste du premier objet JSON bien formé). Appliquées par l'orchestrateur à chaque synthèse d'étape.

## T2.4 — Contrats : Tests unitaires
Créer `tests/unit/test_contracts.py` et `tests/unit/test_validation.py` : validation des modèles (champs requis, enums dynamiques issus du registre), sérialisation/désérialisation, rejet des synthèses incohérentes (statut échec avec messages, IDs inconnus, JSON malformé). *(La phase 9 initialisera `tests/plan_tests.md` et couvrira l'ensemble du pipeline : fixtures de conversations mockées, mode dry-run, CI.)*

## T3.1 — Orchestrateur squelette : Client Gmail concret (câblage OAuth + API)
Ajouter `google-api-python-client` à `pyproject.toml` (absent malgré la mention « déjà déclarées » de T1.7). Nouveau module `src/gmail.py` : chargement de `data/gmail_token.json` via `Credentials.from_authorized_user_info` (contrat T1.7), refresh automatique (google-auth), service Gmail ; implémentation du protocole `ClientGmail` de `src/labels.py` (`list_labels`, `create_label`) et des opérations du pipeline : `search_threads` (requête d'idempotence `is:unread -label:"Agent/traité"`), `get_thread`, `modify` (add/remove de libellés), `trash` (corbeille uniquement). Wrapper dry-run (écritures journalisées, non exécutées — règle E) et garde-fou anti-boucle (plafond d'appels en lecture). Tests unitaires avec client mocké.

## T3.2 — Orchestrateur squelette : Cycle de run, checkpoints, idempotence
`src/orchestrator.py` : `run_id`, démarrage du run, checkpoints JSON persistés à chaque étape validée + reprise sur incident ([workflow](../design/workflow.md)), squelette des étapes 0–7 du run principal avec emplacements pour les phases agentiques (phases 4–7), rapport final (stub), fin de run. Retry 3 tentatives, backoff exponentiel avec jitter sur 429/5xx (réutilisation de `src/client.py`).

## T3.3 — Orchestrateur squelette : CLI et mode dry-run
`src/cli.py` : commandes `tri`, `suppression`, `migrate-labels`, option `--dry-run` (dry-run dès la phase 3 — précaution transverse du plan macro). Registre `config/labels.yaml` validé au démarrage (`src/config.py`), secrets lus via `os.environ` uniquement (règle D), journalisation structurée (`src/journalisation.py`).

## T3.4 — Orchestrateur squelette : Run vide de bout en bout (critère de sortie)
Exécution réelle de `tri` en dry-run sur la boîte de l'utilisateur (lecture seule, aucune écriture Gmail) : vérification des checkpoints, du rapport final JSON, de l'idempotence (2 runs successifs) et de la reprise sur incident (arrêt + relance) ; tests d'intégration avec Gmail mocké. Sortie de phase 3 : un run vide qui tourne de bout en bout.

## T4.1 — Agent spam : Prompts et contrats d'outils Gmail
`src/prompts.py` (nouveau) : prompt conservatoire de l'agent spam (versionné avec le code ; aucun nom de libellé physique en dur — libellés injectés depuis `config/labels.yaml`), règles de véracité, conservatisme (ne replacer depuis le spam que les messages dont la légitimité est certaine). Schémas JSON des outils Gmail `search_threads` / `get_thread` / `label_message` / `list_labels` (allow-list, moindre privilège — §2.4 de la conception). Tests : prompt sans libellé en dur, schémas conformes.

## T4.2 — Agent spam : Runner de conversation éphémère
`src/agents.py` (nouveau) : pattern conversation éphémère (synchrone, script de référence `02b`) — appel Mistral via `client.obtenir_client` + `avec_retry` (timeout 300 s), `response_format_agent(AGENT_SPAM, registre)` strict, `temperature=0.0`, `max_tokens` cap, outils en allow-list ; boucle tool-calls jusqu'à la synthèse ; `extraire_json` + `construire_synthese` + `valider_synthese` (C1–C6) + `collecter_ids_reels` ; exécution des outils contre `ClientGmailAPI` (`search_threads` paginé max 50/run, `get_thread`, `label_message` → `modifier_libelles`). Tests : client Mistral mocké (fixtures SDK), faux service Gmail.

## T4.3 — Agent spam : Branchement des étapes 1–2 dans l'orchestrateur
Dans `src/orchestrator.py`, remplacer les stubs `lecture_spam` / `validation_spam` : conversation agent spam sur la requête `in:spam`, validation de la synthèse, si ok apposition de `Agent/valide-spam` (et `Agent/traité`) sur les messages déplacés via le resolveur + `modifier_libelles` (dry-run journalisé, règle E), checkpoint de la synthèse ; rejet → arrêt propre (déjà en place).

## T4.4 — Agent spam : Tests et validation de bout en bout
TU (prompts, agents, orchestrateur) + TI mockés (`tests/integration`) : run complet avec agent spam mocké — synthèse valide → libellés posés (dry-run journalisé / appliqués en `--reel`) ; synthèse rejetée → arrêt propre + rapport `echec_partiel`. Validation dry-run réelle sur la boîte (règle E), puis petit périmètre réel. Critère de sortie phase 4 : étapes 1–2 opérationnelles. Vérifications ruff/mypy/pytest, kanban → En revue, commit/push sur demande explicite.

## T3.5 — Orchestrateur squelette : option `--tout` (boucle de runs jusqu'à épuisement)
Option CLI `gmailagent tri --tout` : enchaîne les runs tant que `search_threads` renvoie des threads non lus (rattrapage d'un gros retard sans attendre le cron), avec **plafond de runs par invocation** (garde-fou, ex. 10) et un `run_id` distinct par run (checkpoints indépendants, idempotence par libellé `Agent/traité` entre les runs). Alternative documentée au cron externe (conception §2.6/§4.1) pour le rattrapage ponctuel ; le cron reste le mode de fonctionnement quotidien (phase 10). Hors périmètre si `--reel` non passé : dry-run par défaut. Tests : boucle bornée, arrêt quand plus de non lus, plafond atteint → arrêt propre.

## T5.1 — Agent classification : Prompt (enums dynamiques depuis le registre)
Étendre `src/prompts.py` : `PROMPT_CLASSIFICATION` — catégories et urgence injectées dynamiquement depuis `config/labels.yaml` (le schéma strict `SyntheseClassification` est déjà construit par `schema_agent`, T2.2 ; jamais de libellé physique en dur dans le prompt), règles de véracité, déclaration `message_id_rfc` + `empreinte` par message. Tests : prompt sans libellé en dur, enums issus du registre.

## T5.2 — Agent classification : Runner de conversation éphémère générique
`src/agents.py` (nouveau) : `lancer_conversation(agent, ...)` paramétré par agent (réutilisé par la phase 4 — décision D35) — client Mistral (`obtenir_client` + `avec_retry`, timeout 300 s), `temperature=0.0`, `max_tokens` cap (1500), `response_format_agent(agent, registre)` strict, allow-list d'outils Gmail (T4.1), boucle tool-calls avec garde-fou anti-boucle, `extraire_json` → `construire_synthese` → `valider_synthese` (C1–C6) + `collecter_ids_reels`, exécution des outils via `ClientGmailAPI`. Tests : Mistral mocké (fixtures SDK), faux service Gmail.

## T5.3 — Empreintes et normalisation (pré-requis du recalcul C6)
`src/dedup.py` (nouveau) : normalisation du Message-ID RFC 5322 (minuscules, sans `<>`/espaces), du sujet (minuscules, préfixes `Re:`/`Fwd:`/`Tr:` retirés), du corps (décodage quoted-printable/base64, HTML → texte brut, minuscules, espaces normalisés) ; `empreinte_sha256(expediteur, sujet, corps)` ; recalcul à partir des sorties réelles de `get_thread` (conception §3). Tests : vecteurs connus, SHA-256 déterministe. Le groupement par doublons reste en phase 6.

## T5.4 — Agent classification : Branchement des étapes 3–4 dans l'orchestrateur
Dans `src/orchestrator.py`, remplacer les stubs `lecture_classification` / `validation_classification` : conversation sur la requête d'idempotence `is:unread -label:"Agent/traité"` (max 50), validation C1–C6 + **recalcul des empreintes** depuis les sorties réelles (rejet si écart), si ok apposition du libellé de catégorie + `Agent/traité` via le resolveur + `modifier_libelles` (dry-run journalisé, règle E), checkpoint de la synthèse ; rejet → arrêt propre (déjà en place).

## T5.5 — Agent classification : Tests et validation de bout en bout
TU + TI mockés (`tests/integration/test_agent_classification.py`) : classification ok → libellés posés (dry-run journalisé / `--reel` exécuté) ; empreinte erronée → rejet C6 ; synthèse incohérente → arrêt propre + `echec_partiel` ; boîte vide → `aucun_message` ; idempotence (2 runs, même `run_id`). Validation dry-run réelle sur la boîte (règle E, `MISTRAL_API_KEY` exportée), puis petit périmètre réel. Critère de sortie phase 5 : étapes 3–4 opérationnelles. ruff/mypy/pytest, kanban → En revue, commit/push sur demande explicite.

## T7.1 — Agent suppression : Prompt et contrat de sortie
Étendre `src/prompts.py` : `prompt_suppression(registre)` — rôle du run de suppression (planifié T+24h, requête de sélection injectée par l'orchestrateur ; seule la catégorie `classification.notification` est éligible, D47), règles de véracité (ne retenir que des messages réellement sélectionnés et lus via les outils), **corbeille uniquement** : le libellé système `TRASH` est appliqué par l'agent via l'outil `label_message` (conception §2.1, workflow S3) ; aucun outil de suppression définitive n'est exposé (moindre privilège). Libellés injectés depuis le registre (clés `suivi.traite`, `classification.notification` et `suivi.doublon` — clause `doublon` inerte en v1, D46 ; notification seule éligible, D47) ; jamais de libellé physique en dur. Sortie : unique objet JSON racine conforme au schéma strict `SyntheseSuppression` (déjà construit en T2.2 : statuts `supprimes`/`aucun_message`/`echec_technique`, champs `count` et `ids`). Allow-list `OUTILS_GMAIL` réutilisée telle quelle (D41). Tests (`tests/unit/test_prompts.py`) : prompt sans libellé en dur, statuts, corbeille uniquement, objet JSON unique à la racine.

## T7.2 — Agent suppression : Branchement dans le runner
Dans `src/agents.py`, `_prompt_systeme` : branche `AGENT_SUPPRESSION` → `prompt_suppression(registre)` (lève aujourd'hui `AgentInconnuError`) ; le runner générique `lancer_conversation(agent, requete, ...)` est réutilisé tel quel (D35). Garde de complétude adaptée : si `statut=supprimes`, `count == len(ids)` et chaque id provient d'une exécution d'outil réelle (C3) ; la garde « threads lus » s'applique. Tests (`tests/unit/test_agents.py`, Mistral mocké) : conversation `supprimes` avec `TRASH` posé via `label_message` ; `aucun_message` ; rejet C3 (id non manipulé) ; `echec_technique`.

## T7.3 — Run de suppression : Orchestrateur et CLI
`src/orchestrator.py` : `lancer_run_suppression(run_id, *, dry_run, ...)` — run **séparé** du run de tri, avec ses propres checkpoints (`data/checkpoints/<run_id>.json`) : étapes démarrage → `lecture_suppression` (requête construite depuis le registre : `label:"<libellé traité>" label:"<libellé notification>" older_than:24h OR label:"<libellé doublon>"` (notification seule éligible, D47 ; clause `doublon` inerte en v1, D46) — jamais de libellé en dur) → `validation_suppression` (C1–C3 + complétude `count`/`ids` ; rejet → arrêt propre, rapport `echec_partiel` avec `etape_fautive`) → rapport ; reprise sur incident par `--run-id` ; idempotence par la requête `older_than:24h` (un message déjà en corbeille n'est plus sélectionné ; les catégories `a-repondre`/`information` ne sont jamais éligibles, D47). `src/cli.py` : remplacer le stub `_cmd_suppression` par l'appel à `lancer_run_suppression` (dry-run par défaut, règle E — écritures journalisées, non exécutées ; `--reel` pour exécution réelle). Tests unitaires (`test_orchestrator.py`, `test_cli.py`).

## T7.4 — Agent suppression : Tests et validation de bout en bout
TU + nouveau TI `tests/integration/test_agent_suppression.py` (pile réelle orchestrateur → `lancer_conversation`, faux Mistral scénarisé + faux service Gmail filtrant la requête de suppression) : `supprimes` valide → `TRASH` posé en réel / journalisé en dry-run (aucune écriture en dry-run), rapport `succes` avec `count`/`ids` au checkpoint ; `aucun_message` → `succes`, zéro écriture ; synthèse rejetée (C3) → `echec_partiel`, `etape_fautive="lecture_suppression"` ; idempotence (2 runs, même `run_id` → agent non rappelé) ; clause `doublon` inerte en v1 (D46). Validation dry-run réelle sur la boîte (règle E, `MISTRAL_API_KEY` exportée), puis petit périmètre réel (`--reel`). **Critère de sortie phase 7 : pipeline complet** (tri + suppression T+24h). ruff/mypy/pytest, kanban → En revue, commit/push sur demande explicite.

## T8.1 — Rapport : contrat du résumé agrégé
Étendre `src/contracts.py` : modèle `ResumeRun` — comptes déterministes issus des synthèses validées (par catégorie `classification.*`, par urgence, spam déplacés, doublons, messages mis à la corbeille, `statut_global`) — et champ `resume: ResumeRun | None = None` sur `RapportFinal` (rétro-compatible avec les checkpoints existants, `extra="forbid"` inchangé). Tests TU (`tests/unit/test_contracts.py`) : sérialisation JSON, rejets (champ interdit, valeurs négatives), round-trip checkpoint.

## T8.2 — Rapport : agrégation et restitution (`src/report.py`, orchestrateur, CLI)
Nouveau module `src/report.py` (emplacement prévu par l'arborescence cible du plan macro §2) : `aggreger(syntheses, nb_doublons) -> ResumeRun` (déterministe, à partir des synthèses validées du checkpoint) et `formater_console(rapport: RapportFinal) -> str` (résumé lisible : tri → spam déplacés + comptes par catégorie/urgence ; suppression → nombre de messages mis à la corbeille ; statut global). Branchements : étape 6 (`ETAPE_RAPPORT`) de `lancer_run_tri` et `lancer_run_suppression` construisent le rapport via `report.aggreger` ; `src/cli.py` (`_cmd_tri`, `_cmd_suppression`) imprime le résumé console après le JSON. Tests TU (`tests/unit/test_report.py` nouveau, `test_orchestrator.py`, `test_cli.py`).

## T8.3 — Rapport : tests et validation de bout en bout
TU + TI (compléter `tests/integration/test_agent_spam.py`, `test_agent_classification.py`, `test_agent_suppression.py` : le rapport contient un `resume` cohérent avec les synthèses) : rapport final JSON + résumé console affichés ; rejet → `echec_partiel` avec étape fautive dans le résumé ; boîtes vides → `aucun_message`, resume à zéro. Validation dry-run réelle sur la boîte (règle E, `MISTRAL_API_KEY` exportée). **Critère de sortie phase 8 : étape 6 opérationnelle** (rapport final JSON + résumé console). ruff/mypy/pytest, kanban → En revue, commit/push sur demande explicite.

## T9.1 — Tests : plan de tests consolidé et critères d'acceptation
Rédiger `tests/plan_tests.md` (recensement fidèle des 256 tests existants au 04/11/2026 : 235 TU + 21 TI, correspondance fichier ↔ tâches ↔ critères, conventions — fixtures mockées, dry-run, aucun appel réseau — et commandes de qualité lancées manuellement) et `docs/test/acceptation.md` (critères d'acceptation par phase, avec statut de validation). Aucun nouveau test sauf écart constaté lors du recensement. La CI GitHub Actions est écartée (D48). Vérifications : cohérence du décompte avec `pytest --collect-only`, kanban → En revue, commit/push sur demande explicite.

## T9.2 — Tests/robustesse : erreurs d'outils renvoyées au modèle dans le runner (correctif incident 10/11/2026)
`src/agents.py`, boucle de `lancer_conversation` : try/except autour de `executer_outil` — en cas d'erreur (ex. `HttpError` 404 sur un ID halluciné par le modèle, incident du run `aa073eb8-…` en `--tout --reel` le 10/11/2026), warning `outil en echec` (outil, args bornés, erreur) et renvoi de l'erreur au modèle via le `ToolMessage` (`{"erreur": "…"}`) pour correction et reprise, au lieu de laisser l'exception interrompre le run ; aucun crédit dans `threads_lus`/`messages_lus`/`ids_resultats` en cas d'échec (gardes de complétude et plafonds inchangés : 50 appels, 3 tentatives de synthèse). Tests TU (`tests/unit/test_agents.py`, classe `TestOutilEnEchec` : scénario de l'incident rejoué + abandon propre si l'erreur persiste), recensement `tests/plan_tests.md` mis à jour. Plan détaillé : [docs/tasks/T9.2](../tasks/T9.2_robustesse_runner_erreurs_outils.md). ruff/mypy/pytest, kanban → En revue, commit/push sur `dev` sur demande explicite (règle C).

## T9.3 — Tests/robustesse : synthèse invalide rebouclée vers le modèle + `message_id_rfc` normalisé (incident 10/11/2026, 2e volet)
Incident du run `d9fafc4a-…` (10/11, `--tout --reel`) : la synthèse de classification citait les `message_id_rfc` avec chevrons (`<…@laposte.net>`), rejetés par le pattern strict du contrat → `ValidationError` non rattrapée → run interrompu. Correctifs : `src/validation.py` (`construire_synthese`) normalise `message_id_rfc` via `dedup.normaliser_message_id` avant `model_validate` (cohérent avec le recalcul C6) ; `src/prompts.py` : exemple corrigé (`abc@exemple.fr`, sans chevrons) ; `src/agents.py` (`lancer_conversation`) : try/except autour de `extraire_json`/`construire_synthese`/`valider_synthese` — l'erreur est renvoyée au modèle (UserMessage) avec warning `synthese refusee : validation`, décomptée dans `max_tentatives_synthese`, abandon propre au-delà (même pattern que D56). Tests TU (`test_validation.py` : normalisation ; `test_agents.py::TestSyntheseInvalideRebouclee` : chevrons acceptés+normalisés, synthèse invalide puis corrigée, abandon propre si persistante) + TI rejets C3 adaptées au rebouclage. Plan : [docs/tasks/T9.3](../tasks/T9.3_synthese_validation_rebouclee.md). ruff/mypy/pytest, kanban → En revue, commit/push sur `dev` sur demande explicite (règle C).

## T9.4 — Tests/robustesse : cohérence périmètre/budget d'appels par run (incident 10/11/2026, 3e volet)
Incident du run `161dd25c-…` (10/11, `--tout --reel`) : `GardeFouAtteintError` au 51e appel — le prompt ordonne `get_thread` + `get_message` par thread, soit 1 + 2×25 = 51 appels conformes, au-dessus de `plafond_appels_outils: 50`. Le garde-fou a bien tiré (filet de sécurité), mais un run conforme ne doit jamais l'atteindre. Correctifs : nouveau paramètre `limites.marge_appels_reprise` (défaut 3, `config/settings.yaml` + `src/config.py`) ; cap de `search_threads` dérivé du budget via `Limites.cap_threads_recherche()` = `min(max_threads_par_run, (plafond_appels_outils − 1 − marge) // 2)` = **23** par défaut (pire cas conforme 1+2×23+3 = 50) ; budget d'appels et cap de threads explicites dans le message utilisateur de chaque conversation (`src/agents.py`) ; prompts des 3 agents : `get_message` uniquement si l'aperçu du thread est insuffisant. Le plafond 50 ne change pas ; `--tout` pagine (29 messages → 2 runs de 23 + 6). Tests : `test_config.py::TestCapThreadsRecherche` (cap dérivé + invariant `plafond ≥ 2×cap + 1 + marge` sur plusieurs combinaisons), `test_agents.py` (cap passé au service, cap avec plafond custom, budget présent dans le message utilisateur). Plan : [docs/tasks/T9.4](../tasks/T9.4_coherence_budget_appels.md). ruff/mypy/pytest, kanban → En revue, commit/push sur `dev` sur demande explicite (règle C).

## T9.5 — Tests : analyse des axes de simplification du pipeline (étude, sans implémentation)
Tâche d'analyse demandée par l'utilisateur après les correctifs D56–D58 : recenser et évaluer les axes de simplification du runner/orchestrateur — empilement des paramètres `limites.*` et caps dérivés, boucles de rebouclage (D56/D57) vs gardes de complétude, duplication des 3 prompts (partie « Obligatoire : search_threads + get_thread… »), sémantique d'échec de `--tout` — avec pour chaque axe : gain attendu, risque, fichiers concernés. Livrable : note d'analyse `docs/design/simplification.md` + bilan dans ce kanban ; **aucune implémentation** dans cette tâche. Plan/scope : [docs/tasks/T9.5](../tasks/T9.5_analyse_axes_simplification.md).

## T9.6 — Simplifications + idempotence du spam (issues de l'analyse T9.5 — à traiter plus tard)
Depuis l'analyse T9.5 (volet spam) : (1) factoriser les branchements quasi identiques `_lancer_spam`/`_lancer_classification`/`_lancer_suppression` (`src/orchestrator.py`, ~25 lignes chacun) en un helper commun `_lancer_etape(agent, etape, requete, …)` ; (2) factoriser le bloc « Obligatoire : search_threads + get_thread sur chaque thread… » recopié dans les 3 prompts (`src/prompts.py`) en un bloc commun injecté ; (3) à arbitrer : court-circuit `aucun_message` sans appel au modèle quand `search_threads` renvoie 0 thread ; (4) **fonctionnalité idempotence du spam** : les spams laissés en spam (`aucun_message`) sont re-lus à chaque run car `spam.requete: in:spam` n'a pas de clause d'exclusion — poser un libellé « spam confirmé » (nouvelle clé `suivi.spam-confirme` dans `config/labels.yaml`) sur les messages laissés, et faire évoluer `spam.requete` en `in:spam -label:"<spam confirmé>"` (le cap 23, D58, borne entre-temps). Hors périmètre (invariants à conserver) : C6/recalcul empreintes, allow-list d'outils, dry-run (règle E), corbeille interdite côté spam, validation C1–C6. Plan/scope : [docs/tasks/T9.6](../tasks/T9.6_simplifications_idempotence_spam.md). ruff/mypy/pytest, kanban → En revue, commit/push sur `dev` sur demande explicite (règle C).

## T9.7 — Simplification (T9.5 volet classification, point 2) : validation classification en une passe
Dans `src/orchestrator.py`, fusionner `_recalculer_empreintes` (C6 : un `get_message` par message) et `_appliquer_libelles_classification` (deuxième boucle) en **une seule passe** sur les messages : `get_message` → recalc C6 (rejet si écart) → `modifier_libelles` (catégorie + `Agent/traité`). Gain : moitié des lectures API à l'étape `validation_classification`. Invariants conservés : recalc depuis l'API réelle (C6 anti-hallucination), dry-run (règle E), ordre recalc-avant-libellisation. Tests : `test_orchestrator.py` (un seul `messages.get` par message, rejet C6 avant toute écriture, dry-run sans écriture). Plan : [docs/tasks/T9.7](../tasks/T9.7_validation_classification_une_passe.md).

## T9.8 — Refactor (T9.5 volet classification, point 3) : unifier les mécanismes de refus dans `lancer_conversation`
`src/agents.py` : aujourd'hui 4 retours au modèle distincts (D56 erreur d'outil via ToolMessage, D57 synthèse invalide via UserMessage, garde « threads non lus », garde « messages non classés » + écart corbeille côté suppression), partageant le compteur `tentatives_synthese` de façon implicite. Unifier en **un seul mécanisme « refus avec motif renvoyé au modèle + compteur de tentatives »**, les gardes ne fournissant que le motif. Risque : toucher aux filets de sécurité → la couverture de tests existante (TestOutilEnEchec, TestSyntheseInvalideRebouclee, TestCompletudeLecture/Messages, TestLimiteTentativesSynthese, TI) doit rester verte à l'identique (comportements externes inchangés). Plan : [docs/tasks/T9.8](../tasks/T9.8_unification_refus_runner.md).

## T9.9 — Remise à plat de l'arborescence et des documents du projet (lisibilité humaine)
Constat utilisateur (10/11/2026) : l'ensemble n'est plus visible par un humain. Axes : (1) `AGENTS.md` référence `docs/architecture/*.md` qui **n'existe pas** — créer ce répertoire avec les contrats d'interface (ou corriger la référence) ; (2) les contrôles **C1–C6** ne sont définis que dans `docs/tasks/T2.3_validation_programmatique.md` (~lignes 148-153), en prose non numérotée dans `conception.md` §2.5, et avec une dérive de numérotation (C3/C4 entre T2.3 et D36/D40) — définir C1–C6 une fois, à un seul endroit canonique (ex. `docs/architecture/validation.md`), référencé partout ; (3) `SESSIONS.md` fait 130+ ko — découper en archive + index ; (4) revue de cohérence `README.md` / `docs/projet/*` / `docs/tasks/*` (doublons, pointeurs morts). Livrable : arborescence + docs remis à plat, aucun changement de code fonctionnel. Plan : [docs/tasks/T9.9](../tasks/T9.9_arborescence_docs.md).
