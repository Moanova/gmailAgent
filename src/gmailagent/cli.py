# -------------------------------------------------------------------

# Application  : gmailAgent

# Script       : cli.py

# Version      : 1.0

# Date         : 11-11-2026

# Design       : TSC + Mistral Vibe

# Build        : Mistral Vibe

# -------------------------------------------------------------------

"""CLI gmailAgent : `tri` | `suppression` | `migrate-labels` — dry-run par défaut.

Règle E de AGENTS.md : aucune écriture Gmail sans `--reel` (en dry-run, les
écritures sont journalisées, non exécutées). Les secrets sont lus via
`os.environ` uniquement (règle D) ; le token Gmail vient de
`data/gmail_token.json` (tâche T1.7).

Usage :
  gmailagent tri [--run-id UUID] [--tout] [--reel]
  gmailagent suppression [--run-id UUID] [--reel]
  gmailagent migrate-labels ANCIEN NOUVEAU [--reel]
"""

import argparse
import json
import sys
from uuid import UUID, uuid4

from gmailagent.agent_contracts import RapportFinal
from gmailagent.core_config import parametres_courants
from gmailagent.core_journalisation import configurer, marquer_fin_run, obtenir_logger
from gmailagent.gmail_client import ClientGmailAPI
from gmailagent.pipeline_orchestrator import lancer_run_suppression, lancer_run_tri
from gmailagent.pipeline_report import formater_console

AIDE_REEL = "exécute les écritures Gmail (par défaut : dry-run, écritures journalisées)"


