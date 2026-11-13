from pathlib import Path
from typing import Any

import pytest

from gmailagent.core_config import (
    Limites,
    Parametres,
    ParametresInvalidesError,
    ParametresSuppression,
    RegistreLibelles,
    charger_parametres,
    definir_parametres,
    parametres_courants,
)
from gmailagent.gmail_client import ClientGmailAPI
from gmailagent.gmail_labels import ResolveurLibelles
from gmailagent.pipeline_orchestrator import requete_suppression


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
        assert p.limites.marge_appels_reprise == 3
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


class TestModeleSampling:
    """T9.11 : `temperature`/`top_p` configurables et bornés, avec la règle glouton
    (`temperature=0` exige `top_p=1`, code API 3054 imposé par ex. `mistral-large-latest`)."""

    def test_defauts_glouton(self) -> None:
        modele = Parametres().modele
        assert modele.temperature == 0.0
        assert modele.top_p == 1.0

    def test_settings_du_depot(self) -> None:
        p = charger_parametres()
        assert p.modele.temperature == 0.0
        assert p.modele.top_p == 1.0

    def test_valeurs_custom_chargees(self, tmp_path: Path) -> None:
        cible = tmp_path / "settings.yaml"
        cible.write_text("modele:\n  temperature: 0.7\n  top_p: 0.95\n", encoding="utf-8")
        p = charger_parametres(cible)
        assert p.modele.temperature == 0.7
        assert p.modele.top_p == 0.95

    def test_glouton_sans_top_p_1_rejete(self, tmp_path: Path) -> None:
        cible = tmp_path / "settings.yaml"
        cible.write_text("modele:\n  temperature: 0.0\n  top_p: 0.9\n", encoding="utf-8")
        with pytest.raises(ParametresInvalidesError, match="3054"):
            charger_parametres(cible)

    def test_hors_bornes_rejetes(self, tmp_path: Path) -> None:
        textes = (
            "modele:\n  temperature: 2.5\n",
            "modele:\n  top_p: 0\n",
            "modele:\n  top_p: 1.5\n",
        )
        for texte in textes:
            cible = tmp_path / "settings.yaml"
            cible.write_text(texte, encoding="utf-8")
            with pytest.raises(ParametresInvalidesError):
                charger_parametres(cible)


class TestCapThreadsRecherche:
    """D58 : le cap de threads recherchés est dérivé du budget d'appels (jamais l'inverse),
    pour qu'un run conforme n'atteigne jamais le garde-fou anti-boucle."""

    def test_cap_derive_des_defauts(self) -> None:
        limites = Limites()
        assert limites.marge_appels_reprise == 3
        assert limites.cap_threads_recherche() == 23  # (50 - 1 - 3) // 2, borné par 25

    def test_invariant_budget_couvre_le_pire_cas(self) -> None:
        for plafond, marge, max_threads in [
            (50, 3, 25),
            (20, 2, 25),
            (10, 0, 25),
            (3, 0, 25),
            (50, 3, 5),
        ]:
            limites = Limites(
                plafond_appels_outils=plafond,
                marge_appels_reprise=marge,
                max_threads_par_run=max_threads,
            )
            cap = limites.cap_threads_recherche()
            assert 1 <= cap <= max_threads
            # pire cas conforme : 1 search + 2 appels/thread + marge de reprises
            assert plafond >= 2 * cap + 1 + marge

    def test_settings_du_depot_charge_la_marge(self) -> None:
        p = charger_parametres()
        assert p.limites.marge_appels_reprise == 3
        assert p == Parametres()  # settings.yaml du dépôt == défauts du code
