"""Purpose-separated blind trigrams; exact text verification remains mandatory."""

from uuid import UUID

from sqlalchemy import Select, or_, select

from src.core.config import settings
from src.core.constants import SMS_DISPLAY_GRAM_CHARS, SMS_DISPLAY_INDEX_VERSION
from src.domains.shared.text_normalization import normalize_search_text
from src.domains.sms.models import SmsMessage, SmsSearchTerm
from src.domains.sms.search import blind_digest


def display_hashes(owner: UUID, text: str, *, key: bytes) -> tuple[bytes, ...]:
    """Hash each unique normalized trigram without changing the lexical index.

    Args:
        owner: Tenant owning the encryption key and message.
        text: Body or literal search fragment.
        key: Unwrapped tenant HMAC key.

    Returns:
        Opaque sorted digests; short fragments narrow nothing.
    """
    normalized = normalize_search_text(text)
    grams = {
        normalized[index : index + SMS_DISPLAY_GRAM_CHARS]
        for index in range(len(normalized) - SMS_DISPLAY_GRAM_CHARS + 1)
    }
    return tuple(
        sorted(
            bytes.fromhex(
                blind_digest(owner, f"display-{SMS_DISPLAY_INDEX_VERSION}", gram, key=key)
            )
            for gram in grams
        )
    )


def display_projection(owner: UUID, text: str, *, key: bytes) -> tuple[list[bytes], bool]:
    """Bound storage and explicitly mark a cut so it cannot produce a false negative."""
    hashes = display_hashes(owner, text, key=key)
    return (
        list(hashes[: settings.sms_display_max_index_terms]),
        len(hashes) <= settings.sms_display_max_index_terms,
    )


def display_candidates(
    statement: Select[tuple[SmsMessage]], owner: UUID, required: tuple[bytes, ...]
) -> Select[tuple[SmsMessage]]:
    """Keep matching, missing, old and incomplete projections; short queries keep all."""
    if not required:
        return statement
    valid = select(SmsSearchTerm.message_id).where(
        SmsSearchTerm.user_id == owner,
        SmsSearchTerm.message_id == SmsMessage.id,
        SmsSearchTerm.display_version == SMS_DISPLAY_INDEX_VERSION,
        SmsSearchTerm.display_complete.is_(True),
        SmsSearchTerm.display_hashes.is_not(None),
    )
    matching = select(SmsSearchTerm.message_id).where(
        SmsSearchTerm.user_id == owner,
        SmsSearchTerm.display_version == SMS_DISPLAY_INDEX_VERSION,
        SmsSearchTerm.display_hashes.contains(list(required)),
    )
    return statement.where(or_(SmsMessage.id.in_(matching), ~valid.exists()))
