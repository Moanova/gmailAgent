from uuid import UUID, uuid4

import pytest

from config import RegistreLibelles
from contracts import MessageClasse, MessageLu, Meta


@pytest.fixture
def meta() -> Meta:
    return Meta(run_id=uuid4(), etape="classification", agent="classification")


@pytest.fixture
def meta_fixe() -> Meta:
    return Meta(
        run_id=UUID("12345678-1234-5678-1234-567812345678"),
        etape="spam",
        agent="spam",
    )


@pytest.fixture
def registre() -> RegistreLibelles:
    return RegistreLibelles.model_validate(
        {
            "classification": {
                "a-repondre": "Agent/a-repondre",
                "information": "Agent/information",
                "notification": "Agent/notification",
            },
            "suivi": {
                "traite": "Agent/traité",
                "doublon": "Agent/doublon",
                "valide-spam": "Agent/valide-spam",
            },
        }
    )


@pytest.fixture
def message_lu() -> MessageLu:
    return MessageLu(
        id="18c1f2a3b4c5d6e7",
        objet="Sujet du message",
        expediteur="expediteur@exemple.fr",
        motif="Message nécessitant une réponse",
    )


@pytest.fixture
def message_classe(message_lu: MessageLu) -> MessageClasse:
    return MessageClasse(
        **message_lu.model_dump(),
        categorie="classification.a-repondre",
        urgence="haute",
        message_id_rfc="abc123@exemple.fr",
        empreinte="a" * 64,
    )
