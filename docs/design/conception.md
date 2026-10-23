# Spécification générale — Pipeline de tri de messagerie Gmail

> Historique : une première version de ce document proposait deux scénarios
> d'orchestration — des handoffs conversationnels (scénario A) et des Workflows
> Mistral Studio (scénario B). Tous deux sont écartés (voir §6) au profit d'une
> orchestration programmatique en Python (§2), seule retenue pour la mise en
> œuvre.

## 1. Contexte et objectifs

### 1.1 Contexte

L'ensemble des messages personnels de l'utilisateur est consolidé dans une boîte Gmail unique. Trois catégories de messages coexistent : les messages natifs Gmail, les messages reroutés depuis d'autres messageries (via Thunderbird), et les messages indûment filtrés en spam.

Trois agents spécialisés sont constitués :

| Agent                | Responsabilité                                                                                  | Portée d'outils                                                                        |
| -------------------- | ----------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| Agent classification | Lire les messages non lus, les classer, évaluer l'urgence, appliquer les libellés de classement | search_threads, get_thread, label_message, list_labels                                 |
| Agent spam           | Lire le dossier spam, évaluer la légitimité, replacer si nécessaire                             | search_threads, get_thread, label_message, list_labels                                 |
| Agent suppression    | Mettre à la corbeille les messages traités, après délai de grâce d'une heure                    | search_threads, label_message, list_labels (mise à la corbeille via le libellé TRASH)  |

Chaque agent suit les principes transverses établis :

- sortie structurée JSON (schéma imposé), avec champ statut parmi `synthese`, `aucun_message`, `echec_technique` (variantes par agent, §2.4) ;
- règles de véracité strictes : ne mentionner que des messages réellement lus via les outils ; jamais de classement imaginaire en cas d'échec ou de boîte vide ;
- validation programmatique côté orchestrateur : cohérence des identifiants avec les exécutions d'outils réelles, complétude, non-contradiction ;
- périmètre d'outils minimal (principe du moindre privilège) ; aucun agent ne dispose de la capacité d'envoi ni de suppression définitive ;
- contrats d'interface explicites entre l'orchestrateur et chaque agent, et pour chaque outil utilisé (§2.4).

### 1.2 Conventions de coordination

Les libellés Gmail servent de canal de coordination entre agents et entre exécutions :

- `Agent/traité` : apposé par l'agent classification ou l'agent spam une fois le message traité et validé ;
- `Agent/a-repondre`, `Agent/information`, `Agent/notification` : libellés de classement ;
- `Agent/doublon` : apposé sur les copies redondantes identifiées par le dédoublonnage (§3) ;
- `Agent/valide-spam` : apposé par l'agent spam sur les messages replacés depuis le spam.

La corbeille (jamais la suppression définitive) est le seul moyen d'éliminer les copies redondantes. Les originaux demeurent dans les messageries d'origine.

### 1.3 Scripts de référence

Les scripts fournis (`agent01a`, `agent01b`, `agent01c`, `agent02`, `agent02b`, `agent03a`, `agent03b`, `agent03c`) servent d'exemples de conception uniquement : ils ne sont pas versionnés dans ce dépôt. Ils illustrent :

- le pattern **agent permanent** créé une fois côté Studio, référencé par UUID (`01a`/`01b`/`01c` pour un tri à libellés fixes ; `03a`/`03b`/`03c` pour un tri dynamique avec création de libellés) ;
- le pattern **conversation éphémère**, sans agent enregistré, où modèle, outils et schéma sont passés à chaque appel (`02` en flux, `02b` synchrone) ;
- les fonctions de validation réutilisées par le pipeline : `collecter_ids_reels`, `valider_synthese`, `extraire_json`, ainsi que le garde-fou anti-boucle du script `02`.

---

## 2. Scénario retenu — Orchestration programmatique en Python

### 2.1 Principe

Un orchestrateur Python pilote séquentiellement les trois agents sous forme de conversations. Chaque étape produit une synthèse structurée, validée programmatiquement avant de passer à la suivante. L'état est explicite : en mémoire pendant le run, persisté par checkpoints entre les étapes, et dans Gmail via les libellés (canal persistant entre les runs).

