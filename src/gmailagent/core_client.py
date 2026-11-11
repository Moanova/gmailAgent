# -------------------------------------------------------------------

# Application  : gmailAgent

# Script       : core_client.py

# Version      : 1.0

# Date         : 11-11-2026

# Design       : TSC + Mistral Vibe

# Build        : Mistral Vibe

# -------------------------------------------------------------------

"""Client Mistral commun (instanciation unique) + retry avec backoff exponentiel et jitter sur
429/5xx."""
import random
import time
from collections.abc import Callable
from typing import TypeVar

from googleapiclient.errors import HttpError
from mistralai.client import Mistral
from mistralai.client.errors import SDKError

from gmailagent.core_config import parametres_courants
from gmailagent.core_env import requis
from gmailagent.core_journalisation import obtenir_logger

T = TypeVar("T")

_client: Mistral | None = None
_log = obtenir_logger("client")


def obtenir_client() -> Mistral:
    """Retourne le client Mistral singleton (créé au premier appel avec `MISTRAL_API_KEY` et le
    timeout des paramètres)."""
    global _client
    if _client is None:
        _client = Mistral(
            api_key=requis("MISTRAL_API_KEY"),
            timeout_ms=parametres_courants().limites.timeout_http_ms,
        )
    return _client


def _statut_erreur(erreur: Exception) -> int | None:
    """Code HTTP d'une erreur (SDK Mistral ou `HttpError` Gmail), `None` si indéterminé."""
    if isinstance(erreur, SDKError):
        return erreur.status_code
    if isinstance(erreur, HttpError) and erreur.resp is not None:
        return int(erreur.resp.status)
    return None


def erreur_retentable(erreur: Exception) -> bool:
    """429 ou 5xx — côté API Mistral (SDKError) comme côté outils Gmail (HttpError)."""
    statut = _statut_erreur(erreur)
    return statut == 429 or (statut is not None and 500 <= statut < 600)


def avec_retry(
    operation: Callable[[], T],
    *,
    tentatives: int = 3,
    base: float = 2.0,
    dormir: Callable[[float], None] = time.sleep,
    retentable: Callable[[Exception], bool] = erreur_retentable,
) -> T:
    """Exécute `operation` avec `tentatives` essais sur erreur retentable (429/5xx), backoff
    exponentiel + jitter entre les essais ; relance l'erreur sinon."""
    for essai in range(tentatives):
        try:
            return operation()
        except Exception as erreur:
            if not retentable(erreur):
                raise
            if essai == tentatives - 1:
                _log.error(
                    "echec definitif apres retries",
                    tentatives=tentatives,
                    statut=_statut_erreur(erreur),
                    erreur=repr(erreur),
                )
                raise
            delai = base * 2**essai + random.uniform(0, base)
            _log.warning(
                "erreur transitoire, nouvel essai",
                tentative=essai + 1,
                tentatives=tentatives,
                statut=_statut_erreur(erreur),
                delai=round(delai, 2),
            )
            dormir(delai)
    raise RuntimeError("avec_retry : boucle terminee sans resultat ni exception")
