"""Orchestrateur : cycle du run principal (tri), checkpoints, idempotence.

Étapes 0–7 du run principal (docs/design/workflow.md). Les étapes 1–2 (spam) et
3–4 (classification) sont réelles (phases 4–5) ; le dédoublonnage (étape 5) reste
un stub no-op en v1 (option post-v1, décision D46 — phase 6).

Checkpoints : JSON persistés dans `data/checkpoints/<run_id>.json` à chaque étape
validée ; en cas de crash, relancer avec le même `run_id` saute les étapes déjà
checkpointées (reprise sur incident). L'idempotence est en outre garantie par la
requête Gmail `is:unread -label:"<libellé traité>"`, construite depuis le registre
(clé logique `suivi.traite`) — jamais de libellé physique en dur dans le code.

Run de suppression séparé (planifié T+24h, phase 7) : `lancer_run_suppression` —
corbeille uniquement (TRASH appliqué par l'agent via `label_message`), notifications
traitées seules éligibles (D47).

Idempotence du spam (T9.6) : les messages laissés en spam (statut `aucun_message`)
reçoivent le libellé « spam confirmé » (clé logique `suivi.spam-confirme`) et la requête
de scan exclut ce libellé (`requete_spam`) — jamais de libellé physique en dur.
"""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

from mistralai.client import Mistral
from pydantic import BaseModel, ConfigDict, ValidationError

