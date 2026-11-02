import base64
from pathlib import Path
from uuid import uuid4

import pytest
from googleapiclient.errors import HttpError
from httplib2 import Response

from client import avec_retry
from config import RegistreLibelles
from dedup import empreinte_message
from gmail import ClientGmailAPI
from labels import LibelleGmail, ResolveurLibelles
from orchestrator import (
    Checkpoint,
    CheckpointError,
    charger_checkpoint,
    lancer_run_tri,
    requete_non_lus,
    sauvegarder_checkpoint,
)
from validation import SyntheseInvalideError, construire_synthese

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


@pytest.fixture(autouse=True)
def _journal_vers_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_FILE", str(tmp_path / "journalisation.log"))


class _FauxClientGmail:
    def __init__(
        self,
        labels: list[LibelleGmail] | None = None,
        erreur: Exception | None = None,
    ) -> None:
        if labels is None:
            labels = [LibelleGmail(id="Label_1", name="Agent/traité")]
        self._labels = labels
        self._erreur = erreur
        self.appels_list = 0
        self.creations: list[str] = []

    def list_labels(self) -> list[LibelleGmail]:
        self.appels_list += 1
        if self._erreur is not None:
            raise self._erreur
        return list(self._labels)

    def create_label(self, name: str) -> LibelleGmail:
        self.creations.append(name)
        return LibelleGmail(id=f"Label_{len(self.creations)}", name=name)


class _ServiceVide:
    def users(self) -> "_ServiceVide":
        return self

    def labels(self) -> "_ServiceVide":
        return self

    def threads(self) -> "_ServiceVide":
        return self

    def messages(self) -> "_ServiceVide":
        return self

    def list(self, **kwargs: object) -> "_ServiceVide":
        return self

    def get(self, **kwargs: object) -> "_ServiceVide":
        return self

    def modify(self, **kwargs: object) -> "_ServiceVide":
        return self

    def create(self, **kwargs: object) -> "_ServiceVide":
        return self

    def trash(self, **kwargs: object) -> "_ServiceVide":
        return self

    def execute(self) -> dict[str, object]:
        return {}


def _faux_conversation_vide(agent: str, requete: str, meta: object, **kwargs: object):
    synthese = construire_synthese(
        agent, {"statut": "aucun_message", "messages": []}, meta  # type: ignore[arg-type]
    )
    return synthese, []


def _run(
    registre: RegistreLibelles,
    tmp_path: Path,
    client: _FauxClientGmail,
    *,
    run_id=None,
    dry_run: bool = True,
    client_api: ClientGmailAPI | None = None,
    conversation=None,
):
    return lancer_run_tri(
        run_id=run_id,
        dry_run=dry_run,
        client=client,
        client_api=client_api or ClientGmailAPI(_ServiceVide(), dry_run=dry_run),
        conversation=conversation or _faux_conversation_vide,
        registre=registre,
        dossier_checkpoints=tmp_path,
    )


class TestRequeteIdempotence:
    def test_construite_depuis_le_registre(self, registre: RegistreLibelles) -> None:
        resolveur = ResolveurLibelles(registre, _FauxClientGmail(), dry_run=True)
        requete = requete_non_lus(registre, resolveur)
        attendu = f'is:unread -label:"{registre.libelle("suivi.traite")}"'
        assert requete == attendu
        assert "Agent/traité" in requete


