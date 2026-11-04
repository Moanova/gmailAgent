from uuid import uuid4

from contracts import (
    MessageClasse,
    MessageLu,
    Meta,
    RapportFinal,
    ResumeRun,
    SyntheseClassification,
    SyntheseSpam,
    SyntheseSuppression,
)
from report import aggreger, formater_console


def _meta() -> Meta:
    return Meta(run_id=uuid4(), etape="rapport", agent="orchestrateur")


def _message_classe(categorie: str, urgence: str, mid: str = "m1") -> MessageClasse:
    return MessageClasse(
        id=mid,
        objet="Sujet",
        expediteur="exp@ex.fr",
        motif="motif",
        categorie=categorie,
        urgence=urgence,  # type: ignore[arg-type]
        message_id_rfc="abc@ex.fr",
        empreinte="a" * 64,
    )


def _message_lu(mid: str = "m1") -> MessageLu:
    return MessageLu(id=mid, objet="Sujet", expediteur="news@ex.fr", motif="newsletter")


class TestAggreger:
    def test_tri_complet(self) -> None:
        meta = _meta()
        syntheses = {
            "classification": SyntheseClassification(
                statut="synthese",
                messages=[
                    _message_classe("classification.notification", "haute", "m1"),
                    _message_classe("classification.a-repondre", "basse", "m2"),
                    _message_classe("classification.notification", "moyenne", "m3"),
                ],
                meta=meta,
            ),
            "spam": SyntheseSpam(statut="deplaces", messages=[_message_lu()], meta=meta),
        }
        resume = aggreger(syntheses, nb_doublons=0)
        assert resume.par_categorie == {
            "classification.notification": 2,
            "classification.a-repondre": 1,
        }
        assert resume.par_urgence == {"haute": 1, "moyenne": 1, "basse": 1}
        assert resume.spam_deplaces == 1
        assert resume.doublons == 0
        assert resume.corbeille == 0

    def test_aucun_message_zeros(self) -> None:
        meta = _meta()
        syntheses = {
            "classification": SyntheseClassification(
                statut="aucun_message", messages=[], meta=meta
            ),
            "spam": SyntheseSpam(statut="aucun_message", messages=[], meta=meta),
        }
        resume = aggreger(syntheses, nb_doublons=0)
        assert resume.par_categorie == {}
        assert resume.spam_deplaces == 0
        assert resume.corbeille == 0

    def test_suppression_supprimes(self) -> None:
        meta = _meta()
        syntheses = {
            "suppression": SyntheseSuppression(
                statut="supprimes", count=2, ids=["m1", "m2"], meta=meta
            )
        }
        resume = aggreger(syntheses, nb_doublons=0)
        assert resume.corbeille == 2
        assert resume.par_categorie == {}

    def test_echec_technique_zeros(self) -> None:
        meta = _meta()
        syntheses = {
            "spam": SyntheseSpam(
                statut="echec_technique", messages=[], erreur="boom", meta=meta
            )
        }
        resume = aggreger(syntheses, nb_doublons=3)
        assert resume.spam_deplaces == 0
        assert resume.doublons == 3


class TestFormaterConsole:
    def test_succes_avec_resume(self) -> None:
        meta = _meta()
        rapport = RapportFinal(
            meta=meta,
            statut_global="succes",
            resume=ResumeRun(
                par_categorie={"classification.notification": 2},
                par_urgence={"haute": 1, "basse": 1},
                spam_deplaces=1,
            ),
        )
        texte = formater_console(rapport)
        assert "succes" in texte
        assert "spam : 1 message(s) replacé(s)" in texte
        assert "classés : 2 message(s)" in texte
        assert "classification.notification : 2" in texte
        assert "urgence haute : 1" in texte
        assert "Agent/" not in texte

    def test_echec_partiel_avec_etape_fautive(self) -> None:
        rapport = RapportFinal(
            meta=_meta(), statut_global="echec_partiel", etape_fautive="lecture_spam"
        )
        texte = formater_console(rapport)
        assert "echec_partiel" in texte
        assert "étape fautive : lecture_spam" in texte

    def test_sans_resume(self) -> None:
        rapport = RapportFinal(meta=_meta(), statut_global="succes")
        texte = formater_console(rapport)
        assert texte == f"run {rapport.meta.run_id} : succes"

    def test_corbeille_affichee(self) -> None:
        rapport = RapportFinal(
            meta=_meta(), statut_global="succes", resume=ResumeRun(corbeille=3)
        )
        assert "corbeille : 3 message(s)" in formater_console(rapport)
