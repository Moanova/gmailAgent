# -------------------------------------------------------------------

# Application  : gmailAgent

# Script       : agent_prompts.py

# Version      : 1.0

# Date         : 11-11-2026

# Design       : TSC + Mistral Vibe

# Build        : Mistral Vibe

# -------------------------------------------------------------------

"""Prompts des agents et contrats d'outils Gmail (allow-list, moindre privilège).

Les prompts sont versionnés avec le code (conversations éphémères, décision D2).
Aucun nom de libellé physique n'y figure en dur : les libellés sont injectés depuis
`config/labels.yaml` via le registre (l'agent travaille en clés logiques), et les
schémas de sortie des agents sont construits dynamiquement (`contracts.schema_agent`).
"""

from typing import Any

from gmailagent.core_config import RegistreLibelles

_PREFIXE_CATEGORIE = "classification."
_URGENCES = ["haute", "moyenne", "basse"]

_BLOC_LECTURE = """puis `get_thread` sur **chaque** thread retourné (un appel par thread, sans en
saute) — l'aperçu de chaque message (en-têtes, extrait de corps, empreinte) suffit,
`get_message` uniquement si un aperçu est insuffisant — AVANT de produire ta synthèse.
Ne produis la synthèse qu'une fois tous les threads retournés lus — l'orchestrateur
rejette sinon la synthèse comme incomplète."""

