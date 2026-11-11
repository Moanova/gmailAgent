"""Tests d'intégration (T7.4) : agent suppression de bout en bout, Gmail + Mistral mockés.

La pile réelle est exercée (`lancer_run_suppression` -> `agents.lancer_conversation` avec
un faux client Mistral qui rejoue une conversation scénarisée, et un faux service
googleapiclient filtrant la requête de suppression). Aucun appel réseau, aucune écriture
réelle (dry-run) — sauf test explicite en mode réel contre le faux service.
"""

import base64
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from mistralai.client.models import ToolExecutionEntry

from gmailagent.agent_validation import SyntheseInvalideError
from gmailagent.core_config import RegistreLibelles
from gmailagent.gmail_client import ClientGmailAPI
from gmailagent.pipeline_orchestrator import charger_checkpoint, lancer_run_suppression

REQUETE_SUPPRESSION = 'label:"Agent/traité" label:"Agent/notification" older_than:24h'

ETAPES_SUPPRESSION = [
    "demarrage",
    "lecture_suppression",
    "validation_suppression",
    "rapport",
    "fin",
]


def _b64url(texte: str) -> str:
    return base64.urlsafe_b64encode(texte.encode("utf-8")).decode("ascii").rstrip("=")


def _message_gmail(message_id: str, sujet: str = "Message traité") -> dict[str, Any]:
    return {
        "id": message_id,
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {"name": "Message-ID", "value": f"<{message_id}@ex.fr>"},
                {"name": "Subject", "value": sujet},
                {"name": "From", "value": "exp@ex.fr"},
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
    """Faux service googleapiclient : ne sert que la requête de suppression
    (`older_than:24h`) ; les messages sont servis par thread."""

    def __init__(
        self,
        threads_suppression: list[str] | None = None,
        messages: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self.liste_threads_suppression = (
            threads_suppression if threads_suppression is not None else []
        )
        self.messages_par_thread = messages if messages is not None else {}
        self.appels: list[str] = []
        self.queries: list[str] = []
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
                        {"id": "L_notif", "name": "Agent/notification"},
                        {"id": "L_doublon", "name": "Agent/doublon"},
                    ]
                }
            )
        self.queries.append(str(kwargs.get("q", "")))
        assert "older_than:24h" in self.queries[-1]
        assert "Agent/notification" in self.queries[-1]
        return _Requete({"threads": [{"id": t} for t in self.liste_threads_suppression]})

    def get(self, **kwargs: Any) -> _Requete:
        self.appels.append("get")
        identifiant = str(kwargs.get("id", ""))
        message = self.messages_par_thread.get(identifiant) or _message_gmail(f"m-{identifiant}")
        return _Requete({"id": identifiant, "messages": [message]})

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


def _payload_suppression(statut: str, ids: list[str]) -> str:
    return json.dumps({"statut": statut, "count": len(ids), "ids": ids})


def _scenario_suppression(
    threads: list[str],
    ids_trash: list[str],
    ids_synthese: list[str],
    statut: str = "supprimes",
) -> list[_Reponse]:
    scenario = [
        _Reponse(_Msg(tool_calls=[_appel("search_threads", {"query": REQUETE_SUPPRESSION})]))
    ]
    for t in threads:
        scenario.append(_Reponse(_Msg(tool_calls=[_appel("get_thread", {"threadId": t})])))
    for m in ids_trash:
        appel_trash = _appel("label_message", {"messageId": m, "addLabelIds": ["TRASH"]})
        scenario.append(_Reponse(_Msg(tool_calls=[appel_trash])))
    scenario.append(_Reponse(_Msg(content=_payload_suppression(statut, ids_synthese))))
    return scenario


