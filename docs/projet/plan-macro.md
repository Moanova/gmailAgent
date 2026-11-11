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
  a-repondre:  "Agent/pour-réponse"
  information:  "Agent/information"
  notification: "Agent/notification"
suivi:
  traite:         "Agent/traité"
  doublon:       "Agent/doublon"
  valide-spam:   "Agent/valide-spam"
  spam-confirme: "Agent/spam-confirme"
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

## 2. Arborescence réelle du projet

```
gmailAgent/
├── AGENTS.md                  # méthode de travail (workflow kanban, règles C/D/E/H)
├── README.md                  # installation, commandes, utilisation
├── SESSIONS.md                # journal des séances (index ; historique : docs/sessions-archive.md)
├── pyproject.toml             # dépendances, point d'entrée `gmailagent`, config ruff/mypy/pytest
├── .env.example               # template des secrets (MISTRAL_API_KEY, GOOGLE_CLIENT_ID/SECRET)
├── .gitignore                 # .venv/, .env, data/, logs/ ignorés
├── config/
│   ├── labels.yaml            # registre clé logique -> libellé physique (section 1)
│   └── settings.yaml          # paramètres du pipeline (chemins, modèle, limites, délai de grâce)
├── scripts/
│   └── init_oauth.py          # script one-shot : 1er flux OAuth Gmail -> data/gmail_token.json
├── src/gmailagent/            # package unique + préfixes de domaine (option E, D64)
│   ├── __init__.py
│   ├── __main__.py            # `python -m gmailagent ...` (D65)
│   ├── cli.py                 # `gmailagent tri [--tout] | suppression | migrate-labels` (+ --reel, --run-id)
│   ├── core_env.py            # secrets via os.environ uniquement (règle D)
│   ├── core_journalisation.py # structlog : console + logs/gmailagent.log
│   ├── core_client.py         # client Mistral unique (timeout 300 s) + retry/backoff 429/5xx
│   ├── core_config.py         # chargement + validation du registre et des paramètres
│   ├── gmail_client.py        # client Gmail concret (OAuth, search/get/modify/trash, dry-run)
│   ├── gmail_labels.py        # résolution runtime clé -> labelId (cache par run), création
│   ├── agent_contracts.py     # modèles pydantic + schémas JSON stricts dynamiques des 3 agents
│   ├── agent_prompts.py       # prompts des 3 agents (sans nom de libellé en dur)
│   ├── agent_runner.py        # conversation éphémère générique `lancer_conversation`
│   ├── agent_validation.py    # collecter_ids_reels, valider_synthese (C1-C6), extraire_json
│   ├── agent_dedup.py         # normalisation, empreintes SHA-256, groupement
│   ├── pipeline_orchestrator.py # pipeline, checkpoints data/checkpoints/, requêtes depuis le registre
│   └── pipeline_report.py     # agrégation + rapport final (JSON + résumé console)
├── tests/
│   ├── plan_tests.md          # recensement des tests (302 tests au 11/11/2026)
│   ├── unit/                  # tests unitaires
│   └── integration/           # tests d'intégration mockés (aucun appel réseau)
├── docs/
│   ├── architecture/          # contrats canoniques : validation.md (C1-C6), agents.md, gmail.md
│   ├── design/                # conception.md, workflow.md, simplification.md, conception-studio-apps.md (D63)
│   ├── projet/                # kanban.md, plan-macro.md (ce fichier), tasks/ (41 suivis de tâches)
│   ├── test/acceptation.md    # critères d'acceptation par phase
│   └── sessions-archive.md    # archive des séances
├── data/                      # runtime, ignoré par git : gmail_token.json (chmod 600), checkpoints/
└── logs/                      # runtime, ignoré par git : gmailagent.log
```

## 3. Macro-phases