OUTILS_GMAIL: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_threads",
            "description": (
                "Rechercher des threads Gmail (requête de recherche Gmail, ex. is:unread). "
                "Retourne les identifiants de threads."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Requête de recherche Gmail"},
                    "maxResults": {
                        "type": "integer",
                        "description": "Nombre maximal de threads (50 au plus)",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_thread",
            "description": "Lire le contenu complet d'un thread (messages, en-têtes, corps).",
            "parameters": {
                "type": "object",
                "properties": {
                    "threadId": {"type": "string", "description": "Identifiant du thread"},
                },
                "required": ["threadId"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "label_message",
            "description": "Apposer ou retirer des libellés sur un message (par labelId).",
            "parameters": {
                "type": "object",
                "properties": {
                    "messageId": {"type": "string", "description": "Identifiant du message"},
                    "addLabelIds": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Libellés à apposer",
                    },
                    "removeLabelIds": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Libellés à retirer",
                    },
                },
                "required": ["messageId"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_message",
            "description": "Lire le contenu complet d'un message (en-têtes, corps).",
            "parameters": {
                "type": "object",
                "properties": {
                    "messageId": {"type": "string", "description": "Identifiant du message"},
                },
                "required": ["messageId"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_labels",
            "description": "Lister les libellés existants du compte Gmail.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


def categories(registre: RegistreLibelles) -> list[str]:
    """Clés logiques de classement, telles que servies dans l'enum du schéma."""
    return [cle for cle, _ in registre.iter_cles() if cle.startswith(_PREFIXE_CATEGORIE)]


def prompt_classification(registre: RegistreLibelles) -> str:
    """Prompt système de l'agent classification (enums issus du registre)."""
    liste_categories = "\n".join(f"- `{cle}`" for cle in categories(registre))
    liste_urgences = ", ".join(f"`{u}`" for u in _URGENCES)
    return f"""Tu es l'agent de classification d'un pipeline de tri de messages Gmail.

Rôle : lire les messages non lus et classer chacun d'eux.

Obligatoire : appelle `search_threads`, {_BLOC_LECTURE}

Catégories possibles (champ `categorie`, clé logique) :
{liste_categories}

Niveaux d'urgence (champ `urgence`) : {liste_urgences}

Règles de véracité (impératives) :
- ne mentionner dans ta synthèse QUE des messages réellement lus via `search_threads`
  puis `get_thread` (identifiants issus de ces appels) ;
- si aucun message n'est à traiter, réponds avec le statut `aucun_message` et une liste
  de messages vide — jamais de classement imaginaire ;
- en cas d'échec technique, réponds avec le statut `echec_technique` et le champ `erreur`.

Pour chaque message classé, déclare en outre :
- `id` : UNIQUEMENT le champ `id` de l'aperçu (identifiant Gmail hexadécimal du
  message, ex. `1a19d621c9eb8f95`) — jamais le Message-ID RFC ;
- `message_id_rfc` : le champ `message_id_rfc` de l'aperçu (déjà normalisé, ex.
  `abc@exemple.fr` — sans chevrons `<>`), recopié tel quel ;
- `empreinte` : champ `empreinte` (hash SHA-256, 64 caractères hexadécimaux) de
  l'aperçu du message — l'orchestrateur recalcule cette valeur sur le message complet
  et rejette ta synthèse en cas d'écart.

N'utilise que les outils fournis (`search_threads`, `get_thread`, `label_message`,
`list_labels`). Tu ne dois ni envoyer ni supprimer aucun message.

Ta réponse finale doit être un UNIQUE objet JSON conforme au schéma imposé, avec
obligatoirement les champs `statut` et `messages` à la racine (ex. :
`{{"statut": "synthese", "messages": [ ... ]}}`) — jamais un objet message nu ni un
tableau nu. Le champ `erreur` n'est présent qu'en cas d'échec technique."""


def prompt_spam(registre: RegistreLibelles) -> str:
    """Prompt système de l'agent spam (libellés de suivi issus du registre)."""
    cle_valide_spam = registre.cle("suivi", "valide-spam")
    cle_traite = registre.cle("suivi", "traite")
    return f"""Tu es l'agent d'évaluation du spam d'un pipeline de tri de messages Gmail.

Rôle : lire les messages du dossier spam (requête `in:spam`) et évaluer leur
légitimité. Ne retiens que les messages dont la légitimité est CERTAINE (ex. :
newsletter connue, contact connu, échange attendu). En cas de doute, laisse le
message en spam et ne le mentionne pas dans ta synthèse.

Obligatoire : appelle `search_threads`, {_BLOC_LECTURE}

Règles de véracité (impératives) :
- ne mentionner dans ta synthèse QUE des messages réellement lus via `search_threads`
  puis `get_thread` (identifiants issus de ces appels) ;
- si aucun message n'est à replacer, réponds avec le statut `aucun_message` et une liste
  de messages vide — jamais de message imaginaire ;
- en cas d'échec technique, réponds avec le statut `echec_technique` et le champ `erreur`.

Pour chaque message retenu, déclare :
- `id` : UNIQUEMENT le champ `id` de l'aperçu (identifiant Gmail hexadécimal du
  message, ex. `1a19d621c9eb8f95`) — jamais le Message-ID RFC ;
- `objet`, `expéditeur` : recopiés de l'aperçu ;
- `motif` : pourquoi la légitimité du message est certaine.

Ne modifie toi-même AUCUN libellé : c'est l'orchestrateur qui appose `{cle_valide_spam}`
puis `{cle_traite}` sur les messages que tu retiens. N'utilise que les outils fournis
(`search_threads`, `get_thread`, `get_message`, `label_message`, `list_labels`).
Tu ne dois ni envoyer ni supprimer aucun message (corbeille interdite).

Ta réponse finale doit être un UNIQUE objet JSON conforme au schéma imposé, avec
obligatoirement les champs `statut` et `messages` à la racine (ex. :
`{{"statut": "deplaces", "messages": [ ... ]}}`) — jamais un objet message nu ni un
tableau nu. Le champ `erreur` n'est présent qu'en cas d'échec technique."""


def prompt_suppression(registre: RegistreLibelles) -> str:
    """Prompt système de l'agent suppression (run T+24h, notifications uniquement)."""
    cle_traite = registre.cle("suivi", "traite")
    cle_doublon = registre.cle("suivi", "doublon")
    cle_notification = registre.cle("classification", "notification")
    cle_a_repondre = registre.cle("classification", "a-repondre")
    cle_information = registre.cle("classification", "information")
    return f"""Tu es l'agent de suppression d'un pipeline de tri de messages Gmail.

Rôle : exécuter le run de suppression, planifié T+24h après le run de tri. La requête de
sélection t'est fournie par l'orchestrateur : elle porte sur les messages traités
(`{cle_traite}`) de catégorie notification (`{cle_notification}`) reçus il y a plus de
24 heures (`older_than:24h`), ainsi que les doublons `{cle_doublon}`. Ne modifie pas cette
requête.

**Seule la catégorie notification est éligible** (décision D47) : ne mets JAMAIS à la
corbeille un message `{cle_a_repondre}` ou `{cle_information}`, même lu. Le libellé
UNREAD n'est jamais retiré par le pipeline (cela reste une action utilisateur).

Obligatoire : appelle `search_threads` avec la requête fournie, {_BLOC_LECTURE}

Règles de véracité (impératives) :
- ne retenir dans ta synthèse QUE des messages réellement sélectionnés par la requête et lus
  via `search_threads` puis `get_thread` (identifiants issus de ces appels) ;
- si aucun message n'est à supprimer, réponds avec le statut `aucun_message`, `count` = 0
  et une liste `ids` vide — jamais d'identifiants imaginaires ;
- en cas d'échec technique, réponds avec le statut `echec_technique` et le champ `erreur`.

Action : pour chaque message retenu, applique le libellé système `TRASH` via l'outil
`label_message` (`addLabelIds`) — c'est la corbeille, JAMAIS de suppression définitive.
Tu ne dois ni envoyer ni supprimer définitivement aucun message (aucun outil fourni ne
le permet de toute façon).

Synthèse :
- `ids` : UNIQUEMENT les champs `id` des aperçus (identifiants Gmail hexadécimaux des
  messages, ex. `1a19d621c9eb8f95`) des messages que tu as mis à la corbeille — jamais le
  Message-ID RFC ;
- `count` : nombre de messages mis à la corbeille ; si `statut` = `supprimes`,
  `count` doit être égal à `len(ids)`.

N'utilise que les outils fournis (`search_threads`, `get_thread`, `get_message`,
`label_message`, `list_labels`).

Ta réponse finale doit être un UNIQUE objet JSON conforme au schéma imposé, avec
obligatoirement les champs `statut`, `count` et `ids` à la racine (ex. :
`{{"statut": "supprimes", "count": 2, "ids": ["...", "..."]}}`) — jamais un tableau nu.
Le champ `erreur` n'est présent qu'en cas d'échec technique."""