from gmailagent.agent_contracts import (
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
from gmailagent.agent_dedup import empreinte_message, normaliser_message_id
from gmailagent.agent_runner import lancer_conversation
from gmailagent.agent_validation import SyntheseInvalideError
from gmailagent.core_client import obtenir_client
from gmailagent.core_config import (
    RACINE_PROJET,
    RegistreLibelles,
    charger_registre,
    parametres_courants,
)
from gmailagent.core_journalisation import configurer, obtenir_logger
from gmailagent.gmail_client import ClientGmailAPI, nouveau_client
from gmailagent.gmail_labels import ClientGmail, ResolveurLibelles
from gmailagent.pipeline_report import aggreger

CLE_TRAITE = "suivi.traite"
CLE_VALIDE_SPAM = "suivi.valide-spam"
CLE_SPAM_CONFIRME = "suivi.spam-confirme"
CLE_NOTIFICATION = "classification.notification"
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


def _lancer_etape(
    agent: str,
    etape: str,
    requete: str,
    rid: UUID,
    reg: RegistreLibelles,
    *,
    dry_run: bool,
    client_api: ClientGmailAPI | None,
    client_mistral: Mistral | None,
    conversation: ConversationFn | None,
) -> tuple[SyntheseEtape, list[Any]]:
    """Lance la conversation d'une étape (T9.6 : helper commun aux 3 agents)."""
    api = _api_client(client_api, dry_run)
    lance = conversation if conversation is not None else lancer_conversation
    if conversation is None and client_mistral is None:
        mistral = obtenir_client()
    else:
        mistral = cast("Mistral", client_mistral)
    meta = Meta(run_id=rid, etape=etape, agent=agent)
    return lance(
        agent,
        requete,
        meta,
        client_mistral=mistral,
        client_gmail=api,
        registre=reg,
        dry_run=dry_run,
    )


def _valider_et_labelliser_classification(
    synthese: SyntheseClassification, resolveur: ResolveurLibelles, api: ClientGmailAPI
) -> None:
    """Validation puis apposition des libellés de classification en une seule fonction
    (T9.7) : pour chaque message, recalc de `message_id_rfc`/`empreinte` depuis la
    lecture API réelle (`get_message`) — conception §3 : rejet si écart, avant toute
    écriture (recalcul C6) — puis apposition du libellé de catégorie + `traité`
    (ordre recalc-avant-libellisation, kanban T5.4). Dry-run : journalisé, règle E."""
    for message in synthese.messages:
        recalc_id, recalc_empreinte = empreinte_message(api.get_message(message.id))
        if recalc_empreinte != message.empreinte or recalc_id != normaliser_message_id(
            message.message_id_rfc
        ):
            raise SyntheseInvalideError(
                f"clés de dédoublonnage recalculées différentes pour {message.id} — rejet C6"
            )
    id_traite = resolveur.resoudre(CLE_TRAITE)
    for message in synthese.messages:
        id_categorie = resolveur.resoudre(message.categorie)
        api.modifier_libelles(message.id, ajouter=[id_categorie, id_traite])


def _ids_threads_lus(executions: list[Any]) -> list[str]:
    """Ids des threads lus via `get_thread` durant la conversation (exécutions réelles)."""
    ids: list[str] = []
    for appel in executions:
        if getattr(appel, "name", "") != "get_thread":
            continue
        brut: Any = getattr(appel, "arguments", "")
        args = json.loads(brut) if isinstance(brut, str) and brut.strip() else brut
        if isinstance(args, dict) and isinstance(args.get("threadId"), str):
            ids.append(args["threadId"])
    return ids


def _appliquer_libelles_spam(
    synthese: SyntheseSpam,
    executions: list[Any],
    resolveur: ResolveurLibelles,
    api: ClientGmailAPI,
) -> None:
    """Replacer depuis le spam : appose `valide-spam` + `traité`, retire SPAM, remet
    INBOX. Si `aucun_message` (T9.6, idempotence du spam) : appose `spam-confirme`
    sur les messages lus et laissés en spam (SPAM conservé).
    Dry-run : journalisé, non exécuté (règle E)."""
    if synthese.statut == "deplaces":
        id_valide_spam = resolveur.resoudre(CLE_VALIDE_SPAM)
        id_traite = resolveur.resoudre(CLE_TRAITE)
        for message in synthese.messages:
            api.modifier_libelles(
                message.id,
                ajouter=[id_valide_spam, id_traite, LABEL_INBOX],
                retirer=[LABEL_SPAM],
            )
        return
    if synthese.statut == "aucun_message":
        id_confirme = resolveur.resoudre(CLE_SPAM_CONFIRME)
        for thread_id in _ids_threads_lus(executions):
            thread = api.get_thread(thread_id)
            for message in thread.get("messages", []):
                if isinstance(message, dict) and isinstance(message.get("id"), str):
                    api.modifier_libelles(message["id"], ajouter=[id_confirme])


class Checkpoint(BaseModel):
    """État persisté d'un run : étapes validées, synthèses d'étapes, rapport."""

    model_config = ConfigDict(extra="forbid")

    run_id: UUID
    etapes_validees: list[str]
    syntheses: dict[str, SyntheseEtape] = {}
    rapport: RapportFinal | None = None


def _dossier_checkpoints() -> Path:
    return RACINE_PROJET / parametres_courants().chemins.checkpoints


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


def requete_spam(registre: RegistreLibelles, resolveur: ResolveurLibelles) -> str:
    """Requête du scan spam : base `spam.requete` (settings) hors messages déjà
    confirmés spam — libellé « spam confirmé » (clé `suivi.spam-confirme`) résolu
    via le registre (idempotence du spam, T9.6) ; jamais de libellé en dur."""
    resolveur.resoudre(CLE_SPAM_CONFIRME)
    return f'{parametres_courants().spam.requete} -label:"{registre.libelle(CLE_SPAM_CONFIRME)}"'


def requete_suppression(registre: RegistreLibelles, resolveur: ResolveurLibelles) -> str:
    """Requête du run de suppression (T+24h) : notifications traitées depuis plus de
    24 h.

    `label:"<traité>" label:"<notification>" older_than:24h` — seules
    les messages de catégorie `notification` (clé logique `classification.notification`)
    sont éligibles (décision D47) ; le délai de grâce est de 24 h (D47). Les libellés
    physiques proviennent du registre et sont résolus/créés via le resolveur ; jamais de
    nom de libellé en dur dans le code. La clause `doublon` a été retirée (D59 ; phase 6
    non embarquée, D46 — à ré-ajouter à la reprise). Le libellé UNREAD n'est jamais
    retiré par le pipeline (action utilisateur).
    """
    resolveur.resoudre(CLE_TRAITE)
    resolveur.resoudre(CLE_NOTIFICATION)
    return (
        f'label:"{registre.libelle(CLE_TRAITE)}" '
        f'label:"{registre.libelle(CLE_NOTIFICATION)}" '
        f"older_than:{parametres_courants().suppression.delai_grace}"
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
        executions_spam: list[Any] = []
        if "lecture_spam" not in checkpoint.etapes_validees:
            synthese, executions_spam = _lancer_etape(
                AGENT_SPAM,
                "lecture_spam",
                requete_spam(reg, resolveur),
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
            _appliquer_libelles_spam(synthese_s, executions_spam, resolveur, api)
            _valider_etape(checkpoint, "validation_spam", dossier)

        etape_courante = "lecture_classification"
        if "lecture_classification" not in checkpoint.etapes_validees:
            synthese, _executions = _lancer_etape(
                AGENT_CLASSIFICATION,
                "lecture_classification",
                requete_non_lus(reg, resolveur),
                rid,
                reg,
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
            _valider_et_labelliser_classification(synthese_c, resolveur, api)
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
                resume=aggreger(checkpoint.syntheses, nb_doublons=0),
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
    """Run de suppression séparé (planifié T+24h) : conversation agent suppression sur
    `label:"<traité>" label:"<notification>" older_than:24h`
    (notifications seules éligibles, délai 24 h — D47 ; clause doublon retirée, D59).

    Corbeille uniquement : l'agent applique lui-même `TRASH` via `label_message` pendant
    la conversation (écriture journalisée en dry-run, règle E) ; l'orchestrateur valide
    (C1–C3 + garde de complétude action, dans `lancer_conversation`) et checkpoint.
    `dry_run=True` par défaut (règle E). Rejet → `echec_partiel` + `etape_fautive`,
    checkpoint persisté, exception relancée (arrêt propre). Idempotence : la requête
    `older_than:24h` et l'exclusion de la corbeille par la recherche Gmail.
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
            synthese, _executions = _lancer_etape(
                AGENT_SUPPRESSION,
                ETAPE_LECTURE_SUPPRESSION,
                requete_suppression(reg, resolveur),
                rid,
                reg,
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
                resume=aggreger(checkpoint.syntheses, nb_doublons=0),
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
