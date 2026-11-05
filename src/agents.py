"""Runner de conversation éphémère (pattern synchrone, script de référence 02b).

Un appel = modèle + outils + schéma de sortie passés à chaque fois (décision D2 :
conversations éphémères, configuration versionnée avec le code). L'orchestrateur est
le seul médiateur : les agents ne s'appellent jamais entre eux (conception §2.4).

La boucle tool-calls est bornée (garde-fou anti-boucle) ; la synthèse finale est
parsée (`extraire_json`), construite (`construire_synthese`) puis validée
(`valider_synthese`, C1–C6, avec `collecter_ids_reels` sur les exécutions réelles).
"""

import json
from typing import Any

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
from config import RegistreLibelles, parametres_courants
from contracts import (
    AGENT_CLASSIFICATION,
    AGENT_SPAM,
    AGENT_SUPPRESSION,
    AgentInconnuError,
    Meta,
    SyntheseEtape,
    SyntheseSuppression,
    response_format_agent,
)
from env import optionnel
from gmail import ClientGmailAPI
from journalisation import obtenir_logger
from prompts import OUTILS_GMAIL, prompt_classification, prompt_spam, prompt_suppression
from validation import (
    SyntheseInvalideError,
    collecter_ids_reels,
    construire_synthese,
    extraire_json,
    valider_synthese,
)

NOM_VAR_ENV_MODELE = "MISTRAL_MODEL"
LABEL_TRASH = "TRASH"

Message = SystemMessage | UserMessage | AssistantMessage | ToolMessage
AppelOutil = ToolExecutionEntry | FunctionCallEntry


def modele_effectif(modele: str | None) -> str:
    return modele or optionnel(NOM_VAR_ENV_MODELE, parametres_courants().modele.defaut)


def _normalise_requete(requete: str) -> str:
    """Normalise une requête Gmail pour comparaison : guillemets retirés, espaces normalisés.

    `label:"Agent/traité"` et `label:Agent/traité` sont équivalents côté Gmail (pas d'espace
    dans le nom) — la dérive de formatage du modèle ne doit pas déclencher la garde.
    """
    return " ".join(requete.replace('"', "").split())


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


def _vers_tool_call(appel: FunctionCallEntry) -> ToolCall:
    """Convertit un appel normalisé en ToolCall (forme requête) pour l'écho assistant."""
    return ToolCall.model_validate(
        {
            "type": "function",
            "id": appel.tool_call_id,
            "function": {
                "name": appel.name,
                "arguments": json.dumps(_arguments_outil(appel), ensure_ascii=False),
            },
        }
    )


def _normaliser_tool_call(brut: Any) -> FunctionCallEntry:
    """Normalise un appel d'outil reçu de l'API en FunctionCallEntry.

    L'API renvoie des ToolCall (forme requête : id + function.name/arguments,
    type="function") ; on les convertit en FunctionCallEntry (type="function.call")
    pour que `collecter_ids_reels` les reconnaisse (C3) et que le dispatch
    fonctionne uniformément.
    """
    if isinstance(brut, FunctionCallEntry):
        return brut
    if isinstance(brut, ToolExecutionEntry):
        return FunctionCallEntry(
            tool_call_id=brut.id or "",
            name=brut.name,
            arguments=brut.arguments if isinstance(brut.arguments, (str, dict)) else "{}",
        )
    if isinstance(brut, ToolCall):
        return FunctionCallEntry(
            tool_call_id=brut.id or "",
            name=brut.function.name,
            arguments=brut.function.arguments
            if isinstance(brut.function.arguments, (str, dict))
            else "{}",
        )
    raise ValueError(f"appel d'outil inattendu : {type(brut).__name__}")


_ENTETES_APERCU = ("message-id", "subject", "from", "to", "date")


def _apercu_message(message: dict[str, Any]) -> dict[str, Any]:
    """Aperçu borné d'un message pour le LLM : en-têtes clés + extrait de corps.

    Le corps complet n'est PAS renvoyé au modèle (risque de dépassement du contexte,
    erreur 400 prompt_too_long) ; l'orchestrateur relit le message complet via
    `get_message` pour le recalcul des empreintes (C6).
    """
    payload = message.get("payload")
    if not isinstance(payload, dict):
        return {"id": message.get("id"), "erreur": "payload absent"}
    headers = payload.get("headers", [])
    entetes = {
        str(h.get("name", "")): str(h.get("value", ""))
        for h in headers
        if isinstance(h, dict) and str(h.get("name", "")).lower() in _ENTETES_APERCU
    }
    from dedup import _collecter_texte, empreinte_message

    corps = _collecter_texte(payload)
    empreinte = empreinte_message(message)[1]
    limite_corps = parametres_courants().limites.limite_corps_apercu
    if len(corps) > limite_corps:
        corps = corps[:limite_corps] + "…[tronqué]"
    return {
        "id": message.get("id"),
        "threadId": message.get("threadId"),
        "entetes": entetes,
        "corps": corps,
        "message_id_rfc": empreinte_message(message)[0],
        "empreinte": empreinte,
    }


