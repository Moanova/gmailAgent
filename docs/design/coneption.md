# Spécification générale — Pipeline de tri de messagerie Gmail

## 1. Contexte et objectifs

### 1.1 Contexte

L'ensemble des messages personnels de l'utilisateur est consolidé dans une boîte Gmail unique. Trois catégories de messages coexistent : les messages natifs Gmail, les messages reroutés depuis d'autres messageries (via Thunderbird), et les messages indûment filtrés en spam.

Trois agents spécialisés sont constitués :


| Agent                | Responsabilité                                                                                  | Portée d'outils                                                        |
| -------------------- | ----------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| Agent classification | Lire les messages non lus, les classer, évaluer l'urgence, appliquer les libellés de classement | search\_threads, get\_thread, label\_thread                            |
| Agent spam           | Lire le dossier spam, évaluer la légitimité, replacer si nécessaire                             | search\_threads, get\_thread, label\_thread                            |
| Agent suppression    | Mettre à la corbeille les messages traités, après délai de grâce                                | search\_threads, label\_thread (mise à la corbeille via libellé TRASH) |


Chaque agent suit les principes transverses établis :

- sortie structurée JSON (schéma imposé), avec champ statut parmi `synthese`, `aucun_message`, `echec_technique` ;
- règles de véracité strictes : ne mentionner que des messages réellement lus via les outils ; jamais de classement imaginaire en cas d'échec ou de boîte vide ;
- validation programmatique côté appelant : cohérence des identifiants avec les exécutions d'outils réelles, complétude, non-contradiction ;
- périmètre d'outils minimal (principe du moindre privilège) ; aucun agent ne dispose de la capacité d'envoi ni de suppression définitive.

### 1.2 Conventions de coordination

Les libellés Gmail servent de canal de coordination entre agents :

- `Agent/traité` : apposé par l'agent classification ou l'agent spam une fois le message traité et validé ;
- `Agent/a-repondre`, `Agent/information`, `Agent/notification` : libellés de classement ;
- `Agent/valide-spam` : apposé par l'agent spam sur les messages replacés depuis le spam.

La corbeille (jamais la suppression définitive) est le seul moyen d'éliminer les copies redondantes. Les originaux demeurent dans les messageries d'origine.

---

## 2. Scénario A — Orchestration par handoffs

### 2.1 Principe

Un agent coordinateur est créé côté Studio. Il ne dispose d'aucun connecteur : sa seule capacité est de déléguer aux trois agents spécialisés, désignés comme outils de type handoff. Le flux est conversationnel : la coordination s'effectue au sein d'une exécution unique de l'API Conversations.

Référence documentation : [https://docs.mistral.ai/studio/agents/handoffs](https://docs.mistral.ai/studio/agents/handoffs)

### 2.2 Agents à créer (une seule fois)

Quatre appels à `client.beta.agents.create` :

1. Agent classification — instructions de tri, connecteur Gmail restreint (include : search\_threads, get\_thread, label\_thread), schéma de sortie structurée via `completion_args.response_format` (identique au script 1a existant), pas de handoff.
2. Agent spam — instructions d'évaluation conservatoire du spam, mêmes outils restreints, schéma de sortie analogue avec statut `deplaces`/`aucun_message`/`echec_technique`, pas de handoff.
3. Agent suppression — instructions de mise à la corbeille des messages portant `Agent/traité` depuis plus d'une heure, outils restreints, schéma de sortie avec statut `supprimes`/`aucun_message`/`echec_technique`, pas de handoff.
4. Agent coordinateur — modèle plus capacitaire (mistral-medium ou large), aucun connecteur, handoffs vers les trois agents ci-dessus ; instructions de séquencement (2.4).

### 2.3 Schémas de sortie

Identiques à ceux déjà spécifiés dans les scripts fournis (scripts 1a, 1b, 2) : objet à deux champs, `statut` (enum) et `messages` (liste d'objets à champs requis : id, objet, expediteur, categorie, urgence, motif). L'agent suppression et l'agent spam utilisent des variants mineurs (champs d'objet adaptés : count, ids).

### 2.4 Séquencement des handoffs

L'agent coordinateur reçoit une requête utilisateur unique et déroule :

1. délégation à l'agent spam (traiter le spam avant la classification, afin que les messages replacés soient pris en compte) ;
2. délégation à l'agent classification (tri des non lus, désormais enrichi des messages replacés) ;
3. retour à l'utilisateur avec les deux synthèses agrégées.

La suppression n'est pas déclenchée dans la même exécution (délai de grâce d'une heure) ; elle fait l'objet d'un appel séparé à l'agent suppression, éventuellement planifié.