def _aide_tout() -> str:
    """Texte d'aide de l'option `--tout` (plafond de runs depuis les paramètres)."""
    plafond = parametres_courants().limites.plafond_runs_tout
    return (
        f"boucle de runs jusqu'à épuisement des non lus (plafond {plafond} runs, "
        "run_id distinct par run ; en dry-run : un seul run, les libellés n'étant pas posés)"
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Construit le parser argparse et parse `argv` (sous-commandes `tri`, `suppression`,
    `migrate-labels`)."""
    parser = argparse.ArgumentParser(
        prog="gmailagent",
        description="Agent personnel de traitement des messages Gmail (dry-run par défaut).",
    )
    parser.add_argument("--reel", action="store_true", help=AIDE_REEL)
    sous = parser.add_subparsers(dest="commande", required=True)

    def _sous_commande(nom: str, aide: str) -> argparse.ArgumentParser:
        p = sous.add_parser(nom, help=aide)
        # SUPPRESS : sans --reel après la sous-commande, ne pas écraser la valeur
        # du parser principal (--reel avant la sous-commande).
        p.add_argument("--reel", action="store_true", default=argparse.SUPPRESS, help=AIDE_REEL)
        return p

    p_tri = _sous_commande("tri", "run principal de tri (étapes 0-7)")
    p_tri.add_argument(
        "--run-id",
        type=UUID,
        default=None,
        help="run_id existant pour reprise sur incident",
    )
    p_tri.add_argument("--tout", action="store_true", help=_aide_tout())
    p_sup = _sous_commande(
        "suppression", "run de suppression T+24h (notifications uniquement, corbeille)"
    )
    p_sup.add_argument(
        "--run-id",
        type=UUID,
        default=None,
        help="run_id existant pour reprise sur incident",
    )
    p_mig = _sous_commande(
        "migrate-labels",
        "déplace les messages d'un ancien libellé vers un nouveau",
    )
    p_mig.add_argument("ancien", help="libellé physique source (ex. Agent/ancien)")
    p_mig.add_argument("nouveau", help="libellé physique cible (ex. Agent/nouveau)")
    return parser.parse_args(argv)


def _afficher_rapport(rapport: RapportFinal) -> None:
    """Affiche le rapport final : JSON, résumé console, statut du run."""
    print(json.dumps(rapport.model_dump(mode="json"), indent=2, ensure_ascii=False))
    print(formater_console(rapport))
    print(f"run {rapport.meta.run_id} terminé : {rapport.statut_global}")


def _cmd_tri(args: argparse.Namespace, run_id: UUID) -> int:
    """Commande `tri` : run principal (ou boucle `--tout`), affiche le rapport, retourne le code
    de sortie."""
    dry_run = not args.reel
    if getattr(args, "tout", False):
        return _cmd_tri_tout(dry_run)
    statut = "interrompu"
    try:
        rapport = lancer_run_tri(run_id, dry_run=dry_run)
        statut = rapport.statut_global
        _afficher_rapport(rapport)
        return 0 if rapport.statut_global == "succes" else 1
    finally:
        marquer_fin_run(statut)  # balise fin_run émise aussi en cas d'incident


def _cmd_tri_tout(dry_run: bool) -> int:
    """`tri --tout` : boucle de runs (run_id distinct par run) jusqu'à épuisement des
    non lus, avec plafond de runs (garde-fou). En dry-run : un seul run (les libellés
    ne sont pas posés, la boucle ne pourrait pas progresser)."""
    log = obtenir_logger("cli")
    plafond = parametres_courants().limites.plafond_runs_tout
    nb_runs = 0
    for _ in range(plafond):
        statut = "interrompu"
        try:
            rapport = lancer_run_tri(uuid4(), dry_run=dry_run)
            statut = rapport.statut_global
        finally:
            marquer_fin_run(statut)  # balise fin_run par run, même en cas d'incident
        nb_runs += 1
        _afficher_rapport(rapport)
        if statut != "succes":
            print(f"--tout : arrêt sur échec au run {nb_runs}")
            return 1
        synthese = rapport.synthese_classification
        if dry_run:
            log.info(
                "dry-run : les libellés ne sont pas posés, arrêt de --tout après le 1er run",
                nb_runs=nb_runs,
            )
            break
        if synthese is not None and synthese.statut == "aucun_message":
            break
    else:
        log.warning(
            "plafond de runs atteint (--tout)", plafond=plafond, nb_runs=nb_runs
        )
    print(f"--tout : {nb_runs} run(s) exécuté(s)")
    return 0


def _cmd_suppression(args: argparse.Namespace, run_id: UUID) -> int:
    """Commande `suppression` : run de suppression T+24h, affiche le rapport, retourne le code de
    sortie."""
    dry_run = not args.reel
    statut = "interrompu"
    try:
        rapport = lancer_run_suppression(run_id, dry_run=dry_run)
        statut = rapport.statut_global
        _afficher_rapport(rapport)
        return 0 if rapport.statut_global == "succes" else 1
    finally:
        marquer_fin_run(statut)  # balise fin_run émise aussi en cas d'incident


def _cmd_migrate_labels(args: argparse.Namespace) -> int:
    """Commande `migrate-labels` : déplace les messages d'un libellé physique vers un autre
    (dry-run par défaut)."""
    dry_run = not args.reel
    client = ClientGmailAPI.depuis_token(dry_run=dry_run)
    labels = {libelle["name"]: libelle["id"] for libelle in client.list_labels()}
    if args.ancien not in labels:
        print(f"libellé source inconnu : {args.ancien!r}", file=sys.stderr)
        return 1
    id_ancien = labels[args.ancien]
    id_nouveau = labels.get(args.nouveau)
    if id_nouveau is None:
        id_nouveau = client.create_label(args.nouveau)["id"]
    threads = client.search_threads(f'label:"{args.ancien}"')
    total = 0
    for thread_id in threads:
        for message in client.get_thread(thread_id).get("messages", []):
            message_id = message.get("id")
            if message_id:
                client.modifier_libelles(message_id, ajouter=[id_nouveau], retirer=[id_ancien])
                total += 1
    obtenir_logger("cli").info(
        "migrate-labels",
        ancien=args.ancien,
        nouveau=args.nouveau,
        threads=len(threads),
        messages=total,
        dry_run=dry_run,
    )
    mode = "dry-run" if dry_run else "réel"
    print(f"migrate-labels ({mode}) : {total} message(s) « {args.ancien} » -> « {args.nouveau} »")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Point d'entrée CLI : parse les arguments, configure la journalisation, dispatche la
    sous-commande, retourne le code de sortie."""
    args = _parse_args(argv)
    run_id: UUID = args.run_id if getattr(args, "run_id", None) is not None else uuid4()
    if not (args.commande == "tri" and getattr(args, "tout", False)):
        configurer(str(run_id))
    # En mode --tout, chaque run appelle configurer avec son propre run_id
    # (re-liaison du run_id + en-tête debut_run par run).
    try:
        if args.commande == "tri":
            return _cmd_tri(args, run_id)
        if args.commande == "suppression":
            return _cmd_suppression(args, run_id)
        try:
            rc = _cmd_migrate_labels(args)
            marquer_fin_run("succes" if rc == 0 else "echec")
            return rc
        except Exception:
            marquer_fin_run("interrompu")
            raise
    except Exception as erreur:
        print(f"erreur : {erreur}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