### 2.2 Étapes du pipeline

| #   | Étape                     | Implémentation                          | Entrées                               | Sorties                         |
| --- | ------------------------- | --------------------------------------- | ------------------------------------- | ------------------------------- |
| 1   | lecture spam              | conversation agent spam                 | —                                     | synthèse_spam (JSON)            |
| 2   | validation spam           | code Python                             | synthèse_spam, exécutions d'outils    | ok / rejet (interrompt le run)  |
| 3   | lecture non lus           | conversation agent classification       | —                                     | synthèse_classification (JSON)  |
| 4   | validation classification | code Python                             | synthèse_classification, exécutions   | ok / rejet (interrompt le run)  |
| 5   | dédoublonnage             | code Python déterministe (§3)           | synthèse_classification, empreintes   | libellé `Agent/doublon` posé    |
| 6   | agrégation et restitution | code Python                             | synthèses validées                    | rapport final                   |

L'ordre est imposé : le spam est traité avant la classification, afin que les messages replacés rejoignent le pool des non lus à classer.

L'étape de suppression fait l'objet d'un **run séparé**, planifié (T+1h) : conversation avec l'agent suppression, portant sur les messages `label:"Agent/traité" older_than:1h`, suivie de sa propre validation. Le délai de grâce d'une heure s'applique aussi aux doublons étiquetés `Agent/doublon`.

### 2.3 Agents permanents ou éphémères ?

Les deux patterns des scripts de référence sont évalués :

| Critère                                          | Agents permanents (`01a`, `03a`)                          | Conversations éphémères (`02`, `02b`)                     |
| ------------------------------------------------ | --------------------------------------------------------- | --------------------------------------------------------- |
| Création                                         | Une fois, côté Studio ; référencés par UUID               | À chaque exécution                                        |
| Configuration (prompt, outils, schéma de sortie)  | Stockée côté Studio                                       | Passée à l'appel, dans le code                            |
| Versionnement                                    | Hors dépôt ; risque de dérive non tracée                  | Versionnée avec le code (git)                             |
| Reproductibilité                                  | Dépend de la configuration Studio                         | Totale                                                    |
| Réutilisation                                     | Studio (interactif) + API                                 | Code / API uniquement                                     |
| Nettoyage                                        | Cycle create/delete à gérer (`01c`, `03c`)                | Aucun                                                     |
| Historique des exécutions                        | Côté Studio                                               | À journaliser par l'orchestrateur                         |

**Recommandation : conversations éphémères pour le pipeline.** L'orchestration étant pilotée par du code, un agent permanent ajouterait un état externe dont la configuration échapperait au versionnement, sans bénéfice pour un usage non interactif. Les agents permanents gardent un intérêt pour un usage manuel ponctuel depuis l'interface Studio, hors pipeline.

### 2.4 Contrats d'interface

La communication repose sur des contrats explicites, dans les deux patterns (permanent comme éphémère) :

1. **Contrat de sortie par agent** — schéma JSON strict imposé au niveau du décodage (`response_format.json_schema`, `strict: true`), `additionalProperties: false` :
   - classification : `statut` (`synthese` | `aucun_message` | `echec_technique`) et `messages[]` avec champs requis `id` (messageId), `objet`, `expediteur`, `categorie` (enum des trois libellés de classement), `urgence` (enum `haute`/`moyenne`/`basse`), `motif`, plus `message_id_rfc` et `empreinte` pour le dédoublonnage (§3) ;
   - spam : variantes de statut `deplaces` / `aucun_message` / `echec_technique`, champs adaptés (`id`, `objet`, `expediteur`, `motif`) ;
   - suppression : variantes `supprimes` / `aucun_message` / `echec_technique`, avec `count` et `ids`.
