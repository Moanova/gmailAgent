"""Tests d'intégration (T4.4) : agent spam de bout en bout, Gmail + Mistral mockés.

La pile réelle est exercée (orchestrateur -> agents.lancer_conversation avec un faux
client Mistral qui rejoue une conversation scénarisée, et un faux service googleapiclient).
Aucun appel réseau, aucune écriture réelle.
"""

import base64
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from mistralai.client.models import ToolExecutionEntry

from config import RegistreLibelles
from gmail import ClientGmailAPI
from orchestrator import charger_checkpoint, lancer_run_tri
from validation import SyntheseInvalideError

REQUETE_NON_LUS = 'is:unread -label:"Agent/traité"'

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


def _b64url(texte: str) -> str:
    return base64.urlsafe_b64encode(texte.encode("utf-8")).decode("ascii").rstrip("=")


def _message_gmail(message_id: str, sujet: str = "Newsletter") -> dict[str, Any]:
    return {
        "id": message_id,
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {"name": "Message-ID", "value": f"<{message_id}@ex.fr>"},
                {"name": "Subject", "value": sujet},
                {"name": "From", "value": "news@ex.fr"},
            ],
            "body": {"data": _b64url("corps")},
        },
    }


class _Requete:
    def __init__(self, resultat: Any) -> None:
        self._resultat = resultat

    def execute(self) -> Any:
        return self._resultat


class _FauxService:
    """Faux service googleapiclient : threads spam et non lus séparés selon la requête."""

    def __init__(
        self,
        threads: list[str] | None = None,
        threads_spam: list[str] | None = None,
        message: dict[str, Any] | None = None,
    ) -> None:
        self.message = message if message is not None else _message_gmail("m-spam1")
        self.liste_threads = threads if threads is not None else []
        self.liste_threads_spam = threads_spam if threads_spam is not None else []
        self.appels: list[str] = []
        self.modifications: list[tuple[str, list[str], list[str]]] = []
        self._mode = ""

    def users(self) -> "_FauxService":
        return self

    def labels(self) -> "_FauxService":
        self._mode = "labels"
        return self

    def threads(self) -> "_FauxService":
        self._mode = "threads"
        return self

    def messages(self) -> "_FauxService":
        self._mode = "messages"
        return self

    def list(self, **kwargs: Any) -> _Requete:
        self.appels.append(f"{self._mode}.list")
        if self._mode == "labels":
            return _Requete(
                {
                    "labels": [
                        {"id": "L_traite", "name": "Agent/traité"},
                        {"id": "L_valspam", "name": "Agent/valide-spam"},
                        {"id": "L_arep", "name": "Agent/a-repondre"},
                    ]
                }
            )
        if "spam" in str(kwargs.get("q", "")):
            return _Requete({"threads": [{"id": t} for t in self.liste_threads_spam]})
        return _Requete({"threads": [{"id": t} for t in self.liste_threads]})

    def get(self, **kwargs: Any) -> _Requete:
        self.appels.append("get")
        identifiant = str(kwargs.get("id", ""))
        return _Requete({"id": identifiant, "messages": [self.message]})

    def modify(self, userId: str, id: str, body: "dict[str, list[str]]") -> _Requete:
        self.appels.append("modify")
        self.modifications.append(
            (id, list(body.get("addLabelIds", [])), list(body.get("removeLabelIds", [])))
        )
        return _Requete({"id": id})

    def create(self, **kwargs: Any) -> _Requete:
        self.appels.append("create")
        return _Requete({"id": "L_cree", "name": str(kwargs.get("body", {}))})


class _Msg:
    def __init__(self, content: str | None = None, tool_calls: list[Any] | None = None) -> None:
        self.content = content
        self.tool_calls = tool_calls


class _Reponse:
    def __init__(self, message: _Msg) -> None:
        self.choices = [type("Choix", (), {"message": message})()]


class _FauxChat:
    def __init__(self, reponses: list[_Reponse]) -> None:
        self._reponses = list(reponses)
        self.appels: list[dict[str, Any]] = []

    def complete(self, **kwargs: Any) -> _Reponse:
        self.appels.append(kwargs)
        return self._reponses.pop(0)


class _FauxMistral:
    def __init__(self, reponses: list[_Reponse]) -> None:
        self.chat = _FauxChat(reponses)


def _appel(nom: str, args: dict[str, Any]) -> Any:
    return ToolExecutionEntry(name=nom, arguments=json.dumps(args, ensure_ascii=False))


def _payload_spam(statut: str, ids: list[str]) -> str:
    return json.dumps(
        {
            "statut": statut,
            "messages": [
                {
                    "id": mid,
                    "objet": f"S-{mid}",
                    "expediteur": "news@ex.fr",
                    "motif": "newsletter connue",
                }
                for mid in ids
            ],
        }
    )


def _scenario_spam_deplaces(ids: list[str] | None = None) -> list[_Reponse]:
    ids = ["m-spam1"] if ids is None else ids
    return [
        _Reponse(_Msg(tool_calls=[_appel("search_threads", {"query": "in:spam"})])),
        _Reponse(_Msg(tool_calls=[_appel("get_thread", {"threadId": "t-spam"})])),
        _Reponse(_Msg(content=_payload_spam("deplaces", ids))),
    ]


