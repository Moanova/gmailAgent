# gmailAgent

Agent personnel de traitement des messages Gmail : pipeline de tri orchestré en Python
(lecture du spam, classification des non lus, suppression différée en
corbeille — dédoublonnage en option post-v1, non actif en v1, D46), avec conversations éphémères Mistral et validation programmatique des
synthèses (authenticité des identifiants, complétude, empreintes recalculées).

Spécification : [docs/design/conception.md](docs/design/conception.md) —
workflow : [docs/design/workflow.md](docs/design/workflow.md).

## Prérequis

- Python ≥ 3.11
- Clé API Mistral dans la variable d'environnement `MISTRAL_API_KEY` (voir `.env.example`)
- Modèle Mistral optionnel via `MISTRAL_MODEL` (défaut : `mistral-small-latest`, ex. `mistral-large-4`) ; chaque appel est journalisé avec le modèle utilisé dans `logs/gmailagent.log`
- Token Gmail dans `data/gmail_token.json`, généré une seule fois par
  `python scripts/init_oauth.py` (premier flux OAuth, voir tâche T1.7 dans
  [docs/projet/kanban.md](docs/projet/kanban.md))

## Installation

```bash
python -m venv .venv
.venv/bin/pip install -e ".[dev]"    # Windows : .venv\Scripts\pip.exe ...
```

La commande `gmailagent` est alors disponible (point d'entrée `cli:main`).

## Configuration

- `config/labels.yaml` : registre des libellés `Agent/*` (clé logique → libellé physique).
- `config/settings.yaml` : paramètres du pipeline (chemins, modèle par défaut, plafonds et
  garde-fous, délai de grâce de la suppression T+24h, requête spam). Priorité :
  variable d'environnement (`MISTRAL_MODEL`, `LOG_FILE`) > `settings.yaml` > défaut du code.

## Usage

**Dry-run par défaut** (règle E) : aucune écriture Gmail sans `--reel` — en dry-run,
les écritures sont journalisées dans `logs/gmailagent.log`, non exécutées.

Chaque run est encadré dans `logs/gmailagent.log` par des lignes d'événements
`debut_run` / `fin_run` horodatées (chaque ligne JSON porte aussi `run_id`) :
`jq 'select(.evenement=="debut_run" or .evenement=="fin_run")' logs/gmailagent.log`.

| Commande | Options | Description |
| --- | --- | --- |
| `gmailagent tri` | `[--run-id UUID] [--tout] [--reel]` | Run principal de tri (étapes 0–7 : spam puis classification). Imprime le rapport final JSON puis le résumé console, puis `run <id> terminé : <statut>`. Code retour 0 si `succes`, 1 sinon. `--run-id` : reprise sur incident depuis les checkpoints (`data/checkpoints/<run_id>.json`). `--tout` : boucle de runs jusqu'à épuisement des non lus (plafond 10 runs, `run_id` distinct par run ; en dry-run : un seul run car les libellés ne sont pas posés). |
| `gmailagent suppression` | `[--run-id UUID] [--reel]` | Run de suppression T+24h (phase 7) : corbeille uniquement (`TRASH`) sur les notifications traitées — `label:"Agent/traité" label:"Agent/notification" older_than:24h` (notification seule éligible, D47). |
| `gmailagent migrate-labels ANCIEN NOUVEAU` | `[--reel]` | Déplace les messages d'un libellé physique vers un autre (le libellé cible est créé s'il manque). |

`--reel` est accepté avant ou après la sous-commande (`gmailagent --reel tri` ≡ `gmailagent tri --reel`).

Exemples :

```bash
gmailagent tri                                   # dry-run : lecture réelle, zéro écriture Gmail
gmailagent tri --run-id 7e2337c1-...             # reprise sur incident (même run_id)
gmailagent tri --reel                            # écritures réelles — petit périmètre d'abord
python -m cli migrate-labels "Agent/ancien" "Agent/nouveau"   # renommage de libellé
```

Aide : `gmailagent --help`, `gmailagent tri --help`.

> `--tout` (tâche T3.5, conception §2.6) : rattrapage d'un retard volumineux en une seule
> invocation — alternative ponctuelle au cron (qui reste le mode quotidien, phase 10).

## Tests et qualité

```bash
ruff check src tests
mypy src                          # strict
python -m pytest tests -q         # unitaires + intégration mockés (aucun appel réseau)
```

## Documentation du projet

- [AGENTS.md](AGENTS.md) — méthode de travail (workflow par tâche, dry-run, secrets)
- [docs/design/conception.md](docs/design/conception.md) — spécification générale (état actuel)
- [docs/design/workflow.md](docs/design/workflow.md) — workflow (schéma Mermaid)
- [docs/architecture/](docs/architecture/) — contrats canoniques (`validation.md` C1–C6, `agents.md`, `gmail.md`)
- [docs/projet/plan-macro.md](docs/projet/plan-macro.md) — plan macro (10 phases ; **sera supprimé en fin de projet**)
- [docs/projet/kanban.md](docs/projet/kanban.md) — suivi des tâches (+ [fichiers de suivi](docs/projet/tasks/))
- [SESSIONS.md](SESSIONS.md) — index du journal des séances (décisions D1…D63) + [archive](docs/sessions-archive.md)

Branche de travail unique : `dev` (push direct, pas de PR ni de branche dédiée).
