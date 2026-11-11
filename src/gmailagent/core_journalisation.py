import logging
from pathlib import Path

import structlog
import structlog.contextvars
import structlog.dev
import structlog.processors
import structlog.stdlib
from structlog.types import Processor

from gmailagent.core_config import parametres_courants
from gmailagent.core_env import optionnel

_configure = False
_run_id_courant: str | None = None


def configurer(run_id: str, etape: str | None = None) -> None:
    global _configure, _run_id_courant
    if _configure and run_id != _run_id_courant:
        # Nouveau run dans un processus déjà configuré (ex. --tout : plusieurs runs
        # se succèdent) : re-liaison du run_id + nouvel en-tête de run.
        structlog.contextvars.bind_contextvars(run_id=run_id)
        if etape is not None:
            structlog.contextvars.bind_contextvars(etape=etape)
        _run_id_courant = run_id
        obtenir_logger("run").info("début de run", evenement="debut_run")
    if _configure:
        return
    _configure = True

    structlog.contextvars.bind_contextvars(run_id=run_id)
    if etape is not None:
        structlog.contextvars.bind_contextvars(etape=etape)

    processeurs: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    console = logging.StreamHandler()
    console.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=processeurs,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.dev.ConsoleRenderer(),
            ],
        )
    )

    chemin_log = optionnel("LOG_FILE", parametres_courants().chemins.journal)
    Path(chemin_log).parent.mkdir(parents=True, exist_ok=True)
    fichier = logging.FileHandler(chemin_log, encoding="utf-8")
    fichier.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=processeurs,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.JSONRenderer(),
            ],
        )
    )

    logging.basicConfig(
        level=optionnel("LOG_LEVEL", "INFO").upper(),
        handlers=[console, fichier],
        force=True,
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # En-tête horodatée de run : chaque exécution est encadrée dans le fichier de log
    # par une ligne `debut_run` (le run_id est déjà lié via contextvars ci-dessus).
    _run_id_courant = run_id
    obtenir_logger("run").info("début de run", evenement="debut_run")


def marquer_fin_run(statut: str) -> None:
    """Pied de page horodaté de run (séparation des exécutions dans le fichier de log)."""
    obtenir_logger("run").info("fin de run", evenement="fin_run", statut=statut)


def obtenir_logger(nom: str) -> structlog.stdlib.BoundLogger:
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(nom)
    return logger
