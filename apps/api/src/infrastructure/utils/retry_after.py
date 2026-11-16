"""Read a server's ``Retry-After`` as the delay a delivery outbox waits.

What a remote server answers is not ours: a vendor's quota or a person's own ntfy
server may state a delay in seconds, as an HTTP date, or as something neither.
Every outbox stores the delay it waits as ``DeliveryResult.retry_after_seconds``,
which refuses anything outside one second and one day, so a delay is bounded where
it is read, once, for every transport (ADR-391).
"""

from __future__ import annotations

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

from src.core.constants import (
    DELIVERY_RETRY_AFTER_DEFAULT_SECONDS,
    DELIVERY_RETRY_AFTER_MAX_SECONDS,
)


def delivery_retry_delay(value: str | None) -> int:
    """The seconds an outbox waits before trying a delivery again.

    Args:
        value: The ``Retry-After`` header as the server sent it, or None.

    Returns:
        The stated delay, in seconds or until the stated date, held between
        ``DELIVERY_RETRY_AFTER_DEFAULT_SECONDS`` and ``DELIVERY_RETRY_AFTER_MAX_SECONDS``;
        the default when nothing readable was stated.
    """
    text = (value or "").strip()
    if not text:
        return DELIVERY_RETRY_AFTER_DEFAULT_SECONDS
    try:
        seconds = (
            int(text)
            if text.isdecimal()
            else int((parsedate_to_datetime(text) - datetime.now(UTC)).total_seconds())
        )
    except ValueError, TypeError, OverflowError:
        return DELIVERY_RETRY_AFTER_DEFAULT_SECONDS
    return max(DELIVERY_RETRY_AFTER_DEFAULT_SECONDS, min(DELIVERY_RETRY_AFTER_MAX_SECONDS, seconds))


__all__ = ["delivery_retry_delay"]
