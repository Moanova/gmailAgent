# -------------------------------------------------------------------
# Application  : gmailAgent
# Script       : core_config.py
# Version      : 1.0
# Date         : 11-11-2026
# Design       : TSC + Mistral Vibe
# Build        : Mistral Vibe
# -------------------------------------------------------------------

"""Configuration du projet : registre de libellés (`config/labels.yaml`) et paramètres du
pipeline (`config/settings.yaml`, optionnel), modèles Pydantic stricts (extra=forbid)."""

from pathlib import Path
from typing import Annotated, Any

import yaml
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, ValidationError

PREFIXE_LIBELLE = "Agent/"
RACINE_PROJET = Path(__file__).resolve().parents[2]


class RegistreInvalideError(RuntimeError):
    """Registre de libellés introuvable, illisible ou invalide."""
    pass


def _valide_libelle(valeur: str) -> str:
    """Valide un libellé physique : préfixe `Agent/` obligatoire et nom non vide."""
    if not valeur.startswith(PREFIXE_LIBELLE) or len(valeur) == len(PREFIXE_LIBELLE):
        raise ValueError(
            f"libellé invalide {valeur!r} : "
            f"doit commencer par {PREFIXE_LIBELLE!r} et être non vide"
        )
    return valeur


Libelle = Annotated[str, AfterValidator(_valide_libelle)]
GroupeLibelles = dict[str, Libelle]


def _valide_groupe(valeur: GroupeLibelles) -> GroupeLibelles:
    """Valide un groupe de libellés non vide."""
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
        """Valide un registre depuis le YAML brut (dict groupe -> clé -> libellé), enveloppé dans
        le champ `groupes`."""
        if not isinstance(obj, dict):
            raise ValidationError.from_exception_data(
                "RegistreLibelles", [{"type": "dict", "loc": (), "input": obj}]
            )
        return super().model_validate({"groupes": obj}, **kwargs)

    def cle(self, groupe: str, cle: str) -> str:
        """Construit la clé logique complète à partir du groupe et du nom (`groupe.nom`)."""
        return f"{groupe}.{cle}"

    def libelle(self, cle: str) -> str:
        """Libellé physique associé à une clé logique ; lève `RegistreInvalideError` si la clé
        est inconnue."""
        groupe, _, nom = cle.partition(".")
        try:
            return self.groupes[groupe][nom]
        except KeyError:
            raise RegistreInvalideError(f"clé logique inconnue : {cle!r}") from None

    def iter_cles(self) -> list[tuple[str, str]]:
        """Liste des couples (clé logique, libellé physique) du registre."""
        return [
            (self.cle(groupe, nom), libelle)
            for groupe, cles in self.groupes.items()
            for nom, libelle in cles.items()
        ]


def _chemin_par_defaut() -> Path:
    """Chemin par défaut du registre : `config/labels.yaml` à la racine du projet."""
    return RACINE_PROJET / "config" / "labels.yaml"


def charger_registre(chemin: str | Path | None = None) -> RegistreLibelles:
    """Charge et valide le registre de libellés (`chemin`, ou `config/labels.yaml` par défaut)."""
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


class Chemins(BaseModel):
    """Chemins runtime relatifs à la racine du projet (token Gmail, checkpoints, journal)."""
    model_config = ConfigDict(extra="forbid")

    token_gmail: str = "data/gmail_token.json"
    checkpoints: str = "data/checkpoints"
    journal: str = "logs/gmailagent.log"


class Modele(BaseModel):
    """Modèle Mistral par défaut (la variable d'environnement `MISTRAL_MODEL` reste prioritaire)."""
    model_config = ConfigDict(extra="forbid")

    defaut: str = Field(min_length=1, default="mistral-small-latest")