def _scenario_spam_vide() -> list[_Reponse]:
    return [
        _Reponse(_Msg(tool_calls=[_appel("search_threads", {"query": "in:spam"})])),
        _Reponse(_Msg(content=_payload_spam("aucun_message", []))),
    ]


def _scenario_classification_vide() -> list[_Reponse]:
    return [
        _Reponse(
            _Msg(tool_calls=[_appel("search_threads", {"query": REQUETE_NON_LUS})])
        ),
        _Reponse(_Msg(content=json.dumps({"statut": "aucun_message", "messages": []}))),
    ]


@pytest.fixture(autouse=True)
def _journal_vers_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_FILE", str(tmp_path / "journalisation.log"))


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


class TestAgentSpamBoutEnBout:
    def test_deplaces_pose_libelles_et_remet_inbox(
        self, registre: RegistreLibelles, tmp_path: Path
    ) -> None:
        service = _FauxService(threads=[], threads_spam=["t-spam"])
        api = ClientGmailAPI(service, dry_run=False)
        mistral = _FauxMistral(_scenario_spam_deplaces() + _scenario_classification_vide())
        rapport = lancer_run_tri(
            dry_run=False,
            client_api=api,
            client_mistral=mistral,  # type: ignore[arg-type]
            registre=registre,
            dossier_checkpoints=tmp_path,
        )
        assert rapport.statut_global == "succes"
        assert rapport.synthese_spam is not None
        assert rapport.synthese_spam.statut == "deplaces"
        assert [m.id for m in rapport.synthese_spam.messages] == ["m-spam1"]
        assert rapport.resume is not None
        assert rapport.resume.spam_deplaces == 1
        assert rapport.resume.par_categorie == {}
        assert service.modifications == [
            ("m-spam1", ["L_valspam", "L_traite", "INBOX"], ["SPAM"])
        ]
        checkpoint = charger_checkpoint(rapport.meta.run_id, tmp_path)
        assert checkpoint.etapes_validees == ETAPES_COMPLETES
        assert "spam" in checkpoint.syntheses
        assert checkpoint.syntheses["spam"].statut == "deplaces"

    def test_deplaces_dry_run_aucune_ecriture(
        self, registre: RegistreLibelles, tmp_path: Path
    ) -> None:
        service = _FauxService(threads=[], threads_spam=["t-spam"])
        api = ClientGmailAPI(service, dry_run=True)
        mistral = _FauxMistral(_scenario_spam_deplaces() + _scenario_classification_vide())
        rapport = lancer_run_tri(
            dry_run=True,
            client_api=api,
            client_mistral=mistral,  # type: ignore[arg-type]
            registre=registre,
            dossier_checkpoints=tmp_path,
        )
        assert rapport.statut_global == "succes"
        assert service.modifications == []
        assert "modify" not in service.appels

    def test_synthese_rejetee_arrete_proprement(
        self, registre: RegistreLibelles, tmp_path: Path
    ) -> None:
        rid = uuid4()
        service = _FauxService(threads=[], threads_spam=["t-spam"])
        api = ClientGmailAPI(service, dry_run=True)
        mistral = _FauxMistral(_scenario_spam_deplaces(ids=["m-inconnu"]))
        with pytest.raises(SyntheseInvalideError, match="non manipul"):
            lancer_run_tri(
                run_id=rid,
                dry_run=True,
                client_api=api,
                client_mistral=mistral,  # type: ignore[arg-type]
                registre=registre,
                dossier_checkpoints=tmp_path,
            )
        checkpoint = charger_checkpoint(rid, tmp_path)
        assert checkpoint.rapport is not None
        assert checkpoint.rapport.statut_global == "echec_partiel"
        assert checkpoint.rapport.etape_fautive == "lecture_spam"

    def test_boite_spam_vide_aucun_message(
        self, registre: RegistreLibelles, tmp_path: Path
    ) -> None:
        service = _FauxService(threads=[], threads_spam=[])
        api = ClientGmailAPI(service, dry_run=True)
        mistral = _FauxMistral(_scenario_spam_vide() + _scenario_classification_vide())
        rapport = lancer_run_tri(
            dry_run=True,
            client_api=api,
            client_mistral=mistral,  # type: ignore[arg-type]
            registre=registre,
            dossier_checkpoints=tmp_path,
        )
        assert rapport.statut_global == "succes"
        assert rapport.synthese_spam is not None
        assert rapport.synthese_spam.statut == "aucun_message"
        assert service.modifications == []

    def test_idempotence_agent_spam_non_rappele(
        self, registre: RegistreLibelles, tmp_path: Path
    ) -> None:
        service = _FauxService(threads=[], threads_spam=["t-spam"])
        api = ClientGmailAPI(service, dry_run=True)
        mistral = _FauxMistral(_scenario_spam_deplaces() + _scenario_classification_vide())
        premier = lancer_run_tri(
            dry_run=True,
            client_api=api,
            client_mistral=mistral,  # type: ignore[arg-type]
            registre=registre,
            dossier_checkpoints=tmp_path,
        )
        nb_appels = len(mistral.chat.appels)
        second = lancer_run_tri(
            run_id=premier.meta.run_id,
            dry_run=True,
            client_api=api,
            client_mistral=mistral,  # type: ignore[arg-type]
            registre=registre,
            dossier_checkpoints=tmp_path,
        )
        assert second.statut_global == "succes"
        assert len(mistral.chat.appels) == nb_appels