### 2.5 Validation programmatique

La validation s'effectue côté script Python appelant, sur la réponse de la conversation :

- parcours des `tool.execution` de la réponse pour recueillir les identifiants réellement manipulés (fonction `collecter_ids_reels`, inchangée) ;
- pour chaque synthèse partielle rendue par les agents délégués : contrôle de non-contradiction (statut d'échec sans messages), d'authenticité (identifiants connus) et de complétude ;
- rejet explicite avec motif en cas d'incohérence ; jamais de restitution aveugle.

### 2.6 Appel Python (forme générale)

```python
response = client.beta.conversations.start(
    agent_id="<uuid-coordinateur>",   # UUID obligatoire, pas le nom
    inputs=[{"role": "user", "content": "Traite mes messages non lus et le spam, puis restitue les synthèses."}],
)
```

La fonction de lancement gère `SDKError` (erreur technique), la réponse vide, le JSON invalide et les rejets de validation, comme dans les scripts existants.

### 2.7 Limites connues du scénario A

- Pas d'état partagé de premier ordre : la coordination repose sur les libellés et les instructions du coordinateur.
- Pas de reprise sur incident : un échec en cours d'exécution interrompt la chaîne ; la relance doit être manuelle.
- Pas de planification native : le déclenchement reste à la charge du script ou d'un cron.

---

## 3. Scénario B — Orchestration par Studio Workflows

### 3.1 Principe

Le pipeline est défini comme un workflow : processus multi-étapes durable, où chaque étape est journalisée, les tentatives et reprises sont natives, et l'état est partagé entre étapes. Les étapes non-LLM (validation) trouvent leur place comme activités de premier ordre.

Référence documentation : [https://docs.mistral.ai/studio/workflows/getting-started/overview](https://docs.mistral.ai/studio/workflows/getting-started/overview)

### 3.2 Étapes du workflow


| #   | Étape                     | Type                       | Entrées                               | Sorties                         |
| --- | ------------------------- | -------------------------- | ------------------------------------- | ------------------------------- |
| 1   | lecture spam              | appel agent spam           | —                                     | synthèse\_spam (JSON)           |
| 2   | validation spam           | code (non-LLM)             | synthèse\_spam, ids\_outils           | ok / rejet (interrompt)         |
| 3   | lecture non lus           | appel agent classification | —                                     | synthese\_classification (JSON) |
| 4   | validation classification | code (non-LLM)             | synthese\_classification, ids\_outils | ok / rejet (interrompt)         |
| 5   | agrégation et restitution | code (non-LLM)             | synthèses validées                    | rapport final                   |
| 6   | suppression différée      | appel agent suppression    | déclencheur temporel (T+1h)           | synthèse\_suppression           |


L'étape 6 est une exécution séparée du workflow, déclenchée sur planification (par exemple quotidienne) : elle met à la corbeille les messages portant `Agent/traité` depuis plus d'une heure. Le partage d'état entre étapes 1 à 5 est assuré par le moteur de workflow ; entre l'exécution principale et l'étape 6, par les libellés Gmail (canal de coordination persistant conservé).

### 3.3 Durabilité et reprise

Chaque étape est enregistrée dans l'historique d'événements ; en cas de crash, l'exécution reprend au dernier pas complété. Les tentatives (retries) sont configurées par activité, avec temporisation croissante, notamment sur les appels d'agents (erreurs transitoires de quota ou de disponibilité).

### 3.4 Planification

Le workflow principal (étapes 1 à 5) est déclenchable :

- manuellement, par appel depuis le script Python (répondant au besoin initial « lorsque j'en ai besoin ») ;
- ou sur planification récurrente (quotidienne), sans dépendance au poste local.

L'étape 6 est planifiée indépendamment.

### 3.5 Validation programmatique

Les fonctions de validation (`collecter_ids_reels`, `valider_synthese`, inchangées par rapport aux scripts fournis) sont intégrées comme activités de code du workflow (étapes 2 et 4). Un rejet interrompt le pipeline et marque l'exécution en échec, avec motif journalisé et consultable dans l'historique — remplaçant le simple message de rejet du scénario script.

### 3.6 Restitution

Le rapport final (étape 5) agrège :

- synthèse de classification validée (messages classés, urgence, motif) ;
- synthèse spam validée (messages replacés) ;
- statut global (succès / échec partiel avec étape fautive).

Sa forme reprend le format texte des scripts existants (`[SYNTHÈSE VALIDÉE] ...`), ou un schéma JSON unique agrégé si le script appelant doit l'exploiter.

### 3.7 Appel Python (forme générale)

Le script local se réduit à un déclencheur : démarrage du workflow (par SDK ou API), puis récupération du résultat ou des événements d'exécution. La gestion d'erreur se limite à l'échec de démarrage ; les erreurs internes sont gérées par le moteur et visibles dans l'observabilité du workflow.

---

## 4. Comparaison et critères de choix


| Critère                     | Scénario A (handoffs)                   | Scénario B (workflow)                            |
| --------------------------- | --------------------------------------- | ------------------------------------------------ |
| Complexité de mise en œuvre | Modérée (agents + 1 coordinateur)       | Plus élevée (définition du workflow)             |
| Reprise sur incident        | Non (relance manuelle)                  | Native (reprise au dernier pas)                  |
| État partagé                | Via libellés Gmail                      | Natif entre étapes                               |
| Validation programmatique   | Côté script appelant                    | Étapes de code intégrées                         |
| Planification               | Externe (cron)                          | Native                                           |
| Observabilité               | Limitée à la réponse API                | Historique d'événements, traces                  |
| Pertinence pédagogique      | Élève la coordination conversationnelle | Encapsule la mécanique ; moins formatrice        |
| Statut de la fonctionnalité | Stable                                  | Public Preview (interface susceptible d'évoluer) |


Recommandation : pour un premier codage avec Vibe CLI, commencer par le scénario A, qui réutilise presque intégralement les scripts existants (il suffit d'ajouter l'agent coordinateur et d'adapter la validation aux synthèses multiples) ; migrer vers le scénario B une fois le pipeline stabilisé, pour bénéficier de la durabilité et de la planification.

---

## 5. Références documentaires

- Agents et Conversations : [https://docs.mistral.ai/studio/agents/agents-api](https://docs.mistral.ai/studio/agents/agents-api)
- Handoffs : [https://docs.mistral.ai/studio/agents/handoffs](https://docs.mistral.ai/studio/agents/handoffs)
- Connecteurs (gestion) : [https://docs.mistral.ai/studio/connectors/management](https://docs.mistral.ai/studio/connectors/management)
- Connecteurs (conversations) : [https://docs.mistral.ai/studio/connectors/conversations](https://docs.mistral.ai/studio/connectors/conversations)
- Workflows (vue d'ensemble) : [https://docs.mistral.ai/studio/workflows/getting-started/overview](https://docs.mistral.ai/studio/workflows/getting-started/overview)
- SDK Python : [https://docs.mistral.ai/resources/sdks](https://docs.mistral.ai/resources/sdks)