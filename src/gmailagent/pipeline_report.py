"""Agrégation des synthèses validées et restitution console (rapport final, phase 8).

`aggreger` calcule un `ResumeRun` (T8.1) de façon déterministe depuis les synthèses
validées du checkpoint ; `formater_console` produit le résumé lisible affiché par la CLI
après le JSON du rapport. Aucun nom de libellé physique en dur : seules les clés logiques
(ex. `classification.notification`) apparaissent dans le résumé.
"""

from collections.abc import Mapping

from gmailagent.agent_contracts import (
    RapportFinal,
    ResumeRun,
    SyntheseClassification,
    SyntheseEtape,
    SyntheseSpam,
    SyntheseSuppression,
)


def aggreger(syntheses: Mapping[str, SyntheseEtape], nb_doublons: int) -> ResumeRun:
    """Résumé agrégé d'un run, calculé depuis les synthèses validées du checkpoint."""
    par_categorie: dict[str, int] = {}
    par_urgence: dict[str, int] = {}
    spam_deplaces = 0
    corbeille = 0

    classification = syntheses.get("classification")
    if isinstance(classification, SyntheseClassification):
        for message in classification.messages:
            par_categorie[message.categorie] = par_categorie.get(message.categorie, 0) + 1
            par_urgence[message.urgence] = par_urgence.get(message.urgence, 0) + 1

    spam = syntheses.get("spam")
    if isinstance(spam, SyntheseSpam) and spam.statut == "deplaces":
        spam_deplaces = len(spam.messages)

    suppression = syntheses.get("suppression")
    if isinstance(suppression, SyntheseSuppression) and suppression.statut == "supprimes":
        corbeille = suppression.count

    return ResumeRun(
        par_categorie=par_categorie,
        par_urgence=par_urgence,
        spam_deplaces=spam_deplaces,
        doublons=nb_doublons,
        corbeille=corbeille,
    )


def formater_console(rapport: RapportFinal) -> str:
    """Résumé console lisible d'un rapport final (affiché après le JSON par la CLI)."""
    lignes = [f"run {rapport.meta.run_id} : {rapport.statut_global}"]
    if rapport.etape_fautive:
        lignes.append(f"  étape fautive : {rapport.etape_fautive}")
    resume = rapport.resume
    if resume is not None:
        if resume.spam_deplaces:
            lignes.append(f"  spam : {resume.spam_deplaces} message(s) replacé(s)")
        total = sum(resume.par_categorie.values())
        if total:
            lignes.append(f"  classés : {total} message(s)")
            for categorie in sorted(resume.par_categorie):
                lignes.append(f"    - {categorie} : {resume.par_categorie[categorie]}")
            for urgence in sorted(resume.par_urgence):
                lignes.append(f"    - urgence {urgence} : {resume.par_urgence[urgence]}")
        if resume.corbeille:
            lignes.append(f"  corbeille : {resume.corbeille} message(s)")
        if resume.doublons:
            lignes.append(f"  doublons : {resume.doublons}")
    return "\n".join(lignes)
