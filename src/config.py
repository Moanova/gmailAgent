from pathlib import Path
from typing import Annotated, Any

import yaml
from pydantic import AfterValidator, BaseModel, ConfigDict, ValidationError

PREFIXE_LIBELLE = "Agent/"


class RegistreInvalideError(RuntimeError):
    pass


def _valide_libelle(valeur: str) -> str:
    if not valeur.startswith(PREFIXE_LIBELLE) or len(valeur) == len(PREFIXE_LIBELLE):
        raise ValueError(
            f"libellé invalide {valeur!r} : "
            f"doit commencer par {PREFIXE_LIBELLE!r} et être non vide"
        )
    return valeur


Libelle = Annotated[str, AfterValidator(_valide_libelle)]
GroupeLibelles = dict[str, Libelle]


def _valide_groupe(valeur: GroupeLibelles) -> GroupeLibelles:
    if not valeur:
        raise ValueError("groupe de libellés vide")
    return valeur


Groupe = Annotated[GroupeLibelles, AfterValidator(_valide_groupe)]


class RegistreLibelles(BaseModel):
    """Registre des libellés : groupe -> clé logique -> libellé physique.

    Le fichier `config/labels.yaml` est la seule source de vérité : toute
    clé ajoutée au YAML devient immédiatement résoluble, sans modification
    de code (décision D4).
    """

    model_config = ConfigDict(extra="forbid")

    groupes: dict[str, Groupe]

    @classmethod
    def model_validate(cls, obj: Any, **kwargs: Any) -> "RegistreLibelles":
        if not isinstance(obj, dict):
            raise ValidationError.from_exception_data(
                "RegistreLibelles", [{"type": "dict", "loc": (), "input": obj}]
            )
        return super().model_validate({"groupes": obj}, **kwargs)

    def cle(self, groupe: str, cle: str) -> str:
        return f"{groupe}.{cle}"

    def libelle(self, cle: str) -> str:
        groupe, _, nom = cle.partition(".")
        try:
            return self.groupes[groupe][nom]
        except KeyError:
            raise RegistreInvalideError(f"clé logique inconnue : {cle!r}") from None

    def iter_cles(self) -> list[tuple[str, str]]:
        return [
            (self.cle(groupe, nom), libelle)
            for groupe, cles in self.groupes.items()
            for nom, libelle in cles.items()
        ]


def _chemin_par_defaut() -> Path:
    return Path(__file__).resolve().parent.parent / "config" / "labels.yaml"


def charger_registre(chemin: str | Path | None = None) -> RegistreLibelles:
    cible = Path(chemin) if chemin is not None else _chemin_par_defaut()
    try:
        texte = cible.read_text(encoding="utf-8")
    except OSError as erreur:
        raise RegistreInvalideError(f"registre introuvable ou illisible : {cible}") from erreur
    try:
        donnees = yaml.safe_load(texte)
    except yaml.YAMLError as erreur:
        raise RegistreInvalideError(f"YAML invalide dans {cible} : {erreur}") from erreur
    try:
        return RegistreLibelles.model_validate(donnees)
    except ValidationError as erreur:
        raise RegistreInvalideError(f"registre invalide dans {cible} : {erreur}") from erreur
