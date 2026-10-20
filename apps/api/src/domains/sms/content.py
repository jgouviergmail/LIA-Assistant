"""Unreadable ciphertext is an unavailable source, never an empty message."""

from src.core.exceptions import ExternalServiceError
from src.core.security.utils import decrypt_data


def read_sms_content(value: str) -> str:
    try:
        return decrypt_data(value)
    except ValueError:
        raise ExternalServiceError("sms", detail="SMS_CONTENT_UNAVAILABLE") from None
