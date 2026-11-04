"""Orchestrateur : cycle du run principal (tri), checkpoints, idempotence.

Étapes 0–7 du run principal (docs/design/workflow.md). Les étapes 1–2 (spam) et
3–4 (classification) sont réelles (phases 4–5) ; le dédoublonnage (étape 5) reste
un stub no-op en v1 (option post-v1, décision D46 — phase 6).

Checkpoints : JSON persistés dans `data/checkpoints/<run_id>.json` à chaque étape
validée ; en cas de crash, relancer avec le même `run_id` saute les étapes déjà
checkpointées (reprise sur incident). L'idempotence est en outre garantie par la
requête Gmail `is:unread -label:"<libellé traité>"`, construite depuis le registre
(clé logique `suivi.traite`) — jamais de libellé physique en dur dans le code.

Run de suppression séparé (planifié T+1h, phase 7) : `lancer_run_suppression` —
corbeille uniquement (TRASH appliqué par l'agent via `label_message`).
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

from mistralai.client import Mistral
from pydantic import BaseModel, ConfigDict, ValidationError

from agents import lancer_conversation
from client import obtenir_client
from config import RegistreLibelles, charger_registre
from contracts import (
    AGENT_CLASSIFICATION,
    AGENT_SPAM,
    AGENT_SUPPRESSION,
    Meta,
    RapportFinal,
    SyntheseClassification,
    SyntheseEtape,
    SyntheseSpam,
    SyntheseSuppression,
)
from dedup import empreinte_message, normaliser_message_id
from gmail import ClientGmailAPI, nouveau_client
from journalisation import configurer, obtenir_logger
from labels import ClientGmail, ResolveurLibelles
from validation import SyntheseInvalideError

CLE_TRAITE = "suivi.traite"
CLE_VALIDE_SPAM = "suivi.valide-spam"
CLE_DOUBLON = "suivi.doublon"
REQUETE_SPAM = "in:spam"
LABEL_SPAM = "SPAM"
LABEL_INBOX = "INBOX"
AGENT_ORCHESTRATEUR = "orchestrateur"
ETAPE_DEMARRAGE = "demarrage"
ETAPE_RAPPORT = "rapport"
ETAPE_FIN = "fin"
ETAPE_LECTURE_SUPPRESSION = "lecture_suppression"
ETAPE_VALIDATION_SUPPRESSION = "validation_suppression"


class CheckpointError(RuntimeError):
    pass


ConversationFn = Callable[..., tuple[SyntheseEtape, list[Any]]]


def _api_client(client_api: ClientGmailAPI | None, dry_run: bool) -> ClientGmailAPI:
    if client_api is not None:
        return client_api
    return ClientGmailAPI.depuis_token(dry_run=dry_run)


def _lancer_classification(
    rid: UUID,
    reg: RegistreLibelles,
    resolveur: ResolveurLibelles,
    *,
    dry_run: bool,
    client_api: ClientGmailAPI | None,
    client_mistral: Mistral | None,
    conversation: ConversationFn | None,
) -> tuple[SyntheseEtape, list[Any]]:
    api = _api_client(client_api, dry_run)
    lance = conversation if conversation is not None else lancer_conversation
    if conversation is None and client_mistral is None:
        mistral = obtenir_client()
    else:
        mistral = cast("Mistral", client_mistral)
    meta = Meta(run_id=rid, etape="lecture_classification", agent=AGENT_CLASSIFICATION)
    requete = requete_non_lus(reg, resolveur)
    return lance(
        AGENT_CLASSIFICATION,
        requete,
        meta,
        client_mistral=mistral,
        client_gmail=api,
        registre=reg,
        dry_run=dry_run,
    )


def _lancer_spam(
    rid: UUID,
    reg: RegistreLibelles,
    *,
    dry_run: bool,
    client_api: ClientGmailAPI | None,
    client_mistral: Mistral | None,
    conversation: ConversationFn | None,
) -> tuple[SyntheseEtape, list[Any]]:
    api = _api_client(client_api, dry_run)
    lance = conversation if conversation is not None else lancer_conversation
    if conversation is None and client_mistral is None:
        mistral = obtenir_client()
    else:
        mistral = cast("Mistral", client_mistral)
    meta = Meta(run_id=rid, etape="lecture_spam", agent=AGENT_SPAM)
    return lance(
        AGENT_SPAM,
        REQUETE_SPAM,
        meta,
        client_mistral=mistral,
        client_gmail=api,
        registre=reg,
        dry_run=dry_run,
    )


def _lancer_suppression(
    rid: UUID,
    reg: RegistreLibelles,
    resolveur: ResolveurLibelles,
    *,
    dry_run: bool,
    client_api: ClientGmailAPI | None,
    client_mistral: Mistral | None,
    conversation: ConversationFn | None,
) -> tuple[SyntheseEtape, list[Any]]:
    api = _api_client(client_api, dry_run)
    lance = conversation if conversation is not None else lancer_conversation
    if conversation is None and client_mistral is None:
        mistral = obtenir_client()
    else:
        mistral = cast("Mistral", client_mistral)
    meta = Meta(run_id=rid, etape=ETAPE_LECTURE_SUPPRESSION, agent=AGENT_SUPPRESSION)
    requete = requete_suppression(reg, resolveur)
    return lance(
        AGENT_SUPPRESSION,
        requete,
        meta,
        client_mistral=mistral,
        client_gmail=api,
        registre=reg,
        dry_run=dry_run,
    )


def _recalculer_empreintes(synthese: SyntheseClassification, api: ClientGmailAPI) -> None:
    """Recalcule message_id_rfc/empreinte depuis les lectures réelles (rejet C6 si écart)."""
    for message in synthese.messages:
        recalc_id, recalc_empreinte = empreinte_message(api.get_message(message.id))
        if recalc_empreinte != message.empreinte or recalc_id != normaliser_message_id(
            message.message_id_rfc
        ):
            raise SyntheseInvalideError(
                f"clés de dédoublonnage recalculées différentes pour {message.id} — rejet C6"
            )


def _appliquer_libelles_classification(
    synthese: SyntheseClassification, resolveur: ResolveurLibelles, api: ClientGmailAPI
) -> None:
    """Appose le libellé de catégorie + `Agent/traité` (dry-run : journalisé, règle E)."""
    id_traite = resolveur.resoudre(CLE_TRAITE)
    for message in synthese.messages:
        id_categorie = resolveur.resoudre(message.categorie)
        api.modifier_libelles(message.id, ajouter=[id_categorie, id_traite])


def _appliquer_libelles_spam(
    synthese: SyntheseSpam, resolveur: ResolveurLibelles, api: ClientGmailAPI
) -> None:
    """Replacer depuis le spam : appose `valide-spam` + `traité`, retire SPAM, remet
    INBOX (dry-run : journalisé, règle E)."""
    if synthese.statut != "deplaces":
        return
    id_valide_spam = resolveur.resoudre(CLE_VALIDE_SPAM)
    id_traite = resolveur.resoudre(CLE_TRAITE)
    for message in synthese.messages:
        api.modifier_libelles(
            message.id,
            ajouter=[id_valide_spam, id_traite, LABEL_INBOX],
            retirer=[LABEL_SPAM],
        )


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


def requete_suppression(registre: RegistreLibelles, resolveur: ResolveurLibelles) -> str:
    """Requête du run de suppression (T+1h) : traités depuis plus d'une heure + doublons.

    Les libellés physiques proviennent du registre (clés logiques `suivi.traite` et
    `suivi.doublon`) et sont résolus/créés via le resolveur ; jamais de nom de libellé
    en dur dans le code. La clause `doublon` est inerte en v1 (phase 6 non embarquée,
    décision D46).
    """
    resolveur.resoudre(CLE_TRAITE)
    resolveur.resoudre(CLE_DOUBLON)
    return (
        f'label:"{registre.libelle(CLE_TRAITE)}" older_than:1h '
        f'label:"{registre.libelle(CLE_DOUBLON)}"'
    )


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
    client_api: ClientGmailAPI | None = None,
    client_mistral: Mistral | None = None,
    conversation: ConversationFn | None = None,
    registre: RegistreLibelles | None = None,
    dossier_checkpoints: Path | None = None,
) -> RapportFinal:
    """Cycle du run principal (étapes 0–7) : étapes 1–4 réelles (phases 4–5), le reste en stub.

    `dry_run=True` par défaut (règle E) : aucune écriture Gmail. En cas d'échec,
    le motif est journalisé, le rapport marqué `echec_partiel` avec l'étape
    fautive, et l'exception est relancée (arrêt propre du run).
    """
    rid = run_id if run_id is not None else uuid4()
    configurer(str(rid))
    log = obtenir_logger("orchestrateur")
    reg = registre if registre is not None else charger_registre()
    dossier = dossier_checkpoints if dossier_checkpoints is not None else _dossier_checkpoints()
    if client is not None:
        client_gmail: ClientGmail = client
    elif client_api is not None:
        client_gmail = client_api
    else:
        client_gmail = nouveau_client(dry_run=dry_run)
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

        etape_courante = "lecture_spam"
        if "lecture_spam" not in checkpoint.etapes_validees:
            synthese, _executions = _lancer_spam(
                rid,
                reg,
                dry_run=dry_run,
                client_api=client_api,
                client_mistral=client_mistral,
                conversation=conversation,
            )
            checkpoint.syntheses["spam"] = synthese
            _valider_etape(checkpoint, "lecture_spam", dossier)

        etape_courante = "validation_spam"
        if "validation_spam" not in checkpoint.etapes_validees:
            synthese_s = checkpoint.syntheses.get("spam")
            if not isinstance(synthese_s, SyntheseSpam):
                raise CheckpointError("synthèse spam absente du checkpoint")
            api = _api_client(client_api, dry_run)
            _appliquer_libelles_spam(synthese_s, resolveur, api)
            _valider_etape(checkpoint, "validation_spam", dossier)

        etape_courante = "lecture_classification"
        if "lecture_classification" not in checkpoint.etapes_validees:
            synthese, _executions = _lancer_classification(
                rid,
                reg,
                resolveur,
                dry_run=dry_run,
                client_api=client_api,
                client_mistral=client_mistral,
                conversation=conversation,
            )
            checkpoint.syntheses["classification"] = synthese
            _valider_etape(checkpoint, "lecture_classification", dossier)

        etape_courante = "validation_classification"
        if "validation_classification" not in checkpoint.etapes_validees:
            synthese_c = checkpoint.syntheses.get("classification")
            if not isinstance(synthese_c, SyntheseClassification):
                raise CheckpointError("synthèse classification absente du checkpoint")
            api = _api_client(client_api, dry_run)
            _recalculer_empreintes(synthese_c, api)
            _appliquer_libelles_classification(synthese_c, resolveur, api)
            _valider_etape(checkpoint, "validation_classification", dossier)

        etape_courante = "dedoublonnage"
        if "dedoublonnage" not in checkpoint.etapes_validees:
            log.warning(
                "etape en stub (option post-v1, decision D46)",
                etape="dedoublonnage",
                implementee_en="phase 6 (post-v1)",
            )
            _valider_etape(checkpoint, "dedoublonnage", dossier)

        etape_courante = ETAPE_RAPPORT
        if ETAPE_RAPPORT not in checkpoint.etapes_validees:
            meta = Meta(run_id=rid, etape=ETAPE_RAPPORT, agent=AGENT_ORCHESTRATEUR)
            synthese_c = checkpoint.syntheses.get("classification")
            synthese_s = checkpoint.syntheses.get("spam")
            checkpoint.rapport = RapportFinal(
                meta=meta,
                synthese_spam=(
                    synthese_s if isinstance(synthese_s, SyntheseSpam) else None
                ),
                synthese_classification=(
                    synthese_c if isinstance(synthese_c, SyntheseClassification) else None
                ),
                nb_doublons=0,
                statut_global="succes",
            )
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


def lancer_run_suppression(
    run_id: UUID | None = None,
    *,
    dry_run: bool = True,
    client: ClientGmail | None = None,
    client_api: ClientGmailAPI | None = None,
    client_mistral: Mistral | None = None,
    conversation: ConversationFn | None = None,
    registre: RegistreLibelles | None = None,
    dossier_checkpoints: Path | None = None,
) -> RapportFinal:
    """Run de suppression séparé (planifié T+1h) : conversation agent suppression sur
    `label:"<traité>" older_than:1h` (+ doublons, inerte en v1, D46).

    Corbeille uniquement : l'agent applique lui-même `TRASH` via `label_message` pendant
    la conversation (écriture journalisée en dry-run, règle E) ; l'orchestrateur valide
    (C1–C3 + garde de complétude action, dans `lancer_conversation`) et checkpoint.
    `dry_run=True` par défaut (règle E). Rejet → `echec_partiel` + `etape_fautive`,
    checkpoint persisté, exception relancée (arrêt propre). Idempotence : la requête
    `older_than:1h` et l'exclusion de la corbeille par la recherche Gmail.
    """
    rid = run_id if run_id is not None else uuid4()
    configurer(str(rid))
    log = obtenir_logger("orchestrateur")
    reg = registre if registre is not None else charger_registre()
    dossier = dossier_checkpoints if dossier_checkpoints is not None else _dossier_checkpoints()
    if client is not None:
        client_gmail: ClientGmail = client
    elif client_api is not None:
        client_gmail = client_api
    else:
        client_gmail = nouveau_client(dry_run=dry_run)
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
            requete = requete_suppression(reg, resolveur)
            log.info(
                "run suppression demarre", run_id=str(rid), dry_run=dry_run, requete=requete
            )
            _valider_etape(checkpoint, ETAPE_DEMARRAGE, dossier)

        etape_courante = ETAPE_LECTURE_SUPPRESSION
        if ETAPE_LECTURE_SUPPRESSION not in checkpoint.etapes_validees:
            synthese, _executions = _lancer_suppression(
                rid,
                reg,
                resolveur,
                dry_run=dry_run,
                client_api=client_api,
                client_mistral=client_mistral,
                conversation=conversation,
            )
            checkpoint.syntheses["suppression"] = synthese
            _valider_etape(checkpoint, ETAPE_LECTURE_SUPPRESSION, dossier)

        etape_courante = ETAPE_VALIDATION_SUPPRESSION
        if ETAPE_VALIDATION_SUPPRESSION not in checkpoint.etapes_validees:
            synthese_s = checkpoint.syntheses.get("suppression")
            if not isinstance(synthese_s, SyntheseSuppression):
                raise CheckpointError("synthèse suppression absente du checkpoint")
            _valider_etape(checkpoint, ETAPE_VALIDATION_SUPPRESSION, dossier)

        etape_courante = ETAPE_RAPPORT
        if ETAPE_RAPPORT not in checkpoint.etapes_validees:
            meta = Meta(run_id=rid, etape=ETAPE_RAPPORT, agent=AGENT_ORCHESTRATEUR)
            synthese_s = checkpoint.syntheses.get("suppression")
            checkpoint.rapport = RapportFinal(
                meta=meta,
                synthese_suppression=(
                    synthese_s if isinstance(synthese_s, SyntheseSuppression) else None
                ),
                statut_global="succes",
            )
            _valider_etape(checkpoint, ETAPE_RAPPORT, dossier)

        etape_courante = ETAPE_FIN
        if ETAPE_FIN not in checkpoint.etapes_validees:
            _valider_etape(checkpoint, ETAPE_FIN, dossier)
        log.info("run suppression termine", run_id=str(rid), etapes=checkpoint.etapes_validees)
    except Exception as erreur:
        log.error("run interrompu", etape=etape_courante, erreur=repr(erreur))
        meta = Meta(run_id=rid, etape=etape_courante, agent=AGENT_ORCHESTRATEUR)
        checkpoint.rapport = RapportFinal(
            meta=meta,
            statut_global="echec_partiel",
            etape_fautive=etape_courante,
        )
        sauvegarder_checkpoint(checkpoint, dossier)
        raise

    rapport = checkpoint.rapport
    if rapport is None:
        raise CheckpointError(f"rapport absent après le run {rid}")
    return rapport
