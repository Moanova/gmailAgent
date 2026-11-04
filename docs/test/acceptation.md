# Critères d'acceptation — gmailAgent

Critères de sortie par phase du [plan macro](../projet/plan-macro.md), avec l'état de
validation au 04/11/2026. La validation utilisateur (étape 6 de AGENTS.md) s'effectue en
dry-run réel sur la boîte Gmail (`MISTRAL_API_KEY` exportée), puis sur un petit périmètre
réel (`--reel`) — règle E.

## Par phase

| Phase | Critère de sortie | État au 04/11/2026 |
| --- | --- | --- |
| 1. Fondations | Package installable (`pip install -e ".[dev]"`), config validée au démarrage, secrets hors dépôt (règle D) | ✔ Validée (T1.1–T1.7 Terminé) |
| 2. Contrats | Tout échange inter-étapes typé (Pydantic strict) et testé ; schémas JSON dynamiques depuis le registre | ✔ Validée (T2.1–T2.4 Terminé) |
| 3. Orchestrateur squelette | Un run vide tourne de bout en bout, dry-run sans aucun appel d'écriture Gmail (règle E) | ✔ Validée (T3.1–T3.4 Terminé) |
| 4. Agent spam | Étapes 1–2 opérationnelles (lecture spam, validation, apposition `Agent/valide-spam`) | ✔ Validée (T4.1–T4.4 Terminé, dry-run réel 03/11) |
| 5. Agent classification | Étapes 3–4 opérationnelles (lecture non lus, validation IDs + empreintes recalculées C6, apposition catégorie + `Agent/traité`) | ✔ Validée (T5.1–T5.5 Terminé, dry-run réel 02/11 : 13 messages / 12 fils) |
| 6. Dédoublonnage | Étape 5 opérationnelle, testée unitairement | **Option post-v1 (D46)** — fondations livrées (T5.3, C6) ; critères applicables à la reprise post-v1 |
| 7. Agent suppression | Pipeline complet : run séparé T+24h, corbeille uniquement, **notifications seules éligibles** (D47), requête `label:"Agent/traité" label:"Agent/notification" older_than:24h OR label:"Agent/doublon"` | Code/tests ✔ (T7.1–T7.4 En revue) ; **validation réelle en attente du délai de 24 h (D47)** |
| 8. Rapport et restitution | Étape 6 opérationnelle : rapport final JSON (avec `resume`) + résumé console | Code/tests ✔ (T8.1–T8.3 En revue) ; validation réelle faite en dry-run (résumé console constaté) |
| 9. Tests | Plan de tests consolidé (`tests/plan_tests.md`) + critères d'acceptation (ce document) ; 261 tests verts | ✔ Ce document (T9.1) ; CI écartée (D48 — commandes de qualité manuelles) |
| 10. Déploiement | Secrets (env), cron/timer, journalisation des métriques | Hors périmètre v1 — planification externe manuelle |

## Transverses (toutes phases)

- **Dry-run par défaut (règle E)** : aucune écriture Gmail sans `--reel` ; en dry-run les
  écritures sont journalisées dans `logs/gmailagent.log` (chaque run encadré par
  `debut_run`/`fin_run` horodatés).
- **Jamais de suppression définitive** : corbeille uniquement (`TRASH`).
- **UNREAD jamais retiré par le pipeline** (action utilisateur) — D47.
- **Registre de libellés** : aucun nom de libellé physique en dur dans le code ni les
  prompts (clés logiques, `config/labels.yaml`).
- **Véracité** : synthèses validées programmatiquement (C1–C6 + gardes de complétude) ;
  un rejet interrompt le run proprement (`echec_partiel` + `etape_fautive`).
- **Idempotence** : requête `is:unread -label:"Agent/traité"` + checkpoints + reprise
  `--run-id`.
- **Qualité** : `ruff check src tests`, `mypy src` (strict), `python -m pytest tests -q`
  — 261 tests au 04/11/2026.
