# Contrat canonique — validation programmatique des synthèses (C1–C6)

Définition **canonique et numérotée** des contrôles C1–C6, référencée par
[`docs/design/conception.md`](../design/conception.md) §2.5 et
[`docs/projet/tasks/T2.3_validation_programmatique.md`](../projet/tasks/T2.3_validation_programmatique.md).
Sources de vérité du code : `src/gmailagent/agent_validation.py` (`valider_synthese`, `collecter_ids_reels`,
`extraire_json`, `construire_synthese`) et `src/gmailagent/pipeline_orchestrator.py` (recalcul C6).

Tout rejet lève `SyntheseInvalideError` avec un motif explicite (une ligne, sans contenu
utilisateur) ; dans le runner, le refus est renvoyé au modèle et décompté dans
`max_tentatives_synthese` (`config/settings.yaml`) avant abandon propre du run.

## Contrôles (ordre d'application dans `valider_synthese`)

| # | Contrôle | Règle | Implémentation |
| --- | --- | --- | --- |
| C1 | Non-contradiction statut/messages | `echec_technique` → `messages`/`count` nul ET `erreur` renseignée ; `synthese`/`deplaces`/`supprimes` → `erreur` vide | `_valider_non_contradiction` |
| C2 | Non-contradiction statut/erreur | `aucun_message` → `messages` vide ET `erreur` vide | `_valider_non_contradiction` |
| C3 | Complétude | `synthese`/`deplaces`/`supprimes` → `messages` non vide (suppression : `count > 0` et `ids` non vide) | `_valider_completude` |
| C4 | Authenticité des IDs | chaque `message.id` (ou `ids[]` pour la suppression) ∈ ids réellement manipulés par les outils — arguments **et** résultats (décision D40) | `_valider_authenticite` + `collecter_ids_reels` |
| C5 | Cohérence suppression | `count == len(ids)` | `_valider_completude` |
| C6 | Cohérence classification (clés de dédoublonnage) | chaque `MessageClasse` a `message_id_rfc` (normalisé, sans chevrons — D57) et `empreinte` (SHA-256, 64 hex) conformes aux patterns Pydantic, **recalculés depuis la lecture API réelle** (`get_message`) par l'orchestrateur — rejet si écart (conception §3, anti-hallucination) | `_valider_empreintes` (format) + recalcul C6 dans `src/gmailagent/pipeline_orchestrator.py` (`_valider_et_labelliser_classification`) |

## Gardes de complétude de la conversation (runner, complémentaires de C1–C6)

Dans `src/gmailagent/agent_runner.py` (`lancer_conversation`, mécanisme de refus unifié `_refuser`) :
threads retournés par `search_threads` tous lus via `get_thread` ; messages lus tous
classifiés (agent classification) ; écart entre mises à la corbeille réelles (TRASH) et
`ids` de la synthèse (agent suppression).

## Note sur la dérive de numérotation (historique)

Les décisions D36/D40 employaient « C3 » pour l'authenticité des ids. La numérotation
canonique est celle de ce document (C3 = complétude, C4 = authenticité), alignée sur le code
(`src/gmailagent/agent_validation.py`) et sur le tableau de T2.3. Aucun renommage n'est effectué ailleurs :
les références existantes continuent de pointer ici.