| Phase | Contenu | Sortie concrète |
| --- | --- | --- |
| **1. Fondations** | `pyproject.toml`, client Mistral commun, retry/backoff (429/5xx), logging structuré, registre de libellés + résolution runtime | Package installable, config validée au démarrage |
| **2. Contrats** | Modèles pydantic (`MessageClasse`, `SyntheseEtape`, `RapportFinal`, enveloppe `meta`), schémas JSON stricts construits depuis le registre, `agent_validation.py` (fonctions reprises des scripts de référence) | Tout échange inter-étapes typé et testé |
| **3. Orchestrateur squelette** | Cycle de run (run_id, checkpoints JSON, idempotence `is:unread -label:"Agent/traité"`), CLI (`tri`, `suppression`, `migrate-labels`), planification cron | Un run vide qui tourne de bout en bout |
| **4. Agent spam** | Conversation éphémère, prompt conservatoire, schéma `deplaces`/`aucun_message`/`echec_technique`, validation, apposition `Agent/valide-spam` (déplacés) / `Agent/spam-confirme` (laissés en spam, requête `in:spam -label:"Agent/spam-confirme"`, D61) | Étapes 1–2 du pipeline opérationnelles |
| **5. Agent classification** | Conversation éphémère, schéma enrichi (`message_id_rfc`, `empreinte`), validation IDs + complétude | Étapes 3–4 opérationnelles |
| **6. Dédoublonnage** *(option post-v1 — non embarquée dans la v1, décision D46)* | Normalisation (Message-ID, sujet, corps), SHA-256, groupement déterministe, recalcul/validation des empreintes, pose `Agent/doublon` | Étape 5 opérationnelle, testée unitairement |
| **7. Agent suppression** | Run séparé T+24h, requête `label:"Agent/traité" label:"Agent/notification" older_than:24h` (notification seule éligible — D47 ; clause `doublon` retirée en v1, D59), corbeille uniquement | Pipeline complet |
| **8. Rapport et restitution** | Agrégation des synthèses validées, rapport final JSON + résumé console | Étape 6 |
| **9. Tests** | Unitaires (validation, normalisation, empreintes, registre), fixtures de conversations mockées, mode **dry-run** (aucun appel d'écriture Gmail) | 302 tests verts (commandes manuelles — CI écartée, D48) |
| **10. Déploiement** | Secrets (env), cron/timer, journalisation des métriques (appels outils, tokens, latences) pour ajuster les plafonds | Exécution quotidienne autonome |

## 4. Ordre de développement

1 → 2 → 3 (squelette qui tourne à vide) → 5 (classification, cœur du système)
→ 4 (spam) → 7 (suppression) → 8 → 9 → 10 pour la **v1**.

La classification (phase 5) est volontairement placée avant le spam (phase 4) :
c'est l'agent le plus représentatif du pattern commun, et il valide les
contrats et la validation programmatique avant leur réutilisation.

La **phase 6 (dédoublonnage) est conservée comme option post-v1** (décision D46) : en v1,
l'étape 5 reste un stub no-op (`nb_doublons=0` dans le rapport, aucun libellé
`Agent/doublon` posé — la clause `doublon` du run de suppression a été retirée en v1 (D59)). Ses fondations
sont déjà en place (normalisation + empreintes, T5.3 ; recalcul C6 à l'étape 4) et seront
réutilisées telles quelles lors de la reprise post-v1.

## 5. Précautions transverses

- **Dry-run dès la phase 3** : permettre de tester le pipeline sans aucun
  appel d'écriture vers Gmail.
- **Validation systématique** : aucun libellé n'est apposé sans validation
  préalable de la synthèse (un libellé posé à tort est pénible à défaire à
  grande échelle).
- **Jamais de suppression définitive** : corbeille uniquement, avec délai de
  grâce de 24 h ; seules les notifications (`Agent/notification`) traitées sont
  éligibles (D47). Le libellé UNREAD n'est jamais retiré par le pipeline (action
  utilisateur).
- **Règles de véracité** : les synthèses ne mentionnent que des messages
  réellement lus via les outils ; l'orchestrateur recalcule les empreintes de
  dédoublonnage à partir des sorties réelles de `get_thread`.

## 6. Références

- Spécification : [docs/design/conception.md](../design/conception.md)
- Scripts de référence (exemples de conception, hors dépôt) : patterns
  `agent01a/01b/01c` (agent permanent), `agent02/02b` (conversation éphémère),
  `agent03a/03b/03c` (agent permanent dynamique), et les fonctions
  `collecter_ids_reels`, `valider_synthese`, `extraire_json`.
