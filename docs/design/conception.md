# Spécification générale — Pipeline de tri de messagerie Gmail

Description de l'**implémentation actuelle** (branche `dev`). Contrats canoniques :
[`docs/architecture/`](../architecture/) (`validation.md` pour C1–C6, `agents.md`,
`gmail.md`). Workflow : [workflow.md](workflow.md).

## 1. Contexte et objectifs

### 1.1 Contexte

L'ensemble des messages personnels de l'utilisateur est consolidé dans une boîte Gmail unique. Trois catégories de messages coexistent : les messages natifs Gmail, les messages reroutés depuis d'autres messageries (via Thunderbird), et les messages indûment filtrés en spam.

Trois agents spécialisés sont constitués, pilotés par un orchestrateur Python :

| Agent | Responsabilité | Portée d'outils |
| --- | --- | --- |
| Agent classification | Lire les messages non lus, les classer, évaluer l'urgence, apposer les libellés de classement + `Agent/traité` | allow-list commune (ci-dessous) |
| Agent spam | Lire le dossier spam, évaluer la légitimité, replacer si nécessaire (`Agent/valide-spam` + INBOX) | allow-list commune |
| Agent suppression | Mettre à la corbeille les notifications traitées après délai de grâce de 24 h (D47) | allow-list commune (TRASH via `label_message`) |

Allow-list commune (`OUTILS_GMAIL`, moindre privilège) : `search_threads`, `get_thread`,
`get_message`, `label_message`, `list_labels`. Aucun agent ne peut envoyer ni supprimer
définitivement.

Principes transverses :

