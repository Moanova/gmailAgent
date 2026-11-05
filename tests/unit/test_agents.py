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
from contracts import (
    AGENT_CLASSIFICATION,
    AGENT_SPAM,
    AGENT_SUPPRESSION,
    AgentInconnuError,
    Meta,
    SyntheseSpam,
    SyntheseSuppression,
)
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


@pytest.fixture
def meta_spam(meta: Meta) -> Meta:
    return Meta(run_id=meta.run_id, etape="lecture_spam", agent=AGENT_SPAM)


@pytest.fixture
def meta_suppression(meta: Meta) -> Meta:
    return Meta(run_id=meta.run_id, etape="lecture_suppression", agent=AGENT_SUPPRESSION)


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
        mid = "m1" if id == "t1" else f"m-{id}"
        return _Requete({"id": id, "messages": [{"id": mid}]})


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
        from agents import _apercu_message
        from config import parametres_courants

        limite_corps = parametres_courants().limites.limite_corps_apercu
        corps_long = "x" * (limite_corps + 500)
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
        assert len(apercu["corps"]) <= limite_corps + len("…[tronqué]")
        assert apercu["corps"].endswith("…[tronqué]")
        assert apercu["message_id_rfc"] == "a@b.fr"
        assert len(apercu["empreinte"]) == 64
        assert set(apercu["entetes"]) == {"Message-ID", "Subject", "From"}

    def test_borner_reponse(self) -> None:
        from agents import _borner_reponse
        from config import parametres_courants

        limite = parametres_courants().limites.limite_reponse_outil
        texte = _borner_reponse({"data": "y" * (limite + 100)})
        assert len(texte) <= limite + len('…["tronqué"]')


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


def _payload_classification(messages: list[dict[str, str]]) -> str:
    return json.dumps({"statut": "synthese", "messages": messages})


def _msg_classifie(mid: str, cat: str = "classification.information") -> dict[str, str]:
    return {
        "id": mid,
        "objet": f"S-{mid}",
        "expediteur": "e@x.fr",
        "motif": "m",
        "categorie": cat,
        "urgence": "basse",
        "message_id_rfc": f"{mid}@x.fr",
        "empreinte": "a" * 64,
    }


def _msg_spam(mid: str) -> dict[str, str]:
    return {
        "id": mid,
        "objet": f"S-{mid}",
        "expediteur": "e@x.fr",
        "motif": "newsletter connue",
    }


def _payload_spam(statut: str = "deplaces", ids: list[str] | None = None) -> str:
    messages = [_msg_spam(i) for i in (ids or [])]
    return json.dumps({"statut": statut, "messages": messages})


def _payload_suppression(statut: str = "supprimes", ids: list[str] | None = None) -> str:
    ids = ids or []
    return json.dumps({"statut": statut, "count": len(ids), "ids": ids})


