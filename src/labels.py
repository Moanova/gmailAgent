from collections.abc import Iterator
from enum import StrEnum
from typing import Protocol, TypedDict

from config import RegistreLibelles
from journalisation import obtenir_logger


class LibelleGmail(TypedDict):
    id: str
    name: str


class ClientGmail(Protocol):
    def list_labels(self) -> list[LibelleGmail]: ...

    def create_label(self, name: str) -> LibelleGmail: ...


class CleLogique(StrEnum):
    A_REPONDRE = "classification.a-repondre"
    INFORMATION = "classification.information"
    NOTIFICATION = "classification.notification"
    TRAITE = "suivi.traite"
    DOUBLON = "suivi.doublon"
    VALIDE_SPAM = "suivi.valide-spam"


class LibelleIrresolubleError(RuntimeError):
    pass


def _libelle_physique(registre: RegistreLibelles, cle: CleLogique) -> str:
    return {
        CleLogique.A_REPONDRE: registre.classification.a_repondre,
        CleLogique.INFORMATION: registre.classification.information,
        CleLogique.NOTIFICATION: registre.classification.notification,
        CleLogique.TRAITE: registre.suivi.traite,
        CleLogique.DOUBLON: registre.suivi.doublon,
        CleLogique.VALIDE_SPAM: registre.suivi.valide_spam,
    }[cle]


def iter_cles(registre: RegistreLibelles) -> Iterator[tuple[CleLogique, str]]:
    for cle in CleLogique:
        yield cle, _libelle_physique(registre, cle)


class ResolveurLibelles:
    def __init__(
        self,
        registre: RegistreLibelles,
        client: ClientGmail,
        *,
        dry_run: bool = False,
    ) -> None:
        self._registre = registre
        self._client = client
        self._dry_run = dry_run
        self._cache: dict[CleLogique, str] = {}
        self._labels_vus = False
        self._log = obtenir_logger("labels")

    def resoudre(self, cle: CleLogique) -> str:
        if cle not in self._cache:
            self._rafraichir()
        if cle in self._cache:
            return self._cache[cle]
        return self._creer(cle)

    def _rafraichir(self) -> None:
        if self._labels_vus:
            return
        self._labels_vus = True
        existants = {libelle["name"]: libelle["id"] for libelle in self._client.list_labels()}
        for cle, nom in iter_cles(self._registre):
            if nom in existants:
                self._cache[cle] = existants[nom]

    def _creer(self, cle: CleLogique) -> str:
        nom = _libelle_physique(self._registre, cle)
        if self._dry_run:
            placeholder = f"DRYRUN:{nom}"
            self._log.warning(
                "dry-run : création de libellé journalisée, non exécutée",
                cle=cle.value,
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
                f"création du libellé {nom!r} (clé {cle.value}) impossible : {erreur}"
            ) from erreur
        self._log.info("libellé créé", cle=cle.value, libelle=nom, labelId=cree["id"])
        self._cache[cle] = cree["id"]
        return cree["id"]