- sortie structurée JSON (schéma imposé strict), avec champ `statut` (`synthese`/`deplaces`/`supprimes`, `aucun_message`, `echec_technique` selon l'agent) ;
- règles de véracité strictes : ne mentionner que des messages réellement lus via les outils ; jamais de classement imaginaire ;
- validation programmatique côté orchestrateur (C1–C6, voir §2.5 et `docs/architecture/validation.md`) ;
- contrats d'interface explicites (§2.4).

### 1.2 Conventions de coordination (libellés Gmail)

- `Agent/traité` : message traité et validé (classification ou spam replacé) ;
- `Agent/a-repondre`, `Agent/information`, `Agent/notification` : libellés de classement ;
- `Agent/valide-spam` : message replacé depuis le spam ;
- `Agent/spam-confirme` : message laissé en spam par l'agent spam — exclu des scans suivants (idempotence du spam) ;
- `Agent/doublon` : **non posé en v1** (étape 5 no-op, D46).

La corbeille (jamais la suppression définitive) est le seul moyen d'éliminer des messages.
Le libellé UNREAD n'est jamais retiré par le pipeline (action utilisateur).

---

## 2. Orchestration programmatique en Python

### 2.1 Principe

Un orchestrateur Python (`src/orchestrator.py`) pilote séquentiellement les trois agents sous forme de **conversations éphémères** (décision D2 : prompt, outils et schéma de sortie passés à chaque appel, configuration versionnée avec le code). Chaque étape produit une synthèse structurée, validée programmatiquement avant de passer à la suivante. L'état est explicite : en mémoire pendant le run, persisté par checkpoints entre les étapes (`data/checkpoints/<run_id>.json`), et dans Gmail via les libellés (canal persistant entre les runs).

**Configuration.** Deux fichiers YAML dans `config/` : `labels.yaml` (registre des libellés `Agent/*` — clé logique → libellé physique, seule source de vérité pour les libellés, aucun nom physique en dur dans le code) et `settings.yaml` (paramètres du pipeline : chemins, modèle par défaut, plafonds et garde-fous, délai de grâce de la suppression, requête spam de base). Priorité de résolution : variable d'environnement (`MISTRAL_MODEL`, `LOG_FILE`, ...) > `settings.yaml` > défaut du code. Restent volontairement dans le code : les libellés système `TRASH`/`SPAM`/`INBOX` (D43), les prompts et schémas d'outils (D2) et les contrats de validation. Le modèle utilisé est journalisé à chaque conversation (`conversation lancee` dans `logs/gmailagent.log`).

### 2.2 Étapes du pipeline

| # | Étape | Implémentation | Sorties |
| --- | --- | --- | --- |
| 1 | lecture spam | conversation agent spam (`in:spam -label:"Agent/spam-confirme"`) | `synthese_spam` (JSON) |
| 2 | validation spam | code Python : si `deplaces` → `Agent/valide-spam` + `Agent/traité`, retire SPAM, remet INBOX ; si `aucun_message` → `Agent/spam-confirme` sur les messages lus laissés en spam | ok / rejet (interrompt le run) |
| 3 | lecture non lus | conversation agent classification (`is:unread -label:"Agent/traité"`) | `synthese_classification` (JSON) |
| 4 | validation classification | code Python : recalcul C6 des empreintes depuis la lecture API réelle (rejet si écart, avant toute écriture), puis catégorie + `Agent/traité` | ok / rejet |
| 5 | dédoublonnage — **no-op en v1** (D46) | stub | — |
| 6 | agrégation et restitution | code Python | rapport final JSON + résumé console |

L'ordre est imposé : le spam est traité avant la classification, afin que les messages replacés rejoignent le pool des non lus à classer.

L'étape de suppression fait l'objet d'un **run séparé**, planifié T+24h : conversation avec l'agent suppression sur `label:"Agent/traité" label:"Agent/notification" older_than:24h` — **seules les notifications traitées sont éligibles** (D47) — suivie de sa propre validation. L'agent applique lui-même `TRASH` via `label_message` pendant la conversation (corbeille uniquement).

### 2.3 Conversations éphémères

Les agents fonctionnent en **conversations éphémères** (décision D2) : pas d'agent permanent enregistré, modèle + outils + schéma passés à chaque appel — configuration versionnée avec le code (git), totalement reproductible, aucun cycle create/delete.

### 2.4 Contrats d'interface

Communication par contrats explicites (voir `docs/architecture/agents.md`) :

1. **Contrat de sortie par agent** — schéma JSON strict (`response_format.json_schema`, `strict: true`), enums `statut`/`categorie`/`urgence` construits dynamiquement depuis le registre de libellés (`contracts.schema_agent`) ;
2. **Enveloppe commune** — `{statut, messages, erreur?, meta: {run_id, etape, agent, timestamp}}` ;
3. **Contrat orchestrateur** — modèles Pydantic typés (`MessageClasse`, `SyntheseEtape`, `RapportFinal`, `ResumeRun`) ; la sérialisation JSON alimente checkpoints et rapport final ;
4. **Contrat d'outils** — allow-list `OUTILS_GMAIL` (moindre privilège) ;
5. **Médiation** — les agents ne s'appellent jamais entre eux ; l'orchestrateur est le seul médiateur.

### 2.5 Validation programmatique

À chaque synthèse d'étape, le runner applique (`src/validation.py`) :

- `collecter_ids_reels` : identifiants réellement manipulés par les outils (arguments et résultats) ;
- `valider_synthese` : non-contradiction, complétude, authenticité des identifiants (C1–C6) ;
- `extraire_json` : extraction robuste du premier objet JSON bien formé ;
- **périmètre de recherche imposé par le code** (D54) : la requête exécutée par `search_threads` est toujours celle fournie par l'orchestrateur ; une dérive est substituée et journalisée (`requete search_remplacee`).

Un rejet interrompt le run, est journalisé avec son motif, et n'est jamais restitué tel quel à l'utilisateur. S'y ajoute le recalcul des empreintes (C6, §3).

> **Définition canonique numérotée des contrôles C1–C6** : [docs/architecture/validation.md](../architecture/validation.md) (C6 inclut le recalcul depuis la lecture API réelle, §3).

### 2.6 Reprise sur incident et planification

- **Checkpoints** : après chaque étape validée, l'état du run est persisté en JSON local.
- **Idempotence** : requêtes construites depuis le registre — classification `is:unread -label:"Agent/traité"`, spam `in:spam -label:"Agent/spam-confirme"`, suppression `label:"Agent/traité" label:"Agent/notification" older_than:24h` ; un run interrompu puis relancé (même `run_id`, `--run-id`) ne retraite pas les étapes déjà checkpointées.
- **Reprise** : en cas de crash, le run relancé saute les étapes déjà checkpointées. Erreurs transitoires (429, 5xx) retentées : 3 tentatives, backoff exponentiel avec jitter (base 2 s).
- **Planification** : exécutable Python déclenché manuellement ou par cron (quotidien, heures creuses) ; le run de suppression est planifié indépendamment (T+24h). `--tout` enchaîne les runs jusqu'à épuisement des non lus (plafond de runs, `run_id` distinct par run) pour vider un retard ponctuel.

### 2.7 Limites connues

- Pas de parallélisme inter-agents : le pipeline est séquentiel par conception (quotas, ordre spam → classification).
- Planification externe (cron), sans moteur de workflow.
- L'état entre les runs repose sur les libellés Gmail et les checkpoints locaux ; la perte des checkpoints dégrade la reprise au niveau du run entier (l'idempotence par libellés reste le filet de sécurité).