class Limites(BaseModel):
    """Limites et plafonds du pipeline (surchargés par `config/settings.yaml`)."""
    model_config = ConfigDict(extra="forbid")

    max_tokens: int = Field(ge=1, default=8000)
    plafond_appels_outils: int = Field(ge=1, default=50)
    max_tentatives_synthese: int = Field(ge=1, default=3)
    max_threads_par_run: int = Field(ge=1, default=25)
    marge_appels_reprise: int = Field(ge=0, default=3)
    plafond_lectures: int = Field(ge=1, default=100)
    max_resultats: int = Field(ge=1, default=50)
    limite_corps_apercu: int = Field(ge=1, default=2000)
    limite_reponse_outil: int = Field(ge=1, default=20000)
    plafond_runs_tout: int = Field(ge=1, default=10)
    timeout_http_ms: int = Field(ge=1, default=300_000)

    def cap_threads_recherche(self) -> int:
        """Cap de threads renvoyés par `search_threads` dans un run (D58).

        Cohérent avec le budget d'appels par construction : pire cas conforme =
        1 search + 2 appels par thread (`get_thread` + `get_message`), plus la marge
        de reprises après erreur d'outil (D56). Invariant :
        `plafond_appels_outils >= 2 * cap + 1 + marge_appels_reprise`.
        """
        return max(
            1,
            min(
                self.max_threads_par_run,
                (self.plafond_appels_outils - 1 - self.marge_appels_reprise) // 2,
            ),
        )


class ParametresSuppression(BaseModel):
    """Paramètres du run de suppression (délai de grâce avant corbeille)."""
    model_config = ConfigDict(extra="forbid")

    delai_grace: str = Field(min_length=1, default="24h")


class ParametresSpam(BaseModel):
    """Paramètres du scan spam (requête de base, ex. `in:spam`)."""
    model_config = ConfigDict(extra="forbid")

    requete: str = Field(min_length=1, default="in:spam")


class Parametres(BaseModel):
    """Paramètres du pipeline, chargés depuis `config/settings.yaml` (optionnel : sans
    fichier, les défauts du code s'appliquent).

    Priorité : argument explicite ou variable d'environnement > ce fichier > défaut
    du code. Les libellés `Agent/*` restent dans `labels.yaml` (registre), les
    libellés système TRASH/SPAM/INBOX et les contrats restent dans le code (D43, D2).
    """

    model_config = ConfigDict(extra="forbid")

    chemins: Chemins = Field(default_factory=Chemins)
    modele: Modele = Field(default_factory=Modele)
    limites: Limites = Field(default_factory=Limites)
    suppression: ParametresSuppression = Field(default_factory=ParametresSuppression)
    spam: ParametresSpam = Field(default_factory=ParametresSpam)


class ParametresInvalidesError(RuntimeError):
    """Fichier de paramètres introuvable, illisible ou invalide."""
    pass


def _chemin_parametres_par_defaut() -> Path:
    """Chemin par défaut des paramètres : `config/settings.yaml` à la racine du projet."""
    return RACINE_PROJET / "config" / "settings.yaml"


def charger_parametres(chemin: str | Path | None = None) -> Parametres:
    """Charge les paramètres depuis `chemin` ; sans chemin ni fichier, retourne les défauts du
    code."""
    if chemin is not None:
        cible = Path(chemin)
        if not cible.exists():
            raise ParametresInvalidesError(f"paramètres introuvables : {cible}")
    else:
        cible = _chemin_parametres_par_defaut()
        if not cible.exists():
            return Parametres()
    try:
        texte = cible.read_text(encoding="utf-8")
    except OSError as erreur:
        raise ParametresInvalidesError(f"paramètres illisibles : {cible}") from erreur
    try:
        donnees = yaml.safe_load(texte)
    except yaml.YAMLError as erreur:
        raise ParametresInvalidesError(f"YAML invalide dans {cible} : {erreur}") from erreur
    if donnees is None:
        return Parametres()
    try:
        return Parametres.model_validate(donnees)
    except ValidationError as erreur:
        raise ParametresInvalidesError(f"paramètres invalides dans {cible} : {erreur}") from erreur


_parametres_courants: Parametres | None = None


def parametres_courants() -> Parametres:
    """Paramètres courants, chargés une fois et mis en cache (voir `definir_parametres`)."""
    global _parametres_courants
    if _parametres_courants is None:
        _parametres_courants = charger_parametres()
    return _parametres_courants


def definir_parametres(valeur: Parametres | None) -> None:
    """Remplace les paramètres courants en mémoire (tests) ; `None` réinitialise le cache."""
    global _parametres_courants
    _parametres_courants = valeur
