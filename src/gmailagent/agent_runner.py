# -------------------------------------------------------------------
# Application  : gmailAgent
# Script       : agent_runner.py
# Version      : 1.1
# Date         : 13-11-2026
# Design       : TSC + Mistral Vibe
# Build        : Mistral Vibe
# -------------------------------------------------------------------

"""Runner de conversation éphémère (pattern synchrone, script de référence 02b).

Un appel = modèle + outils + schéma de sortie passés à chaque fois (décision D2 :
conversations éphémères, configuration versionnée avec le code). L'orchestrateur est
le seul médiateur : les agents ne s'appellent jamais entre eux (conception §2.4).

La boucle tool-calls est bornée (garde-fou anti-boucle) ; la synthèse finale est
parsée (`extraire_json`), construite (`construire_synthese`) puis validée
(`valider_synthese`, C1–C6, avec `collecter_ids_reels` sur les exécutions réelles).

Une erreur d'exécution d'outil (ex. `HttpError` 404 sur un identifiant invalide) est
renvoyée au modèle via le `ToolMessage` (`{"erreur": ...}`) avec un warning `outil en
echec` — jamais un abandon direct du run (D56) ; l'appel en échec n'est pas crédité dans
les exécutions réelles (C3). Une synthèse invalide (JSON illisible, contrat Pydantic,
C1–C6) est de même renvoyée au modèle pour correction, décomptée dans
`max_tentatives_synthese` — abandon propre au-delà (D57).

Court-circuit (T9.6) : si `search_threads` renvoie 0 thread, la synthèse
`aucun_message` est produite directement, sans appel au modèle (trivial sur liste
vide ; la validation C1–C6 reste appliquée à la synthèse vide).
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
from pydantic import ValidationError

from gmailagent.agent_contracts import (
    AGENT_CLASSIFICATION,
    AGENT_SPAM,
    AGENT_SUPPRESSION,
    AgentInconnuError,
    Meta,
    SyntheseEtape,
    SyntheseSuppression,
    response_format_agent,
)
from gmailagent.agent_prompts import (
    OUTILS_GMAIL,
    prompt_classification,
    prompt_spam,
    prompt_suppression,
)
from gmailagent.agent_validation import (
    ExtractionJsonError,
    SyntheseInvalideError,
    collecter_ids_reels,
    construire_synthese,
    extraire_json,
    valider_synthese,
)
from gmailagent.core_client import avec_retry
from gmailagent.core_config import RegistreLibelles, parametres_courants
from gmailagent.core_env import optionnel
from gmailagent.core_journalisation import obtenir_logger
from gmailagent.gmail_client import ClientGmailAPI

NOM_VAR_ENV_MODELE = "MISTRAL_MODEL"
LABEL_TRASH = "TRASH"

Message = SystemMessage | UserMessage | AssistantMessage | ToolMessage
AppelOutil = ToolExecutionEntry | FunctionCallEntry


def modele_effectif(modele: str | None) -> str:
    """Modèle effectif : argument explicite, puis variable d'environnement `MISTRAL_MODEL`, puis
    défaut de `config/settings.yaml`."""
    return modele or optionnel(NOM_VAR_ENV_MODELE, parametres_courants().modele.defaut)


def _normalise_requete(requete: str) -> str:
    """Normalise une requête Gmail pour comparaison : guillemets retirés, espaces normalisés.

    `label:"Agent/traité"` et `label:Agent/traité` sont équivalents côté Gmail (pas d'espace
    dans le nom) — la dérive de formatage du modèle ne doit pas déclencher de substitution.
    """
    return " ".join(requete.replace('"', "").split())


class GardeFouAtteintError(RuntimeError):
    """Garde-fou anti-boucle atteint (plafond d'appels d'outils dépassé) : abandon propre du run."""
    pass


def _arguments_outil(appel: AppelOutil) -> dict[str, Any]:
    """Arguments d'un appel d'outil en dict (chaîne JSON ou dict ; `{}` sinon)."""
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
    """Identifiant de l'appel d'outil (`tool_call_id`, ou `id`)."""
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
    from gmailagent.agent_dedup import _collecter_texte, empreinte_message

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
    """Aperçu borné d'un thread : id + liste des aperçus de ses messages."""
    messages = thread.get("messages", [])
    return {
        "id": thread.get("id"),
        "messages": [
            _apercu_message(m) for m in messages if isinstance(m, dict)
        ],
    }


def _borner_reponse(resultat: dict[str, Any]) -> str:
    """Sérialise un résultat d'outil en JSON, tronqué à la limite `limite_reponse_outil`."""
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
            int(args.get("maxResults", limites.max_resultats)), limites.cap_threads_recherche()
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


