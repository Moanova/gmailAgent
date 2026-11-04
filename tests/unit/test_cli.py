from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

import cli
from cli import _parse_args, main
from contracts import Meta, RapportFinal


@pytest.fixture(autouse=True)
def _journal_vers_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_FILE", str(tmp_path / "journalisation.log"))


def _rapport_succes() -> RapportFinal:
    meta = Meta(
        run_id=UUID("12345678-1234-5678-1234-567812345678"),
        etape="rapport",
        agent="orchestrateur",
    )
    return RapportFinal(meta=meta, nb_doublons=0, statut_global="succes")


class _FauxAPI:
    instances: list["_FauxAPI"] = []

    def __init__(self, dry_run: bool) -> None:
        self.dry_run = dry_run
        self.modifications: list[tuple[str, list[str], list[str]]] = []
        self.creations: list[str] = []
        self.dernier_query = ""
        _FauxAPI.instances.append(self)

    @classmethod
    def depuis_token(cls, chemin: Any = None, *, dry_run: bool = False) -> "_FauxAPI":
        return cls(dry_run)

    def list_labels(self) -> list[dict[str, str]]:
        return [{"id": "L_ancien", "name": "Agent/ancien"}]

    def create_label(self, name: str) -> dict[str, str]:
        self.creations.append(name)
        if self.dry_run:
            return {"id": f"DRYRUN:{name}", "name": name}
        return {"id": "L_nouveau", "name": name}

    def search_threads(self, query: str, max_results: int = 50) -> list[str]:
        self.dernier_query = query
        return ["t1", "t2"]

    def get_thread(self, thread_id: str) -> dict[str, Any]:
        return {
            "id": thread_id,
            "messages": [{"id": f"{thread_id}-m1"}, {"id": f"{thread_id}-m2"}],
        }

    def modifier_libelles(
        self,
        message_id: str,
        ajouter: list[str] | None = None,
        retirer: list[str] | None = None,
    ) -> None:
        if self.dry_run:
            return
        self.modifications.append((message_id, list(ajouter or []), list(retirer or [])))


@pytest.fixture(autouse=True)
def _reset_faux_api() -> None:
    _FauxAPI.instances = []


class TestParseArgs:
    def test_tri_sans_reel_est_dry_run(self) -> None:
        args = _parse_args(["tri"])
        assert args.commande == "tri"
        assert args.reel is False

    def test_reel(self) -> None:
        assert _parse_args(["--reel", "tri"]).reel is True
        assert _parse_args(["migrate-labels", "A", "B", "--reel"]).reel is True

    def test_sous_commande_requise(self) -> None:
        with pytest.raises(SystemExit):
            _parse_args([])

    def test_run_id(self) -> None:
        args = _parse_args(["tri", "--run-id", "12345678-1234-5678-1234-567812345678"])
        assert args.run_id == UUID("12345678-1234-5678-1234-567812345678")

    def test_run_id_suppression(self) -> None:
        args = _parse_args(["suppression", "--run-id", "12345678-1234-5678-1234-567812345678"])
        assert args.run_id == UUID("12345678-1234-5678-1234-567812345678")


class TestMain:
    def test_tri_dry_run_par_defaut(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        appels: dict[str, Any] = {}

        def faux_run(run_id: Any = None, *, dry_run: bool, **kwargs: Any) -> RapportFinal:
            appels["dry_run"] = dry_run
            return _rapport_succes()

        monkeypatch.setattr(cli, "lancer_run_tri", faux_run)
        assert main(["tri"]) == 0
        assert appels["dry_run"] is True
        assert "succes" in capsys.readouterr().out

    def test_tri_reel(self, monkeypatch: pytest.MonkeyPatch) -> None:
        appels: dict[str, Any] = {}

        def faux_run(run_id: Any = None, *, dry_run: bool, **kwargs: Any) -> RapportFinal:
            appels["dry_run"] = dry_run
            return _rapport_succes()

        monkeypatch.setattr(cli, "lancer_run_tri", faux_run)
        assert main(["--reel", "tri"]) == 0
        assert appels["dry_run"] is False

    def test_suppression_dry_run_par_defaut(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        appels: dict[str, Any] = {}

        def faux_run_suppression(
            run_id: Any = None, *, dry_run: bool, **kwargs: Any
        ) -> RapportFinal:
            appels["dry_run"] = dry_run
            appels["run_id"] = run_id
            return _rapport_succes()

        monkeypatch.setattr(cli, "lancer_run_suppression", faux_run_suppression)
        assert main(["suppression"]) == 0
        assert appels["dry_run"] is True
        assert appels["run_id"] is not None
        assert "succes" in capsys.readouterr().out

    def test_suppression_reel(self, monkeypatch: pytest.MonkeyPatch) -> None:
        appels: dict[str, Any] = {}

        def faux_run_suppression(
            run_id: Any = None, *, dry_run: bool, **kwargs: Any
        ) -> RapportFinal:
            appels["dry_run"] = dry_run
            return _rapport_succes()

        monkeypatch.setattr(cli, "lancer_run_suppression", faux_run_suppression)
        assert main(["--reel", "suppression"]) == 0
        assert appels["dry_run"] is False

    def test_migrate_labels_dry_run(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(cli, "ClientGmailAPI", _FauxAPI)
        assert main(["migrate-labels", "Agent/ancien", "Agent/nouveau"]) == 0
        api = _FauxAPI.instances[-1]
        assert api.dry_run is True
        assert api.dernier_query == 'label:"Agent/ancien"'
        assert api.modifications == []
        assert api.creations == ["Agent/nouveau"]
        assert "dry-run" in capsys.readouterr().out

    def test_migrate_labels_reel(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(cli, "ClientGmailAPI", _FauxAPI)
        assert main(["--reel", "migrate-labels", "Agent/ancien", "Agent/nouveau"]) == 0
        api = _FauxAPI.instances[-1]
        assert api.dry_run is False
        assert len(api.modifications) == 4
        assert api.modifications[0] == ("t1-m1", ["L_nouveau"], ["L_ancien"])

    def test_migrate_labels_ancien_inconnu(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(cli, "ClientGmailAPI", _FauxAPI)
        assert main(["migrate-labels", "Agent/inconnu", "Agent/nouveau"]) == 1
        assert "inconnu" in capsys.readouterr().err
