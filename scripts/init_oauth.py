"""Initialisation OAuth Gmail — à exécuter UNE SEULE FOIS, manuellement.

Ouvre le consentement Google dans le navigateur, échange le code
d'autorisation contre les tokens, et stocke le refresh_token dans
`data/gmail_token.json` (dossier `data/` ignoré par git).

Pré-requis (tâche T1.7) :
  - variables d'environnement GOOGLE_CLIENT_ID et GOOGLE_CLIENT_SECRET
    (renseignées dans .env ou exportées) ;
  - écran de consentement OAuth en statut « En production » sur la
    console Google Cloud (sinon le refresh_token expire après 7 jours).

Usage :
  python scripts/init_oauth.py
"""

import json
import sys
from pathlib import Path

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

RACINE = Path(__file__).resolve().parent.parent
FICHIER_TOKEN = RACINE / "data" / "gmail_token.json"


def main() -> int:
    import os

    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
    if not client_id or not client_secret:
        print(
            "GOOGLE_CLIENT_ID et GOOGLE_CLIENT_SECRET sont requis "
            "(les renseigner dans .env ou les exporter).",
            file=sys.stderr,
        )
        return 1

    if FICHIER_TOKEN.exists():
        print(f"{FICHIER_TOKEN} existe déjà — aucune ré-autorisation nécessaire.", file=sys.stderr)
        return 1

    config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }
    flow = InstalledAppFlow.from_client_config(config, SCOPES)
    credentials: Credentials = flow.run_local_server(
        host="localhost",
        port=0,
        access_type="offline",
        prompt="consent",
    )

    if not credentials.refresh_token:
        print("Aucun refresh_token reçu — réexécuter avec prompt=consent.", file=sys.stderr)
        return 1

    jeton = {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes": list(credentials.scopes or []),
    }
    FICHIER_TOKEN.parent.mkdir(parents=True, exist_ok=True)
    FICHIER_TOKEN.write_text(json.dumps(jeton, indent=2), encoding="utf-8")
    FICHIER_TOKEN.chmod(0o600)
    print(f"refresh_token stocké dans {FICHIER_TOKEN} (permissions 600).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
