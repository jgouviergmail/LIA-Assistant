"""How the radio can refuse (ADR-324).

Every refusal names itself with a stable code (``detail.code``) the web app
translates in the listener's language; a number the reader needs (the longest
timer, the most sites) travels beside it. Built on the central taxonomy (rule
#18: never a raw ``HTTPException``) and kept in the domain, like the e-mail
share's and the bookmarks' raisers, because ``core/exceptions.py`` is
size-frozen. A session, a segment or a site that is not the caller's is
indistinguishable from one that does not exist (``hide_existence``).
"""

from __future__ import annotations

from typing import Any, Final, NoReturn
from uuid import UUID

from fastapi import status

from src.core.exceptions import BaseAPIException, ResourceNotFoundError
from src.domains.radio.setup_builder import (
    REFUSED_BUDGET,
    REFUSED_INSTANCE_FULL,
    REFUSED_NO_VOICE,
    REFUSED_VOICE_UNAVAILABLE,
)

#: The instance runs as many sessions as it may (``RADIO_MAX_ACTIVE_SESSIONS``).
INSTANCE_FULL: Final = "radio_instance_full"
#: The voice engine the radio is configured on offers no voice at all.
NO_VOICE: Final = "radio_no_voice"
#: The voice engine the radio is configured on cannot be served (no key, no client).
VOICE_UNAVAILABLE: Final = "radio_voice_unavailable"
#: The listener's radio spent its rolling day's budget (``RADIO_BUDGET_24H_EUR``):
#: the bound and the instant it lifts travel beside the code.
BUDGET_REACHED: Final = "radio_budget_reached"
#: A setting asks for a longer automatic stop than the instance allows.
TIMER_TOO_LONG: Final = "radio_timer_too_long"
#: A setting names a voice the radio's engine does not offer.
VOICE_UNKNOWN: Final = "radio_voice_unknown"
#: A setting names a personality that does not exist or is not offered any more.
PERSONALITY_UNKNOWN: Final = "radio_personality_unknown"
#: The listener already added as many sites as the instance allows.
SOURCE_LIMIT: Final = "radio_source_limit"
#: The address given does not lead to a feed the radio can read.
SOURCE_REFUSED: Final = "radio_source_refused"

#: What each refusal answers.
_STATUSES: Final[dict[str, int]] = {
    INSTANCE_FULL: status.HTTP_503_SERVICE_UNAVAILABLE,
    NO_VOICE: status.HTTP_503_SERVICE_UNAVAILABLE,
    VOICE_UNAVAILABLE: status.HTTP_503_SERVICE_UNAVAILABLE,
    BUDGET_REACHED: status.HTTP_429_TOO_MANY_REQUESTS,
    TIMER_TOO_LONG: status.HTTP_422_UNPROCESSABLE_CONTENT,
    VOICE_UNKNOWN: status.HTTP_422_UNPROCESSABLE_CONTENT,
    PERSONALITY_UNKNOWN: status.HTTP_422_UNPROCESSABLE_CONTENT,
    SOURCE_LIMIT: status.HTTP_409_CONFLICT,
    SOURCE_REFUSED: status.HTTP_422_UNPROCESSABLE_CONTENT,
}

#: The start refusals the setup and the admission raise, by their reason word.
START_REFUSALS: Final[dict[str, str]] = {
    REFUSED_INSTANCE_FULL: INSTANCE_FULL,
    REFUSED_NO_VOICE: NO_VOICE,
    REFUSED_VOICE_UNAVAILABLE: VOICE_UNAVAILABLE,
    REFUSED_BUDGET: BUDGET_REACHED,
}


def refuse(code: str, **detail: Any) -> NoReturn:
    """Refuse with a stable code.

    Args:
        code: One of this module's codes.
        **detail: Facts the reader needs beside the code (``max_minutes``,
            ``max_eur`` and ``lifts_at``).

    Raises:
        BaseAPIException: With ``detail = {"code": code, **detail}``.
    """
    status_code = _STATUSES[code]
    raise BaseAPIException(
        status_code=status_code,
        detail={"code": code, **detail},
        log_level="info" if status_code < 500 else "warning",
        log_event="radio_refused",
        refusal=code,
    )


def raise_session_not_found(session_id: UUID) -> NoReturn:
    """404 for a session that is not the caller's or does not exist.

    Raises:
        ResourceNotFoundError: 404 Not Found.
    """
    raise ResourceNotFoundError(resource_type="radio_session", resource_id=session_id)


def raise_segment_not_found(session_id: UUID) -> NoReturn:
    """404 for a segment that is not ready, not the caller's, or gone.

    Raises:
        ResourceNotFoundError: 404 Not Found.
    """
    raise ResourceNotFoundError(resource_type="radio_segment", resource_id=session_id)


def raise_source_not_found(source_id: UUID) -> NoReturn:
    """404 for a site that is not the caller's or does not exist.

    Raises:
        ResourceNotFoundError: 404 Not Found.
    """
    raise ResourceNotFoundError(resource_type="radio_source", resource_id=source_id)


def raise_article_not_found(story_id: UUID) -> NoReturn:
    """404 for a story that does not exist or is not the caller's to read.

    Raises:
        ResourceNotFoundError: 404 Not Found.
    """
    raise ResourceNotFoundError(resource_type="radio_article", resource_id=story_id)


__all__ = [
    "BUDGET_REACHED",
    "INSTANCE_FULL",
    "NO_VOICE",
    "PERSONALITY_UNKNOWN",
    "SOURCE_LIMIT",
    "SOURCE_REFUSED",
    "START_REFUSALS",
    "TIMER_TOO_LONG",
    "VOICE_UNAVAILABLE",
    "VOICE_UNKNOWN",
    "raise_article_not_found",
    "raise_segment_not_found",
    "raise_session_not_found",
    "raise_source_not_found",
    "refuse",
]
