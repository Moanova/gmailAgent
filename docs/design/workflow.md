# Workflow général du traitement — Schéma Mermaid

Ce document matérialise le pipeline décrit dans
[conception.md](conception.md) sous forme de diagramme Mermaid. Il distingue
les **phases agentiques** (conversation LLM + outils Gmail, décision
probabiliste) des **phases programmatiques** (code Python déterministe,
validation, agrégation).

## Légende

| Forme / couleur | Signification |
| --- | --- |
| 🟦 Nœud bleu (bordure bleue) | **Phase agentique** : conversation avec un agent (LLM + outils Gmail) |
| 🟩 Nœud vert (bordure verte) | **Phase programmatique** : code Python déterministe (validation, dédoublonnage, orchestration) |
| Losange | **Passage conditionnel** : la validation décide de la suite |
| Ligne pleine `ok` | Passage à l'étape suivante |
| Ligne pleine `rejet` | Interruption du run, journalisation du motif, statut `echec_technique` |
| Ligne pointillée | Déclenchement temporel entre deux runs indépendants |

## Diagramme

```mermaid
flowchart TD
    subgraph RUN["Run principal — tri (manuel ou planifié)"]
        direction TB
        A0(["Démarrage du run<br/>run_id, checkpoint initial"]):::prog
        A1[/"Étape 1 — Lecture spam<br/>conversation agent spam (LLM + outils Gmail)"/]:::agent
        A2{"Étape 2 — Validation spam<br/>cohérence, authenticité, complétude"}
        A3[/"Étape 3 — Lecture non lus<br/>conversation agent classification (LLM + outils Gmail)"/]:::agent
        A4{"Étape 4 — Validation classification<br/>IDs, complétude, empreintes recalculées"}
        A5["Étape 5 — Dédoublonnage<br/>no-op en v1 (option post-v1, D46)"]
        A6["Étape 6 — Agrégation et restitution<br/>rapport final JSON"]
        A7(["Fin du run<br/>checkpoint final"])
        RJ[/"Journalisation du motif de rejet<br/>arrêt du run — statut échec"/]

        A0 --> A1
        A1 --> A2
        A2 -- "ok" --> A3
        A2 -- "rejet" --> RJ
        A3 --> A4
        A4 -- "ok" --> A5
        A4 -- "rejet" --> RJ
        RJ --> A7
        A5 --> A6
        A6 --> A7
    end

    subgraph SUP["Run de suppression — planifié T+24h, indépendant"]
        direction TB
        S0(["Démarrage du run de suppression"])
        S1[/"Lecture des messages traités<br/>conversation agent suppression (LLM + outils Gmail)"/]:::agent
        S2{"Validation<br/>cohérence des IDs, complétude"}
        S3[/"Mise à la corbeille via le libellé TRASH<br/>(jamais de suppression définitive)"/]:::agent
        S4(["Fin du run"])
        SR[/"Journalisation du motif de rejet<br/>arrêt du run — statut échec"/]

        S0 --> S1
        S1 --> S2
        S2 -- "ok" --> S3
        S2 -- "rejet" --> SR
        SR --> S4
        S3 --> S4
    end

    A7 -. "délai de grâce de 24 h<br/>(état persistant : libellés Gmail)" .-> S0

    classDef agent fill:#dbeafe,stroke:#1d4ed8,stroke-width:2px,color:#1e3a8a;
    classDef prog fill:#dcfce7,stroke:#15803d,stroke-width:2px,color:#14532d;
    classDef agent stroke-width:2px;
```

## Lecture du schéma

### Run principal (tri)

| # | Étape | Type | Condition de passage à la suivante |
| --- | --- | --- | --- |
| 0 | Démarrage du run, checkpoint initial | Programmatique | Toujours (création du `run_id`) |
| 1 | Lecture spam — conversation agent spam | **Agentique** | Synthèse produite (quel que soit le statut) |
| 2 | Validation spam | Programmatique | `ok` si statut cohérent, IDs authentifiés, synthèse complète ; `rejet` sinon. Si `aucun_message` : apposition `Agent/spam-confirme` sur les messages lus laissés en spam (idempotence) |
| 3 | Lecture non lus — conversation agent classification | **Agentique** | Validation spam passée (ordre imposé : spam avant classification) |
| 4 | Validation classification | Programmatique | `ok` si cohérence + authenticité + complétude + empreintes recalculées conformes ; `rejet` sinon |
| 5 | Dédoublonnage — **no-op en v1** (option post-v1, D46 : stub, `nb_doublons=0`) | Programmatique | Validation classification passée |
| 6 | Agrégation et restitution (rapport final) | Programmatique | Dédoublonnage terminé |
| 7 | Fin du run, checkpoint final | Programmatique | — |

### Run de suppression (T+24h)

| # | Étape | Type | Condition de passage |
| --- | --- | --- | --- |
| 0 | Démarrage du run de suppression | Programmatique | Déclencheur temporel (planifié, indépendant du run principal) |
| 1 | Lecture des messages traités — conversation agent suppression | **Agentique** | Synthèse produite |
| 2 | Validation | Programmatique | `ok` / `rejet` (mêmes règles) |
| 3 | Mise à la corbeille via TRASH | **Agentique** (l'agent applique le libellé via l'outil) | Validation passée ; porte sur `label:"traité" label:"notification" older_than:24h` *(notification seule éligible — D47)* |
| 4 | Fin du run | Programmatique | — |

### Couplage entre les deux runs

Les deux runs sont **indépendants** (processus séparés, planifiés séparément).
Le seul canal de coordination est **Gmail lui-même**, via les libellés posés
durant le run principal (`traité` ; `doublon` uniquement post-v1, D46) : c'est l'état persistant qui
permet au run de suppression de sélectionner les messages ayant dépassé le
délai de grâce de 24 h. Aucun état n'est transmis directement entre les
deux exécutions.

## Mécanismes transverses (non représentés pour la lisibilité)

- **Reprise sur incident** : à chaque étape validée, un checkpoint est
  persisté (fichier JSON local). En cas de crash, le run relancé saute les
  étapes déjà checkpointées. L'idempotence est en outre garantie par les
  requêtes construites depuis le registre : classification
  `is:unread -label:"traité"`, spam `in:spam -label:"spam-confirme"`.
- **Retry sur erreur transitoire** : chaque phase agentique est retentée
  (3 tentatives, backoff exponentiel avec jitter, base 2 s) sur les erreurs
  429/5xx, que ce soit côté API Mistral ou côté outils Gmail. Au-delà,
  l'étape échoue et le run s'interrompt avec journalisation.
- **Garde-fou anti-boucle** : plafond d'appels sur les outils de consultation
  (`search_threads`, `list_labels`) ; au-delà, abandon propre du run.
- **Règle de véracité** : une synthèse rejetée n'est jamais restituée telle
  quelle ; le rejet est journalisé avec son motif et le run s'arrête.
