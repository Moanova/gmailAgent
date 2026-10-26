import random
import time
from collections.abc import Callable
from typing import TypeVar

from mistralai.client import Mistral
from mistralai.client.errors import SDKError

from env import requis
from journalisation import obtenir_logger

T = TypeVar("T")

_client: Mistral | None = None
_log = obtenir_logger("client")


def obtenir_client() -> Mistral:
    global _client
    if _client is None:
        _client = Mistral(api_key=requis("MISTRAL_API_KEY"), timeout_ms=300_000)
    return _client


def _est_retentable(erreur: SDKError) -> bool:
    return erreur.status_code == 429 or 500 <= erreur.status_code < 600


def avec_retry(
    operation: Callable[[], T],
    *,
    tentatives: int = 3,
    base: float = 2.0,
    dormir: Callable[[float], None] = time.sleep,
) -> T:
    for essai in range(tentatives):
        try:
            return operation()
        except SDKError as erreur:
            retentable = _est_retentable(erreur)
            if not retentable:
                raise
            if essai == tentatives - 1:
                _log.error(
                    "echec definitif apres retries",
                    tentatives=tentatives,
                    status_code=erreur.status_code,
                )
                raise
            delai = base * 2**essai + random.uniform(0, base)
            _log.warning(
                "erreur transitoire, nouvel essai",
                tentative=essai + 1,
                tentatives=tentatives,
                status_code=erreur.status_code,
                delai=round(delai, 2),
            )
            dormir(delai)
    raise RuntimeError("avec_retry : boucle terminee sans resultat ni exception")