def _apercu_thread(thread: dict[str, Any]) -> dict[str, Any]:
    messages = thread.get("messages", [])
    return {
        "id": thread.get("id"),
        "messages": [
            _apercu_message(m) for m in messages if isinstance(m, dict)
        ],
    }


def _borner_reponse(resultat: dict[str, Any]) -> str:
    texte = json.dumps(resultat, ensure_ascii=False)
    limite = parametres_courants().limites.limite_reponse_outil
    if len(texte) > limite:
        texte = texte[:limite] + '…["tronqué"]'
    return texte


def executer_outil(nom: str, args: dict[str, Any], client: ClientGmailAPI) -> dict[str, Any]:
    """Exécute un outil Gmail contre le client (écritures neutralisées en dry-run).

    `get_thread`/`get_message` renvoient un aperçu borné (jamais le JSON brut complet)
    pour ne pas dépasser le contexte du modèle.
    """
    if nom == "search_threads":
        limites = parametres_courants().limites
        max_results = min(
            int(args.get("maxResults", limites.max_resultats)), limites.max_threads_par_run
        )
        ids = client.search_threads(str(args["query"]), max_results=max_results)
        return {"threads": ids}
    if nom == "get_thread":
        return _apercu_thread(client.get_thread(str(args["threadId"])))
    if nom == "get_message":
        return _apercu_message(client.get_message(str(args["messageId"])))
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


def _normaliser_payload(payload: Any) -> dict[str, Any]:
    """Normalise le JSON extrait en enveloppe de synthèse {statut, messages, ...}.

    Tolérance : si le modèle renvoie un objet message nu (champs `id`/`objet`) ou une
    liste de messages au lieu de l'enveloppe, on l'enveloppe (`statut="synthese"`).
    """
    if isinstance(payload, list):
        return {"statut": "synthese", "messages": payload}
    if isinstance(payload, dict):
        if "statut" in payload or "messages" in payload:
            return payload
        if "id" in payload and "objet" in payload:
            return {"statut": "synthese", "messages": [payload]}
    raise SyntheseInvalideError(
        f"payload JSON inattendu (ni enveloppe synthèse ni message) : {str(payload)[:200]}"
    )


