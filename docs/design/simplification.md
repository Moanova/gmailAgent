# Note de synthèse — simplifications et modifications évaluées (T9.5)

> **Document d'archive projet** : les simplifications listées ci-dessous ont été
> **implémentées et validées le 11/11/2026** (T9.6, T9.7, T9.8 — « Terminé » dans le kanban ;
> T9.9 en cours pour la remise à plat documentaire). Ce n'est pas une liste d'actions futures.

Rédigée le 10/11/2026 à l'issue de la tâche **T9.5** (analyse des axes de simplification, volet
par volet : spam, classification, suppression, orchestrateur/transverse). Contexte : incidents
du 10/11/2026 corrigés par D56–D58 (tâches T9.2–T9.4, terminées et validées en conditions
réelles — `--tout --reel`, 29 messages traités sans erreur).

Toutes les simplifications ci-dessous ont été **évaluées puis approuvées** par l'utilisateur
(décision **D60** ; les deux suppressions de code mort/inerte ont été approuvées séparément,
**D59**). L'implémentation est répartie dans les tâches **T9.6 / T9.7 / T9.8** (code) et
**T9.9** (arborescence + documents) — à lancer sur demande explicite.

## Bilan par volet

### Volet spam
- **Factoriser les branchements** `_lancer_spam`/`_lancer_classification`/`_lancer_suppression`
  (~25 lignes quasi identiques chacun, `src/gmailagent/pipeline_orchestrator.py`) → un helper `_lancer_etape(...)`.
  → T9.6, quick win sûr.
- **Factoriser le bloc « lecture » commun aux 3 prompts** (`src/gmailagent/agent_prompts.py` : « Obligatoire :
  `search_threads`, puis `get_thread` sur chaque thread… » recopié à l'identique) → bloc injecté.
  → T9.6, quick win sûr.
- **Court-circuit spam vide** : si `search_threads` renvoie 0 thread, rendre `aucun_message`
  sans appel au modèle (économie d'appels LLM par run). Approuvé avec la réserve notée :
  contourne C1–C6, trivial sur liste vide. → T9.6.
- **Fonctionnalité — idempotence du spam** : les spams laissés en spam (`aucun_message`) sont
  re-lus à chaque run (`in:spam` sans clause d'exclusion ; constaté dans les logs du 10/11).
  Proposition : libellé « spam confirmé » (nouvelle clé `suivi.spam-confirme`) posé sur les
  messages laissés, et `spam.requete` = `in:spam -label:"<spam confirmé>"` (cap 23, D58, borne
  entre-temps). → T9.6.

### Volet classification
- **Validation en une passe** : fusionner `_recalculer_empreintes` (C6, un `get_message` par
  message) et `_appliquer_libelles_classification` en une seule boucle → moitié des lectures API
  à l'étape `validation_classification`. → **T9.7**, quick win sûr.
- **Unifier les mécanismes de refus** dans `lancer_conversation` (`src/gmailagent/agent_runner.py`) : D56 (erreur
  d'outil), D57 (synthèse invalide), gardes « threads non lus » / « messages non classés » /
  « écart corbeille » → un seul mécanisme « refus avec motif renvoyé au modèle + compteur ».
  Critère d'acceptation : tests existants verts **sans modification**. → **T9.8**, refactor à
  risque maîtrisé.

### Volet suppression
- **Supprimer la clause inerte** `OR label:"Agent/doublon"` de `requete_suppression` (D46,
  phase 6 post-v1 ; à ré-ajouter à la reprise) + l'appel `resoudre(CLE_DOUBLON)` associé.
  Approuvé (D59). → T9.6.
- **Supprimer la méthode morte `corbeille()`** de `src/gmailagent/gmail_client.py` (jamais appelée — le TRASH
  passe par `label_message`) + ses tests. Approuvé (D59). → T9.6.
- Le reste du volet est volontairement contraint (seul volet avec écritures) : corbeille
  uniquement, UNREAD jamais retiré, `notification` seule éligible (D47) — inchangé.

### Volet orchestrateur / transverse
- **Squelette de run dupliqué** : `lancer_run_tri` / `lancer_run_suppression` (~90 lignes
  chacune, même schéma checkpoint → étapes → `except` → `echec_partiel`) → un
  `_executer_run(rid, etapes, …)` générique avec étapes déclarées en liste de `(nom, callable)`.
  → à traiter avec T9.8 (refactor à risque maîtrisé, couverture `test_orchestrator.py` + TI).
- **Rien à changer côté checkpoints / idempotence / reprise `--run-id`** : conception solide et
  testée, conservée telle quelle.
- **Paramètres `limites.*`** : la cohérence est désormais assurée par construction
  (`cap_threads_recherche()`, D58 + test d'invariant) ; aucune simplification supplémentaire
  retenue au-delà de la documentation (T9.9).

## Classement

| Classe | Éléments | Tâche |
|---|---|---|
| Quick wins sûrs | factorisation `_lancer_etape`, bloc prompt commun, suppressions D59 (clause doublon, `corbeille()`), validation en une passe | T9.6, T9.7 |
| Refactor à risque maîtrisé | unification des refus + squelette de run générique (tests existants à garder verts) | T9.8 |
| Fonctionnalité | idempotence du spam (libellé « spam confirmé ») ; court-circuit spam vide (réserve notée) | T9.6 |
| Documentation / arborescence | `docs/architecture/` (référencé mais inexistant), définition canonique de C1–C6 (dérive C3/C4 à corriger), archive de `SESSIONS.md`, cohérence README/kanban | T9.9 |

## Invariants conservés (hors périmètre de toute simplification)

C6/recalcul des empreintes depuis les lectures API réelles, allow-list d'outils, périmètre de
requête imposé par le code (D54), dry-run (règle E), corbeille uniquement (jamais de suppression
définitive), UNREAD jamais retiré par le pipeline, validation C1–C6, aucun libellé physique en
dur dans le code, checkpoints + idempotence par requête.

## Traçabilité

- Correctifs incidents 10/11 : D56 (T9.2), D57 (T9.3), D58 (T9.4) — commits `91d2044`,
  `a35bb9f`, `0fe8a0b`, validés en réel le 10/11/2026.
- Décisions : D59 (suppressions clause doublon + `corbeille()`), D60 (approbation de l'ensemble
  des simplifications évaluées en T9.5).
- Tâches d'implémentation : **T9.6, T9.7, T9.8 implémentées et validées le 11/11/2026
  (« Terminé » — 302 tests verts)** ; T9.9 (docs/arborescence) en cours au 11/11/2026.