---

## 3. Clés de dédoublonnage et empreintes (état actuel)

L'étape 5 (dédoublonnage) est un **stub no-op en v1** (décision D46 : `nb_doublons=0`, aucun libellé `Agent/doublon` posé). Les fondations sont en place et utilisées à l'étape 4 :

1. **Clé primaire : l'en-tête `Message-ID` (RFC 5322)** — normalisé (espaces et `<>` retirés, minuscules) ;
2. **Clé secondaire : empreinte SHA-256** du triplet (expéditeur, sujet, corps) normalisés (`src/dedup.py`).

L'agent classification déclare `message_id_rfc` et `empreinte` dans sa synthèse ; l'orchestrateur **recalcule** ces valeurs depuis la lecture API réelle (`get_message`) et rejette la synthèse en cas d'écart (C6, anti-hallucination — [docs/architecture/validation.md](../architecture/validation.md)).

---

## 4. Gestion des rate limits

Deux familles de quotas : API Mistral (429) et API Gmail (unités de quota).

Mesures en place :

1. **Bornage par run** : `search_threads` capé par `cap_threads_recherche()` = `min(max_threads_par_run, (plafond_appels_outils - 1 - marge_appels_reprise) // 2)` (23 par défaut, D58) ; les non lus restants sont absorbés au run suivant (ou immédiatement avec `--tout`, §2.6).
2. **Backoff exponentiel avec jitter** : 3 tentatives, base 2 s, sur 429/5xx (API Mistral et outils Gmail).
3. **Garde-fou anti-boucle** : plafond d'appels d'outils (`plafond_appels_outils: 50`) et plafond de lectures (`plafond_lectures: 100`) ; au-delà, abandon propre du run.
4. **Cache intra-run** : `list_labels` mis en cache par run.
5. **Lissage de charge** : run de suppression séparé (T+24h), planification en heures creuses.
6. **Plafonds de modèle** : `temperature: 0.0`, `max_tokens: 8000`, timeout HTTP 300 s (`config/settings.yaml`).
7. **Observabilité** : chaque exécution d'outil journalisée avec ses arguments bornés (`outil execute` dans `logs/gmailagent.log`), chaque run encadré par `debut_run`/`fin_run` horodatés.

---

## 5. Références documentaires

- SDK Python Mistral : [https://docs.mistral.ai/resources/sdks](https://docs.mistral.ai/resources/sdks)
- API Gmail (quotas) : [https://developers.google.com/gmail/api/reference/usage](https://developers.google.com/gmail/api/reference/usage)
