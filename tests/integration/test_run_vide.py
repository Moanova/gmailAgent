"""Tests d'intégration (T3.4) : run vide de bout en bout, Gmail mocké.

La pile réelle est exercée (CLI -> ClientGmailAPI -> faux service googleapiclient) ;
seule la couche HTTP Gmail est simulée. Aucun appel réseau, aucune écriture réelle.
"""

from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

import cli
from cli import main
from config import RegistreLibelles
from contracts import Meta
from gmail import ClientGmailAPI
from orchestrator import Checkpoint, charger_checkpoint, lancer_run_tri, sauvegarder_checkpoint
from validation import construire_synthese


def _conversation_vide(agent: str, requete: str, meta: Meta, **kwargs: object):
    synthese = construire_synthese(agent, {"statut": "aucun_message", "messages": []}, meta)
    return synthese, []

ETAPES_COMPLETES = [
    "demarrage",
    "lecture_spam",
    "validation_spam",
    "lecture_classification",
    "validation_classification",
    "dedoublonnage",
    "rapport",
    "fin",
]

LECTURES = {"labels.list", "threads.list", "threads.get"}


class _Requete:
    def __init__(self, resultat: Any) -> None:
        self._resultat = resultat

    def execute(self) -> Any:
        return self._resultat


class _FauxService:
    """Simule la chaîne users().labels()/threads()/messages() de googleapiclient."""

    def __init__(self) -> None:
        self.appels: list[tuple[str, dict[str, Any]]] = []

    def users(self) -> "_FauxUsers":
        return _FauxUsers(self)


class _FauxUsers:
    def __init__(self, service: _FauxService) -> None:
        self._service = service

    def labels(self) -> "_FauxLabels":
        return _FauxLabels(self._service)

    def threads(self) -> "_FauxThreads":
        return _FauxThreads(self._service)

    def messages(self) -> "_FauxMessages":
        return _FauxMessages(self._service)


class _FauxLabels:
    def __init__(self, service: _FauxService) -> None:
        self._service = service

    def list(self, userId: str) -> _Requete:
        self._service.appels.append(("labels.list", {"userId": userId}))
        return _Requete(
            {
                "labels": [
                    {"id": "L_traite", "name": "Agent/traité"},
                    {"id": "L_ancien", "name": "Agent/ancien"},
                ]
            }
        )

    def create(self, userId: str, body: dict[str, str]) -> _Requete:
        self._service.appels.append(("labels.create", {"name": body["name"]}))
        return _Requete({"id": "L_nouveau", "name": body["name"]})


class _FauxThreads:
    def __init__(self, service: _FauxService) -> None:
        self._service = service

    def list(self, userId: str, q: str, maxResults: int) -> _Requete:
        self._service.appels.append(("threads.list", {"q": q, "maxResults": maxResults}))
        return _Requete({"threads": [{"id": "t1"}, {"id": "t2"}]})

    def get(self, userId: str, id: str) -> _Requete:
        self._service.appels.append(("threads.get", {"id": id}))
        return _Requete({"id": id, "messages": [{"id": f"{id}-m1"}, {"id": f"{id}-m2"}]})


class _FauxMessages:
    def __init__(self, service: _FauxService) -> None:
        self._service = service

    def modify(self, userId: str, id: str, body: dict[str, list[str]]) -> _Requete:
        self._service.appels.append(("messages.modify", {"id": id, "body": body}))
        return _Requete({"id": id})

    def trash(self, userId: str, id: str) -> _Requete:
        self._service.appels.append(("messages.trash", {"id": id}))
        return _Requete({"id": id})


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


@pytest.fixture
def service_faux(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _FauxService:
    monkeypatch.setenv("LOG_FILE", str(tmp_path / "journalisation.log"))
    service = _FauxService()
    monkeypatch.setattr(
        cli.ClientGmailAPI,
        "depuis_token",
        staticmethod(
            lambda chemin=None, *, dry_run=False: ClientGmailAPI(service, dry_run=dry_run)
        ),
    )
    return service


def _actions(service: _FauxService) -> list[str]:
    return [action for action, _ in service.appels]


class TestRunVide:
    def test_tri_complet_en_dry_run(
        self, registre: RegistreLibelles, tmp_path: Path, service_faux: _FauxService
    ) -> None:
        client = ClientGmailAPI(service_faux, dry_run=True)
        rapport = lancer_run_tri(
            client=client,
            registre=registre,
            dossier_checkpoints=tmp_path,
            conversation=_conversation_vide,
        )
        assert rapport.statut_global == "succes"
        checkpoint = charger_checkpoint(rapport.meta.run_id, tmp_path)
        assert checkpoint.etapes_validees == ETAPES_COMPLETES
        assert (tmp_path / f"{rapport.meta.run_id}.json").exists()
        assert set(_actions(service_faux)) <= LECTURES

    def test_idempotence_deux_runs_meme_run_id(
        self, registre: RegistreLibelles, tmp_path: Path, service_faux: _FauxService
    ) -> None:
        client = ClientGmailAPI(service_faux, dry_run=True)
        premier = lancer_run_tri(
            client=client,
            registre=registre,
            dossier_checkpoints=tmp_path,
            conversation=_conversation_vide,
        )
        nb_appels = len(service_faux.appels)
        second = lancer_run_tri(
            run_id=premier.meta.run_id,
            client=client,
            registre=registre,
            dossier_checkpoints=tmp_path,
            conversation=_conversation_vide,
        )
        assert second.meta.run_id == premier.meta.run_id
        assert second.statut_global == "succes"
        assert len(service_faux.appels) == nb_appels

    def test_reprise_apres_crash_sur_checkpoint_partiel(
        self, registre: RegistreLibelles, tmp_path: Path, service_faux: _FauxService
    ) -> None:
        rid = uuid4()
        sauvegarder_checkpoint(Checkpoint(run_id=rid, etapes_validees=["demarrage"]), tmp_path)
        client = ClientGmailAPI(service_faux, dry_run=True)
        rapport = lancer_run_tri(
            run_id=rid,
            client=client,
            registre=registre,
            dossier_checkpoints=tmp_path,
            conversation=_conversation_vide,
        )
        assert rapport.statut_global == "succes"
        checkpoint = charger_checkpoint(rid, tmp_path)
        assert checkpoint.etapes_validees == ETAPES_COMPLETES
        assert checkpoint.etapes_validees.count("demarrage") == 1


class TestMigrateLabels:
    def test_dry_run_aucune_ecriture(
        self, service_faux: _FauxService, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(["migrate-labels", "Agent/ancien", "Agent/nouveau"]) == 0
        actions = _actions(service_faux)
        assert "threads.list" in actions
        assert "threads.get" in actions
        assert "messages.modify" not in actions
        assert "labels.create" not in actions
        assert "messages.trash" not in actions
        assert "dry-run" in capsys.readouterr().out

    def test_reel_deplace_les_messages(
        self, service_faux: _FauxService, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(["--reel", "migrate-labels", "Agent/ancien", "Agent/nouveau"]) == 0
        actions = _actions(service_faux)
        assert "labels.create" in actions
        modifs = [kw for action, kw in service_faux.appels if action == "messages.modify"]
        assert len(modifs) == 4
        assert modifs[0]["body"] == {"addLabelIds": ["L_nouveau"], "removeLabelIds": ["L_ancien"]}
        requete = next(kw for action, kw in service_faux.appels if action == "threads.list")
        assert requete["q"] == 'label:"Agent/ancien"'
        assert "réel" in capsys.readouterr().out
