import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from mistralai.client.models import ToolExecutionEntry

from agents import (
    GardeFouAtteintError,
    executer_outil,
    lancer_conversation,
)
from config import RegistreLibelles
from contracts import AGENT_CLASSIFICATION, AgentInconnuError, Meta
from gmail import ClientGmailAPI
from validation import SyntheseInvalideError


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


@pytest.fixture
def meta() -> Meta:
    return Meta(run_id=uuid4(), etape="lecture_classification", agent=AGENT_CLASSIFICATION)


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


class _Requete:
    def __init__(self, resultat: Any) -> None:
        self._resultat = resultat

    def execute(self) -> Any:
        return self._resultat


class _FauxService:
    def __init__(self, threads: list[str] | None = None) -> None:
        self.appels: list[str] = []
        self.threads = threads if threads is not None else ["t1"]

    def users(self) -> "_FauxUsers":
        return _FauxUsers(self)


class _FauxUsers:
    def __init__(self, service: _FauxService) -> None:
        self._service = service

    def threads(self) -> "_FauxThreads":
        return _FauxThreads(self._service)

    def messages(self) -> "_FauxMessages":
        return _FauxMessages(self._service)


class _FauxThreads:
    def __init__(self, service: _FauxService) -> None:
        self._service = service

    def list(self, userId: str, q: str, maxResults: int) -> _Requete:
        self._service.appels.append("threads.list")
        return _Requete({"threads": [{"id": t} for t in self._service.threads]})

    def get(self, userId: str, id: str) -> _Requete:
        self._service.appels.append("threads.get")
        return _Requete({"id": id, "messages": [{"id": "m1"}]})


class _FauxMessages:
    def __init__(self, service: _FauxService) -> None:
        self._service = service

    def get(self, userId: str, id: str) -> _Requete:
        self._service.appels.append("messages.get")
        return _Requete({"id": id, "payload": {"headers": [], "body": {}}})

    def modify(self, userId: str, id: str, body: dict[str, list[str]]) -> _Requete:
        self._service.appels.append("messages.modify")
        return _Requete({"id": id})


def _appel(nom: str, args: dict[str, Any]) -> ToolExecutionEntry:
    return ToolExecutionEntry(name=nom, arguments=json.dumps(args, ensure_ascii=False))


def _appel_reel(nom: str, args: dict[str, Any], id_appel: str = "call_1") -> Any:
    """Appel d'outil sous la forme réellement renvoyée par l'API Mistral (ToolCall)."""
    from mistralai.client.models import ToolCall

    return ToolCall.model_validate(
        {
            "type": "function",
            "id": id_appel,
            "function": {"name": nom, "arguments": json.dumps(args, ensure_ascii=False)},
        }
    )


def _synthese_payload(statut: str = "synthese", message_id: str = "m1") -> str:
    return json.dumps(
        {
            "statut": statut,
            "messages": [
                {
                    "id": message_id,
                    "objet": "Sujet",
                    "expediteur": "exp@exemple.fr",
                    "motif": "motif",
                    "categorie": "classification.a-repondre",
                    "urgence": "haute",
                    "message_id_rfc": "abc@exemple.fr",
                    "empreinte": "a" * 64,
                }
            ],
        }
    )


def _conversation_ok() -> list[_Reponse]:
    return [
        _Reponse(_Msg(tool_calls=[_appel("search_threads", {"query": "is:unread"})])),
        _Reponse(_Msg(tool_calls=[_appel("get_thread", {"threadId": "t1"})])),
        _Reponse(_Msg(tool_calls=[_appel("label_message", {"messageId": "m1"})])),
        _Reponse(_Msg(content=_synthese_payload())),
    ]


