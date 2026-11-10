# Plan de tests — gmailAgent

Document de consolidation et de traçabilité, rédigé en phase 9 (T9.1, 04/11/2026).
Les tests ont été écrits **par phase, avec chaque tâche** (chaque tâche du
[kanban](../docs/projet/kanban.md) comportait sa spec de tests) ; ce document les
recense tels qu'ils existent réellement (audit de couverture), il ne décrit pas un
plan idéalisé.

État au 10/11/2026 : **283 tests, tous verts** — 262 unitaires (TU) + 21 d'intégration
(TI). Recensement : `python -m pytest tests --collect-only -q`.

## Conventions

- **Aucun appel réseau** : Mistral est mocké (conversations scénarisées rejouées) et le
  service `googleapiclient` est un faux service en mémoire (threads/libellés/modify
  enregistrés). Les TI (`tests/integration/`) esercitent la pile réelle
  orchestrateur → `lancer_conversation` avec ces faux.
- **Dry-run** (règle E de AGENTS.md) : testé à chaque niveau — aucune écriture Gmail en
  dry-run (`messages.modify` non appelé), écritures journalisées ; exécution réelle
  simulée contre le faux service.
- **Secrets** : aucun ; `LOG_FILE` est redirigé vers un répertoire temporaire par fixture
  automatique (`monkeypatch`).
- **Commandes de qualité** (lancées manuellement — CI écartée, décision D48) :
  `ruff check src tests`, `mypy src` (strict), `python -m pytest tests -q`.

## Recensement par fichier

### Tests unitaires (`tests/unit/`, 240 tests)

| Fichier | Nb | Portée | Tâches |
| --- | --- | --- | --- |
| `test_contracts.py` | 62 | Modèles Pydantic, en-tête `meta`, schémas JSON stricts dynamiques (enums depuis le registre), `ResumeRun`, `RapportFinal.resume` (rétro-compat), union discriminée `SyntheseEtape` (D44) | T2.1, T2.2, T2.4, T8.1 |
| `test_validation.py` | 39 | `extraire_json`, `collecter_ids_reels`, `valider_synthese` (C1–C6), `construire_synthese` | T2.3, T2.4 |
| `test_agents.py` | 46 | Runner `lancer_conversation` (boucle tool-calls, garde-fou, plafonds), prompts sélectionnés par agent, gardes de complétude (threads lus, messages classés, corbeille réelle == `ids`), rejets C3, abandon après 3 refus, erreurs d'outils renvoyées au modèle + warning `outil en echec` (D56) | T4.2, T5.2, T7.2, T9.2 |
| `test_orchestrator.py` | 29 | Requêtes depuis le registre (idempotence, suppression D47), cycle de run, checkpoints, reprise sur incident, étapes 1–4 (spam/classification + C6), run de suppression (T7.3), `resume` des rapports (T8.2) | T3.2, T4.3, T5.4, T7.3, T8.2 |
| `test_prompts.py` | 19 | Prompts sans libellé physique en dur, enums/clés depuis le registre, conservatisme/véracité, corbeille uniquement, catégorie notification seule éligible (D47), schémas d'outils | T4.1, T5.1, T7.1 |
| `test_cli.py` | 19 | Parsing (`--reel`, `--run-id`, `--tout`), dry-run par défaut, commandes `tri`/`suppression`/`migrate-labels`, résumé console (T8.2), boucle `--tout` (`TestTout` : épuisement, plafond, dry-run 1 run, arrêt sur échec) | T3.3, T7.3, T8.2, T3.5 |
| `test_gmail.py` | 17 | Client Gmail concret mocké : token, labels, recherche paginée bornée, dry-run (écritures journalisées), plafond de lectures | T3.1 |
| `test_dedup.py` | 11 | Normalisation (Message-ID RFC, sujet, corps), SHA-256 déterministe, `empreinte_message` depuis `get_thread` | T5.3 |
| `test_report.py` | 8 | `aggreger` (comptes déterministes), `formater_console` (résumé, aucun `Agent/` en dur) | T8.2 |
| `test_journalisation.py` | 1 | Bornes de run `debut_run`/`fin_run` horodatées dans le log | modif. journalisation 04/11/2026 |

### Tests d'intégration (`tests/integration/`, 21 tests)

| Fichier | Nb | Portée | Tâche |
| --- | --- | --- | --- |
| `test_run_vide.py` | 5 | Run vide de bout en bout (critère de sortie phase 3) : checkpoints, idempotence, reprise | T3.4 |
| `test_agent_spam.py` | 5 | Agent spam bout en bout : libellés posés/retirés (réel), dry-run sans écriture, rejet C3, `aucun_message`, idempotence, `resume` | T4.4 |
| `test_agent_classification.py` | 5 | Classification bout en bout : libellés posés, empreintes recalculées (rejet C6), dry-run, `aucun_message`, idempotence, `resume` | T5.5 |
| `test_agent_suppression.py` | 6 | Suppression bout en bout (T+24h, notifications seules éligibles, D47) : TRASH réel/journalisé, rejet C3, garde action, `aucun_message`, idempotence, `resume` | T7.4 |

## Couverture par critère transverse

- **Dry-run / règle E** : `test_gmail.py`, `test_agents.py::TestExecuterOutil`, TI (dry-run sans écriture) ✔
- **Idempotence** (requête `-label:"Agent/traité"`, checkpoints, 2 runs même `run_id`) : TU orchestrateur + TI ✔
- **Reprise sur incident** (`--run-id`, D44) : `test_orchestrator.py` ✔
- **Véracité / validation C1–C6** : `test_validation.py`, `test_agents.py`, TI rejets ✔
- **Registre de libellés** (aucun nom physique en dur) : `test_prompts.py`, requêtes testées depuis le registre ✔
- **Corbeille uniquement / moindre privilège** : allow-list testée, `test_agents.py`, TI ✔
- **Dédoublonnage (phase 6, option post-v1 D46)** : normalisation/empreintes testées (T5.3) ; groupement non implémenté en v1 — sera couvert à la reprise post-v1.

## Hors périmètre des tests automatisés

Validation en conditions réelles sur la boîte Gmail (dry-run réel avec `MISTRAL_API_KEY`,
puis petit périmètre `--reel`) : effectuée manuellement par l'utilisateur (étape 6 de
AGENTS.md, règle E) — critères dans [docs/test/acceptation.md](../docs/test/acceptation.md).