class TestLancerRunTri:
    def test_run_vide_de_bout_en_bout(self, registre: RegistreLibelles, tmp_path: Path) -> None:
        client = _FauxClientGmail()
        rapport = _run(registre, tmp_path, client)
        assert rapport.statut_global == "succes"
        checkpoint = charger_checkpoint(rapport.meta.run_id, tmp_path)
        assert checkpoint.etapes_validees == ETAPES_COMPLETES
        assert checkpoint.rapport is not None
        assert (tmp_path / f"{rapport.meta.run_id}.json").exists()
        assert client.creations == []

    def test_dry_run_ne_cree_pas_le_libelle(
        self, registre: RegistreLibelles, tmp_path: Path
    ) -> None:
        client = _FauxClientGmail(labels=[])
        _run(registre, tmp_path, client, dry_run=True)
        assert client.creations == []

    def test_run_reel_cree_le_libelle_traite_si_absent(
        self, registre: RegistreLibelles, tmp_path: Path
    ) -> None:
        client = _FauxClientGmail(labels=[])
        _run(registre, tmp_path, client, dry_run=False)
        assert client.creations == ["Agent/traité"]

    def test_reprise_sur_incident_ne_rejoue_pas(
        self, registre: RegistreLibelles, tmp_path: Path
    ) -> None:
        client = _FauxClientGmail()
        premier = _run(registre, tmp_path, client)
        appels_apres_premier = client.appels_list
        second = _run(registre, tmp_path, client, run_id=premier.meta.run_id)
        assert second.meta.run_id == premier.meta.run_id
        assert second.statut_global == "succes"
        assert client.appels_list == appels_apres_premier

    def test_reprise_apres_crash_partiel(self, registre: RegistreLibelles, tmp_path: Path) -> None:
        rid = uuid4()
        sauvegarder_checkpoint(Checkpoint(run_id=rid, etapes_validees=["demarrage"]), tmp_path)
        rapport = _run(registre, tmp_path, _FauxClientGmail(), run_id=rid)
        assert rapport.statut_global == "succes"
        checkpoint = charger_checkpoint(rid, tmp_path)
        assert checkpoint.etapes_validees == ETAPES_COMPLETES

    def test_rejet_arrete_proprement_et_persiste(
        self, registre: RegistreLibelles, tmp_path: Path
    ) -> None:
        rid = uuid4()
        client = _FauxClientGmail(erreur=RuntimeError("API indisponible"))
        with pytest.raises(RuntimeError, match="API indisponible"):
            _run(registre, tmp_path, client, run_id=rid)
        checkpoint = charger_checkpoint(rid, tmp_path)
        assert checkpoint.rapport is not None
        assert checkpoint.rapport.statut_global == "echec_partiel"
        assert checkpoint.rapport.etape_fautive == "demarrage"


class TestCheckpoints:
    def test_round_trip_json(self, tmp_path: Path) -> None:
        rid = uuid4()
        cp = Checkpoint(run_id=rid, etapes_validees=["demarrage"])
        sauvegarder_checkpoint(cp, tmp_path)
        assert charger_checkpoint(rid, tmp_path) == cp

    def test_absent(self, tmp_path: Path) -> None:
        with pytest.raises(CheckpointError, match="illisible"):
            charger_checkpoint(uuid4(), tmp_path)


class TestAvecRetry:
    def _http_error(self, statut: int) -> HttpError:
        return HttpError(Response({"status": str(statut)}), b"corps")

    def test_succes_apres_429(self) -> None:
        appels = {"n": 0}

        def operation() -> str:
            appels["n"] += 1
            if appels["n"] == 1:
                raise self._http_error(429)
            return "ok"

        assert avec_retry(operation, dormir=lambda _d: None) == "ok"
        assert appels["n"] == 2

    def test_400_non_retentable(self) -> None:
        appels = {"n": 0}

        def operation() -> str:
            appels["n"] += 1
            raise self._http_error(400)

        with pytest.raises(HttpError):
            avec_retry(operation, dormir=lambda _d: None)
        assert appels["n"] == 1

    def test_epuisement_apres_3_tentatives(self) -> None:
        appels = {"n": 0}

        def operation() -> str:
            appels["n"] += 1
            raise self._http_error(500)

        with pytest.raises(HttpError):
            avec_retry(operation, dormir=lambda _d: None)
        assert appels["n"] == 3

    def test_erreur_non_http_non_retentable(self) -> None:
        def operation() -> str:
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            avec_retry(operation, dormir=lambda _d: None)


def _payload_message(message_id: str = "m1") -> dict[str, object]:
    corps = base64.urlsafe_b64encode(b"corps").decode().rstrip("=")
    return {
        "payload": {
            "headers": [
                {"name": "Message-ID", "value": "abc@ex.fr"},
                {"name": "Subject", "value": "Sujet"},
                {"name": "From", "value": "exp@ex.fr"},
            ],
            "body": {"data": corps},
        }
    }


