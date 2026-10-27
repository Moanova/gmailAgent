import json
from typing import Any

from contracts import (
    AGENT_CLASSIFICATION,
    MessageClasse,
    Meta,
    SyntheseClassification,
    SyntheseEtape,
    SyntheseSpam,
    SyntheseSuppression,
)

_STATUTS_ECHEC = {"echec_technique"}
_STATUTS_VIDES = {"aucun_message"}
_STATUTS_AVEC_MESSAGES = {"synthese", "deplaces", "supprimes"}

_CHAMPS_IDS: tuple[str, ...] = (
    "threadId",
    "thread_id",
    "messageId",
    "message_id",
    "id",
)


class ExtractionJsonError(ValueError):
    pass


class SyntheseInvalideError(ValueError):
    pass


def extraire_json(texte: str) -> dict[str, Any]:
    """Extrait le premier objet JSON bien formé d'un texte.

    Parcourt les accolades ouvrantes, tente ``json.loads`` sur chaque candidat
    (accolades équilibrées, chaînes avec échappements gérées), retourne le
    premier objet valide. Lève ``ExtractionJsonError`` sinon.
    """
    depart = 0
    while True:
        ouvrante = texte.find("{", depart)
        if ouvrante == -1:
            raise ExtractionJsonError("aucun objet JSON trouvé dans le texte")
        profondeur = 0
        dans_chaine = False
        echappe = False
        for i in range(ouvrante, len(texte)):
            caractere = texte[i]
            if echappe:
                echappe = False
                continue
            if caractere == "\\":
                echappe = True
                continue
            if caractere == '"':
                dans_chaine = not dans_chaine
                continue
            if dans_chaine:
                continue
            if caractere == "{":
                profondeur += 1
            elif caractere == "}":
                profondeur -= 1
                if profondeur == 0:
                    candidat = texte[ouvrante : i + 1]
                    try:
                        resultat: Any = json.loads(candidat)
                    except json.JSONDecodeError:
                        break
                    if isinstance(resultat, dict):
                        return resultat
                    break
        depart = ouvrante + 1


def _arguments_dict(entry: Any) -> dict[str, Any]:
    brut: Any = entry.arguments
    if isinstance(brut, str):
        try:
            parse: Any = json.loads(brut)
        except json.JSONDecodeError:
            return {}
        return parse if isinstance(parse, dict) else {}
    if isinstance(brut, dict):
        return brut
    return {}


def collecter_ids_reels(outputs: list[Any]) -> set[str]:
    """Identifiants réellement manipulés par les outils durant la conversation.

    Parcourt les entrées ``tool.execution`` (et ``function.call`` en secours),
    parse les arguments (str JSON ou dict), collecte les valeurs des champs
    d'identifiants connus (``threadId``, ``messageId``, ``id``, variantes
    snake_case). Retourne un ensemble dédupliqué.
    """
    ids: set[str] = set()
    for entree in outputs:
        type_entree: str = getattr(entree, "type", "")
        if type_entree not in ("tool.execution", "function.call"):
            continue
        args = _arguments_dict(entree)
        for champ in _CHAMPS_IDS:
            valeur = args.get(champ)
            if isinstance(valeur, str):
                ids.add(valeur)
            elif isinstance(valeur, list):
                ids.update(v for v in valeur if isinstance(v, str))
    return ids


def _messages_ids(synthese: SyntheseEtape) -> list[str]:
    if isinstance(synthese, SyntheseSuppression):
        return list(synthese.ids)
    return [message.id for message in synthese.messages]


def _valider_non_contradiction(synthese: SyntheseEtape) -> None:
    statut = synthese.statut
    nb_messages = (
        synthese.count if isinstance(synthese, SyntheseSuppression) else len(synthese.messages)
    )
    if statut in _STATUTS_ECHEC:
        if nb_messages > 0:
            raise SyntheseInvalideError(
                f"statut {statut!r} avec {nb_messages} message(s) — contradiction"
            )
        if not synthese.erreur:
            raise SyntheseInvalideError(
                f"statut {statut!r} sans champ erreur renseigné"
            )
    elif statut in _STATUTS_VIDES:
        if nb_messages > 0:
            raise SyntheseInvalideError(
                f"statut {statut!r} avec {nb_messages} message(s) — contradiction"
            )
        if synthese.erreur:
            raise SyntheseInvalideError(
                f"statut {statut!r} avec champ erreur renseigné — contradiction"
            )
    elif statut in _STATUTS_AVEC_MESSAGES:
        if synthese.erreur:
            raise SyntheseInvalideError(
                f"statut {statut!r} avec champ erreur renseigné — contradiction"
            )


def _valider_completude(synthese: SyntheseEtape) -> None:
    if synthese.statut in _STATUTS_AVEC_MESSAGES:
        if isinstance(synthese, SyntheseSuppression):
            if synthese.count == 0 or not synthese.ids:
                raise SyntheseInvalideError(
                    f"statut {synthese.statut!r} sans id de message — incomplet"
                )
            if synthese.count != len(synthese.ids):
                raise SyntheseInvalideError(
                    f"count={synthese.count} != len(ids)={len(synthese.ids)} — incohérent"
                )
        elif not synthese.messages:
            raise SyntheseInvalideError(
                f"statut {synthese.statut!r} sans message — incomplet"
            )


def _valider_authenticite(synthese: SyntheseEtape, ids_reels: set[str]) -> None:
    ids_synthese = _messages_ids(synthese)
    inconnus = [i for i in ids_synthese if i not in ids_reels]
    if inconnus:
        raise SyntheseInvalideError(
            f"{len(inconnus)} id(s) non manipulés par les outils : "
            f"{inconnus[:5]}{'…' if len(inconnus) > 5 else ''}"
        )


def _valider_empreintes(synthese: SyntheseEtape) -> None:
    if not isinstance(synthese, SyntheseClassification):
        return
    for message in synthese.messages:
        assert isinstance(message, MessageClasse)
        if not message.message_id_rfc or not message.empreinte:
            raise SyntheseInvalideError(
                f"message {message.id} sans clé de dédoublonnage — incomplet"
            )


def valider_synthese(synthese: SyntheseEtape, ids_reels: set[str]) -> None:
    """Valide une synthèse d'étape : non-contradiction, complétude, authenticité.

    Lève ``SyntheseInvalideError`` avec un motif explicite en cas d'échec.
    Appelée par l'orchestrateur à chaque étape ; un rejet interrompt le run.
    """
    _valider_non_contradiction(synthese)
    _valider_completude(synthese)
    _valider_authenticite(synthese, ids_reels)
    _valider_empreintes(synthese)


def construire_synthese(
    agent: str,
    payload: dict[str, Any],
    meta: Meta,
) -> SyntheseEtape:
    """Construit le modèle Pydantic complet d'une synthèse d'étape.

    Le payload (produit par le LLM, conforme au schéma de T2.2) est validé
    contre le modèle de l'agent, avec injection de ``meta``.
    """
    modeles: dict[str, type[SyntheseEtape]] = {
        AGENT_CLASSIFICATION: SyntheseClassification,
        "spam": SyntheseSpam,
        "suppression": SyntheseSuppression,
    }
    try:
        cls = modeles[agent]
    except KeyError:
        raise SyntheseInvalideError(f"agent inconnu : {agent!r}") from None
    return cls.model_validate({**payload, "meta": meta.model_dump(mode="json")})