def _scenario_suppression_vide() -> list[_Reponse]:
    return [
        _Reponse(_Msg(tool_calls=[_appel("search_threads", {"query": REQUETE_SUPPRESSION})])),
        _Reponse(_Msg(content=_payload_suppression("aucun_message", []))),
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


def _run_suppression(
    registre: RegistreLibelles,
    tmp_path: Path,
    service: _FauxService,
    mistral: _FauxMistral,
    *,
    run_id: Any = None,
    dry_run: bool = True,
):
    return lancer_run_suppression(
        run_id=run_id,
        dry_run=dry_run,
        client_api=ClientGmailAPI(service, dry_run=dry_run),
        client_mistral=mistral,  # type: ignore[arg-type]
        registre=registre,
        dossier_checkpoints=tmp_path,
    )


class TestAgentSuppressionBoutEnBout:
    def test_supprimes_pose_trash_en_reel(
        self, registre: RegistreLibelles, tmp_path: Path
    ) -> None:
        service = _FauxService(threads_suppression=["t-sup1"])
        mistral = _FauxMistral(_scenario_suppression(["t-sup1"], ["m-t-sup1"], ["m-t-sup1"]))
        rapport = _run_suppression(registre, tmp_path, service, mistral, dry_run=False)
        assert rapport.statut_global == "succes"
        assert rapport.synthese_suppression is not None
        assert rapport.synthese_suppression.statut == "supprimes"
        assert rapport.synthese_suppression.count == 1
        assert rapport.synthese_suppression.ids == ["m-t-sup1"]
        assert rapport.resume is not None
        assert rapport.resume.corbeille == 1
        assert service.modifications == [("m-t-sup1", ["TRASH"], [])]
        assert REQUETE_SUPPRESSION in service.queries[0]
        appel0 = mistral.chat.appels[0]
        assert appel0["response_format"].json_schema.name == "SyntheseSuppression"
        assert "TRASH" in appel0["messages"][0].content
        checkpoint = charger_checkpoint(rapport.meta.run_id, tmp_path)
        assert checkpoint.etapes_validees == ETAPES_SUPPRESSION
        assert checkpoint.syntheses["suppression"].statut == "supprimes"

    def test_supprimes_dry_run_aucune_ecriture(
        self, registre: RegistreLibelles, tmp_path: Path
    ) -> None:
        service = _FauxService(threads_suppression=["t-sup1"])
        mistral = _FauxMistral(_scenario_suppression(["t-sup1"], ["m-t-sup1"], ["m-t-sup1"]))
        rapport = _run_suppression(registre, tmp_path, service, mistral, dry_run=True)
        assert rapport.statut_global == "succes"
        assert rapport.synthese_suppression is not None
        assert rapport.synthese_suppression.ids == ["m-t-sup1"]
        assert service.modifications == []
        assert "modify" not in service.appels

    def test_synthese_rejetee_c3_arrete_proprement(
        self, registre: RegistreLibelles, tmp_path: Path
    ) -> None:
        rid = uuid4()
        service = _FauxService(threads_suppression=["t-sup1"])
        from gmailagent.core_config import parametres_courants

        scenario = _scenario_suppression(["t-sup1"], ["m-t-sup1"], ["m-inconnu"])
        scenario += [scenario[-1]] * (
            parametres_courants().limites.max_tentatives_synthese + 2
        )
        mistral = _FauxMistral(scenario)
        with pytest.raises(SyntheseInvalideError, match="non manipul"):
            _run_suppression(registre, tmp_path, service, mistral, run_id=rid, dry_run=True)
        checkpoint = charger_checkpoint(rid, tmp_path)
        assert checkpoint.rapport is not None
        assert checkpoint.rapport.statut_global == "echec_partiel"
        assert checkpoint.rapport.etape_fautive == "lecture_suppression"

    def test_garde_action_ecart_corbeille_ids_refuse_puis_accepte(
        self, registre: RegistreLibelles, tmp_path: Path
    ) -> None:
        service = _FauxService(
            threads_suppression=["t-sup1", "t-sup2"],
            messages={
                "t-sup1": _message_gmail("m-sup1"),
                "t-sup2": _message_gmail("m-sup2"),
            },
        )
        scenario = _scenario_suppression(["t-sup1", "t-sup2"], ["m-sup1"], ["m-sup2"])
        scenario.append(_Reponse(_Msg(content=_payload_suppression("supprimes", ["m-sup1"]))))
        mistral = _FauxMistral(scenario)
        rapport = _run_suppression(registre, tmp_path, service, mistral, dry_run=False)
        assert rapport.statut_global == "succes"
        assert rapport.synthese_suppression is not None
        assert rapport.synthese_suppression.ids == ["m-sup1"]
        assert service.modifications == [("m-sup1", ["TRASH"], [])]

    def test_aucun_message(
        self, registre: RegistreLibelles, tmp_path: Path
    ) -> None:
        service = _FauxService(threads_suppression=[])
        mistral = _FauxMistral(_scenario_suppression_vide())
        rapport = _run_suppression(registre, tmp_path, service, mistral, dry_run=True)
        assert rapport.statut_global == "succes"
        assert rapport.synthese_suppression is not None
        assert rapport.synthese_suppression.statut == "aucun_message"
        assert rapport.synthese_suppression.count == 0
        assert service.modifications == []

    def test_idempotence_agent_non_rappele(
        self, registre: RegistreLibelles, tmp_path: Path
    ) -> None:
        service = _FauxService(threads_suppression=["t-sup1"])
        mistral = _FauxMistral(_scenario_suppression(["t-sup1"], ["m-t-sup1"], ["m-t-sup1"]))
        premier = _run_suppression(registre, tmp_path, service, mistral, dry_run=True)
        nb_appels = len(mistral.chat.appels)
        second = _run_suppression(
            registre, tmp_path, service, mistral, run_id=premier.meta.run_id, dry_run=True
        )
        assert second.statut_global == "succes"
        assert len(mistral.chat.appels) == nb_appels
