"""Orchestrateur squelette : cycle du run principal (tri), checkpoints, idempotence.

Étapes 0–7 du run principal (docs/design/workflow.md). En phase 3, les phases
agentiques (étapes 1 et 3) et le dédoublonnage (étape 5) sont des stubs —
implémentés en phases 4, 5 et 6. Le run vide ne fait aucun appel à l'API Mistral.

Checkpoints : JSON persistés dans `data/checkpoints/<run_id>.json` à chaque étape
validée ; en cas de crash, relancer avec le même `run_id` saute les étapes déjà
checkpointées (reprise sur incident). L'idempotence est en outre garantie par la
requête Gmail `is:unread -label:"<libellé traité>"`, construite depuis le registre
(clé logique `suivi.traite`) — jamais de libellé physique en dur dans le code.
"""

from pathlib import Path
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, ValidationError

from config import RegistreLibelles, charger_registre
from contracts import Meta, RapportFinal, SyntheseEtape
from gmail import nouveau_client
from journalisation import configurer, obtenir_logger
from labels import ClientGmail, ResolveurLibelles

CLE_TRAITE = "suivi.traite"
AGENT_ORCHESTRATEUR = "orchestrateur"
ETAPE_DEMARRAGE = "demarrage"
ETAPE_RAPPORT = "rapport"
ETAPE_FIN = "fin"


class CheckpointError(RuntimeError):
    pass


class Checkpoint(BaseModel):
    """État persisté d'un run : étapes validées, synthèses d'étapes, rapport."""

    model_config = ConfigDict(extra="forbid")

    run_id: UUID
    etapes_validees: list[str]
    syntheses: dict[str, SyntheseEtape] = {}
    rapport: RapportFinal | None = None


def _dossier_checkpoints() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "checkpoints"


def _fichier_checkpoint(run_id: UUID, dossier: Path) -> Path:
    return dossier / f"{run_id}.json"


def sauvegarder_checkpoint(checkpoint: Checkpoint, dossier: Path | None = None) -> Path:
    cible_dossier = dossier if dossier is not None else _dossier_checkpoints()
    cible_dossier.mkdir(parents=True, exist_ok=True)
    cible = _fichier_checkpoint(checkpoint.run_id, cible_dossier)
    cible.write_text(checkpoint.model_dump_json(indent=2), encoding="utf-8")
    return cible


def charger_checkpoint(run_id: UUID, dossier: Path | None = None) -> Checkpoint:
    cible = _fichier_checkpoint(run_id, dossier if dossier is not None else _dossier_checkpoints())
    try:
        return Checkpoint.model_validate_json(cible.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as erreur:
        raise CheckpointError(f"checkpoint illisible : {cible} ({erreur})") from erreur


def requete_non_lus(registre: RegistreLibelles, resolveur: ResolveurLibelles) -> str:
    """Requête d'idempotence du run : non lus sans le libellé « traité ».

    Le libellé physique provient du registre (clé logique `suivi.traite`) et est
    résolu/créé via le resolveur ; jamais de nom de libellé en dur dans le code.
    """
    resolveur.resoudre(CLE_TRAITE)
    return f'is:unread -label:"{registre.libelle(CLE_TRAITE)}"'


def _valider_etape(checkpoint: Checkpoint, etape: str, dossier: Path) -> None:
    checkpoint.etapes_validees.append(etape)
    sauvegarder_checkpoint(checkpoint, dossier)
    obtenir_logger("orchestrateur").info(
        "etape validee", etape=etape, run_id=str(checkpoint.run_id)
    )


def lancer_run_tri(
    run_id: UUID | None = None,
    *,
    dry_run: bool = True,
    client: ClientGmail | None = None,
    registre: RegistreLibelles | None = None,
    dossier_checkpoints: Path | None = None,
) -> RapportFinal:
    """Cycle du run principal (étapes 0–7), squelette de la phase 3.

    `dry_run=True` par défaut (règle E) : aucune écriture Gmail. En cas d'échec,
    le motif est journalisé, le rapport marqué `echec_partiel` avec l'étape
    fautive, et l'exception est relancée (arrêt propre du run).
    """
    rid = run_id if run_id is not None else uuid4()
    configurer(str(rid))
    log = obtenir_logger("orchestrateur")
    reg = registre if registre is not None else charger_registre()
    dossier = dossier_checkpoints if dossier_checkpoints is not None else _dossier_checkpoints()
    client_gmail = client if client is not None else nouveau_client(dry_run=dry_run)
    resolveur = ResolveurLibelles(reg, client_gmail, dry_run=dry_run)

    try:
        checkpoint = charger_checkpoint(rid, dossier)
        log.info(
            "reprise sur incident",
            run_id=str(rid),
            etapes_validees=checkpoint.etapes_validees,
        )
    except CheckpointError:
        checkpoint = Checkpoint(run_id=rid, etapes_validees=[])

    etape_courante = ETAPE_DEMARRAGE
    try:
        if ETAPE_DEMARRAGE not in checkpoint.etapes_validees:
            requete = requete_non_lus(reg, resolveur)
            log.info("run demarre", run_id=str(rid), dry_run=dry_run, requete_idempotence=requete)
            _valider_etape(checkpoint, ETAPE_DEMARRAGE, dossier)

        for etape_agent, phase in (
            ("lecture_spam", "phase 4 (agent spam)"),
            ("lecture_classification", "phase 5 (agent classification)"),
        ):
            etape_courante = etape_agent
            if etape_agent not in checkpoint.etapes_validees:
                log.warning(
                    "etape en stub (squelette phase 3)",
                    etape=etape_agent,
                    implementee_en=phase,
                )
                _valider_etape(checkpoint, etape_agent, dossier)
            if etape_agent == "lecture_spam":
                etape_courante = "validation_spam"
            else:
                etape_courante = "validation_classification"
            if etape_courante not in checkpoint.etapes_validees:
                _valider_etape(checkpoint, etape_courante, dossier)

        etape_courante = "dedoublonnage"
        if "dedoublonnage" not in checkpoint.etapes_validees:
            log.warning(
                "etape en stub (squelette phase 3)",
                etape="dedoublonnage",
                implementee_en="phase 6",
            )
            _valider_etape(checkpoint, "dedoublonnage", dossier)

        etape_courante = ETAPE_RAPPORT
        if ETAPE_RAPPORT not in checkpoint.etapes_validees:
            meta = Meta(run_id=rid, etape=ETAPE_RAPPORT, agent=AGENT_ORCHESTRATEUR)
            checkpoint.rapport = RapportFinal(meta=meta, nb_doublons=0, statut_global="succes")
            _valider_etape(checkpoint, ETAPE_RAPPORT, dossier)

        etape_courante = ETAPE_FIN
        if ETAPE_FIN not in checkpoint.etapes_validees:
            _valider_etape(checkpoint, ETAPE_FIN, dossier)
        log.info("run termine", run_id=str(rid), etapes=checkpoint.etapes_validees)
    except Exception as erreur:
        log.error("run interrompu", etape=etape_courante, erreur=repr(erreur))
        meta = Meta(run_id=rid, etape=etape_courante, agent=AGENT_ORCHESTRATEUR)
        checkpoint.rapport = RapportFinal(
            meta=meta,
            nb_doublons=0,
            statut_global="echec_partiel",
            etape_fautive=etape_courante,
        )
        sauvegarder_checkpoint(checkpoint, dossier)
        raise

    rapport = checkpoint.rapport
    if rapport is None:
        raise CheckpointError(f"rapport absent après le run {rid}")
    return rapport
