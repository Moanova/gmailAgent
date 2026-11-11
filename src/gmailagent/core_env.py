# -------------------------------------------------------------------

# Application  : gmailAgent

# Script       : core_env.py

# Version      : 1.0

# Date         : 11-11-2026

# Design       : TSC + Mistral Vibe

# Build        : Mistral Vibe

# -------------------------------------------------------------------

"""Lecture des secrets via les variables d'environnement (`os.environ` uniquement, règle D de
AGENTS.md)."""
import os


class VariableManquanteError(RuntimeError):
    """Variable d'environnement requise absente ou vide."""
    pass


def requis(nom: str) -> str:
    """Retourne la valeur de la variable `nom` ; lève `VariableManquanteError` si elle est
    absente ou vide."""
    valeur = os.environ.get(nom)
    if not valeur:
        raise VariableManquanteError(
            f"Variable d'environnement {nom} requise — "
            "copier .env.example en .env et la renseigner, "
            "ou l'exporter dans l'environnement courant."
        )
    return valeur


def optionnel(nom: str, defaut: str) -> str:
    """Retourne la valeur de la variable `nom`, ou `defaut` si elle est absente ou vide."""
    return os.environ.get(nom) or defaut
