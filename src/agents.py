"""Runner de conversation éphémère (pattern synchrone, script de référence 02b).

Un appel = modèle + outils + schéma de sortie passés à chaque fois (décision D2 :
conversations éphémères, configuration versionnée avec le code). L'orchestrateur est
le seul médiateur : les agents ne s'appellent jamais entre eux (conception §2.4).

La boucle tool-calls est bornée (garde-fou anti-boucle) ; la synthèse finale est
parsée (`extraire_json`), construite (`construire_synthese`) puis validée
(`valider_synthese`, C1–C6, avec `collecter_ids_reels` sur les exécutions réelles).
"""

import json
from typing import Any, cast

from mistralai.client import Mistral
from mistralai.client.models import (
    AssistantMessage,
    ChatCompletionResponse,
    FunctionCallEntry,
    ResponseFormat,
    SystemMessage,
    Tool,
    ToolCall,
    ToolExecutionEntry,
    ToolMessage,
    UserMessage,
)

from client import avec_retry
from config import RegistreLibelles
from contracts import (
    AGENT_CLASSIFICATION,
    AgentInconnuError,
    Meta,
    SyntheseEtape,
    response_format_agent,
)
from gmail import ClientGmailAPI
from journalisation import obtenir_logger
from prompts import OUTILS_GMAIL, prompt_classification
from validation import (
    SyntheseInvalideError,
    collecter_ids_reels,
    construire_synthese,
    extraire_json,
    valider_synthese,
)

MODELE_PAR_DEFAUT = "mistral-large-latest"
MAX_TOKENS_PAR_DEFAUT = 1500
PLAFOND_APPELS_OUTILS = 50

Message = SystemMessage | UserMessage | AssistantMessage | ToolMessage
AppelOutil = ToolExecutionEntry | FunctionCallEntry


class GardeFouAtteintError(RuntimeError):
    pass


def _arguments_outil(appel: AppelOutil) -> dict[str, Any]:
    brut: Any = appel.arguments
    if isinstance(brut, str):
        if not brut.strip():
            return {}
        parse: Any = json.loads(brut)
        return parse if isinstance(parse, dict) else {}
    if isinstance(brut, dict):
        return brut
    return {}


def _tool_call_id(appel: AppelOutil) -> str:
    if isinstance(appel, FunctionCallEntry):
        return appel.tool_call_id
    return appel.id or ""


def _vers_tool_call(appel: AppelOutil) -> ToolCall:
    """Convertit une exécution d'outil reçue en ToolCall (forme requête) pour le renvoi."""
    return ToolCall.model_validate(
        {
            "type": "function",
            "id": _tool_call_id(appel),
            "function": {
                "name": appel.name,
                "arguments": json.dumps(_arguments_outil(appel), ensure_ascii=False),
            },
        }
    )


def executer_outil(nom: str, args: dict[str, Any], client: ClientGmailAPI) -> dict[str, Any]:
    """Exécute un outil Gmail contre le client (écritures neutralisées en dry-run)."""
    if nom == "search_threads":
        ids = client.search_threads(
            str(args["query"]), max_results=int(args.get("maxResults", 50))
        )
        return {"threads": ids}
    if nom == "get_thread":
        return client.get_thread(str(args["threadId"]))
    if nom == "get_message":
        return client.get_message(str(args["messageId"]))
    if nom == "list_labels":
        return {"labels": client.list_labels()}
    if nom == "label_message":
        client.modifier_libelles(
            str(args["messageId"]),
            ajouter=[str(x) for x in args.get("addLabelIds", [])],
            retirer=[str(x) for x in args.get("removeLabelIds", [])],
        )
        return {"ok": True, "messageId": str(args["messageId"])}
    raise ValueError(f"outil inconnu : {nom!r}")


def _prompt_systeme(agent: str, registre: RegistreLibelles) -> str:
    if agent == AGENT_CLASSIFICATION:
        return prompt_classification(registre)
    raise AgentInconnuError(f"agent sans prompt : {agent!r}")


def lancer_conversation(
    agent: str,
    requete: str,
    meta: Meta,
    *,
    client_mistral: Mistral,
    client_gmail: ClientGmailAPI,
    registre: RegistreLibelles,
    dry_run: bool = True,
    plafond_appels: int = PLAFOND_APPELS_OUTILS,
    modele: str = MODELE_PAR_DEFAUT,
    max_tokens: int = MAX_TOKENS_PAR_DEFAUT,
) -> tuple[SyntheseEtape, list[AppelOutil]]:
    """Lance une conversation éphémère et retourne (synthèse validée, exécutions outils)."""
    log = obtenir_logger("agents")
    messages: list[Message] = [
        SystemMessage(content=_prompt_systeme(agent, registre), role="system"),
        UserMessage(
            content=(
                f"Requête de sélection : {requete}\n"
                "Lis les threads correspondants avec les outils, puis produis ta synthèse."
            ),
            role="user",
        ),
    ]
    outils = [Tool.model_validate(outil) for outil in OUTILS_GMAIL]
    format_sortie = ResponseFormat.model_validate(response_format_agent(agent, registre))
    executions: list[AppelOutil] = []
    appels = 0
    while True:
        reponse: ChatCompletionResponse = avec_retry(
            lambda: client_mistral.chat.complete(
                model=modele,
                messages=messages,
                tools=outils,
                response_format=format_sortie,
                temperature=0.0,
                max_tokens=max_tokens,
            )
        )
        message = reponse.choices[0].message
        if message is None:
            raise SyntheseInvalideError("réponse Mistral sans message")
        appels_tool = message.tool_calls
        if appels_tool:
            contenu = message.content if isinstance(message.content, str) else ""
            messages.append(
                AssistantMessage(
                    role="assistant",
                    content=contenu,
                    tool_calls=[_vers_tool_call(cast(AppelOutil, brut)) for brut in appels_tool],
                )
            )
            for brut in appels_tool:
                appel = cast(AppelOutil, brut)
                appels += 1
                if appels > plafond_appels:
                    raise GardeFouAtteintError(
                        f"garde-fou anti-boucle : {appels} appels d'outils "
                        f"(plafond {plafond_appels}) — abandon du run"
                    )
                executions.append(appel)
                args = _arguments_outil(appel)
                resultat = executer_outil(appel.name, args, client_gmail)
                log.debug("outil execute", outil=appel.name, dry_run=dry_run)
                messages.append(
                    ToolMessage(
                        role="tool",
                        tool_call_id=_tool_call_id(appel),
                        name=appel.name,
                        content=json.dumps(resultat, ensure_ascii=False),
                    )
                )
            continue
        contenu_final = message.content
        if not isinstance(contenu_final, str):
            raise SyntheseInvalideError("contenu final de l'agent non textuel")
        payload = extraire_json(contenu_final)
        synthese = construire_synthese(agent, payload, meta)
        ids_reels = collecter_ids_reels(list(executions))
        valider_synthese(synthese, ids_reels)
        log.info("synthese validee", agent=agent, statut=synthese.statut, dry_run=dry_run)
        return synthese, executions
