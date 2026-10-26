from pathlib import Path
from typing import Annotated

import yaml
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, ValidationError

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


class ClassificationLibelles(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    a_repondre: Libelle = Field(alias="a-repondre")
    information: Libelle
    notification: Libelle


class SuiviLibelles(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    traite: Libelle
    doublon: Libelle
    valide_spam: Libelle = Field(alias="valide-spam")


class RegistreLibelles(BaseModel):
    classification: ClassificationLibelles
    suivi: SuiviLibelles


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
