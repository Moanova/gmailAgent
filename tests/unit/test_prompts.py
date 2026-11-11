import json

import pytest

from gmailagent.agent_prompts import (
    OUTILS_GMAIL,
    categories,
    prompt_classification,
    prompt_spam,
    prompt_suppression,
)
from gmailagent.core_config import RegistreLibelles


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
                "spam-confirme": "Agent/spam-confirme",
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


class TestPromptSpam:
    def test_cles_suivi_depuis_le_registre(self, registre: RegistreLibelles) -> None:
        prompt = prompt_spam(registre)
        assert "suivi.valide-spam" in prompt
        assert "suivi.traite" in prompt

    def test_aucun_libelle_physique_en_dur(self, registre: RegistreLibelles) -> None:
        assert "Agent/" not in prompt_spam(registre)

    def test_conservatisme_veracite_et_statuts(self, registre: RegistreLibelles) -> None:
        prompt = prompt_spam(registre)
        for mot in (
            "in:spam",
            "doute",
            "deplaces",
            "aucun_message",
            "echec_technique",
            "motif",
            "véracité",
        ):
            assert mot in prompt

    def test_pas_de_libellisation_par_lagent(self, registre: RegistreLibelles) -> None:
        prompt = prompt_spam(registre)
        assert "Ne modifie toi-même AUCUN libellé" in prompt
        assert "ni envoyer ni supprimer" in prompt

    def test_objet_json_unique_a_la_racine(self, registre: RegistreLibelles) -> None:
        prompt = prompt_spam(registre)
        assert "UNIQUE objet JSON" in prompt
        assert "`statut`" in prompt
        assert "`messages`" in prompt


class TestBlocLectureCommun:
    def test_bloc_lecture_identique_dans_les_trois_prompts(
        self, registre: RegistreLibelles
    ) -> None:
        """T9.6 : le bloc « Obligatoire : search_threads + get_thread sur chaque thread »
        est factorisé (injecté) — présent à l'identique dans les 3 prompts."""
        extrait = "puis `get_thread` sur **chaque** thread retourné (un appel par thread, sans en"
        for prompt in (
            prompt_classification(registre),
            prompt_spam(registre),
            prompt_suppression(registre),
        ):
            assert extrait in prompt
            assert "Ne produis la synthèse qu'une fois tous les threads" in prompt


class TestPromptSuppression:
    def test_cles_suivi_depuis_le_registre(self, registre: RegistreLibelles) -> None:
        prompt = prompt_suppression(registre)
        assert "suivi.traite" in prompt
        assert "suivi.doublon" in prompt
        assert "classification.notification" in prompt

    def test_aucun_libelle_physique_en_dur(self, registre: RegistreLibelles) -> None:
        assert "Agent/" not in prompt_suppression(registre)

    def test_statuts_champs_et_requete(self, registre: RegistreLibelles) -> None:
        prompt = prompt_suppression(registre)
        for mot in (
            "T+24h",
            "older_than:24h",
            "supprimes",
            "aucun_message",
            "echec_technique",
            "count",
            "ids",
            "véracité",
        ):
            assert mot in prompt

    def test_corbeille_uniquement(self, registre: RegistreLibelles) -> None:
        prompt = prompt_suppression(registre)
        assert "TRASH" in prompt
        assert "label_message" in prompt
        assert "JAMAIS de suppression définitive" in prompt
        assert "ni envoyer ni supprimer définitivement" in prompt

    def test_count_egal_len_ids_si_supprimes(self, registre: RegistreLibelles) -> None:
        prompt = prompt_suppression(registre)
        assert "égal à `len(ids)`" in prompt

    def test_categorie_notification_seule_eligible(self, registre: RegistreLibelles) -> None:
        prompt = prompt_suppression(registre)
        assert "classification.notification" in prompt
        assert "classification.a-repondre" in prompt
        assert "classification.information" in prompt
        assert "JAMAIS" in prompt
        assert "UNREAD" in prompt

    def test_objet_json_unique_a_la_racine(self, registre: RegistreLibelles) -> None:
        prompt = prompt_suppression(registre)
        assert "UNIQUE objet JSON" in prompt
        assert "`statut`" in prompt
        assert "`count`" in prompt
        assert "`ids`" in prompt
