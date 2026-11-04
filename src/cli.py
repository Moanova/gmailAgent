"""CLI gmailAgent : `tri` | `suppression` | `migrate-labels` — dry-run par défaut.

Règle E de AGENTS.md : aucune écriture Gmail sans `--reel` (en dry-run, les
écritures sont journalisées, non exécutées). Les secrets sont lus via
`os.environ` uniquement (règle D) ; le token Gmail vient de
`data/gmail_token.json` (tâche T1.7).

Usage :
  gmailagent tri [--run-id UUID] [--reel]
  gmailagent suppression [--run-id UUID] [--reel]
  gmailagent migrate-labels ANCIEN NOUVEAU [--reel]
"""

import argparse
import json
import sys
from uuid import UUID, uuid4

from gmail import ClientGmailAPI
from journalisation import configurer, marquer_fin_run, obtenir_logger
from orchestrator import lancer_run_suppression, lancer_run_tri
from report import formater_console

AIDE_REEL = "exécute les écritures Gmail (par défaut : dry-run, écritures journalisées)"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
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


def _cmd_tri(args: argparse.Namespace, run_id: UUID) -> int:
    dry_run = not args.reel
    rapport = lancer_run_tri(run_id, dry_run=dry_run)
    print(json.dumps(rapport.model_dump(mode="json"), indent=2, ensure_ascii=False))
    print(formater_console(rapport))
    print(f"run {rapport.meta.run_id} terminé : {rapport.statut_global}")
    marquer_fin_run(rapport.statut_global)
    return 0 if rapport.statut_global == "succes" else 1


def _cmd_suppression(args: argparse.Namespace, run_id: UUID) -> int:
    dry_run = not args.reel
    rapport = lancer_run_suppression(run_id, dry_run=dry_run)
    print(json.dumps(rapport.model_dump(mode="json"), indent=2, ensure_ascii=False))
    print(formater_console(rapport))
    print(f"run {rapport.meta.run_id} terminé : {rapport.statut_global}")
    marquer_fin_run(rapport.statut_global)
    return 0 if rapport.statut_global == "succes" else 1


def _cmd_migrate_labels(args: argparse.Namespace) -> int:
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
    args = _parse_args(argv)
    run_id: UUID = args.run_id if getattr(args, "run_id", None) is not None else uuid4()
    configurer(str(run_id))
    try:
        if args.commande == "tri":
            return _cmd_tri(args, run_id)
        if args.commande == "suppression":
            return _cmd_suppression(args, run_id)
        return _cmd_migrate_labels(args)
    except Exception as erreur:
        print(f"erreur : {erreur}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
