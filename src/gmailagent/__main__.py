"""Point d'entrée `python -m gmailagent` (équivalent à la commande `gmailagent`)."""

import sys

from gmailagent.cli import main

if __name__ == "__main__":
    sys.exit(main())