def _contenu_texte(contenu: Any) -> str:
    """Extrait le texte d'un contenu de message : `str` tel quel ; liste de chunks (réponse des
    modèles récents, ex. `mistral-large-latest`) -> concaténation des champs `text` des chunks de
    type `"text"` uniquement — le raisonnement (`ThinkChunk`, type `"thinking"`) est ignoré (T9.11).
    `None` ou tout autre forme -> chaîne vide (le refus de synthèse passera alors par
    `extraire_json` -> `_refuser`)."""
    if isinstance(contenu, str):
        return contenu
    if not isinstance(contenu, list):
        return ""
    textes: list[str] = []
    for chunk in contenu:
        if isinstance(chunk, dict):
            if chunk.get("type") != "text":
                continue
            texte = chunk.get("text")
        else:
            if getattr(chunk, "type", None) != "text":
                continue
            texte = getattr(chunk, "text", None)
        if isinstance(texte, str):
            textes.append(texte)
    return "".join(textes)


def _prompt_systeme(agent: str, registre: RegistreLibelles) -> str:
    """Retourne le prompt système de l'agent demandé ; lève `AgentInconnuError` sinon."""
    if agent == AGENT_CLASSIFICATION:
        return prompt_classification(registre)
    if agent == AGENT_SPAM:
        return prompt_spam(registre)
    if agent == AGENT_SUPPRESSION:
        return prompt_suppression(registre)
    raise AgentInconnuError(f"agent sans prompt : {agent!r}")


