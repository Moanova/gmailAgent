import json
from typing import Any

import pytest
from mistralai.client.models import (
    FunctionCallEntry,
    MessageOutputEntry,
    ToolExecutionEntry,
)
from pydantic import ValidationError

from contracts import (
    AGENT_CLASSIFICATION,
    MessageClasse,
    MessageLu,
    Meta,
    SyntheseClassification,
    SyntheseSpam,
    SyntheseSuppression,
)
from validation import (
    ExtractionJsonError,
    SyntheseInvalideError,
    collecter_ids_reels,
    construire_synthese,
    extraire_json,
    valider_synthese,
)


def _tool(name: str, arguments: str) -> ToolExecutionEntry:
    return ToolExecutionEntry(name=name, arguments=arguments)


def _function_call(name: str, arguments: dict[str, Any]) -> FunctionCallEntry:
    return FunctionCallEntry(tool_call_id=f"tc-{name}", name=name, arguments=arguments)


class TestExtraireJson:
    def test_json_noye_dans_texte(self) -> None:
        texte = 'Voici le résultat : {"statut": "synthese", "messages": []} — fin.'
        assert extraire_json(texte) == {"statut": "synthese", "messages": []}

    def test_accolades_imbriquees_et_echappements(self) -> None:
        texte = 'texte {"a": {"b": [1, 2, {"c": "}"}], "d": "échappé \\" ici"}, "e": 1} suite'
        resultat = extraire_json(texte)
        assert resultat["a"]["b"][2]["c"] == "}"
        assert resultat["a"]["d"] == 'échappé " ici'
        assert resultat["e"] == 1

    def test_premier_candidat_malforme_saute(self) -> None:
        assert extraire_json('intro {"invalide": } milieu {"ok": true}') == {"ok": True}

    def test_texte_sans_json_rejete(self) -> None:
        with pytest.raises(ExtractionJsonError, match="aucun objet JSON"):
            extraire_json("pas de JSON ici")

    def test_json_malforme_rejete(self) -> None:
        with pytest.raises(ExtractionJsonError):
            extraire_json('{"a": } {"b": }')

    def test_tableau_racine_rejete(self) -> None:
        with pytest.raises(ExtractionJsonError):
            extraire_json("[1, 2, 3]")


class TestCollecterIdsReels:
    def test_extraction_tool_execution_str_json(self) -> None:
        outputs = [
            _tool("search_threads", '{"query": "is:unread", "maxResults": 50}'),
            _tool("get_thread", '{"threadId": "thread-1"}'),
            _tool("label_message", '{"messageId": "msg-1", "labelIds": ["Label_1"]}'),
        ]
        assert collecter_ids_reels(outputs) == {"thread-1", "msg-1"}

    def test_extraction_function_call_dict(self) -> None:
        outputs = [_function_call("label_message", {"message_id": "msg-2"})]
        assert collecter_ids_reels(outputs) == {"msg-2"}

    @pytest.mark.parametrize(
        ("champ", "valeur", "attendu"),
        [
            ("threadId", "t1", {"t1"}),
            ("thread_id", "t2", {"t2"}),
            ("messageId", "m1", {"m1"}),
            ("message_id", "m2", {"m2"}),
            ("id", "x1", {"x1"}),
            ("id", ["t1", "t2"], {"t1", "t2"}),
        ],
    )
    def test_champs_ids_reconnus(
        self, champ: str, valeur: Any, attendu: set[str]
    ) -> None:
        outputs = [_tool("get_thread", json.dumps({champ: valeur}))]
        assert collecter_ids_reels(outputs) == attendu

    def test_entree_non_outil_ignoree(self) -> None:
        outputs: list[Any] = [
            MessageOutputEntry(content='{"id": "factice"}', role="assistant"),
        ]
        assert collecter_ids_reels(outputs) == set()

    def test_arguments_malformes_ignores(self) -> None:
        outputs = [_tool("get_thread", '{"threadId": ')]
        assert collecter_ids_reels(outputs) == set()

    def test_deduplication(self) -> None:
        outputs = [
            _tool("get_thread", '{"threadId": "t1"}'),
            _tool("get_thread", '{"threadId": "t1"}'),
            _tool("label_message", '{"messageId": "t1"}'),
        ]
        assert collecter_ids_reels(outputs) == {"t1"}

    def test_liste_vide(self) -> None:
        assert collecter_ids_reels([]) == set()


class TestValiderSyntheseCasValides:
    def test_classification(
        self, message_classe: MessageClasse, meta: Meta
    ) -> None:
        s = SyntheseClassification(
            statut="synthese", messages=[message_classe], meta=meta
        )
        valider_synthese(s, {message_classe.id})

    def test_spam(self, message_lu: MessageLu, meta: Meta) -> None:
        s = SyntheseSpam(statut="deplaces", messages=[message_lu], meta=meta)
        valider_synthese(s, {message_lu.id})

    def test_suppression(self, meta: Meta) -> None:
        s = SyntheseSuppression(
            statut="supprimes", count=2, ids=["m1", "m2"], meta=meta
        )
        valider_synthese(s, {"m1", "m2"})

    def test_aucun_message(self, meta: Meta) -> None:
        s = SyntheseSpam(statut="aucun_message", messages=[], meta=meta)
        valider_synthese(s, set())

    def test_echec_technique(self, meta: Meta) -> None:
        s = SyntheseClassification(
            statut="echec_technique",
            messages=[],
            erreur="quota API dépassé",
            meta=meta,
        )
        valider_synthese(s, set())


