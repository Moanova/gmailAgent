"""Tests d'intégration (T5.5) : agent classification de bout en bout, Gmail + Mistral mockés.

La pile réelle est exercée (orchestrateur -> agents.lancer_conversation avec un faux
client Mistral qui rejoue une conversation scénarisée, et un faux service googleapiclient).
Aucun appel réseau.
"""

import base64
import json
from pathlib import Path
from typing import Any

import pytest

from config import RegistreLibelles
from dedup import empreinte_message
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


def _message_gmail(
    message_id: str, sujet: str = "Sujet", corps: str = "corps du message"
) -> dict[str, Any]:
    return {
        "id": message_id,
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {"name": "Message-ID", "value": f"<{message_id}@ex.fr>"},
                {"name": "Subject", "value": sujet},
                {"name": "From", "value": "exp@ex.fr"},
            ],
            "body": {"data": _b64url(corps)},
        },
    }


class _Requete:
    def __init__(self, resultat: Any) -> None:
        self._resultat = resultat

    def execute(self) -> Any:
        return self._resultat


class _FauxService:
    """Faux service googleapiclient avec 1 thread contenant 1 message."""

    def __init__(
        self,
        message: dict[str, Any] | None = None,
        threads: list[str] | None = None,
        threads_spam: list[str] | None = None,
    ) -> None:
        self.message = message if message is not None else _message_gmail("m1")
        self.liste_threads = threads if threads is not None else ["t1"]
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
                        {"id": "L_arep", "name": "Agent/a-repondre"},
                        {"id": "L_valspam", "name": "Agent/valide-spam"},
                        {"id": "L_spamconfirme", "name": "Agent/spam-confirme"},
                    ]
                }
            )
        if "spam" in str(kwargs.get("q", "")):
            return _Requete({"threads": [{"id": t} for t in self.liste_threads_spam]})
        return _Requete({"threads": [{"id": t} for t in self.liste_threads]})

    def get(self, **kwargs: Any) -> _Requete:
        self.appels.append("get")
        identifiant = str(kwargs.get("id", ""))
        if identifiant == "t1":
            return _Requete({"id": "t1", "messages": [self.message]})
        return _Requete(self.message)

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
        self.choices = [type("C", (), {"message": message})()]


class _FauxChat:
    def __init__(self, scenario: list[_Reponse]) -> None:
        self._scenario = list(scenario)
        self.appels: list[dict[str, Any]] = []

    def complete(self, **kwargs: Any) -> _Reponse:
        self.appels.append(kwargs)
        return self._scenario.pop(0)


class _FauxMistral:
    def __init__(self, scenario: list[_Reponse]) -> None:
        self.chat = _FauxChat(scenario)


def _appel(nom: str, args: dict[str, Any]) -> Any:
    from mistralai.client.models import ToolExecutionEntry

    return ToolExecutionEntry(name=nom, arguments=json.dumps(args, ensure_ascii=False))


def _scenario_spam_vide() -> list[_Reponse]:
    """T9.6 : search spam renvoie 0 thread -> court-circuit `aucun_message` dans le runner."""
    return [
        _Reponse(_Msg(tool_calls=[_appel("search_threads", {"query": "in:spam"})])),
    ]


def _scenario_classification(empreinte: str) -> list[_Reponse]:
    return _scenario_spam_vide() + [
        _Reponse(
            _Msg(tool_calls=[_appel("search_threads", {"query": REQUETE_NON_LUS})])
        ),
        _Reponse(_Msg(tool_calls=[_appel("get_thread", {"threadId": "t1"})])),
        _Reponse(_Msg(tool_calls=[_appel("get_message", {"messageId": "m1"})])),
        _Reponse(
            _Msg(
                content=json.dumps(
                    {
                        "statut": "synthese",
                        "messages": [
                            {
                                "id": "m1",
                                "objet": "Sujet",
                                "expediteur": "exp@ex.fr",
                                "motif": "à traiter",
                                "categorie": "classification.a-repondre",
                                "urgence": "haute",
                                "message_id_rfc": "m1@ex.fr",
                                "empreinte": empreinte,
                            }
                        ],
                    }
                )
            )
        ),
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
                "spam-confirme": "Agent/spam-confirme",
            },
        }
    )