class TestLancerConversation:
    def test_conversation_complete_avec_outils(
        self, registre: RegistreLibelles, meta: Meta
    ) -> None:
        mistral = _FauxMistral(_conversation_ok())
        service = _FauxService()
        client_gmail = ClientGmailAPI(service, dry_run=True)
        synthese, executions = lancer_conversation(
            AGENT_CLASSIFICATION,
            "is:unread",
            meta,
            client_mistral=mistral,  # type: ignore[arg-type]
            client_gmail=client_gmail,
            registre=registre,
        )
        assert synthese.statut == "synthese"
        assert len(executions) == 3
        assert len(mistral.chat.appels) == 4
        assert mistral.chat.appels[0]["temperature"] == 0.0
        assert mistral.chat.appels[0]["response_format"].type == "json_schema"
        assert service.appels == ["threads.list", "threads.get"]  # dry-run : pas de modify

    def test_rejet_synthese_non_authentique(
        self, registre: RegistreLibelles, meta: Meta
    ) -> None:
        reponses = _conversation_ok()
        reponses[-1] = _Reponse(_Msg(content=_synthese_payload(message_id="m-inconnu")))
        mistral = _FauxMistral(reponses)
        client_gmail = ClientGmailAPI(_FauxService(), dry_run=True)
        with pytest.raises(SyntheseInvalideError, match="non manipulés"):
            lancer_conversation(
                AGENT_CLASSIFICATION,
                "is:unread",
                meta,
                client_mistral=mistral,  # type: ignore[arg-type]
                client_gmail=client_gmail,
                registre=registre,
            )

    def test_garde_fou_anti_boucle(self, registre: RegistreLibelles, meta: Meta) -> None:
        reponses = [_Reponse(_Msg(tool_calls=[_appel("search_threads", {"query": "q"})]))]
        mistral = _FauxMistral(reponses)

        class _ChatInfini(_FauxChat):
            def complete(self, **kwargs: Any) -> _Reponse:
                self.appels.append(kwargs)
                return _Reponse(_Msg(tool_calls=[_appel("search_threads", {"query": "q"})]))

        mistral.chat = _ChatInfini([])  # type: ignore[assignment]
        client_gmail = ClientGmailAPI(_FauxService(), dry_run=True)
        with pytest.raises(GardeFouAtteintError, match="anti-boucle"):
            lancer_conversation(
                AGENT_CLASSIFICATION,
                "q",
                meta,
                client_mistral=mistral,  # type: ignore[arg-type]
                client_gmail=client_gmail,
                registre=registre,
                plafond_appels=2,
            )

    def test_tool_calls_reels_form_toolcall(
        self, registre: RegistreLibelles, meta: Meta
    ) -> None:
        """Régression : l'API renvoie des ToolCall (function.name/arguments), pas des
        ToolExecutionEntry — la boucle doit fonctionner et C3 doit voir les ids."""
        scenario = [
            _Reponse(_Msg(tool_calls=[_appel_reel("search_threads", {"query": "is:unread"})])),
            _Reponse(_Msg(tool_calls=[_appel_reel("get_thread", {"threadId": "t1"})])),
            _Reponse(_Msg(tool_calls=[_appel_reel("get_message", {"messageId": "m1"})])),
            _Reponse(_Msg(content=_synthese_payload())),
        ]
        mistral = _FauxMistral(scenario)
        service = _FauxService()
        service.appels = []
        client_gmail = ClientGmailAPI(service, dry_run=True)
        synthese, executions = lancer_conversation(
            AGENT_CLASSIFICATION,
            "is:unread",
            meta,
            client_mistral=mistral,  # type: ignore[arg-type]
            client_gmail=client_gmail,
            registre=registre,
        )
        assert synthese.statut == "synthese"
        assert len(executions) == 3
        assert all(e.type == "function.call" for e in executions)
        assert service.appels == ["threads.list", "threads.get", "messages.get"]

    def test_agent_sans_prompt(self, registre: RegistreLibelles, meta: Meta) -> None:
        mistral = _FauxMistral([])
        client_gmail = ClientGmailAPI(_FauxService(), dry_run=True)
        with pytest.raises(AgentInconnuError, match="sans prompt"):
            lancer_conversation(
                "agent-inconnu",
                "q",
                meta,
                client_mistral=mistral,  # type: ignore[arg-type]
                client_gmail=client_gmail,
                registre=registre,
            )


class TestExecuterOutil:
    def test_outil_inconnu(self) -> None:
        client_gmail = ClientGmailAPI(_FauxService(), dry_run=True)
        with pytest.raises(ValueError, match="outil inconnu"):
            executer_outil("envoyer_email", {}, client_gmail)

    def test_search_threads(self) -> None:
        service = _FauxService()
        client_gmail = ClientGmailAPI(service, dry_run=True)
        resultat = executer_outil("search_threads", {"query": "is:unread"}, client_gmail)
        assert resultat == {"threads": ["t1"]}
        assert service.appels == ["threads.list"]

    def test_label_message_dry_run_non_execute(self) -> None:
        service = _FauxService()
        client_gmail = ClientGmailAPI(service, dry_run=True)
        resultat = executer_outil(
            "label_message", {"messageId": "m1", "addLabelIds": ["L1"]}, client_gmail
        )
        assert resultat == {"ok": True, "messageId": "m1"}
        assert "messages.modify" not in service.appels

    def test_label_message_reel(self) -> None:
        service = _FauxService()
        client_gmail = ClientGmailAPI(service, dry_run=False)
        executer_outil(
            "label_message",
            {"messageId": "m1", "addLabelIds": ["L1"], "removeLabelIds": ["L2"]},
            client_gmail,
        )
        assert service.appels == ["messages.modify"]


