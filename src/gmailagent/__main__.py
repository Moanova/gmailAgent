# -------------------------------------------------------------------

# Application  : gmailAgent

# Script       : __main__.py

# Version      : 1.0

# Date         : 11-11-2026

# Design       : TSC + Mistral Vibe

# Build        : Mistral Vibe

# -------------------------------------------------------------------

"""Point d'entrée `python -m gmailagent` (équivalent à la commande `gmailagent`)."""

import sys

from gmailagent.cli import main

if __name__ == "__main__":
    sys.exit(main())
