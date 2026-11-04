import json
from pathlib import Path

import pytest

import journalisation


def test_entete_et_pied_de_page_par_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOG_FILE", str(tmp_path / "gmailagent.log"))
    monkeypatch.setattr(journalisation, "_configure", False)
    monkeypatch.setattr(journalisation, "_run_id_courant", None)

    run_id = "11111111-2222-3333-4444-555555555555"
    journalisation.configurer(run_id)
    journalisation.obtenir_logger("test").info("ligne de run", detail="x")
    journalisation.marquer_fin_run("succes")

    lignes = [
        json.loads(ligne)
        for ligne in (tmp_path / "gmailagent.log").read_text(encoding="utf-8").splitlines()
        if ligne.strip()
    ]
    assert lignes[0]["evenement"] == "debut_run"
    assert lignes[0]["run_id"] == run_id
    assert "timestamp" in lignes[0]
    assert lignes[-1]["evenement"] == "fin_run"
    assert lignes[-1]["run_id"] == run_id
    assert lignes[-1]["statut"] == "succes"
    assert "timestamp" in lignes[-1]
    assert any(ligne.get("detail") == "x" for ligne in lignes[1:-1])


def test_rebind_run_id_nouveau_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """En mode --tout, plusieurs runs se succèdent dans le même processus : chaque
    nouveau run_id doit réémettre un en-tête debut_run et re-lier le run_id (pas de
    doublon pour le même run_id)."""
    monkeypatch.setenv("LOG_FILE", str(tmp_path / "gmailagent.log"))
    monkeypatch.setattr(journalisation, "_configure", False)
    monkeypatch.setattr(journalisation, "_run_id_courant", None)

    journalisation.configurer("run-a")
    journalisation.configurer("run-a")  # même run : pas de doublon
    journalisation.configurer("run-b")  # nouveau run : nouvel en-tête + re-liaison
    journalisation.obtenir_logger("test").info("ligne run-b")

    lignes = [
        json.loads(ligne)
        for ligne in (tmp_path / "gmailagent.log").read_text(encoding="utf-8").splitlines()
        if ligne.strip()
    ]
    debuts = [x for x in lignes if x.get("evenement") == "debut_run"]
    assert [d["run_id"] for d in debuts] == ["run-a", "run-b"]
    ligne_b = next(x for x in lignes if x.get("event") == "ligne run-b")
    assert ligne_b["run_id"] == "run-b"