2. **Enveloppe commune** — toute synthèse d'étape est enveloppée avant traitement par l'orchestrateur : `{statut, messages, erreur?, meta: {run_id, etape, agent, timestamp}}`. Le champ `erreur` n'est présent qu'en cas d'échec technique.
3. **Contrat orchestrateur** — modèles typés (pydantic) pour les échanges entre étapes : `MessageClasse`, `SyntheseEtape`, `RapportFinal`. Le typage fort détecte les dérives de contrat à la compilation ; la sérialisation JSON alimente les checkpoints et le rapport final.
4. **Contrat d'outils** — allow-list par agent (`tool_configuration.include`), conforme au moindre privilège. Si des outils hors Gmail venaient à être utilisés (calendrier, drive, CRM...), chacun fera l'objet d'un schéma de sortie attendu et d'un validateur dédié ; la fonction `collecter_ids_reels` est alors généralisée par connecteur, le contexte (message, thread, libellé, ressource externe) étant déduit du nom de l'outil, sur le pattern du script `03b`.
5. **Médiation** — les agents ne s'appellent jamais entre eux : l'orchestrateur Python est le seul médiateur, les données transitent exclusivement via les contrats ci-dessus. La persistance entre les exécutions repose sur les libellés Gmail.

### 2.5 Validation programmatique

Les fonctions de validation des scripts de référence sont appliquées par l'orchestrateur à chaque synthèse d'étape :

- `collecter_ids_reels` : parcours des exécutions d'outils réelles pour recueillir les identifiants réellement manipulés (messages, threads, libellés) ;
- `valider_synthese` : contrôle de non-contradiction (statut d'échec sans messages), d'authenticité (identifiants connus) et de complétude ;
- `extraire_json` : extraction robuste du premier objet JSON bien formé.

Un rejet interrompt le run, est journalisé avec son motif, et n'est jamais restitué tel quel à l'utilisateur. S'y ajoute le contrôle des empreintes de dédoublonnage (§3).

### 2.6 Reprise sur incident et planification

- **Checkpoints** : après chaque étape validée, l'état du run (run_id, étapes, statuts, identifiants) est persisté dans un fichier JSON local.
- **Idempotence** : la recherche de l'agent classification porte sur `is:unread -label:"Agent/traité"` ; un run interrompu puis relancé ne retraite pas les messages déjà traités. La suppression porte sur `label:"Agent/traité" older_than:1h`.
- **Reprise** : en cas de crash, le run est relancé ; les étapes déjà checkpointées sont sautées. Une erreur transitoire (429, 5xx) est retentée selon la politique de backoff (§4).
- **Planification** : le pipeline est un exécutable Python, déclenché manuellement ou par cron / timer systemd (quotidien, en heures creuses). Le run de suppression est planifié indépendamment (T+1h). Si le pipeline est hébergé sur un serveur, il ne dépend pas du poste local.

### 2.7 Limites connues

- Pas de parallélisme inter-agents : le pipeline est séquentiel par conception, pour maîtriser les quotas et garantir l'ordre spam → classification.
- Planification externe (cron), sans moteur de workflow.
- L'état entre les runs repose sur les libellés Gmail et les checkpoints locaux ; la perte des checkpoints dégrade la reprise au niveau du run entier (l'idempotence par libellés reste le filet de sécurité).

---

## 3. Gestion des doublons

**Origine.** Les messages reroutés depuis d'autres messageries (via Thunderbird) coexistent avec leurs originaux : mêmes contenus, threads Gmail distincts, identifiants de message différents.

**Clés de dédoublonnage.**

1. **Clé primaire : l'en-tête `Message-ID` (RFC 5322)**, conservé intact lors d'un reroutage. Normalisation : suppression des espaces et de l'encadrement `<>`, mise en minuscules.
2. **Clé secondaire : empreinte SHA-256** sur le triplet (expéditeur normalisé, sujet normalisé, corps normalisé). Normalisations : sujet en minuscules débarrassé des préfixes `Re:` / `Fwd:` / `Tr:` et des espaces ; corps décodé (quoted-printable, base64), HTML réduit en texte brut, minuscules, espaces normalisés. Ce filet attrape les reroutages qui auraient altéré le `Message-ID`.