def _prompt_systeme(agent: str, registre: RegistreLibelles) -> str:
    if agent == AGENT_CLASSIFICATION:
        return prompt_classification(registre)
    if agent == AGENT_SPAM:
        return prompt_spam(registre)
    if agent == AGENT_SUPPRESSION:
        return prompt_suppression(registre)
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
    plafond_appels: int | None = None,
    modele: str | None = None,
    max_tokens: int | None = None,
) -> tuple[SyntheseEtape, list[AppelOutil]]:
    """Lance une conversation éphémère et retourne (synthèse validée, exécutions outils)."""
    log = obtenir_logger("agents")
    limites = parametres_courants().limites
    modele = modele_effectif(modele)
    if max_tokens is None:
        max_tokens = limites.max_tokens
    if plafond_appels is None:
        plafond_appels = limites.plafond_appels_outils
    log.info(
        "conversation lancee",
        agent=agent,
        modele=modele,
        max_tokens=max_tokens,
        dry_run=dry_run,
    )
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
    tentatives_synthese = 0
    threads_trouves: set[str] = set()
    threads_lus: set[str] = set()
    messages_lus: set[str] = set()
    ids_resultats: set[str] = set()
    ids_corbeille: set[str] = set()
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
                    tool_calls=[
                        _vers_tool_call(_normaliser_tool_call(brut)) for brut in appels_tool
                    ],
                )
            )
            for brut in appels_tool:
                appel = _normaliser_tool_call(brut)
                appels += 1
                if appels > plafond_appels:
                    raise GardeFouAtteintError(
                        f"garde-fou anti-boucle : {appels} appels d'outils "
                        f"(plafond {plafond_appels}) — abandon du run"
                    )
                executions.append(appel)
                args = _arguments_outil(appel)
                if appel.name == "search_threads" and _normalise_requete(
                    str(args.get("query", ""))
                ) != _normalise_requete(requete):
                    recu = str(args.get("query", ""))
                    raise SyntheseInvalideError(
                        f"requête de recherche modifiée par l'agent (attendu {requete!r}, "
                        f"reçu {recu!r}) — abandon du run"
                    )
                resultat = executer_outil(appel.name, args, client_gmail)
                if appel.name == "search_threads" and isinstance(resultat, dict):
                    threads_trouves.update(
                        t for t in resultat.get("threads", []) if isinstance(t, str)
                    )
                if appel.name == "get_thread":
                    threads_lus.add(str(args.get("threadId", "")))
                    if isinstance(resultat, dict):
                        ids_resultats.add(str(args.get("threadId", "")))
                        for m in resultat.get("messages", []):
                            if isinstance(m, dict) and isinstance(m.get("id"), str):
                                messages_lus.add(m["id"])
                                ids_resultats.add(m["id"])
                if appel.name == "get_message":
                    messages_lus.add(str(args.get("messageId", "")))
                if appel.name == "label_message" and LABEL_TRASH in [
                    str(x) for x in args.get("addLabelIds", [])
                ]:
                    ids_corbeille.add(str(args.get("messageId", "")))
                if appel.name == "search_threads" and isinstance(resultat, dict):
                    ids_resultats.update(
                        t for t in resultat.get("threads", []) if isinstance(t, str)
                    )
                log.info(
                    "outil execute",
                    outil=appel.name,
                    args=_borner_reponse(args),
                    dry_run=dry_run,
                )
                messages.append(
                    ToolMessage(
                        role="tool",
                        tool_call_id=_tool_call_id(appel),
                        name=appel.name,
                        content=_borner_reponse(resultat),
                    )
                )
            continue
        contenu_final = message.content
        if not isinstance(contenu_final, str):
            raise SyntheseInvalideError("contenu final de l'agent non textuel")
        manquants = sorted(threads_trouves - threads_lus)
        if manquants:
            tentatives_synthese += 1
            if tentatives_synthese > limites.max_tentatives_synthese:
                raise SyntheseInvalideError(
                    f"synthèse incomplète après {limites.max_tentatives_synthese} tentatives : "
                    f"{len(manquants)} thread(s) non lus — abandon du run"
                )
            log.warning(
                "synthese refusee : threads non lus",
                manquants=manquants[:10],
                total=len(manquants),
                tentative=tentatives_synthese,
            )
            messages.append(AssistantMessage(role="assistant", content=contenu_final))
            messages.append(
                UserMessage(
                    content=(
                        "Synthèse incomplète : tu n'as pas encore lu "
                        f"{len(manquants)} thread(s) retourné(s) par search_threads "
                        f"(ids : {', '.join(manquants[:10])}{'…' if len(manquants) > 10 else ''}). "
                        "Appelle get_thread sur chacun d'eux avant de produire la synthèse."
                    ),
                    role="user",
                )
            )
            continue
        payload = _normaliser_payload(extraire_json(contenu_final))
        synthese = construire_synthese(agent, payload, meta)
        ids_reels = collecter_ids_reels(list(executions)) | ids_resultats
        valider_synthese(synthese, ids_reels)
        if agent == AGENT_SUPPRESSION and isinstance(synthese, SyntheseSuppression):
            ecart = ids_corbeille.symmetric_difference(set(synthese.ids))
            if synthese.statut != "supprimes":
                ecart |= ids_corbeille
            if ecart:
                tentatives_synthese += 1
                if tentatives_synthese > limites.max_tentatives_synthese:
                    raise SyntheseInvalideError(
                        f"synthèse incohérente avec les mises à la corbeille réelles "
                        f"après {limites.max_tentatives_synthese} tentatives — écart : "
                        f"{sorted(ecart)[:10]} — abandon du run"
                    )
                log.warning(
                    "synthese refusee : ecart corbeille reelle / ids",
                    ecart=sorted(ecart)[:10],
                    total=len(ecart),
                    tentative=tentatives_synthese,
                )
                messages.append(AssistantMessage(role="assistant", content=contenu_final))
                messages.append(
                    UserMessage(
                        content=(
                            "Synthèse incohérente : "
                            f"{len(ecart)} id(s) en écart entre les messages réellement "
                            "passés à la corbeille (label_message avec TRASH) et le champ "
                            f"`ids` de ta synthèse (ids : {', '.join(sorted(ecart)[:10])}). "
                            "Corrige `ids` et `count` pour qu'ils correspondent exactement "
                            "aux messages mis à la corbeille."
                        ),
                        role="user",
                    )
                )
                continue
        ids_synthese = {
            m.id for m in getattr(synthese, "messages", []) if hasattr(m, "id")
        }
        messages_manquants = sorted(messages_lus - ids_synthese)
        if (
            agent == AGENT_CLASSIFICATION
            and messages_manquants
            and synthese.statut not in ("aucun_message", "echec_technique")
        ):
            tentatives_synthese += 1
            if tentatives_synthese > limites.max_tentatives_synthese:
                raise SyntheseInvalideError(
                    f"synthèse incomplète après {limites.max_tentatives_synthese} tentatives : "
                    f"{len(messages_manquants)} message(s) lus non classés — abandon du run"
                )
            log.warning(
                "synthese refusee : messages lus non classes",
                manquants=messages_manquants[:10],
                total=len(messages_manquants),
                tentative=tentatives_synthese,
            )
            messages.append(AssistantMessage(role="assistant", content=contenu_final))
            messages.append(
                UserMessage(
                    content=(
                        "Synthèse incomplète : "
                        f"{len(messages_manquants)} message(s) lu(s) via get_thread "
                        "ou get_message ne figurent pas dans ta synthèse (ids : "
                        f"{', '.join(messages_manquants[:10])}"
                        f"{'…' if len(messages_manquants) > 10 else ''}). "
                        "Classe CHACUN des messages lus avant de produire la synthèse."
                    ),
                    role="user",
                )
            )
            continue
        log.info("synthese validee", agent=agent, statut=synthese.statut, dry_run=dry_run)
        return synthese, executions
