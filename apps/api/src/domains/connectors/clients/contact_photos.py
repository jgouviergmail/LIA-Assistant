"""A contact's photo, on the three clients (ADR-369, lot 9).

One contract: a read answers the bytes and their type, or None for no photo; a write replaces it;
a removal takes it off. What a provider or a card calls a photo is believed only when its first
bytes agree, so a card's script never leaves as an image, and only a JPEG or a PNG does.

Google names an address, read here without the person's token: only on the hosts Google draws
photos from, through ``pinned_stream`` and under a ceiling, never following a redirect. A card's
photo is read from the bytes it holds (``ENCODING=b``, vCard 3.0, iCloud's own form); an address
it names is never followed: it is anybody's.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

import httpx
import structlog
import vobject

from src.core.constants import WORKBENCH_CONTACT_PHOTO_READ_MAX_BYTES
from src.infrastructure.utils.bounded_read import (
    ACCEPT_ENCODING_HEADER,
    BodyTooLargeError,
    read_bounded,
)
from src.infrastructure.utils.url_validation import pinned_stream, validate_url

logger = structlog.get_logger(__name__)

#: The hosts Google serves a contact's photo from.
_GOOGLE_PHOTO: Final = re.compile(r"https://lh[3-6]\.googleusercontent\.com/[^@\s]*")
_FETCH_TIMEOUT_SECONDS: Final = 10.0
_KINDS: Final = {"image/jpeg": "JPEG", "image/png": "PNG"}


@dataclass(frozen=True, slots=True)
class ContactPhoto:
    """An image and its type, the one its first bytes say."""

    data: bytes
    mime_type: str


def photo_type(data: bytes) -> str | None:
    """The type a photo's first bytes say; None for anything else."""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    return None


def photo_of(data: bytes) -> ContactPhoto | None:
    """Bytes as a photo, when they are one."""
    kind = photo_type(data)
    return ContactPhoto(data, kind) if kind else None


async def fetch_photo(url: str) -> ContactPhoto | None:
    """What Google draws at an address it named; None for anything that is not that.

    Args:
        url: The address, from the provider's own answer.

    Returns:
        The photo; None when it is on another host, unanswered, too large or no image.
    """
    if not _GOOGLE_PHOTO.fullmatch(url):
        return None
    verdict = await validate_url(url)
    if not verdict.valid:
        return None
    try:
        async with (
            httpx.AsyncClient(follow_redirects=False) as http,
            pinned_stream(
                http,
                "GET",
                verdict,
                headers={"Accept-Encoding": ACCEPT_ENCODING_HEADER},
                timeout=_FETCH_TIMEOUT_SECONDS,
            ) as response,
        ):
            if not response.is_success:
                return None
            data = await read_bounded(response, WORKBENCH_CONTACT_PHOTO_READ_MAX_BYTES)
    except (httpx.HTTPError, BodyTooLargeError) as error:
        logger.debug("contact_photo_unread", error_type=type(error).__name__)
        return None
    return photo_of(data)


def card_photo(card_text: str) -> ContactPhoto | None:
    """The photo a card holds; never what it points at.

    Args:
        card_text: A vCard.

    Returns:
        The photo; None when it holds none, or holds what is no image.
    """
    card = vobject.readOne(card_text, ignoreUnreadable=True)
    lines = card.contents.get("photo") or []
    data = lines[0].value if lines else None
    return photo_of(data) if isinstance(data, bytes) else None


def card_with_photo(card_text: str, photo: ContactPhoto | None) -> str:
    """A card with its photo replaced or taken off; every other line stays.

    Args:
        card_text: A vCard.
        photo: The new photo; None takes it off.

    Returns:
        The card, serialized.
    """
    card = vobject.readOne(card_text, ignoreUnreadable=True)
    card.contents.pop("photo", None)
    if photo is not None:
        line = card.add("photo")
        line.value = photo.data
        line.encoding_param = "b"
        line.type_param = _KINDS[photo.mime_type]
    return str(card.serialize())


__all__ = [
    "ContactPhoto",
    "card_photo",
    "card_with_photo",
    "fetch_photo",
    "photo_of",
    "photo_type",
]
