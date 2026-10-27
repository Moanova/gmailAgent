import json
from typing import Any
from uuid import UUID

import pytest
from pydantic import ValidationError

from config import RegistreLibelles
from contracts import (
    AGENT_CLASSIFICATION,
    AGENT_SPAM,
    AGENT_SUPPRESSION,
    AgentInconnuError,
    MessageClasse,
    MessageLu,
    Meta,
    RapportFinal,
    SyntheseClassification,
    SyntheseSpam,
    SyntheseSuppression,
    response_format_agent,
    schema_agent,
)

AGENTS = (AGENT_CLASSIFICATION, AGENT_SPAM, AGENT_SUPPRESSION)


def _objets_du_schema(schema: dict[str, Any]) -> list[dict[str, Any]]:
    objets = [schema]
    objets.extend(schema.get("$defs", {}).values())
    return objets


def _tous_les_refs(schema: dict[str, Any]) -> list[str]:
    refs: list[str] = []

    def parcourir(node: Any) -> None:
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str):
                refs.append(ref)
            for valeur in node.values():
                parcourir(valeur)
        elif isinstance(node, list):
            for valeur in node:
                parcourir(valeur)

    parcourir(schema)
    return refs


class TestMeta:
    def test_timestamp_utc_par_defaut(self, meta: Meta) -> None:
        assert meta.timestamp.tzinfo is not None

    def test_round_trip_json(self, meta_fixe: Meta) -> None:
        dump = meta_fixe.model_dump(mode="json")
        assert dump["run_id"] == "12345678-1234-5678-1234-567812345678"
        assert isinstance(dump["timestamp"], str)
        restaure = Meta.model_validate(dump)
        assert restaure.run_id == UUID("12345678-1234-5678-1234-567812345678")
        assert restaure.timestamp == meta_fixe.timestamp

    def test_champ_interdit_rejete(self, meta_fixe: Meta) -> None:
        with pytest.raises(ValidationError):
            Meta.model_validate({**meta_fixe.model_dump(mode="json"), "inconnu": 1})


class TestMessageLu:
    def test_champs_requis(self, message_lu: MessageLu) -> None:
        assert message_lu.id == "18c1f2a3b4c5d6e7"
        assert message_lu.objet == "Sujet du message"

    @pytest.mark.parametrize("champ", ["id", "objet", "expediteur", "motif"])
    def test_chaine_vide_rejetee(self, message_lu: MessageLu, champ: str) -> None:
        with pytest.raises(ValidationError):
            MessageLu.model_validate({**message_lu.model_dump(), champ: ""})

    def test_champ_interdit_rejete(self, message_lu: MessageLu) -> None:
        with pytest.raises(ValidationError):
            MessageLu.model_validate({**message_lu.model_dump(), "extra": 1})


class TestMessageClasse:
    def test_cle_logique_acceptee(self, message_classe: MessageClasse) -> None:
        assert message_classe.categorie == "classification.a-repondre"

    @pytest.mark.parametrize(
        "categorie",
        [
            "Agent/a-repondre",  # libellé physique
            "a-repondre",  # sans groupe
            "Classification.A-Repondre",  # casse
            "classification.",  # groupe sans clé
        ],
    )
    def test_categorie_invalide_rejetee(
        self, message_classe: MessageClasse, categorie: str
    ) -> None:
        with pytest.raises(ValidationError):
            MessageClasse.model_validate({**message_classe.model_dump(), "categorie": categorie})

    @pytest.mark.parametrize("urgence", ["haute", "moyenne", "basse"])
    def test_urgence_valide(self, message_classe: MessageClasse, urgence: str) -> None:
        m = MessageClasse.model_validate({**message_classe.model_dump(), "urgence": urgence})
        assert m.urgence == urgence

    def test_urgence_invalide_rejetee(self, message_classe: MessageClasse) -> None:
        with pytest.raises(ValidationError):
            MessageClasse.model_validate(
                {**message_classe.model_dump(), "urgence": "critique"}
            )

    def test_empreinte_sha256_requise(self, message_classe: MessageClasse) -> None:
        for empreinte in ("xyz", "A" * 64, "a" * 63, "a" * 65, "g" * 64):
            with pytest.raises(ValidationError):
                MessageClasse.model_validate(
                    {**message_classe.model_dump(), "empreinte": empreinte}
                )

    def test_message_id_rfc_normalise_requis(self, message_classe: MessageClasse) -> None:
        for valeur in ("<abc@exemple.fr>", "abc sans arobase", "a b@c.fr"):
            with pytest.raises(ValidationError):
                MessageClasse.model_validate(
                    {**message_classe.model_dump(), "message_id_rfc": valeur}
                )


class TestSyntheses:
    def test_classification_construction_et_round_trip(
        self, message_classe: MessageClasse, meta: Meta
    ) -> None:
        s = SyntheseClassification(
            statut="synthese", messages=[message_classe], erreur=None, meta=meta
        )
        dump = s.model_dump(mode="json")
        restaure = SyntheseClassification.model_validate(dump)
        assert restaure.messages[0].categorie == "classification.a-repondre"
        assert restaure.erreur is None

    def test_spam_statut_synthese_rejete(self, message_lu: MessageLu, meta: Meta) -> None:
        with pytest.raises(ValidationError):
            SyntheseSpam(statut="synthese", messages=[message_lu], meta=meta)

    def test_suppression_statut_deplaces_rejete(self, meta: Meta) -> None:
        with pytest.raises(ValidationError):
            SyntheseSuppression(statut="deplaces", count=0, ids=[], meta=meta)

    def test_suppression_count_negatif_rejete(self, meta: Meta) -> None:
        with pytest.raises(ValidationError):
            SyntheseSuppression(statut="supprimes", count=-1, ids=[], meta=meta)

    def test_champ_interdit_rejete(self, meta: Meta) -> None:
        with pytest.raises(ValidationError):
            SyntheseSpam.model_validate(
                {
                    "statut": "aucun_message",
                    "messages": [],
                    "meta": meta.model_dump(mode="json"),
                    "inconnu": 1,
                }
            )


