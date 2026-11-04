import json
from pathlib import Path

import pytest

import journalisation


def test_entete_et_pied_de_page_par_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOG_FILE", str(tmp_path / "gmailagent.log"))
    monkeypatch.setattr(journalisation, "_configure", False)

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
