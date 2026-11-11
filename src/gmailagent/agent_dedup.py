# -------------------------------------------------------------------

# Application  : gmailAgent

# Script       : agent_dedup.py

# Version      : 1.0

# Date         : 11-11-2026

# Design       : TSC + Mistral Vibe

# Build        : Mistral Vibe

# -------------------------------------------------------------------

"""Normalisation et empreintes SHA-256 pour le dédoublonnage (conception §3).

Clé primaire : l'en-tête Message-ID (RFC 5322), normalisé. Clé secondaire : empreinte
SHA-256 du triplet (expéditeur, sujet, corps) normalisés. L'orchestrateur recalcule ces
valeurs à partir des sorties réelles de `get_thread` et rejette la synthèse en cas
d'écart (contrôle C6). Le groupement par doublons reste en phase 6.
"""

import base64
import hashlib
import quopri
import re
from html.parser import HTMLParser
from typing import Any

_PREFIXES_SUJET = re.compile(r"^(re|fwd|tr)\s*:\s*", re.IGNORECASE)
_ESPACES = re.compile(r"\s+")


def normaliser_message_id(valeur: str) -> str:
    """Normalise un Message-ID RFC 5322 : chevrons retirés, espaces normalisés, minuscules."""
    return _ESPACES.sub(" ", valeur.strip().strip("<>").strip()).lower()


def normaliser_sujet(sujet: str) -> str:
    """Normalise un sujet : minuscules, préfixes Re:/Fwd:/Tr: retirés en boucle, espaces
    normalisés."""
    s = sujet.lower()
    while True:
        nouveau = _PREFIXES_SUJET.sub("", s)
        if nouveau == s:
            return _ESPACES.sub(" ", s).strip()
        s = nouveau


def normaliser_expediteur(expediteur: str) -> str:
    """Normalise un expéditeur : minuscules, espaces normalisés."""
    return _ESPACES.sub(" ", expediteur.lower()).strip()


class _Textiseur(HTMLParser):
    """Parser HTML (HTMLParser) qui accumule le texte brut ; voir la méthode `texte`."""
    def __init__(self) -> None:
        """Initialise la liste des morceaux de texte."""
        super().__init__()
        self._morceaux: list[str] = []

    def handle_data(self, data: str) -> None:
        """Accumule un morceau de texte brut reçu du parser HTML."""
        self._morceaux.append(data)

    def texte(self) -> str:
        """Retourne le texte accumulé (morceaux joints par des espaces)."""
        return " ".join(self._morceaux)


def html_vers_texte(html: str) -> str:
    """Convertit un fragment HTML en texte brut via `_Textiseur`."""
    textiseur = _Textiseur()
    textiseur.feed(html)
    return textiseur.texte()


def normaliser_corps(corps: str, est_html: bool = False) -> str:
    """Normalise un corps de message : conversion HTML si `est_html`, puis minuscules et espaces
    normalisés."""
    texte = html_vers_texte(corps) if est_html else corps
    return _ESPACES.sub(" ", texte.lower()).strip()


def empreinte_sha256(expediteur: str, sujet: str, corps: str) -> str:
    """Empreinte SHA-256 hexadécimale du triplet (expéditeur, sujet, corps), champs séparés par
    des retours à la ligne."""
    h = hashlib.sha256()
    h.update(expediteur.encode("utf-8"))
    h.update(b"\n")
    h.update(sujet.encode("utf-8"))
    h.update(b"\n")
    h.update(corps.encode("utf-8"))
    return h.hexdigest()


def _entete(headers: list[Any], nom: str) -> str:
    """Valeur de l'en-tête `nom` (insensible à la casse) dans une liste d'en-têtes Gmail ; chaîne
    vide sinon."""
    for h in headers:
        if isinstance(h, dict) and str(h.get("name", "")).lower() == nom.lower():
            return str(h.get("value", ""))
    return ""


def _decoder_data(data: str, transfer_encoding: str) -> str:
    """Décode le champ `data` d'une partie MIME (base64url, plus quoted-printable si l'encodage
    de transfert l'exige)."""
    brut = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))
    if transfer_encoding.lower() == "quoted-printable":
        brut = quopri.decodestring(brut)
    return brut.decode("utf-8", errors="replace")


def _collecter_texte(part: dict[str, Any]) -> str:
    """Extrait le texte d'une partie MIME du payload (décodage, HTML vers texte, récursion sur
    les sous-parties, text/plain prioritaire)."""
    headers = {
        str(h.get("name", "")).lower(): str(h.get("value", ""))
        for h in part.get("headers", [])
        if isinstance(h, dict)
    }
    mime = str(part.get("mimeType", ""))
    body = part.get("body")
    data = body.get("data") if isinstance(body, dict) else None
    texte = ""
    if isinstance(data, str) and data:
        texte = _decoder_data(data, headers.get("content-transfer-encoding", ""))
    if "html" in mime.lower():
        texte = html_vers_texte(texte)
    parts = part.get("parts")
    if isinstance(parts, list) and parts:
        sous = [p for p in parts if isinstance(p, dict)]
        plain = [p for p in sous if "text/plain" in str(p.get("mimeType", ""))]
        if plain:
            return _collecter_texte(plain[0])
        morceaux = [t for t in (_collecter_texte(p) for p in sous) if t]
        if morceaux:
            return texte + "\n" + "\n".join(morceaux) if texte else "\n".join(morceaux)
    return texte


def empreinte_message(message: dict[str, Any]) -> tuple[str, str]:
    """Recalcule (message_id_rfc normalisé, empreinte) depuis une sortie réelle get_thread."""
    payload = message.get("payload")
    if not isinstance(payload, dict):
        return "", ""
    headers = payload.get("headers", [])
    message_id = normaliser_message_id(_entete(headers, "Message-ID"))
    sujet = normaliser_sujet(_entete(headers, "Subject"))
    expediteur = normaliser_expediteur(_entete(headers, "From"))
    corps = normaliser_corps(_collecter_texte(payload))
    return message_id, empreinte_sha256(expediteur, sujet, corps)
