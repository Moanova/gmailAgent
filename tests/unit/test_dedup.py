import base64
import hashlib

from dedup import (
    empreinte_message,
    empreinte_sha256,
    html_vers_texte,
    normaliser_corps,
    normaliser_expediteur,
    normaliser_message_id,
    normaliser_sujet,
)


def _b64url(texte: str) -> str:
    return base64.urlsafe_b64encode(texte.encode("utf-8")).decode("ascii").rstrip("=")


class TestNormalisations:
    def test_message_id(self) -> None:
        assert normaliser_message_id("  <ABC@Example.COM> ") == "abc@example.com"

    def test_sujet_prefixes_et_casse(self) -> None:
        assert normaliser_sujet("Re: Fwd:  Bonjour  le Monde") == "bonjour le monde"
        assert normaliser_sujet("TR:hello") == "hello"
        assert normaliser_sujet("Sujet simple") == "sujet simple"

    def test_expediteur(self) -> None:
        assert normaliser_expediteur("  Jean DUPONT <J@Ex.fr> ") == "jean dupont <j@ex.fr>"

    def test_corps_texte(self) -> None:
        assert normaliser_corps("Bonjour   le\nMonde") == "bonjour le monde"

    def test_corps_html(self) -> None:
        assert normaliser_corps("<p>Bonjour</p><p>le <b>monde</b></p>", est_html=True) == (
            "bonjour le monde"
        )

    def test_html_vers_texte(self) -> None:
        assert html_vers_texte("<div>A<br>B</div>") == "A B"


class TestEmpreinte:
    def test_sha256_deterministe(self) -> None:
        attendu = hashlib.sha256(b"a\nb\nc").hexdigest()
        assert empreinte_sha256("a", "b", "c") == attendu
        assert empreinte_sha256("a", "b", "c") == empreinte_sha256("a", "b", "c")
        assert empreinte_sha256("a", "b", "c") != empreinte_sha256("a", "b", "d")

    def test_empreinte_message_depuis_payload(self) -> None:
        message = {
            "id": "m1",
            "payload": {
                "mimeType": "text/plain",
                "headers": [
                    {"name": "Message-ID", "value": "<AbC@Ex.fr>"},
                    {"name": "Subject", "value": "Re: Bonjour"},
                    {"name": "From", "value": "Jean <J@Ex.fr>"},
                ],
                "body": {"data": _b64url("Corps du message")},
            },
        }
        message_id, empreinte = empreinte_message(message)
        assert message_id == "abc@ex.fr"
        attendu = empreinte_sha256(
            normaliser_expediteur("Jean <J@Ex.fr>"),
            normaliser_sujet("Re: Bonjour"),
            normaliser_corps("Corps du message"),
        )
        assert empreinte == attendu

    def test_empreinte_message_multipart_prefere_text_plain(self) -> None:
        message = {
            "payload": {
                "mimeType": "multipart/alternative",
                "headers": [
                    {"name": "Message-ID", "value": "x@y.fr"},
                    {"name": "Subject", "value": "S"},
                    {"name": "From", "value": "a@b.fr"},
                ],
                "parts": [
                    {
                        "mimeType": "text/plain",
                        "headers": [],
                        "body": {"data": _b64url("texte brut")},
                    },
                    {
                        "mimeType": "text/html",
                        "headers": [],
                        "body": {"data": _b64url("<p>texte <b>html</b></p>")},
                    },
                ],
            }
        }
        _, empreinte = empreinte_message(message)
        attendu = empreinte_sha256("a@b.fr", "s", "texte brut")
        assert empreinte == attendu

    def test_empreinte_message_sans_payload(self) -> None:
        assert empreinte_message({}) == ("", "")

    def test_decodage_quoted_printable(self) -> None:
        import quopri

        brut = quopri.encodestring("Café au lait".encode())
        data = base64.urlsafe_b64encode(brut).decode("ascii").rstrip("=")
        message = {
            "payload": {
                "mimeType": "text/plain",
                "headers": [
                    {"name": "Message-ID", "value": "q@r.fr"},
                    {"name": "Subject", "value": "S"},
                    {"name": "From", "value": "a@b.fr"},
                    {"name": "Content-Transfer-Encoding", "value": "quoted-printable"},
                ],
                "body": {"data": data},
            }
        }
        _, empreinte = empreinte_message(message)
        assert empreinte == empreinte_sha256("a@b.fr", "s", "café au lait")
