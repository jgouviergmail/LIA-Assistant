"""How keeping an answer can be refused (ADR-282).

Built on the central taxonomy (rule #18: never a raw ``HTTPException``), kept
in the domain like the attachments' and the meetings' raisers so
``core/exceptions.py`` — size-frozen — does not grow by a family it has no
reason to know.
"""

from __future__ import annotations

from typing import NoReturn
from uuid import UUID

from fastapi import status

from src.core.exceptions import BaseAPIException, ResourceNotFoundError, ValidationError
from src.core.i18n import normalize_language
from src.core.i18n_api_messages import APIMessages

__all__ = [
    "BookmarkLimitReachedError",
    "raise_bookmark_limit_reached",
    "raise_bookmark_not_found",
    "raise_bookmark_nothing_to_keep",
]


class BookmarkLimitReachedError(BaseAPIException):
    """The account keeps as many bookmarks as it may — 409.

    A class of its own rather than a ``ResourceConflictError`` so a reader can
    tell « the cap » from « already kept » without parsing a sentence: the
    sentence is translated, the class is not.
    """

    def __init__(self, max_per_user: int, detail: str) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
            log_level="info",
            log_event="bookmark_limit_reached",
            max_per_user=max_per_user,
        )


def raise_bookmark_not_found(bookmark_id: UUID) -> NoReturn:
    """Raise 404 for a bookmark that is not the caller's or does not exist.

    One answer for both: « forbidden » would tell a caller the row exists
    (``hide_existence`` semantics).

    Args:
        bookmark_id: The id the caller named.

    Raises:
        ResourceNotFoundError: 404 Not Found.
    """
    raise ResourceNotFoundError(resource_type="bookmark", resource_id=bookmark_id)


def raise_bookmark_limit_reached(max_per_user: int, language: str) -> NoReturn:
    """Raise 409 when the account already keeps as many bookmarks as it may.

    Args:
        max_per_user: The published cap (ADR-184).
        language: The caller's language, for the translated sentence.

    Raises:
        BookmarkLimitReachedError: 409 Conflict.
    """
    raise BookmarkLimitReachedError(
        max_per_user=max_per_user,
        detail=APIMessages.bookmark_limit_reached(max_per_user, normalize_language(language)),
    )


def raise_bookmark_nothing_to_keep(language: str) -> NoReturn:
    """Raise 400 when the answer carries no text to keep.

    Args:
        language: The caller's language, for the translated sentence.

    Raises:
        ValidationError: 400 Bad Request.
    """
    raise ValidationError(
        detail=APIMessages.bookmark_nothing_to_keep(normalize_language(language)),
        field="message_id",
    )
