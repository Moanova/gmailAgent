import logging
from pathlib import Path

import structlog
import structlog.contextvars
import structlog.dev
import structlog.processors
import structlog.stdlib
from structlog.types import Processor

from env import optionnel

_configure = False


def configurer(run_id: str, etape: str | None = None) -> None:
    global _configure
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

    chemin_log = optionnel("LOG_FILE", "logs/gmailagent.log")
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


def obtenir_logger(nom: str) -> structlog.stdlib.BoundLogger:
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(nom)
    return logger
