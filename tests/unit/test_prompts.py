import json

import pytest

from config import RegistreLibelles
from prompts import OUTILS_GMAIL, categories, prompt_classification


@pytest.fixture
def registre() -> RegistreLibelles:
    return RegistreLibelles.model_validate(
        {
            "classification": {
                "a-repondre": "Agent/a-repondre",
                "information": "Agent/information",
                "notification": "Agent/notification",
            },
            "suivi": {
                "traite": "Agent/traité",
                "doublon": "Agent/doublon",
                "valide-spam": "Agent/valide-spam",
            },
        }
    )


class TestOutilsGmail:
    def test_allow_list(self) -> None:
        noms = {outil["function"]["name"] for outil in OUTILS_GMAIL}
        assert noms == {
            "search_threads",
            "get_thread",
            "get_message",
            "label_message",
            "list_labels",
        }

    def test_schemas_conformes(self) -> None:
        for outil in OUTILS_GMAIL:
            assert outil["type"] == "function"
            fonction = outil["function"]
            assert fonction["description"]
            parametres = fonction["parameters"]
            assert parametres["type"] == "object"
            assert "properties" in parametres

    def test_aucun_libelle_physique_en_dur(self) -> None:
        blob = json.dumps(OUTILS_GMAIL, ensure_ascii=False)
        assert "Agent/" not in blob


class TestPromptClassification:
    def test_categories_depuis_le_registre(self, registre: RegistreLibelles) -> None:
        prompt = prompt_classification(registre)
        for cle in (
            "classification.a-repondre",
            "classification.information",
            "classification.notification",
        ):
            assert cle in prompt

    def test_aucun_libelle_physique_en_dur(self, registre: RegistreLibelles) -> None:
        assert "Agent/" not in prompt_classification(registre)

    def test_regles_de_veracite_et_statuts(self, registre: RegistreLibelles) -> None:
        prompt = prompt_classification(registre)
        for mot in (
            "aucun_message",
            "echec_technique",
            "haute",
            "moyenne",
            "basse",
            "message_id_rfc",
            "empreinte",
            "véracité",
        ):
            assert mot in prompt

    def test_categories_helper(self, registre: RegistreLibelles) -> None:
        assert categories(registre) == [
            "classification.a-repondre",
            "classification.information",
            "classification.notification",
        ]