**Calcul et validation.** L'agent classification, qui lit déjà le contenu complet des messages, déclare `message_id_rfc` et `empreinte` dans sa synthèse. L'orchestrateur **recalcule** ces valeurs à partir des sorties réelles de `get_thread` (qu'il collecte déjà pour la validation) et rejette la synthèse en cas d'écart — même principe de véracité que pour les identifiants.

**Politique.** Pour chaque groupe de doublons, la copie arrivée la plus ancienne (`internalDate` minimale) est conservée ; les autres reçoivent le libellé `Agent/doublon`. L'agent suppression les met à la corbeille après le délai de grâce d'une heure. Aucune suppression définitive ; les originaux dans les messageries d'origine ne sont pas touchés.

**Pourquoi du code et pas du LLM.** Le dédoublonnage est une comparaison déterministe : le faire en Python évite des appels de modèle, est reproductible et testable unitairement. L'agent classification se contente de fournir les deux champs ; toute l'intelligence de groupe reste dans l'orchestrateur.

---

## 4. Gestion des rate limits

Deux familles de quotas sont en jeu : l'API Mistral (RPM/TPM selon le tier, erreurs 429) et l'API Gmail (unités de quota par appel, plafond de 250 unités/seconde/utilisateur et 1 milliard par jour).

Mesures retenues :

1. **Bornage par run** : la recherche `search_threads` est paginée avec `max_results` (plafond conseillé : 50 messages par run). Les non lus restants le restent et sont absorbés au run suivant — la pagination Gmail garantit la reprise naturelle.
2. **Backoff exponentiel avec jitter** : 3 tentatives, base de 2 secondes, sur les 429 et 5xx, applicable aux appels Mistral comme aux appels d'outils Gmail.
3. **Garde-fou anti-boucle** : plafond d'appels sur les outils de consultation (`search_threads`, `list_labels`), repris du script `02` ; au-delà, abandon propre du run avec statut `echec_technique`.
4. **Cache intra-run** : `list_labels` appelé une seule fois par agent et par run ; threads lus conservés en mémoire.
5. **Mode incrémental** : si le volume devient significatif, remplacer le scan `is:unread` par `history.list` (à partir du `historyId` mémorisé au run précédent) pour ne lire que les deltas.
6. **Lissage de charge** : le run de suppression est séparé (T+1h) ; la planification est placée en heures creuses.
7. **Plafonds de modèle** : `temperature: 0.0` et `max_tokens` capsés (1500 pour la classification, 2000 si création de libellés), timeout HTTP explicite (300 s) — déjà en place dans les scripts de référence.
8. **Observabilité** : journaliser par run le nombre d'appels d'outils, les tokens consommés et les latences, afin d'ajuster les plafonds sur des données réelles.

---

## 5. Références documentaires

- Agents et Conversations : [https://docs.mistral.ai/studio/agents/agents-api](https://docs.mistral.ai/studio/agents/agents-api)
- Connecteurs (gestion) : [https://docs.mistral.ai/studio/connectors/management](https://docs.mistral.ai/studio/connectors/management)
- Connecteurs (conversations) : [https://docs.mistral.ai/studio/connectors/conversations](https://docs.mistral.ai/studio/connectors/conversations)
- SDK Python : [https://docs.mistral.ai/resources/sdks](https://docs.mistral.ai/resources/sdks)
- API Gmail (quotas) : [https://developers.google.com/gmail/api/reference/usage](https://developers.google.com/gmail/api/reference/usage)

---

## 6. Options écartées

| Option                                 | Motif de l'écart                                                                                                                                                                                           |
| -------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Scénario A — handoffs conversationnels | Pas d'état partagé de premier ordre, pas de reprise sur incident (état partiel possible), validation cantonnée au script appelant, planification externe. Remplacé par l'orchestration programmatique, qui garde la simplicité sans ces faiblesses. |
| Scénario B — Workflows Mistral Studio  | Fonctionnalité en Public Preview (interface susceptible d'évoluer), dépendance à une orchestration externe au code, pour un bénéfice (durabilité, planification) que l'orchestrateur Python + checkpoints + cron reproduit de façon versionnée et testable.              |
