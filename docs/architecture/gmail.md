# Contrat canonique — client Gmail, libellés, dry-run

Sources de vérité du code : `src/gmailagent/gmail_client.py` (`ClientGmailAPI`), `src/gmailagent/gmail_labels.py`
(`ClientGmail` protocole + `ResolveurLibelles`), `src/gmailagent/core_config.py` (registre
`config/labels.yaml`, paramètres `config/settings.yaml`).

## Registre de libellés

`config/labels.yaml` est la seule source de vérité : clé logique → libellé physique
(préfixe `Agent/`, D3/D4). Toute clé ajoutée au YAML est résoluble sans modification de code.
Le `ResolveurLibelles` résout clé → `labelId` via `list_labels` (cache par run) et crée le
libellé via `create_label` s'il est absent.

## Opérations du pipeline (`ClientGmailAPI`)

- `search_threads(query, max_results)` — capé par `cap_threads_recherche()` (D58) ;
- `get_thread(thread_id)`, `get_message(message_id)` — lectures plafonnées
  (`plafond_lectures`, garde-fou anti-boucle) ;
- `modifier_libelles(message_id, ajouter, retirer)` — **TRASH y passe par libellé**
  (corbeille uniquement, jamais de suppression définitive ; la méthode `trash` dédiée a été
  supprimée, D59).

## Requêtes construites depuis le registre (jamais de libellé en dur)

- `requete_non_lus` : `is:unread -label:"<suivi.traite>"` (idempotence du run de tri) ;
- `requete_spam` : `in:spam -label:"<suivi.spam-confirme>"` (idempotence du spam) ;
- `requete_suppression` : `label:"<suivi.traite>" label:"<classification.notification>"
  older_than:<delai_grace>` (run T+24h, notifications seules éligibles, D47).

## Dry-run (règle E de AGENTS.md)

Par défaut (`dry_run=True`) : aucune écriture Gmail — créations de libellés et
modifications de libellés (dont TRASH) sont journalisées, non exécutées. Validation en
conditions réelles d'abord en dry-run, puis sur un petit périmètre réel (`--reel`).