class TestValiderSyntheseRejets:
    def test_c1a_echec_avec_messages(
        self, message_classe: MessageClasse, meta: Meta
    ) -> None:
        s = SyntheseClassification(
            statut="echec_technique",
            messages=[message_classe],
            erreur="x",
            meta=meta,
        )
        with pytest.raises(SyntheseInvalideError, match="contradiction"):
            valider_synthese(s, {message_classe.id})

    def test_c1b_echec_sans_erreur(self, meta: Meta) -> None:
        s = SyntheseClassification(
            statut="echec_technique", messages=[], erreur=None, meta=meta
        )
        with pytest.raises(SyntheseInvalideError, match="sans champ erreur"):
            valider_synthese(s, set())

    def test_c1c_synthese_avec_erreur(
        self, message_classe: MessageClasse, meta: Meta
    ) -> None:
        s = SyntheseClassification(
            statut="synthese",
            messages=[message_classe],
            erreur="x",
            meta=meta,
        )
        with pytest.raises(SyntheseInvalideError, match="contradiction"):
            valider_synthese(s, {message_classe.id})

    def test_c2a_aucun_message_avec_messages(self, message_lu: MessageLu, meta: Meta) -> None:
        s = SyntheseSpam(statut="aucun_message", messages=[message_lu], meta=meta)
        with pytest.raises(SyntheseInvalideError, match="contradiction"):
            valider_synthese(s, {message_lu.id})

    def test_c2b_aucun_message_avec_erreur(self, meta: Meta) -> None:
        s = SyntheseSpam(statut="aucun_message", messages=[], erreur="x", meta=meta)
        with pytest.raises(SyntheseInvalideError, match="contradiction"):
            valider_synthese(s, set())

    def test_c3a_synthese_sans_messages(self, meta: Meta) -> None:
        s = SyntheseClassification(statut="synthese", messages=[], meta=meta)
        with pytest.raises(SyntheseInvalideError, match="incomplet"):
            valider_synthese(s, set())

    def test_c3b_supprimes_vide(self, meta: Meta) -> None:
        s = SyntheseSuppression(statut="supprimes", count=0, ids=[], meta=meta)
        with pytest.raises(SyntheseInvalideError, match="incomplet"):
            valider_synthese(s, set())

    def test_c4_id_inconnu_classification(
        self, message_classe: MessageClasse, meta: Meta
    ) -> None:
        s = SyntheseClassification(
            statut="synthese", messages=[message_classe], meta=meta
        )
        with pytest.raises(SyntheseInvalideError, match="non manipulés"):
            valider_synthese(s, {"autre-id"})

    def test_c4_id_inconnu_suppression(self, meta: Meta) -> None:
        s = SyntheseSuppression(
            statut="supprimes", count=2, ids=["m1", "m2"], meta=meta
        )
        with pytest.raises(SyntheseInvalideError, match="non manipulés"):
            valider_synthese(s, {"m1", "inconnu"})

    def test_c5_count_different_de_len_ids(self, meta: Meta) -> None:
        s = SyntheseSuppression(
            statut="supprimes", count=3, ids=["m1"], meta=meta
        )
        with pytest.raises(SyntheseInvalideError, match="incohérent"):
            valider_synthese(s, {"m1"})

    def test_c6_empreinte_absente(self, meta: Meta) -> None:
        message_sans_empreinte = MessageClasse.model_construct(
            id="msg-1",
            objet="Sujet",
            expediteur="a@b.fr",
            motif="test",
            categorie="classification.a-repondre",
            urgence="haute",
            message_id_rfc="",
            empreinte="",
        )
        s = SyntheseClassification(
            statut="synthese", messages=[message_sans_empreinte], meta=meta
        )
        with pytest.raises(SyntheseInvalideError, match="dédoublonnage"):
            valider_synthese(s, {"msg-1"})


class TestConstruireSynthese:
    def test_classification_avec_meta_injecte(
        self, message_classe: MessageClasse, meta: Meta
    ) -> None:
        payload = {
            "statut": "synthese",
            "messages": [message_classe.model_dump(mode="json")],
            "erreur": None,
        }
        s = construire_synthese(AGENT_CLASSIFICATION, payload, meta)
        assert isinstance(s, SyntheseClassification)
        assert s.meta.run_id == meta.run_id
        valider_synthese(s, {message_classe.id})

    def test_agent_inconnu_rejete(self, meta: Meta) -> None:
        with pytest.raises(SyntheseInvalideError, match="agent inconnu"):
            construire_synthese(
                "inconnu",
                {"statut": "aucun_message", "messages": [], "erreur": None},
                meta,
            )

    def test_champ_interdit_rejete_par_pydantic(self, meta: Meta) -> None:
        with pytest.raises(ValidationError):
            construire_synthese(
                AGENT_CLASSIFICATION,
                {
                    "statut": "synthese",
                    "messages": [],
                    "erreur": None,
                    "champ_interdit": 1,
                },
                meta,
            )

    def test_payload_non_conforme_rejete(self, meta: Meta) -> None:
        with pytest.raises(ValidationError):
            construire_synthese(
                AGENT_CLASSIFICATION,
                {"statut": "statut_invalide", "messages": [], "erreur": None},
                meta,
            )


class TestIntegrationContratsValidation:
    def test_payload_conforme_au_schema_valide_et_valide(
        self, message_classe: MessageClasse, meta: Meta
    ) -> None:
        payload = {
            "statut": "synthese",
            "messages": [message_classe.model_dump(mode="json")],
            "erreur": None,
        }
        ids = collecter_ids_reels(
            [_tool("get_thread", json.dumps({"threadId": "t1"})),
             _tool("label_message", json.dumps({"messageId": message_classe.id}))]
        )
        s = construire_synthese(AGENT_CLASSIFICATION, payload, meta)
        valider_synthese(s, ids)