class TestRapportFinal:
    def test_construction_minimale(self, meta: Meta) -> None:
        r = RapportFinal(meta=meta, statut_global="succes")
        assert r.nb_doublons == 0
        assert r.synthese_spam is None

    def test_construction_complete(
        self,
        meta: Meta,
        message_classe: MessageClasse,
        message_lu: MessageLu,
    ) -> None:
        r = RapportFinal(
            meta=meta,
            synthese_spam=SyntheseSpam(
                statut="deplaces", messages=[message_lu], meta=meta
            ),
            synthese_classification=SyntheseClassification(
                statut="synthese", messages=[message_classe], meta=meta
            ),
            nb_doublons=2,
            statut_global="succes",
        )
        dump = r.model_dump(mode="json")
        restaure = RapportFinal.model_validate(dump)
        assert restaure.nb_doublons == 2
        assert restaure.synthese_classification is not None

    def test_statut_global_invalide_rejete(self, meta: Meta) -> None:
        with pytest.raises(ValidationError):
            RapportFinal(meta=meta, statut_global="partiel")


class TestSchemaAgent:
    @pytest.mark.parametrize("agent", AGENTS)
    def test_additional_properties_false_partout(
        self, agent: str, registre: RegistreLibelles
    ) -> None:
        schema = schema_agent(agent, registre)
        for objet in _objets_du_schema(schema):
            assert objet.get("type") == "object"
            assert objet.get("additionalProperties") is False

    @pytest.mark.parametrize("agent", AGENTS)
    def test_meta_exclu(self, agent: str, registre: RegistreLibelles) -> None:
        schema = schema_agent(agent, registre)
        assert "meta" not in schema["properties"]
        assert "meta" not in schema["required"]

    @pytest.mark.parametrize("agent", AGENTS)
    def test_tous_les_ref_resolus(self, agent: str, registre: RegistreLibelles) -> None:
        schema = schema_agent(agent, registre)
        defs = set(schema.get("$defs", {}).keys())
        for ref in _tous_les_refs(schema):
            assert ref.rsplit("/", 1)[-1] in defs

    @pytest.mark.parametrize("agent", AGENTS)
    def test_aucun_libelle_physique_en_dur(
        self, agent: str, registre: RegistreLibelles
    ) -> None:
        texte = json.dumps(schema_agent(agent, registre))
        for _cle, libelle in registre.iter_cles():
            assert libelle not in texte

    def test_enum_categorie_dynamique(self, registre: RegistreLibelles) -> None:
        schema = schema_agent(AGENT_CLASSIFICATION, registre)
        categorie = schema["$defs"]["MessageClasse"]["properties"]["categorie"]
        assert categorie["enum"] == [
            "classification.a-repondre",
            "classification.information",
            "classification.notification",
        ]

    def test_enum_urgence(self, registre: RegistreLibelles) -> None:
        schema = schema_agent(AGENT_CLASSIFICATION, registre)
        urgence = schema["$defs"]["MessageClasse"]["properties"]["urgence"]
        assert urgence["enum"] == ["haute", "moyenne", "basse"]

    @pytest.mark.parametrize(
        ("agent", "enum_attendu"),
        [
            (AGENT_CLASSIFICATION, ["synthese", "aucun_message", "echec_technique"]),
            (AGENT_SPAM, ["deplaces", "aucun_message", "echec_technique"]),
            (AGENT_SUPPRESSION, ["supprimes", "aucun_message", "echec_technique"]),
        ],
    )
    def test_enum_statut_par_agent(
        self, agent: str, enum_attendu: list[str], registre: RegistreLibelles
    ) -> None:
        schema = schema_agent(agent, registre)
        assert schema["properties"]["statut"]["enum"] == enum_attendu

    def test_spam_sans_categorie_ni_urgence(self, registre: RegistreLibelles) -> None:
        schema = schema_agent(AGENT_SPAM, registre)
        props = schema["$defs"]["MessageLu"]["properties"]
        assert "categorie" not in props
        assert "urgence" not in props

    def test_suppression_sans_defs(self, registre: RegistreLibelles) -> None:
        schema = schema_agent(AGENT_SUPPRESSION, registre)
        assert "$defs" not in schema

    def test_agent_inconnu_rejete(self, registre: RegistreLibelles) -> None:
        with pytest.raises(AgentInconnuError, match="agent inconnu"):
            schema_agent("inconnu", registre)

    def test_registre_par_defaut_charge_yaml(self) -> None:
        schema = schema_agent(AGENT_CLASSIFICATION)
        categorie = schema["$defs"]["MessageClasse"]["properties"]["categorie"]
        assert "classification.a-repondre" in categorie["enum"]


class TestResponseFormatAgent:
    @pytest.mark.parametrize(
        ("agent", "nom_attendu"),
        [
            (AGENT_CLASSIFICATION, "SyntheseClassification"),
            (AGENT_SPAM, "SyntheseSpam"),
            (AGENT_SUPPRESSION, "SyntheseSuppression"),
        ],
    )
    def test_forme_sdk(
        self, agent: str, nom_attendu: str, registre: RegistreLibelles
    ) -> None:
        rf = response_format_agent(agent, registre)
        assert rf["type"] == "json_schema"
        assert rf["json_schema"]["name"] == nom_attendu
        assert rf["json_schema"]["strict"] is True
        assert rf["json_schema"]["schema"] == schema_agent(agent, registre)
