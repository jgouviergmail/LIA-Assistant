"""One decoder for the source identity and its locked number write owner."""

from src.core.security.utils import decrypt_data
from src.domains.telephony.phone_numbers import to_e164
from src.domains.users.models import User
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


def stored_phone_number(actor: User) -> str | None:
    token = actor.phone_number_encrypted
    if not token:
        return None
    try:
        number = decrypt_data(token)
        if to_e164(number) != number:
            raise ValueError("Unreadable saved phone number")
        return number
    except ValueError:
        logger.warning("phone_number_decrypt_failed", user_id=str(actor.id))
        return None