def _refuser(
    messages: list[Message],
    contenu_final: str,
    motif: str,
    *,
    evenement: str,
    abandon: str,
    tentatives: int,
    limite: int,
    cause: BaseException | None = None,
    **log_kwargs: Any,
) -> int:
    """Mécanisme unique de refus renvoyé au modèle (T9.8) : incrémente le compteur de
    tentatives de synthèse, lève `SyntheseInvalideError` au-delà de la limite
    (`max_tentatives_synthese`, `config/settings.yaml`), journalise l'événement, puis
    append `AssistantMessage` + `UserMessage(motif)`. Retourne le nouveau compteur.
    Le refus de niveau outil (erreur d'outil -> `ToolMessage {"erreur": ...}`, kanban T9.2)
    reste à part : il est décompté en appels d'outils, pas en tentatives de synthèse."""
    nouvelle = tentatives + 1
    if nouvelle > limite:
        erreur = SyntheseInvalideError(abandon)
        if cause is not None:
            raise erreur from cause
        raise erreur
    obtenir_logger("agents").warning(evenement, tentative=nouvelle, **log_kwargs)
    messages.append(AssistantMessage(role="assistant", content=contenu_final))
    messages.append(UserMessage(content=motif, role="user"))
    return nouvelle


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
    """Lance une conversation éphémère et retourne (synthèse validée, exécutions réussies)."""
    log = obtenir_logger("agents")
    limites = parametres_courants().limites
    param_modele = parametres_courants().modele
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
        temperature=param_modele.temperature,
        top_p=param_modele.top_p,
        dry_run=dry_run,
    )
    messages: list[Message] = [
        SystemMessage(content=_prompt_systeme(agent, registre), role="system"),
        UserMessage(
            content=(
                f"Requête de sélection : {requete}\n"
                f"Budget : au plus {plafond_appels} appels d'outils pour cette conversation "
                f"(la recherche est cappée à {limites.cap_threads_recherche()} threads). "
                "L'aperçu de `get_thread` suffit (en-têtes, extrait de corps, empreinte) ; "
                "n'appelle `get_message` que si un aperçu est insuffisant. En cas d'erreur "
                "d'un outil, corrige l'argument et réessaie sans boucler.\n"
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
                temperature=param_modele.temperature,
                top_p=param_modele.top_p,
                max_tokens=max_tokens,
            )
        )
        message = reponse.choices[0].message
        if message is None:
            raise SyntheseInvalideError("réponse Mistral sans message")
        appels_tool = message.tool_calls
        if appels_tool:
            contenu = _contenu_texte(message.content)
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
                args = _arguments_outil(appel)
                if appel.name == "search_threads":
                    tentee = str(args.get("query", ""))
                    if _normalise_requete(tentee) != _normalise_requete(requete):
                        log.warning(
                            "requete search_remplacee",
                            tentee=tentee,
                            executee=requete,
                            agent=agent,
                        )
                        args["query"] = requete
                try:
                    resultat = executer_outil(appel.name, args, client_gmail)
                except Exception as erreur_outil:
                    log.warning(
                        "outil en echec",
                        outil=appel.name,
                        args=_borner_reponse(args),
                        erreur=repr(erreur_outil),
                        dry_run=dry_run,
                    )
                    resultat = {"erreur": repr(erreur_outil)}
                else:
                    executions.append(appel)
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
                    if (
                        appel.name == "search_threads"
                        and isinstance(resultat, dict)
                        and not resultat.get("threads")
                    ):
                        log.info(
                            "court-circuit aucun_message : 0 thread retourné, "
                            "synthèse vide sans appel au modèle (T9.6)",
                            agent=agent,
                            requete=requete,
                            dry_run=dry_run,
                        )
                        payload_vide: dict[str, Any] = (
                            {"statut": "aucun_message", "count": 0, "ids": []}
                            if agent == AGENT_SUPPRESSION
                            else {"statut": "aucun_message", "messages": []}
                        )
                        synthese_vide = construire_synthese(agent, payload_vide, meta)
                        valider_synthese(synthese_vide, collecter_ids_reels(list(executions)))
                        return synthese_vide, executions
                messages.append(
                    ToolMessage(
                        role="tool",
                        tool_call_id=_tool_call_id(appel),
                        name=appel.name,
                        content=_borner_reponse(resultat),
                    )
                )
            continue
        contenu_final = _contenu_texte(message.content)
        manquants = sorted(threads_trouves - threads_lus)
        if manquants:
            tentatives_synthese = _refuser(
                messages,
                contenu_final,
                (
                    "Synthèse incomplète : tu n'as pas encore lu "
                    f"{len(manquants)} thread(s) retourné(s) par search_threads "
                    f"(ids : {', '.join(manquants[:10])}{'…' if len(manquants) > 10 else ''}). "
                    "Appelle get_thread sur chacun d'eux avant de produire la synthèse."
                ),
                evenement="synthese refusee : threads non lus",
                abandon=(
                    f"synthèse incomplète après {limites.max_tentatives_synthese} tentatives : "
                    f"{len(manquants)} thread(s) non lus — abandon du run"
                ),
                tentatives=tentatives_synthese,
                limite=limites.max_tentatives_synthese,
                manquants=manquants[:10],
                total=len(manquants),
            )
            continue
        try:
            payload = _normaliser_payload(extraire_json(contenu_final))
            synthese = construire_synthese(agent, payload, meta)
            ids_reels = collecter_ids_reels(list(executions)) | ids_resultats
            valider_synthese(synthese, ids_reels)
        except (ExtractionJsonError, SyntheseInvalideError, ValidationError) as erreur_synthese:
            tentatives_synthese = _refuser(
                messages,
                contenu_final,
                (
                    f"Synthèse invalide (tentative {tentatives_synthese + 1}/"
                    f"{limites.max_tentatives_synthese}) : {erreur_synthese}. "
                    "Corrige ta réponse pour qu'elle soit conforme au schéma imposé "
                    "(statut, messages, champs requis et formats — ex. `message_id_rfc` "
                    "normalisé sans chevrons `<>`, `empreinte` SHA-256 en 64 caractères "
                    "hexadécimaux)."
                ),
                evenement="synthese refusee : validation",
                abandon=(
                    f"synthèse invalide après {limites.max_tentatives_synthese} tentatives "
                    f"— abandon du run : {erreur_synthese}"
                ),
                tentatives=tentatives_synthese,
                limite=limites.max_tentatives_synthese,
                cause=erreur_synthese,
                agent=agent,
                erreur=repr(erreur_synthese),
            )
            continue
        if agent == AGENT_SUPPRESSION and isinstance(synthese, SyntheseSuppression):
            ecart = ids_corbeille.symmetric_difference(set(synthese.ids))
            if synthese.statut != "supprimes":
                ecart |= ids_corbeille
            if ecart:
                tentatives_synthese = _refuser(
                    messages,
                    contenu_final,
                    (
                        "Synthèse incohérente : "
                        f"{len(ecart)} id(s) en écart entre les messages réellement "
                        "passés à la corbeille (label_message avec TRASH) et le champ "
                        f"`ids` de ta synthèse (ids : {', '.join(sorted(ecart)[:10])}). "
                        "Corrige `ids` et `count` pour qu'ils correspondent exactement "
                        "aux messages mis à la corbeille."
                    ),
                    evenement="synthese refusee : ecart corbeille reelle / ids",
                    abandon=(
                        f"synthèse incohérente avec les mises à la corbeille réelles "
                        f"après {limites.max_tentatives_synthese} tentatives — écart : "
                        f"{sorted(ecart)[:10]} — abandon du run"
                    ),
                    tentatives=tentatives_synthese,
                    limite=limites.max_tentatives_synthese,
                    ecart=sorted(ecart)[:10],
                    total=len(ecart),
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
            tentatives_synthese = _refuser(
                messages,
                contenu_final,
                (
                    "Synthèse incomplète : "
                    f"{len(messages_manquants)} message(s) lu(s) via get_thread "
                    "ou get_message ne figurent pas dans ta synthèse (ids : "
                    f"{', '.join(messages_manquants[:10])}"
                    f"{'…' if len(messages_manquants) > 10 else ''}). "
                    "Classe CHACUN des messages lus avant de produire la synthèse."
                ),
                evenement="synthese refusee : messages lus non classes",
                abandon=(
                    f"synthèse incomplète après {limites.max_tentatives_synthese} tentatives : "
                    f"{len(messages_manquants)} message(s) lus non classés — abandon du run"
                ),
                tentatives=tentatives_synthese,
                limite=limites.max_tentatives_synthese,
                manquants=messages_manquants[:10],
                total=len(messages_manquants),
            )
            continue
        log.info("synthese validee", agent=agent, statut=synthese.statut, dry_run=dry_run)
        return synthese, executions
