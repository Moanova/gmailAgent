# Plan macro — Implémentation du pipeline gmailAgent

Ce document consigne le plan de niveau macro pour l'implémentation du pipeline
décrit dans [docs/design/conception.md](../design/conception.md). Il traduit la
spécification en phases de développement ordonnées.

## 1. Principe directeur : registre de libellés

Les libellés Gmail sont susceptibles de changer au fil du temps. Le code ne
doit jamais manipuler de nom de libellé physique en dur.

Un fichier de configuration versionné fait le lien entre **clés logiques**
(stables, utilisées par le code et les agents) et **noms physiques** (les
libellés Gmail, changeants) :

```yaml
# config/labels.yaml
classification:
  a-repondre:  "Agent/a-repondre"
  information:  "Agent/information"
  notification: "Agent/notification"
suivi:
  traite:       "Agent/traité"
  doublon:     "Agent/doublon"
  valide-spam: "Agent/valide-spam"
```

Règles :

- les agents et l'orchestrateur ne manipulent que des **clés logiques** ;
- la résolution clé → `labelId` se fait au runtime via `list_labels`, mis en
  cache par run ;
- les `enum` des schémas JSON (catégorie, urgence) sont **construits
  dynamiquement** à chaque appel à partir du registre — jamais de nom de
  libellé en dur dans un prompt ;
- **renommage** : on édite le YAML, aucune migration de code ; si un libellé
  physique manque, l'orchestrateur le crée (`create_label`) ou échoue
  proprement ;
- **migration** : un outil dédié `migrate-labels` déplace les messages d'un
  ancien libellé vers le nouveau (`search_threads label:"Ancien"`, puis
  `label_message` add/remove).

## 2. Arborescence cible

```
gmailAgent/
├── config/
│   └── labels.yaml            # registre clé logique -> libellé physique
├── src/
│   ├── config.py              # chargement + validation du registre
│   ├── labels.py              # résolution runtime, création, migration
│   ├── contracts.py           # pydantic + schémas JSON dynamiques
│   ├── prompts.py             # prompts des 3 agents (sans nom de libellé en dur)
│   ├── validation.py          # collecter_ids_reels, valider_synthese, extraire_json
│   ├── dedup.py               # normalisation, empreintes, groupement
│   ├── agents.py              # runners spam / classification / suppression
│   ├── orchestrator.py        # pipeline, checkpoints, idempotence
│   ├── report.py              # agrégation et rapport final
│   └── cli.py                 # tri | suppression | migrate-labels | dry-run
└── tests/
```

## 3. Macro-phases

| Phase | Contenu | Sortie concrète |
| --- | --- | --- |
| **1. Fondations** | `pyproject.toml`, client Mistral commun, retry/backoff (429/5xx), logging structuré, registre de libellés + résolution runtime | Package installable, config validée au démarrage |
| **2. Contrats** | Modèles pydantic (`MessageClasse`, `SyntheseEtape`, `RapportFinal`, enveloppe `meta`), schémas JSON stricts construits depuis le registre, `validation.py` (fonctions reprises des scripts de référence) | Tout échange inter-étapes typé et testé |
| **3. Orchestrateur squelette** | Cycle de run (run_id, checkpoints JSON, idempotence `is:unread -label:"Agent/traité"`), CLI (`tri`, `suppression`, `migrate-labels`), planification cron | Un run vide qui tourne de bout en bout |
| **4. Agent spam** | Conversation éphémère, prompt conservatoire, schéma `deplaces`/`aucun_message`/`echec_technique`, validation, apposition `Agent/valide-spam` | Étapes 1–2 du pipeline opérationnelles |
| **5. Agent classification** | Conversation éphémère, schéma enrichi (`message_id_rfc`, `empreinte`), validation IDs + complétude | Étapes 3–4 opérationnelles |
| **6. Dédoublonnage** | Normalisation (Message-ID, sujet, corps), SHA-256, groupement déterministe, recalcul/validation des empreintes, pose `Agent/doublon` | Étape 5 opérationnelle, testée unitairement |
| **7. Agent suppression** | Run séparé T+1h, requête `label:"Agent/traité" older_than:1h` + `Agent/doublon`, corbeille uniquement | Pipeline complet |
| **8. Rapport et restitution** | Agrégation des synthèses validées, rapport final JSON + résumé console | Étape 6 |
| **9. Tests** | Unitaires (validation, normalisation, empreintes, registre), fixtures de conversations mockées, mode **dry-run** (aucun appel d'écriture Gmail) | CI verte |
| **10. Déploiement** | Secrets (env), cron/timer, journalisation des métriques (appels outils, tokens, latences) pour ajuster les plafonds | Exécution quotidienne autonome |

## 4. Ordre de développement

1 → 2 → 3 (squelette qui tourne à vide) → 5 (classification, cœur du système)
→ 4 (spam) → 6 (dédoublonnage) → 7 (suppression) → 8 → 9 → 10.

La classification (phase 5) est volontairement placée avant le spam (phase 4) :
c'est l'agent le plus représentatif du pattern commun, et il valide les
contrats et la validation programmatique avant leur réutilisation.

## 5. Précautions transverses

- **Dry-run dès la phase 3** : permettre de tester le pipeline sans aucun
  appel d'écriture vers Gmail.
- **Validation systématique** : aucun libellé n'est apposé sans validation
  préalable de la synthèse (un libellé posé à tort est pénible à défaire à
  grande échelle).
- **Jamais de suppression définitive** : corbeille uniquement, avec délai de
  grâce d'une heure.
- **Règles de véracité** : les synthèses ne mentionnent que des messages
  réellement lus via les outils ; l'orchestrateur recalcule les empreintes de
  dédoublonnage à partir des sorties réelles de `get_thread`.

## 6. Références

- Spécification : [docs/design/conception.md](../design/conception.md)
- Scripts de référence (exemples de conception, hors dépôt) : patterns
  `agent01a/01b/01c` (agent permanent), `agent02/02b` (conversation éphémère),
  `agent03a/03b/03c` (agent permanent dynamique), et les fonctions
  `collecter_ids_reels`, `valider_synthese`, `extraire_json`.
