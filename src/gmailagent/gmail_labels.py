# -------------------------------------------------------------------

# Application  : gmailAgent

# Script       : gmail_labels.py

# Version      : 1.0

# Date         : 11-11-2026

# Design       : TSC + Mistral Vibe

# Build        : Mistral Vibe

# -------------------------------------------------------------------

"""Résolution runtime des libellés Gmail : clé logique -> `labelId` (cache par run), création si
le libellé manque."""
from typing import Protocol, TypedDict

from gmailagent.core_config import RegistreLibelles
from gmailagent.core_journalisation import obtenir_logger

CleLogique = str


class LibelleGmail(TypedDict):
    """Libellé Gmail renvoyé par l'API (`id` + `name`)."""
    id: str
    name: str


class ClientGmail(Protocol):
    """Protocole du client Gmail utilisé par le resolveur (satisfait par `ClientGmailAPI`)."""
    def list_labels(self) -> list[LibelleGmail]:
        """Liste les libellés existants du compte."""

    def create_label(self, name: str) -> LibelleGmail:
        """Crée un libellé et retourne son `id`."""


class LibelleIrresolubleError(RuntimeError):
    """Libellé introuvable et impossible à créer."""
    pass


class ResolveurLibelles:
    """Résout les clés logiques du registre en `labelId` Gmail : cache par run, création à la
    demande (dry-run : placeholder journalisé)."""
    def __init__(
        self,
        registre: RegistreLibelles,
        client: ClientGmail,
        *,
        dry_run: bool = False,
    ) -> None:
        """Initialise le resolveur : registre (clés -> libellés physiques), client Gmail,
        indicateur dry-run."""
        self._registre = registre
        self._client = client
        self._dry_run = dry_run
        self._cache: dict[CleLogique, str] = {}
        self._labels_vus = False
        self._log = obtenir_logger("labels")

    def resoudre(self, cle: CleLogique) -> str:
        """Retourne le `labelId` de la clé logique (cache, puis liste des libellés, puis
        création)."""
        if cle not in self._cache:
            self._rafraichir()
        if cle in self._cache:
            return self._cache[cle]
        return self._creer(cle)

    def _rafraichir(self) -> None:
        """Charge une seule fois la liste des libellés existants dans le cache (libellé physique
        -> `labelId`)."""
        if self._labels_vus:
            return
        self._labels_vus = True
        existants = {libelle["name"]: libelle["id"] for libelle in self._client.list_labels()}
        for cle, nom in self._registre.iter_cles():
            if nom in existants:
                self._cache[cle] = existants[nom]

    def _creer(self, cle: CleLogique) -> str:
        """Crée le libellé physique de la clé et le met en cache (dry-run : id `DRYRUN:`
        journalisé, non créé)."""
        nom = self._registre.libelle(cle)
        if self._dry_run:
            placeholder = f"DRYRUN:{nom}"
            self._log.warning(
                "dry-run : création de libellé journalisée, non exécutée",
                cle=cle,
                libelle=nom,
                action="create_label",
                dry_run=True,
            )
            self._cache[cle] = placeholder
            return placeholder
        try:
            cree = self._client.create_label(nom)
        except Exception as erreur:
            raise LibelleIrresolubleError(
                f"création du libellé {nom!r} (clé {cle}) impossible : {erreur}"
            ) from erreur
        self._log.info("libellé créé", cle=cle, libelle=nom, labelId=cree["id"])
        self._cache[cle] = cree["id"]
        return cree["id"]
