import json
from pathlib import Path
from typing import Any

import pytest

import gmail
from gmail import (
    ClientGmailAPI,
    PlafondLecturesAtteintError,
    TokenGmailError,
    charger_credentials,
    nouveau_client,
)


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
                    {"id": "Label_1", "name": "Agent/traité"},
                    {"id": "Label_2", "name": "INBOX"},
                    {"name": "entree-sans-id"},
                ]
            }
        )

    def create(self, userId: str, body: dict[str, str]) -> _Requete:
        self._service.appels.append(("labels.create", {"userId": userId, "name": body["name"]}))
        return _Requete({"id": "Label_99", "name": body["name"]})


class _FauxThreads:
    def __init__(self, service: _FauxService) -> None:
        self._service = service

    def list(self, userId: str, q: str, maxResults: int) -> _Requete:
        self._service.appels.append(("threads.list", {"q": q, "maxResults": maxResults}))
        return _Requete({"threads": [{"id": "t1"}, {"id": "t2"}, {"sans-id": True}]})

    def get(self, userId: str, id: str) -> _Requete:
        self._service.appels.append(("threads.get", {"id": id}))
        return _Requete({"id": id, "messages": [{"id": "m1"}]})


class _FauxMessages:
    def __init__(self, service: _FauxService) -> None:
        self._service = service

    def modify(self, userId: str, id: str, body: dict[str, list[str]]) -> _Requete:
        self._service.appels.append(("messages.modify", {"id": id, "body": body}))
        return _Requete({"id": id})

    def trash(self, userId: str, id: str) -> _Requete:
        self._service.appels.append(("messages.trash", {"id": id}))
        return _Requete({"id": id})


def _client(dry_run: bool = False, plafond: int = 100) -> tuple[ClientGmailAPI, _FauxService]:
    service = _FauxService()
    return ClientGmailAPI(service, dry_run=dry_run, plafond_lectures=plafond), service


class TestListLabels:
    def test_mappage_et_filtrage(self) -> None:
        client, service = _client()
        assert client.list_labels() == [
            {"id": "Label_1", "name": "Agent/traité"},
            {"id": "Label_2", "name": "INBOX"},
        ]
        assert service.appels[0][0] == "labels.list"

    def test_compte_comme_lecture(self) -> None:
        client, _ = _client(plafond=1)
        client.list_labels()
        with pytest.raises(PlafondLecturesAtteintError, match="anti-boucle"):
            client.list_labels()


class TestCreateLabel:
    def test_reel(self) -> None:
        client, service = _client()
        cree = client.create_label("Agent/doublon")
        assert cree == {"id": "Label_99", "name": "Agent/doublon"}
        assert service.appels == [("labels.create", {"userId": "me", "name": "Agent/doublon"})]

    def test_dry_run_non_execute(self) -> None:
        client, service = _client(dry_run=True)
        cree = client.create_label("Agent/doublon")
        assert cree["id"] == "DRYRUN:Agent/doublon"
        assert service.appels == []


class TestSearchThreads:
    def test_retourne_ids_et_passe_la_requete(self) -> None:
        client, service = _client()
        query = 'is:unread -label:"Agent/traité"'
        assert client.search_threads(query, max_results=50) == ["t1", "t2"]
        assert service.appels == [("threads.list", {"q": query, "maxResults": 50})]


class TestGetThread:
    def test_retourne_le_thread(self) -> None:
        client, service = _client()
        assert client.get_thread("t1") == {"id": "t1", "messages": [{"id": "m1"}]}
        assert service.appels == [("threads.get", {"id": "t1"})]


class TestModifierLibelles:
    def test_reel_add_remove(self) -> None:
        client, service = _client()
        client.modifier_libelles("m1", ajouter=["Label_1"], retirer=["Label_2"])
        attendu = {
            "id": "m1",
            "body": {"addLabelIds": ["Label_1"], "removeLabelIds": ["Label_2"]},
        }
        assert service.appels == [("messages.modify", attendu)]

    def test_body_vide_si_rien(self) -> None:
        client, service = _client()
        client.modifier_libelles("m1")
        assert service.appels[0] == ("messages.modify", {"id": "m1", "body": {}})

    def test_dry_run_non_execute(self) -> None:
        client, service = _client(dry_run=True)
        client.modifier_libelles("m1", ajouter=["Label_1"])
        assert service.appels == []


class TestPlafondLectures:
    def test_abandon_propre_au_dela(self) -> None:
        client, _ = _client(plafond=2)
        client.search_threads("q")
        client.get_thread("t1")
        with pytest.raises(PlafondLecturesAtteintError, match="abandon propre"):
            client.search_threads("q")


def _ecrire_token(chemin: Path) -> None:
    chemin.write_text(
        json.dumps(
            {
                "token": "at",
                "refresh_token": "rt",
                "token_uri": "https://oauth2.googleapis.com/token",
                "client_id": "cid",
                "client_secret": "cs",
                "scopes": ["https://www.googleapis.com/auth/gmail.modify"],
            }
        ),
        encoding="utf-8",
    )


class TestChargerCredentials:
    def test_recharge_depuis_fichier(self, tmp_path: Path) -> None:
        cible = tmp_path / "gmail_token.json"
        _ecrire_token(cible)
        creds = charger_credentials(cible)
        assert creds.refresh_token == "rt"
        assert creds.token == "at"

    def test_fichier_absent(self, tmp_path: Path) -> None:
        with pytest.raises(TokenGmailError, match="illisible"):
            charger_credentials(tmp_path / "absent.json")

    def test_contenu_non_json(self, tmp_path: Path) -> None:
        cible = tmp_path / "gmail_token.json"
        cible.write_text("pas du json", encoding="utf-8")
        with pytest.raises(TokenGmailError, match="illisible"):
            charger_credentials(cible)

    def test_json_non_objet(self, tmp_path: Path) -> None:
        cible = tmp_path / "gmail_token.json"
        cible.write_text("[1, 2]", encoding="utf-8")
        with pytest.raises(TokenGmailError, match="malformé"):
            charger_credentials(cible)


class TestNouveauClient:
    def test_construit_depuis_token(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        cible = tmp_path / "gmail_token.json"
        _ecrire_token(cible)
        service = _FauxService()
        appels_build: list[dict[str, Any]] = []

        def _faux_build(*args: Any, **kwargs: Any) -> _FauxService:
            appels_build.append({"args": args, "kwargs": kwargs})
            return service

        monkeypatch.setattr(gmail, "build", _faux_build)
        client = nouveau_client(cible, dry_run=True)
        assert appels_build[0]["args"][:2] == ("gmail", "v1")
        assert isinstance(client, ClientGmailAPI)
        assert client.create_label("Agent/x")["id"] == "DRYRUN:Agent/x"
        assert service.appels == []