class TestAgentClassificationBoutEnBout:
    def test_classification_ok_pose_libelles(
        self, registre: RegistreLibelles, tmp_path: Path
    ) -> None:
        message = _message_gmail("m1")
        _, empreinte = empreinte_message(message)
        service = _FauxService(message)
        api = ClientGmailAPI(service, dry_run=False)
        mistral = _FauxMistral(_scenario_classification(empreinte))
        rapport = lancer_run_tri(
            dry_run=False,
            client_api=api,
            client_mistral=mistral,  # type: ignore[arg-type]
            registre=registre,
            dossier_checkpoints=tmp_path,
        )
        assert rapport.statut_global == "succes"
        assert rapport.synthese_classification is not None
        assert len(rapport.synthese_classification.messages) == 1
        assert rapport.resume is not None
        assert rapport.resume.par_categorie == {"classification.a-repondre": 1}
        assert rapport.resume.par_urgence == {"haute": 1}
        assert service.modifications == [("m1", ["L_arep", "L_traite"], [])]
        checkpoint = charger_checkpoint(rapport.meta.run_id, tmp_path)
        assert checkpoint.etapes_validees == ETAPES_COMPLETES
        assert mistral.chat.appels[0]["response_format"].type == "json_schema"

    def test_classification_dry_run_aucune_ecriture(
        self, registre: RegistreLibelles, tmp_path: Path
    ) -> None:
        message = _message_gmail("m1")
        _, empreinte = empreinte_message(message)
        service = _FauxService(message)
        api = ClientGmailAPI(service, dry_run=True)
        mistral = _FauxMistral(_scenario_classification(empreinte))
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

    def test_empreinte_erronee_rejet_c6(self, registre: RegistreLibelles, tmp_path: Path) -> None:
        service = _FauxService()
        api = ClientGmailAPI(service, dry_run=False)
        mistral = _FauxMistral(_scenario_classification("0" * 64))
        with pytest.raises(SyntheseInvalideError, match="C6"):
            lancer_run_tri(
                dry_run=False,
                client_api=api,
                client_mistral=mistral,  # type: ignore[arg-type]
                registre=registre,
                dossier_checkpoints=tmp_path,
            )

    def test_boite_vide_aucun_message(self, registre: RegistreLibelles, tmp_path: Path) -> None:
        service = _FauxService(threads=[])
        api = ClientGmailAPI(service, dry_run=True)
        scenario = _scenario_spam_vide() + [
            _Reponse(
                _Msg(tool_calls=[_appel("search_threads", {"query": REQUETE_NON_LUS})])
            ),
            _Reponse(_Msg(content=json.dumps({"statut": "aucun_message", "messages": []}))),
        ]
        mistral = _FauxMistral(scenario)
        rapport = lancer_run_tri(
            dry_run=True,
            client_api=api,
            client_mistral=mistral,  # type: ignore[arg-type]
            registre=registre,
            dossier_checkpoints=tmp_path,
        )
        assert rapport.statut_global == "succes"
        assert rapport.synthese_classification is not None
        assert rapport.synthese_classification.statut == "aucun_message"
        assert rapport.resume is not None
        assert rapport.resume.par_categorie == {}
        assert rapport.resume.spam_deplaces == 0

    def test_idempotence_agent_non_rappele(
        self, registre: RegistreLibelles, tmp_path: Path
    ) -> None:
        message = _message_gmail("m1")
        _, empreinte = empreinte_message(message)
        service = _FauxService(message)
        api = ClientGmailAPI(service, dry_run=True)
        mistral = _FauxMistral(_scenario_classification(empreinte))
        premier = lancer_run_tri(
            dry_run=True,
            client_api=api,
            client_mistral=mistral,  # type: ignore[arg-type]
            registre=registre,
            dossier_checkpoints=tmp_path,
        )
        nb_appels_mistral = len(mistral.chat.appels)
        second = lancer_run_tri(
            run_id=premier.meta.run_id,
            dry_run=True,
            client_api=api,
            client_mistral=mistral,  # type: ignore[arg-type]
            registre=registre,
            dossier_checkpoints=tmp_path,
        )
        assert second.statut_global == "succes"
        assert len(mistral.chat.appels) == nb_appels_mistral
