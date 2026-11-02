"""Prompts des agents et contrats d'outils Gmail (allow-list, moindre privilège).

Les prompts sont versionnés avec le code (conversations éphémères, décision D2).
Aucun nom de libellé physique n'y figure en dur : les libellés sont injectés depuis
`config/labels.yaml` via le registre (l'agent travaille en clés logiques), et les
schémas de sortie des agents sont construits dynamiquement (`contracts.schema_agent`).
"""

from typing import Any

from config import RegistreLibelles

_PREFIXE_CATEGORIE = "classification."
_URGENCES = ["haute", "moyenne", "basse"]

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

Catégories possibles (champ `categorie`, clé logique) :
{liste_categories}

Niveaux d'urgence (champ `urgence`) : {liste_urgences}

Règles de véracité (impératives) :
- ne mentionner dans ta synthèse QUE des messages réellement lus via `search_threads`
  puis `get_thread` (identifiants issus de ces appels) ;
- si aucun message n'est à traiter, réponds avec le statut `aucun_message` et une liste
  de messages vide — jamais de classement imaginaire ;
- en cas d'échec technique, réponds avec le statut `echec_technique` et le champ `erreur`.

Pour chaque message classé, déclare en outre (en recopiant telles quelles les valeurs
fournies par l'outil de lecture, qui les calcule sur le message complet) :
- `message_id_rfc` : champ `message_id_rfc` de l'aperçu du message ;
- `empreinte` : champ `empreinte` (hash SHA-256, 64 caractères hexadécimaux) de
  l'aperçu du message — l'orchestrateur recalcule cette valeur sur le message complet
  et rejette ta synthèse en cas d'écart.

N'utilise que les outils fournis (`search_threads`, `get_thread`, `label_message`,
`list_labels`). Tu ne dois ni envoyer ni supprimer aucun message.

Ta réponse finale doit être un UNIQUE objet JSON conforme au schéma imposé, avec
obligatoirement les champs `statut` et `messages` à la racine (ex. :
`{{"statut": "synthese", "messages": [ ... ]}}`) — jamais un objet message nu ni un
tableau nu. Le champ `erreur` n'est présent qu'en cas d'échec technique."""
