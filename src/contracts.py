import copy
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from config import RegistreLibelles, charger_registre

Urgence = Literal["haute", "moyenne", "basse"]

StatutClassification = Literal["synthese", "aucun_message", "echec_technique"]
StatutSpam = Literal["deplaces", "aucun_message", "echec_technique"]
StatutSuppression = Literal["supprimes", "aucun_message", "echec_technique"]

_PATTERN_EMPREINTE = r"^[0-9a-f]{64}$"
_PATTERN_MESSAGE_ID_RFC = r"^[^<>\s]+@[^<>\s]+$"
_PATTERN_CLE_LOGIQUE = r"^[a-z0-9-]+\.[a-z0-9-]+$"


class Meta(BaseModel):
    """Enveloppe commune à toute synthèse d'étape."""

    model_config = ConfigDict(extra="forbid")

    run_id: UUID
    etape: str = Field(min_length=1)
    agent: str = Field(min_length=1)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class MessageLu(BaseModel):
    """Message lu par un agent, tel que rapporté dans une synthèse."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    objet: str = Field(min_length=1)
    expediteur: str = Field(min_length=1)
    motif: str = Field(min_length=1)


class MessageClasse(MessageLu):
    """Message classé, avec les clés de dédoublonnage (Message-ID RFC, empreinte SHA-256)."""

    categorie: str = Field(pattern=_PATTERN_CLE_LOGIQUE)
    urgence: Urgence
    message_id_rfc: str = Field(pattern=_PATTERN_MESSAGE_ID_RFC)
    empreinte: str = Field(pattern=_PATTERN_EMPREINTE)


class SyntheseClassification(BaseModel):
    """Synthèse de l'étape de classification."""

    model_config = ConfigDict(extra="forbid")

    statut: StatutClassification
    messages: list[MessageClasse]
    erreur: str | None = None
    meta: Meta


class SyntheseSpam(BaseModel):
    """Synthèse de l'étape de lecture du spam."""

    model_config = ConfigDict(extra="forbid")

    statut: StatutSpam
    messages: list[MessageLu]
    erreur: str | None = None
    meta: Meta


class SyntheseSuppression(BaseModel):
    """Synthèse du run de suppression."""

    model_config = ConfigDict(extra="forbid")

    statut: StatutSuppression
    count: int = Field(ge=0)
    ids: list[str]
    erreur: str | None = None
    meta: Meta


SyntheseEtape = SyntheseClassification | SyntheseSpam | SyntheseSuppression


class RapportFinal(BaseModel):
    """Rapport agrégé du run de tri, restitué à l'utilisateur."""

    model_config = ConfigDict(extra="forbid")

    meta: Meta
    synthese_spam: SyntheseSpam | None = None
    synthese_classification: SyntheseClassification | None = None
    nb_doublons: int = Field(default=0, ge=0)
    statut_global: Literal["succes", "echec_partiel"]
    etape_fautive: str | None = None


AGENT_CLASSIFICATION = "classification"
AGENT_SPAM = "spam"
AGENT_SUPPRESSION = "suppression"

_MODELES_PAR_AGENT: dict[str, type[BaseModel]] = {
    AGENT_CLASSIFICATION: SyntheseClassification,
    AGENT_SPAM: SyntheseSpam,
    AGENT_SUPPRESSION: SyntheseSuppression,
}

_ENUM_URGENCES: list[str] = ["haute", "moyenne", "basse"]

_ENUM_STATUTS: dict[str, list[str]] = {
    AGENT_CLASSIFICATION: ["synthese", "aucun_message", "echec_technique"],
    AGENT_SPAM: ["deplaces", "aucun_message", "echec_technique"],
    AGENT_SUPPRESSION: ["supprimes", "aucun_message", "echec_technique"],
}


class AgentInconnuError(ValueError):
    pass


def _schema_payload(
    cls: type[BaseModel], *, exclure: tuple[str, ...] = ("meta",)
) -> dict[str, Any]:
    schema = copy.deepcopy(cls.model_json_schema())
    for champ in exclure:
        schema.get("properties", {}).pop(champ, None)
        if champ in schema.get("required", []):
            schema["required"].remove(champ)
    defs: dict[str, Any] = schema.get("$defs", {})
    if not defs:
        return schema
    utilises: set[str] = set()

    def collecter_refs(node: Any) -> None:
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str):
                utilises.add(ref.rsplit("/", 1)[-1])
            for valeur in node.values():
                collecter_refs(valeur)
        elif isinstance(node, list):
            for valeur in node:
                collecter_refs(valeur)

    collecter_refs(schema)
    for nom in [n for n in defs if n not in utilises]:
        del defs[nom]
    if not defs:
        schema.pop("$defs", None)
    return schema


def _enum_categories(registre: RegistreLibelles) -> list[str]:
    return [
        cle
        for cle, _ in registre.iter_cles()
        if cle.startswith("classification.")
    ]


def _injecter_enums_agent(
    schema: dict[str, Any], agent: str, registre: RegistreLibelles
) -> None:
    properties: dict[str, Any] = schema["properties"]
    properties["statut"]["enum"] = _ENUM_STATUTS[agent]
    if agent != AGENT_CLASSIFICATION:
        return
    ref: str = properties["messages"]["items"]["$ref"]
    nom_def = ref.rsplit("/", 1)[-1]
    message_props: dict[str, Any] = schema["$defs"][nom_def]["properties"]
    message_props["categorie"]["enum"] = _enum_categories(registre)
    message_props["urgence"]["enum"] = _ENUM_URGENCES


def schema_agent(
    agent: str, registre: RegistreLibelles | None = None
) -> dict[str, Any]:
    """Schéma JSON strict du payload produit par un agent (champ `meta` exclu).

    Les enums `statut`, `categorie` et `urgence` sont construits dynamiquement :
    `categorie` depuis le registre de libellés (`config/labels.yaml`), jamais de
    libellé physique en dur.
    """
    try:
        cls = _MODELES_PAR_AGENT[agent]
    except KeyError:
        raise AgentInconnuError(
            f"agent inconnu : {agent!r} "
            f"(attendu : {', '.join(sorted(_MODELES_PAR_AGENT))})"
        ) from None
    if registre is None:
        registre = charger_registre()
    schema = _schema_payload(cls)
    _injecter_enums_agent(schema, agent, registre)
    return schema


def response_format_agent(
    agent: str, registre: RegistreLibelles | None = None
) -> dict[str, Any]:
    """Enveloppe `response_format` prête pour le SDK Mistral (mode `json_schema` strict).

    Forme : `{"type": "json_schema", "json_schema": {"name": ..., "schema": ..., "strict": true}}`.
    Passée à l'API via `completion_args.response_format` dans les conversations éphémères.
    """
    schema = schema_agent(agent, registre)
    nom = _MODELES_PAR_AGENT[agent].__name__
    return {
        "type": "json_schema",
        "json_schema": {
            "name": nom,
            "schema": schema,
            "strict": True,
        },
    }