class TestCompletudeLecture:
    def test_synthese_refusee_tant_que_threads_non_lus(
        self, registre: RegistreLibelles, meta: Meta
    ) -> None:
        """search renvoie t1,t2 ; synthèse après lecture de t1 seul -> refusée,
        puis acceptée après lecture de t2 et get_message des 2 messages."""
        scenario = [
            _Reponse(_Msg(tool_calls=[_appel("search_threads", {"query": "is:unread"})])),
            _Reponse(_Msg(tool_calls=[_appel("get_thread", {"threadId": "t1"})])),
            _Reponse(
                _Msg(
                    tool_calls=[
                        _appel("get_message", {"messageId": "m1"}),
                        _appel("get_thread", {"threadId": "t2"}),
                    ]
                )
            ),
            _Reponse(_Msg(content=_payload_classification([_msg_classifie("m1")]))),
            _Reponse(_Msg(tool_calls=[_appel("get_message", {"messageId": "m-t2"})])),
            _Reponse(
                _Msg(
                    content=_payload_classification(
                        [_msg_classifie("m1"), _msg_classifie("m-t2")]
                    )
                )
            ),
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
        assert len(synthese.messages) == 2


class TestCompletudeMessages:
    def test_synthese_refusee_si_message_lu_non_classe(
        self, registre: RegistreLibelles, meta: Meta
    ) -> None:
        """t1 et t2 lus, m1 et m-t2 lus via get_message ; synthèse ne couvrant que m1
        -> refusée (garde message), puis acceptée avec les deux."""
        scenario = [
            _Reponse(_Msg(tool_calls=[_appel("search_threads", {"query": "is:unread"})])),
            _Reponse(
                _Msg(
                    tool_calls=[
                        _appel("get_thread", {"threadId": "t1"}),
                        _appel("get_thread", {"threadId": "t2"}),
                        _appel("get_message", {"messageId": "m1"}),
                        _appel("get_message", {"messageId": "m-t2"}),
                    ]
                )
            ),
            _Reponse(_Msg(content=_payload_classification([_msg_classifie("m1")]))),
            _Reponse(
                _Msg(
                    content=_payload_classification(
                        [_msg_classifie("m1"), _msg_classifie("m-t2")]
                    )
                )
            ),
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
        assert len(synthese.messages) == 2


class TestLimiteTentativesSynthese:
    def test_abandon_apres_3_refus(self, registre: RegistreLibelles, meta: Meta) -> None:
        """Le modèle produit indéfiniment une synthèse incomplète -> abandon propre
        après max_tentatives_synthese refus (pas de boucle infinie)."""
        from config import parametres_courants

        scenario = [
            _Reponse(_Msg(tool_calls=[_appel("search_threads", {"query": "is:unread"})])),
            _Reponse(
                _Msg(
                    tool_calls=[
                        _appel("get_thread", {"threadId": "t1"}),
                        _appel("get_thread", {"threadId": "t2"}),
                        _appel("get_message", {"messageId": "m1"}),
                        _appel("get_message", {"messageId": "m-t2"}),
                    ]
                )
            ),
        ]
        scenario += [
            _Reponse(_Msg(content=_payload_classification([_msg_classifie("m1")])))
            for _ in range(parametres_courants().limites.max_tentatives_synthese + 2)
        ]
        mistral = _FauxMistral(scenario)
        service = _FauxService(threads=["t1", "t2"])
        client_gmail = ClientGmailAPI(service, dry_run=True)
        with pytest.raises(SyntheseInvalideError, match="abandon du run"):
            lancer_conversation(
                AGENT_CLASSIFICATION,
                "is:unread",
                meta,
                client_mistral=mistral,  # type: ignore[arg-type]
                client_gmail=client_gmail,
                registre=registre,
            )
        tentatives = parametres_courants().limites.max_tentatives_synthese
        assert len(mistral.chat.appels) == 2 + tentatives + 1


class TestMaxTokens:
    def test_max_tokens_releve_pour_grandes_syntheses(
        self, registre: RegistreLibelles, meta: Meta
    ) -> None:
        """max_tokens par défaut relevé à 8000 (incident réel 04/11 : synthèse tronquée
        à 4000 sur ~50 messages, garde de complétude puis abandon du run)."""
        from config import parametres_courants

        mistral = _FauxMistral(
            [
                _Reponse(_Msg(tool_calls=[_appel("search_threads", {"query": "is:unread"})])),
                _Reponse(_Msg(content='{"statut": "aucun_message", "messages": []}')),
            ]
        )
        client_gmail = ClientGmailAPI(_FauxService(threads=[]), dry_run=True)
        lancer_conversation(
            AGENT_CLASSIFICATION,
            "is:unread",
            meta,
            client_mistral=mistral,  # type: ignore[arg-type]
            client_gmail=client_gmail,
            registre=registre,
        )
        assert parametres_courants().limites.max_tokens == 8000
        assert mistral.chat.appels[0]["max_tokens"] == 8000


class TestModele:
    def _conversation_vide(self) -> list[_Reponse]:
        return [
            _Reponse(_Msg(tool_calls=[_appel("search_threads", {"query": "is:unread"})])),
            _Reponse(_Msg(content='{"statut": "aucun_message", "messages": []}')),
        ]

    def _lancer(
        self,
        registre: RegistreLibelles,
        meta: Meta,
        mistral: _FauxMistral,
        **kwargs: Any,
    ) -> None:
        client_gmail = ClientGmailAPI(_FauxService(threads=[]), dry_run=True)
        lancer_conversation(
            AGENT_CLASSIFICATION,
            "is:unread",
            meta,
            client_mistral=mistral,  # type: ignore[arg-type]
            client_gmail=client_gmail,
            registre=registre,
            **kwargs,
        )

    def test_modele_par_defaut_est_small(
        self, registre: RegistreLibelles, meta: Meta, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from agents import modele_effectif
        from config import parametres_courants

        monkeypatch.delenv("MISTRAL_MODEL", raising=False)
        assert parametres_courants().modele.defaut == "mistral-small-latest"
        assert modele_effectif(None) == "mistral-small-latest"
        mistral = _FauxMistral(self._conversation_vide())
        self._lancer(registre, meta, mistral)
        assert mistral.chat.appels[0]["model"] == "mistral-small-latest"

    def test_modele_surcharge_par_env(
        self, registre: RegistreLibelles, meta: Meta, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from agents import modele_effectif

        monkeypatch.setenv("MISTRAL_MODEL", "mistral-large-4")
        assert modele_effectif(None) == "mistral-large-4"
        mistral = _FauxMistral(self._conversation_vide())
        self._lancer(registre, meta, mistral)
        assert mistral.chat.appels[0]["model"] == "mistral-large-4"

    def test_modele_explicite_prioritaire_sur_env(
        self, registre: RegistreLibelles, meta: Meta, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from agents import modele_effectif

        monkeypatch.setenv("MISTRAL_MODEL", "mistral-large-4")
        assert modele_effectif("mistral-small-latest") == "mistral-small-latest"
        mistral = _FauxMistral(self._conversation_vide())
        self._lancer(registre, meta, mistral, modele="mistral-small-latest")
        assert mistral.chat.appels[0]["model"] == "mistral-small-latest"


class TestGardeRequete:
    def test_requete_modifiee_abandon_propre(
        self, registre: RegistreLibelles, meta: Meta
    ) -> None:
        """Garde de périmètre : search_threads avec une requête différente de celle
        fournie par l'orchestrateur -> abandon propre, aucun outil exécuté."""
        mistral = _FauxMistral(
            [_Reponse(_Msg(tool_calls=[_appel("search_threads", {"query": "older_than:24h"})]))]
        )
        service = _FauxService()
        client_gmail = ClientGmailAPI(service, dry_run=True)
        with pytest.raises(SyntheseInvalideError, match="requête de recherche modifiée"):
            lancer_conversation(
                AGENT_CLASSIFICATION,
                "is:unread",
                meta,
                client_mistral=mistral,  # type: ignore[arg-type]
                client_gmail=client_gmail,
                registre=registre,
            )
        assert service.appels == []

    def test_requete_conforme_executee(
        self, registre: RegistreLibelles, meta: Meta
    ) -> None:
        mistral = _FauxMistral(
            [
                _Reponse(_Msg(tool_calls=[_appel("search_threads", {"query": "is:unread"})])),
                _Reponse(_Msg(content='{"statut": "aucun_message", "messages": []}')),
            ]
        )
        client_gmail = ClientGmailAPI(_FauxService(threads=[]), dry_run=True)
        synthese, _ = lancer_conversation(
            AGENT_CLASSIFICATION,
            "is:unread",
            meta,
            client_mistral=mistral,  # type: ignore[arg-type]
            client_gmail=client_gmail,
            registre=registre,
        )
        assert synthese.statut == "aucun_message"

    def test_arguments_outils_journalises(
        self,
        registre: RegistreLibelles,
        meta: Meta,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import journalisation

        monkeypatch.setenv("LOG_FILE", str(tmp_path / "gmailagent.log"))
        monkeypatch.setattr(journalisation, "_configure", False)
        monkeypatch.setattr(journalisation, "_run_id_courant", None)
        journalisation.configurer(str(meta.run_id))
        mistral = _FauxMistral(
            [
                _Reponse(_Msg(tool_calls=[_appel("search_threads", {"query": "is:unread"})])),
                _Reponse(_Msg(content='{"statut": "aucun_message", "messages": []}')),
            ]
        )
        client_gmail = ClientGmailAPI(_FauxService(threads=[]), dry_run=True)
        lancer_conversation(
            AGENT_CLASSIFICATION,
            "is:unread",
            meta,
            client_mistral=mistral,  # type: ignore[arg-type]
            client_gmail=client_gmail,
            registre=registre,
        )
        lignes = [
            json.loads(ligne)
            for ligne in (tmp_path / "gmailagent.log").read_text(encoding="utf-8").splitlines()
            if ligne.strip()
        ]
        outils = [ligne for ligne in lignes if ligne.get("event") == "outil execute"]
        assert outils
        assert any("is:unread" in str(ligne.get("args", "")) for ligne in outils)


class TestBornageParRun:
    def test_search_threads_borne_a_25(self) -> None:
        from agents import executer_outil
        from config import parametres_courants

        class _ServiceLarges:
            def users(self) -> "_ServiceLarges":
                return self

            def threads(self) -> "_ServiceLarges":
                return self

            def list(self, userId: str, q: str, maxResults: int) -> "_Requete":
                assert maxResults == parametres_courants().limites.max_threads_par_run
                return _Requete({"threads": [{"id": f"t{i}"} for i in range(50)]})

        client_gmail = ClientGmailAPI(_ServiceLarges(), dry_run=True)
        args = {"query": "is:unread", "maxResults": 50}
        resultat = executer_outil("search_threads", args, client_gmail)
        assert parametres_courants().limites.max_threads_par_run == 25
        # le plafond porte sur maxResults passé au service (25), pas sur la réponse
        assert len(resultat["threads"]) == 50

    def test_prompt_distinction_id_vs_rfc(self, registre: RegistreLibelles) -> None:
        from prompts import prompt_classification

        prompt = prompt_classification(registre)
        assert "jamais le Message-ID RFC" in prompt
        assert "identifiant Gmail hexadécimal" in prompt


class TestIdsResultats:
    def test_id_lu_via_resultat_get_thread_accepte(
        self, registre: RegistreLibelles, meta: Meta
    ) -> None:
        """Un thread contenant 2 messages : get_thread(t1) renvoie m1 et m2 ; la synthèse
        citant m2 (présent uniquement dans le RÉSULTAT, pas dans les args) doit être
        acceptée par C3 (le message a réellement été lu)."""

        class _ServiceMulti:
            def users(self) -> "_ServiceMulti":
                return self

            def threads(self) -> "_ServiceMulti":
                return self

            def messages(self) -> "_ServiceMulti":
                return self

            def list(self, userId: str, q: str, maxResults: int) -> _Requete:
                return _Requete({"threads": [{"id": "t1"}]})

            def get(self, userId: str, id: str) -> _Requete:
                return _Requete(
                    {"id": id, "messages": [{"id": "m1"}, {"id": "m2"}]}
                )

            def execute(self) -> dict[str, object]:
                return {}

        scenario = [
            _Reponse(_Msg(tool_calls=[_appel("search_threads", {"query": "is:unread"})])),
            _Reponse(_Msg(tool_calls=[_appel("get_thread", {"threadId": "t1"})])),
            _Reponse(
                _Msg(
                    content=_payload_classification(
                        [_msg_classifie("m1"), _msg_classifie("m2")]
                    )
                )
            ),
        ]
        mistral = _FauxMistral(scenario)
        client_gmail = ClientGmailAPI(_ServiceMulti(), dry_run=True)
        synthese, _ = lancer_conversation(
            AGENT_CLASSIFICATION,
            "is:unread",
            meta,
            client_mistral=mistral,  # type: ignore[arg-type]
            client_gmail=client_gmail,
            registre=registre,
        )
        assert len(synthese.messages) == 2


class TestPromptAgents:
    def test_prompt_spam_selectionne(self, registre: RegistreLibelles) -> None:
        from agents import _prompt_systeme

        prompt = _prompt_systeme(AGENT_SPAM, registre)
        assert "in:spam" in prompt
        assert "suivi.valide-spam" in prompt
        assert "Agent/" not in prompt

    def test_prompt_suppression_selectionne(self, registre: RegistreLibelles) -> None:
        from agents import _prompt_systeme

        prompt = _prompt_systeme(AGENT_SUPPRESSION, registre)
        assert "TRASH" in prompt
        assert "suivi.traite" in prompt
        assert "suivi.doublon" in prompt
        assert "Agent/" not in prompt


class TestConversationSpam:
    def test_conversation_spam_complete(
        self, registre: RegistreLibelles, meta_spam: Meta
    ) -> None:
        scenario = [
            _Reponse(_Msg(tool_calls=[_appel("search_threads", {"query": "in:spam"})])),
            _Reponse(_Msg(tool_calls=[_appel("get_thread", {"threadId": "t1"})])),
            _Reponse(_Msg(content=_payload_spam("deplaces", ["m1"]))),
        ]
        mistral = _FauxMistral(scenario)
        client_gmail = ClientGmailAPI(_FauxService(threads=["t1"]), dry_run=True)
        synthese, executions = lancer_conversation(
            AGENT_SPAM,
            "in:spam",
            meta_spam,
            client_mistral=mistral,  # type: ignore[arg-type]
            client_gmail=client_gmail,
            registre=registre,
        )
        assert isinstance(synthese, SyntheseSpam)
        assert synthese.statut == "deplaces"
        assert [m.id for m in synthese.messages] == ["m1"]
        assert len(executions) == 2
        appel0 = mistral.chat.appels[0]
        assert appel0["response_format"].json_schema.name == "SyntheseSpam"
        assert "in:spam" in appel0["messages"][0].content

    def test_aucun_message_spam_accepte(
        self, registre: RegistreLibelles, meta_spam: Meta
    ) -> None:
        scenario = [
            _Reponse(_Msg(tool_calls=[_appel("search_threads", {"query": "in:spam"})])),
            _Reponse(_Msg(content=_payload_spam("aucun_message", []))),
        ]
        mistral = _FauxMistral(scenario)
        client_gmail = ClientGmailAPI(_FauxService(threads=[]), dry_run=True)
        synthese, _ = lancer_conversation(
            AGENT_SPAM,
            "in:spam",
            meta_spam,
            client_mistral=mistral,  # type: ignore[arg-type]
            client_gmail=client_gmail,
            registre=registre,
        )
        assert synthese.statut == "aucun_message"
        assert synthese.messages == []

    def test_message_lu_non_retenu_accepte_pour_spam(
        self, registre: RegistreLibelles, meta_spam: Meta
    ) -> None:
        """Contraste avec la classification : pour le spam, un message lu mais laissé
        en spam ne figure pas dans la synthèse — accepté (la garde "messages lus non
        classés" est réservée à la classification)."""
        scenario = [
            _Reponse(_Msg(tool_calls=[_appel("search_threads", {"query": "in:spam"})])),
            _Reponse(
                _Msg(
                    tool_calls=[
                        _appel("get_thread", {"threadId": "t1"}),
                        _appel("get_thread", {"threadId": "t2"}),
                    ]
                )
            ),
            _Reponse(_Msg(content=_payload_spam("deplaces", ["m1"]))),
        ]
        mistral = _FauxMistral(scenario)
        client_gmail = ClientGmailAPI(_FauxService(threads=["t1", "t2"]), dry_run=True)
        synthese, _ = lancer_conversation(
            AGENT_SPAM,
            "in:spam",
            meta_spam,
            client_mistral=mistral,  # type: ignore[arg-type]
            client_gmail=client_gmail,
            registre=registre,
        )
        assert [m.id for m in synthese.messages] == ["m1"]

    def test_garde_threads_active_pour_spam(
        self, registre: RegistreLibelles, meta_spam: Meta
    ) -> None:
        """Tout thread retourné par search_threads doit être lu via get_thread, même
        pour le spam : synthèse après lecture de t1 seul -> refusée, puis acceptée
        après lecture de t2."""
        scenario = [
            _Reponse(_Msg(tool_calls=[_appel("search_threads", {"query": "in:spam"})])),
            _Reponse(_Msg(tool_calls=[_appel("get_thread", {"threadId": "t1"})])),
            _Reponse(_Msg(content=_payload_spam("deplaces", ["m1"]))),
            _Reponse(_Msg(tool_calls=[_appel("get_thread", {"threadId": "t2"})])),
            _Reponse(_Msg(content=_payload_spam("deplaces", ["m1", "m-t2"]))),
        ]
        mistral = _FauxMistral(scenario)
        client_gmail = ClientGmailAPI(_FauxService(threads=["t1", "t2"]), dry_run=True)
        synthese, _ = lancer_conversation(
            AGENT_SPAM,
            "in:spam",
            meta_spam,
            client_mistral=mistral,  # type: ignore[arg-type]
            client_gmail=client_gmail,
            registre=registre,
        )
        assert synthese.statut == "deplaces"
        assert len(synthese.messages) == 2

    def test_rejet_id_inconnu_spam(
        self, registre: RegistreLibelles, meta_spam: Meta
    ) -> None:
        scenario = [
            _Reponse(_Msg(tool_calls=[_appel("search_threads", {"query": "in:spam"})])),
            _Reponse(_Msg(tool_calls=[_appel("get_thread", {"threadId": "t1"})])),
            _Reponse(_Msg(content=_payload_spam("deplaces", ["m-inconnu"]))),
        ]
        mistral = _FauxMistral(scenario)
        client_gmail = ClientGmailAPI(_FauxService(threads=["t1"]), dry_run=True)
        with pytest.raises(SyntheseInvalideError, match="non manipul"):
            lancer_conversation(
                AGENT_SPAM,
                "in:spam",
                meta_spam,
                client_mistral=mistral,  # type: ignore[arg-type]
                client_gmail=client_gmail,
                registre=registre,
            )


REQUETE_SUPPRESSION = (
    'label:"Agent/traité" label:"Agent/notification" older_than:24h '
    'OR label:"Agent/doublon"'
)


class TestConversationSuppression:
    def test_conversation_suppression_complete(
        self, registre: RegistreLibelles, meta_suppression: Meta
    ) -> None:
        scenario = [
            _Reponse(_Msg(tool_calls=[_appel("search_threads", {"query": REQUETE_SUPPRESSION})])),
            _Reponse(_Msg(tool_calls=[_appel("get_thread", {"threadId": "t1"})])),
            _Reponse(
                _Msg(
                    tool_calls=[
                        _appel("label_message", {"messageId": "m1", "addLabelIds": ["TRASH"]})
                    ]
                )
            ),
            _Reponse(_Msg(content=_payload_suppression("supprimes", ["m1"]))),
        ]
        mistral = _FauxMistral(scenario)
        service = _FauxService(threads=["t1"])
        client_gmail = ClientGmailAPI(service, dry_run=True)
        synthese, executions = lancer_conversation(
            AGENT_SUPPRESSION,
            REQUETE_SUPPRESSION,
            meta_suppression,
            client_mistral=mistral,  # type: ignore[arg-type]
            client_gmail=client_gmail,
            registre=registre,
        )
        assert isinstance(synthese, SyntheseSuppression)
        assert synthese.statut == "supprimes"
        assert synthese.count == 1
        assert synthese.ids == ["m1"]
        assert any(e.name == "label_message" for e in executions)
        assert "messages.modify" not in service.appels  # dry-run : journalisé, non exécuté
        appel0 = mistral.chat.appels[0]
        assert appel0["response_format"].json_schema.name == "SyntheseSuppression"
        assert REQUETE_SUPPRESSION in appel0["messages"][1].content

    def test_aucun_message_suppression_accepte(
        self, registre: RegistreLibelles, meta_suppression: Meta
    ) -> None:
        scenario = [
            _Reponse(_Msg(tool_calls=[_appel("search_threads", {"query": REQUETE_SUPPRESSION})])),
            _Reponse(_Msg(content=_payload_suppression("aucun_message", []))),
        ]
        mistral = _FauxMistral(scenario)
        client_gmail = ClientGmailAPI(_FauxService(threads=[]), dry_run=True)
        synthese, executions = lancer_conversation(
            AGENT_SUPPRESSION,
            REQUETE_SUPPRESSION,
            meta_suppression,
            client_mistral=mistral,  # type: ignore[arg-type]
            client_gmail=client_gmail,
            registre=registre,
        )
        assert isinstance(synthese, SyntheseSuppression)
        assert synthese.statut == "aucun_message"
        assert synthese.count == 0
        assert synthese.ids == []
        assert not any(e.name == "label_message" for e in executions)

    def test_rejet_c3_id_non_manipule(
        self, registre: RegistreLibelles, meta_suppression: Meta
    ) -> None:
        scenario = [
            _Reponse(_Msg(tool_calls=[_appel("search_threads", {"query": REQUETE_SUPPRESSION})])),
            _Reponse(_Msg(tool_calls=[_appel("get_thread", {"threadId": "t1"})])),
            _Reponse(_Msg(content=_payload_suppression("supprimes", ["m-inconnu"]))),
        ]
        mistral = _FauxMistral(scenario)
        client_gmail = ClientGmailAPI(_FauxService(threads=["t1"]), dry_run=True)
        with pytest.raises(SyntheseInvalideError, match="non manipul"):
            lancer_conversation(
                AGENT_SUPPRESSION,
                REQUETE_SUPPRESSION,
                meta_suppression,
                client_mistral=mistral,  # type: ignore[arg-type]
                client_gmail=client_gmail,
                registre=registre,
            )

    def test_garde_action_ecart_corbeille_ids_refuse_puis_accepte(
        self, registre: RegistreLibelles, meta_suppression: Meta
    ) -> None:
        """m1 est réellement passé à la corbeille (label_message TRASH) mais la synthèse
        cite m-t2 (réel mais non trashé) : refus, puis accepté après correction."""
        scenario = [
            _Reponse(_Msg(tool_calls=[_appel("search_threads", {"query": REQUETE_SUPPRESSION})])),
            _Reponse(
                _Msg(
                    tool_calls=[
                        _appel("get_thread", {"threadId": "t1"}),
                        _appel("get_thread", {"threadId": "t2"}),
                        _appel("label_message", {"messageId": "m1", "addLabelIds": ["TRASH"]}),
                    ]
                )
            ),
            _Reponse(_Msg(content=_payload_suppression("supprimes", ["m-t2"]))),
            _Reponse(_Msg(content=_payload_suppression("supprimes", ["m1"]))),
        ]
        mistral = _FauxMistral(scenario)
        client_gmail = ClientGmailAPI(_FauxService(threads=["t1", "t2"]), dry_run=True)
        synthese, _ = lancer_conversation(
            AGENT_SUPPRESSION,
            REQUETE_SUPPRESSION,
            meta_suppression,
            client_mistral=mistral,  # type: ignore[arg-type]
            client_gmail=client_gmail,
            registre=registre,
        )
        assert isinstance(synthese, SyntheseSuppression)
        assert synthese.ids == ["m1"]

    def test_abandon_apres_ecarts_action_persistants(
        self, registre: RegistreLibelles, meta_suppression: Meta
    ) -> None:
        """La synthèse ne correspond jamais aux mises à la corbeille réelles -> abandon
        propre après max_tentatives_synthese refus (pas de boucle infinie)."""
        from config import parametres_courants

        scenario = [
            _Reponse(_Msg(tool_calls=[_appel("search_threads", {"query": REQUETE_SUPPRESSION})])),
            _Reponse(
                _Msg(
                    tool_calls=[
                        _appel("get_thread", {"threadId": "t1"}),
                        _appel("get_thread", {"threadId": "t2"}),
                        _appel("label_message", {"messageId": "m1", "addLabelIds": ["TRASH"]}),
                    ]
                )
            ),
        ]
        scenario += [
            _Reponse(_Msg(content=_payload_suppression("supprimes", ["m-t2"])))
            for _ in range(parametres_courants().limites.max_tentatives_synthese + 2)
        ]
        mistral = _FauxMistral(scenario)
        client_gmail = ClientGmailAPI(_FauxService(threads=["t1", "t2"]), dry_run=True)
        with pytest.raises(SyntheseInvalideError, match="abandon du run"):
            lancer_conversation(
                AGENT_SUPPRESSION,
                REQUETE_SUPPRESSION,
                meta_suppression,
                client_mistral=mistral,  # type: ignore[arg-type]
                client_gmail=client_gmail,
                registre=registre,
            )
        tentatives = parametres_courants().limites.max_tentatives_synthese
        assert len(mistral.chat.appels) == 2 + tentatives + 1

    def test_garde_threads_active_pour_suppression(
        self, registre: RegistreLibelles, meta_suppression: Meta
    ) -> None:
        """Tout thread retourné par search_threads doit être lu via get_thread, même pour
        la suppression : synthèse après lecture de t1 seul -> refusée, puis acceptée
        après lecture de t2."""
        scenario = [
            _Reponse(_Msg(tool_calls=[_appel("search_threads", {"query": REQUETE_SUPPRESSION})])),
            _Reponse(_Msg(tool_calls=[_appel("get_thread", {"threadId": "t1"})])),
            _Reponse(
                _Msg(
                    tool_calls=[
                        _appel("label_message", {"messageId": "m1", "addLabelIds": ["TRASH"]})
                    ]
                )
            ),
            _Reponse(_Msg(content=_payload_suppression("supprimes", ["m1"]))),
            _Reponse(_Msg(tool_calls=[_appel("get_thread", {"threadId": "t2"})])),
            _Reponse(_Msg(content=_payload_suppression("supprimes", ["m1"]))),
        ]
        mistral = _FauxMistral(scenario)
        client_gmail = ClientGmailAPI(_FauxService(threads=["t1", "t2"]), dry_run=True)
        synthese, _ = lancer_conversation(
            AGENT_SUPPRESSION,
            REQUETE_SUPPRESSION,
            meta_suppression,
            client_mistral=mistral,  # type: ignore[arg-type]
            client_gmail=client_gmail,
            registre=registre,
        )
        assert isinstance(synthese, SyntheseSuppression)
        assert synthese.ids == ["m1"]
