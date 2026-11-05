from pathlib import Path
from typing import Any

import pytest

from config import (
    Limites,
    Parametres,
    ParametresInvalidesError,
    ParametresSuppression,
    RegistreLibelles,
    charger_parametres,
    definir_parametres,
    parametres_courants,
)
from gmail import ClientGmailAPI
from labels import ResolveurLibelles
from orchestrator import requete_suppression


class _Requete:
    def __init__(self, resultat: Any) -> None:
        self._resultat = resultat

    def execute(self) -> Any:
        return self._resultat


class _FauxClientLabels:
    def list_labels(self) -> list[dict[str, str]]:
        return []


class _FauxServiceThreads:
    def __init__(self) -> None:
        self.appels: list[dict[str, Any]] = []

    def users(self) -> "_FauxServiceThreads":
        return self

    def threads(self) -> "_FauxServiceThreads":
        return self

    def list(self, userId: str, q: str, maxResults: int) -> _Requete:
        self.appels.append({"q": q, "maxResults": maxResults})
        return _Requete({"threads": []})


class TestParametresDefauts:
    def test_defauts_code(self) -> None:
        p = Parametres()
        assert p.modele.defaut == "mistral-small-latest"
        assert p.limites.max_tokens == 8000
        assert p.limites.plafond_appels_outils == 50
        assert p.limites.max_tentatives_synthese == 3
        assert p.limites.max_threads_par_run == 25
        assert p.limites.plafond_lectures == 100
        assert p.limites.max_resultats == 50
        assert p.limites.limite_corps_apercu == 2000
        assert p.limites.limite_reponse_outil == 20000
        assert p.limites.plafond_runs_tout == 10
        assert p.limites.timeout_http_ms == 300_000
        assert p.suppression.delai_grace == "24h"
        assert p.spam.requete == "in:spam"
        assert p.chemins.token_gmail == "data/gmail_token.json"
        assert p.chemins.checkpoints == "data/checkpoints"
        assert p.chemins.journal == "logs/gmailagent.log"

    def test_settings_du_depot_charges(self) -> None:
        assert charger_parametres() == Parametres()

    def test_fichier_explicite_manquant_rejete(self, tmp_path: Path) -> None:
        with pytest.raises(ParametresInvalidesError):
            charger_parametres(tmp_path / "inexistant.yaml")

    def test_yaml_partiel_fusionne_avec_defauts(self, tmp_path: Path) -> None:
        cible = tmp_path / "settings.yaml"
        cible.write_text("limites:\n  max_tokens: 4000\n", encoding="utf-8")
        p = charger_parametres(cible)
        assert p.limites.max_tokens == 4000
        assert p.limites.max_threads_par_run == 25
        assert p.modele.defaut == "mistral-small-latest"

    def test_cle_inconnue_rejetee(self, tmp_path: Path) -> None:
        cible = tmp_path / "settings.yaml"
        cible.write_text("inconnu: 1\n", encoding="utf-8")
        with pytest.raises(ParametresInvalidesError):
            charger_parametres(cible)

    def test_valeur_hors_bornes_rejetee(self, tmp_path: Path) -> None:
        cible = tmp_path / "settings.yaml"
        cible.write_text("limites:\n  max_tokens: 0\n", encoding="utf-8")
        with pytest.raises(ParametresInvalidesError):
            charger_parametres(cible)


class TestParametresCourants:
    def test_singleton_et_reset(self) -> None:
        definir_parametres(None)
        assert parametres_courants() == Parametres()
        custom = Parametres(suppression=ParametresSuppression(delai_grace="48h"))
        definir_parametres(custom)
        assert parametres_courants() is custom
        definir_parametres(None)
        assert parametres_courants() == Parametres()


class TestCablages:
    def test_requete_suppression_suit_delai_grace(
        self, registre: RegistreLibelles
    ) -> None:
        definir_parametres(Parametres(suppression=ParametresSuppression(delai_grace="48h")))
        resolveur = ResolveurLibelles(registre, _FauxClientLabels(), dry_run=True)
        requete = requete_suppression(registre, resolveur)
        assert "older_than:48h" in requete
        assert "older_than:24h" not in requete

    def test_search_threads_suit_max_resultats(self) -> None:
        definir_parametres(Parametres(limites=Limites(max_resultats=10)))
        service = _FauxServiceThreads()
        client = ClientGmailAPI(service, dry_run=True)
        client.search_threads("q")
        assert service.appels == [{"q": "q", "maxResults": 10}]
