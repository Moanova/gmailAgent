# -------------------------------------------------------------------

# Application  : gmailAgent

# Script       : gmail_client.py

# Version      : 1.0

# Date         : 11-11-2026

# Design       : TSC + Mistral Vibe

# Build        : Mistral Vibe

# -------------------------------------------------------------------

"""Client Gmail concret : câblage OAuth (refresh token) + API Gmail.

Le token est produit une seule fois par `scripts/init_oauth.py` (tâche T1.7)
dans `data/gmail_token.json` (dossier `data/` ignoré par git) et rechargé ici
via `Credentials.from_authorized_user_info` ; `google-auth` renouvelle
l'access_token automatiquement (pas d'expiration calendaire du refresh token
tant que l'app reste « En production »).

En mode dry-run (règle E de AGENTS.md), les appels d'écriture (création de
libellé, modification de libellés — dont TRASH) sont journalisés mais jamais
exécutés. Les appels de lecture sont plafonnés (garde-fou anti-boucle).
"""

import json
from pathlib import Path
from typing import Any, cast

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from gmailagent.core_config import RACINE_PROJET, parametres_courants
from gmailagent.core_journalisation import obtenir_logger
from gmailagent.gmail_labels import ClientGmail, LibelleGmail

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


class TokenGmailError(RuntimeError):
    """Token Gmail (`data/gmail_token.json`) illisible ou malformé."""
    pass


class PlafondLecturesAtteintError(RuntimeError):
    """Garde-fou anti-boucle : plafond d'appels de lecture dépassé."""
    pass


def _chemin_token_par_defaut() -> Path:
    """Chemin du token Gmail par défaut (paramètre `chemins.token_gmail`, racine du projet)."""
    return RACINE_PROJET / parametres_courants().chemins.token_gmail


def charger_credentials(chemin: str | Path | None = None) -> Credentials:
    """Charge les credentials OAuth depuis le fichier token JSON ; lève `TokenGmailError` sinon."""
    cible = Path(chemin) if chemin is not None else _chemin_token_par_defaut()
    try:
        donnees = json.loads(cible.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as erreur:
        raise TokenGmailError(
            f"token Gmail illisible : {cible} — réexécuter scripts/init_oauth.py (T1.7 partie B)"
        ) from erreur
    if not isinstance(donnees, dict):
        raise TokenGmailError(f"token Gmail malformé (objet JSON attendu) : {cible}")
    return cast(
        Credentials,
        Credentials.from_authorized_user_info(donnees, SCOPES),  # type: ignore[no-untyped-call]
    )


class ClientGmailAPI:
    """Client Gmail réel (googleapiclient) ; satisfait le protocole `ClientGmail`
    de `labels.py` (`list_labels`, `create_label`) et expose les opérations du
    pipeline : `search_threads`, `get_thread`, `modifier_libelles` (TRASH y passe)."""

    def __init__(
        self,
        service: Any,
        *,
        dry_run: bool = False,
        plafond_lectures: int | None = None,
    ) -> None:
        """Initialise le client : service googleapiclient, mode dry-run, plafond de lectures
        (défaut : paramètre `plafond_lectures`)."""
        self._service = service
        self._dry_run = dry_run
        self._plafond = (
            plafond_lectures
            if plafond_lectures is not None
            else parametres_courants().limites.plafond_lectures
        )
        self._lectures = 0
        self._log = obtenir_logger("gmail")

    @classmethod
    def depuis_token(
        cls, chemin: str | Path | None = None, *, dry_run: bool = False
    ) -> "ClientGmailAPI":
        """Construit un client depuis le fichier token (`chemin`, ou `data/gmail_token.json` par
        défaut)."""
        credentials = charger_credentials(chemin)
        service = build("gmail", "v1", credentials=credentials, cache_discovery=False)
        return cls(service, dry_run=dry_run)

    def _compter_lecture(self, outil: str) -> None:
        """Compte un appel de lecture et lève `PlafondLecturesAtteintError` au-delà du plafond."""
        self._lectures += 1
        if self._lectures > self._plafond:
            raise PlafondLecturesAtteintError(
                f"garde-fou anti-boucle : {self._lectures} appels de lecture "
                f"(plafond {self._plafond}) — abandon propre du run"
            )
        self._log.debug("appel de lecture", outil=outil, lectures=self._lectures)

    def _journaliser_ecriture(self, action: str, **kwargs: Any) -> None:
        """Journalise (warning) une écriture neutralisée en dry-run (règle E)."""
        self._log.warning(
            "dry-run : écriture journalisée, non exécutée",
            action=action,
            dry_run=True,
            **kwargs,
        )

    def list_labels(self) -> list[LibelleGmail]:
        """Liste les libellés du compte Gmail."""
        self._compter_lecture("list_labels")
        reponse = self._service.users().labels().list(userId="me").execute()
        bruts = cast(list[dict[str, str]], reponse.get("labels", []))
        return [
            LibelleGmail(id=brut["id"], name=brut["name"])
            for brut in bruts
            if "id" in brut and "name" in brut
        ]

    def create_label(self, name: str) -> LibelleGmail:
        """Crée un libellé (dry-run : journalisé, retourne un id `DRYRUN:`)."""
        if self._dry_run:
            self._journaliser_ecriture("create_label", libelle=name)
            return LibelleGmail(id=f"DRYRUN:{name}", name=name)
        reponse = self._service.users().labels().create(userId="me", body={"name": name}).execute()
        brut = cast(dict[str, str], reponse)
        return LibelleGmail(id=brut["id"], name=brut["name"])

    def search_threads(self, query: str, max_results: int | None = None) -> list[str]:
        """Recherche des threads (requête `query`, `maxResults`) et retourne leurs ids."""
        if max_results is None:
            max_results = parametres_courants().limites.max_resultats
        self._compter_lecture("search_threads")
        reponse = (
            self._service.users()
            .threads()
            .list(userId="me", q=query, maxResults=max_results)
            .execute()
        )
        bruts = cast(list[dict[str, str]], reponse.get("threads", []))
        return [brut["id"] for brut in bruts if "id" in brut]

    def get_thread(self, thread_id: str) -> dict[str, Any]:
        """Retourne le thread complet (JSON brut de l'API)."""
        self._compter_lecture("get_thread")
        return cast(
            dict[str, Any],
            self._service.users().threads().get(userId="me", id=thread_id).execute(),
        )

    def get_message(self, message_id: str) -> dict[str, Any]:
        """Retourne le message complet (JSON brut de l'API)."""
        self._compter_lecture("get_message")
        return cast(
            dict[str, Any],
            self._service.users().messages().get(userId="me", id=message_id).execute(),
        )

    def modifier_libelles(
        self,
        message_id: str,
        ajouter: list[str] | None = None,
        retirer: list[str] | None = None,
    ) -> None:
        """Ajoute/retire des libellés sur un message (dry-run : journalisé, non exécuté, règle E)
        ; TRASH y passe pour la suppression."""
        if self._dry_run:
            self._journaliser_ecriture(
                "modify",
                message_id=message_id,
                ajouter=ajouter or [],
                retirer=retirer or [],
            )
            return
        body: dict[str, list[str]] = {}
        if ajouter:
            body["addLabelIds"] = ajouter
        if retirer:
            body["removeLabelIds"] = retirer
        self._service.users().messages().modify(userId="me", id=message_id, body=body).execute()

def nouveau_client(
    chemin: str | Path | None = None, *, dry_run: bool = False
) -> ClientGmail:
    """Fabrique typée contre le protocole `ClientGmail` (vérifié par mypy)."""
    return ClientGmailAPI.depuis_token(chemin, dry_run=dry_run)