class TestApercuBorne:
    def test_corps_tronque_et_empreinte_fournie(self) -> None:
        from agents import LIMITE_CORPS_APERCU, _apercu_message

        corps_long = "x" * (LIMITE_CORPS_APERCU + 500)
        import base64 as _b64

        message = {
            "id": "m1",
            "threadId": "t1",
            "payload": {
                "mimeType": "text/plain",
                "headers": [
                    {"name": "Message-ID", "value": "<a@b.fr>"},
                    {"name": "Subject", "value": "S"},
                    {"name": "From", "value": "e@x.fr"},
                ],
                "body": {
                    "data": _b64.urlsafe_b64encode(corps_long.encode()).decode().rstrip("=")
                },
            },
        }
        apercu = _apercu_message(message)
        assert len(apercu["corps"]) <= LIMITE_CORPS_APERCU + len("…[tronqué]")
        assert apercu["corps"].endswith("…[tronqué]")
        assert apercu["message_id_rfc"] == "a@b.fr"
        assert len(apercu["empreinte"]) == 64
        assert set(apercu["entetes"]) == {"Message-ID", "Subject", "From"}

    def test_borner_reponse(self) -> None:
        from agents import LIMITE_REPONSE_OUTIL, _borner_reponse

        texte = _borner_reponse({"data": "y" * (LIMITE_REPONSE_OUTIL + 100)})
        assert len(texte) <= LIMITE_REPONSE_OUTIL + len('…["tronqué"]')


class TestNormaliserPayload:
    def test_enveloppe_deja_conforme(self) -> None:
        from agents import _normaliser_payload

        assert _normaliser_payload({"statut": "synthese", "messages": []}) == {
            "statut": "synthese",
            "messages": [],
        }

    def test_objet_message_nu_enveloppe(self) -> None:
        from agents import _normaliser_payload

        msg = {"id": "m1", "objet": "S", "expediteur": "e@x.fr", "motif": "m"}
        assert _normaliser_payload(msg) == {"statut": "synthese", "messages": [msg]}

    def test_liste_enveloppee(self) -> None:
        from agents import _normaliser_payload

        msgs = [{"id": "m1", "objet": "S"}]
        assert _normaliser_payload(msgs) == {"statut": "synthese", "messages": msgs}

    def test_payload_inattendu_rejete(self) -> None:
        from agents import _normaliser_payload
        from validation import SyntheseInvalideError

        with pytest.raises(SyntheseInvalideError, match="inattendu"):
            _normaliser_payload({"foo": "bar"})


class TestCompletudeLecture:
    def test_synthese_refusee_tant_que_threads_non_lus(
        self, registre: RegistreLibelles, meta: Meta
    ) -> None:
        """search_threads renvoie 2 threads ; la 1re synthèse (1 thread lu) est
        refusée, la boucle continue jusqu'à lecture complète."""
        scenario = [
            _Reponse(_Msg(tool_calls=[_appel("search_threads", {"query": "is:unread"})])),
            _Reponse(_Msg(tool_calls=[_appel("get_thread", {"threadId": "t1"})])),
            _Reponse(_Msg(content=_synthese_payload())),  # synthèse prématurée -> refusée
            _Reponse(_Msg(tool_calls=[_appel("get_thread", {"threadId": "t2"})])),
            _Reponse(_Msg(tool_calls=[_appel("get_message", {"messageId": "m1"})])),
            _Reponse(_Msg(content=_synthese_payload())),  # synthèse complète -> acceptée
        ]
        mistral = _FauxMistral(scenario)
        service = _FauxService(threads=["t1", "t2"])
        client_gmail = ClientGmailAPI(service, dry_run=True)
        synthese, _ = lancer_conversation(
            AGENT_CLASSIFICATION,
            "is:unread",
            meta,
            client_mistral=mistral,  # type: ignore[arg-type]
            client_gmail=client_gmail,
            registre=registre,
        )
        assert synthese.statut == "synthese"
        assert "threads.get" in service.appels