class _ServiceAvecMessage:
    def __init__(self) -> None:
        self.modifications: list[tuple[str, list[str], list[str]]] = []

    def users(self) -> "_ServiceAvecMessage":
        return self

    def messages(self) -> "_ServiceAvecMessage":
        return self

    def labels(self) -> "_ServiceAvecMessage":
        return self

    def list(self, **kwargs: object) -> "_ServiceAvecMessage":
        return self

    def get(self, **kwargs: object) -> "_ServiceAvecMessage":
        return self

    def modify(self, userId: str, id: str, body: "dict[str, list[str]]") -> "_ServiceAvecMessage":
        self.modifications.append(
            (id, list(body.get("addLabelIds", [])), list(body.get("removeLabelIds", [])))
        )
        return self

    def execute(self) -> dict[str, object]:
        return _payload_message()


def _conversation_classifiee(meta: object, empreinte: str) -> object:
    def _fn(agent: str, requete: str, meta_arg: object, **kwargs: object):
        payload = {
            "statut": "synthese",
            "messages": [
                {
                    "id": "m1",
                    "objet": "Sujet",
                    "expediteur": "exp@ex.fr",
                    "motif": "motif",
                    "categorie": "classification.a-repondre",
                    "urgence": "haute",
                    "message_id_rfc": "abc@ex.fr",
                    "empreinte": empreinte,
                }
            ],
        }
        synthese = construire_synthese(agent, payload, meta_arg)  # type: ignore[arg-type]
        return synthese, []

    return _fn


class TestEtapes34Classification:
    def test_classification_ok_pose_libelles(
        self, registre: RegistreLibelles, tmp_path: Path
    ) -> None:
        service = _ServiceAvecMessage()
        api = ClientGmailAPI(service, dry_run=False)
        _, empreinte = empreinte_message(_payload_message())
        client_labels = _FauxClientGmail(
            labels=[
                LibelleGmail(id="L_traite", name="Agent/traité"),
                LibelleGmail(id="L_arep", name="Agent/a-repondre"),
            ]
        )
        rapport = _run(
            registre,
            tmp_path,
            client_labels,
            client_api=api,
            conversation=_conversation_classifiee(None, empreinte),
        )
        assert rapport.statut_global == "succes"
        assert rapport.synthese_classification is not None
        assert service.modifications == [("m1", ["L_arep", "L_traite"], [])]
        checkpoint = charger_checkpoint(rapport.meta.run_id, tmp_path)
        assert "classification" in checkpoint.syntheses

    def test_empreinte_erronee_rejette(
        self, registre: RegistreLibelles, tmp_path: Path
    ) -> None:
        service = _ServiceAvecMessage()
        api = ClientGmailAPI(service, dry_run=False)
        client_labels = _FauxClientGmail(
            labels=[
                LibelleGmail(id="L_traite", name="Agent/traité"),
                LibelleGmail(id="L_arep", name="Agent/a-repondre"),
            ]
        )
        with pytest.raises(SyntheseInvalideError, match="C6"):
            _run(
                registre,
                tmp_path,
                client_labels,
                client_api=api,
                conversation=_conversation_classifiee(None, "0" * 64),
            )

    def test_dry_run_ne_modifie_pas(
        self, registre: RegistreLibelles, tmp_path: Path
    ) -> None:
        service = _ServiceAvecMessage()
        api = ClientGmailAPI(service, dry_run=True)
        _, empreinte = empreinte_message(_payload_message())
        client_labels = _FauxClientGmail(
            labels=[
                LibelleGmail(id="L_traite", name="Agent/traité"),
                LibelleGmail(id="L_arep", name="Agent/a-repondre"),
            ]
        )
        rapport = _run(
            registre,
            tmp_path,
            client_labels,
            dry_run=True,
            client_api=api,
            conversation=_conversation_classifiee(None, empreinte),
        )
        assert rapport.statut_global == "succes"
        assert service.modifications == []

    def test_reprise_ne_rappelle_pas_lagent(
        self, registre: RegistreLibelles, tmp_path: Path
    ) -> None:
        appels = {"n": 0}

        def _compte(agent: str, requete: str, meta: object, **kwargs: object):
            appels["n"] += 1
            return _faux_conversation_vide(agent, requete, meta, **kwargs)

        client_labels = _FauxClientGmail()
        premier = _run(registre, tmp_path, client_labels, conversation=_compte)
        _run(registre, tmp_path, client_labels, run_id=premier.meta.run_id, conversation=_compte)
        assert appels["n"] == 1
