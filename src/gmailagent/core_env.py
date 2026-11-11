import os


class VariableManquanteError(RuntimeError):
    pass


def requis(nom: str) -> str:
    valeur = os.environ.get(nom)
    if not valeur:
        raise VariableManquanteError(
            f"Variable d'environnement {nom} requise — "
            "copier .env.example en .env et la renseigner, "
            "ou l'exporter dans l'environnement courant."
        )
    return valeur


def optionnel(nom: str, defaut: str) -> str:
    return os.environ.get(nom) or defaut
