"""Honor typed native provider refusals without sleeping or buying another attempt."""

import math
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime

import httpx
from anthropic import APIStatusError as AnthropicStatusError
from openai import APIStatusError as OpenAIStatusError

from src.core.config import settings
from src.core.exceptions import BaseAPIException


class DiscussionBackoff(ValueError):
    """A provider asked to retry later: the run defers until ``until``, never retries now."""

    def __init__(self, until: datetime) -> None:
        super().__init__("provider_backoff")
        self.until = until


def retry_deadline(error: BaseException, *, now: datetime) -> datetime | None:
    """Read when a refused call may be retried, from the error or its causes.

    A 429 always defers, a 503 only when the provider said until when. The chain
    of causes is followed, up to eight links, because provider failures arrive
    wrapped.

    Args:
        error: The exception a call raised.
        now: The current instant.

    Returns:
        The retry instant (the ``Retry-After`` value, else ``discussion_backoff_minutes``
        from now), or None when the error is not a backoff.
    """
    for _ in range(8):
        if isinstance(error, DiscussionBackoff):
            return error.until
        if isinstance(error, BaseAPIException):
            status, headers = error.status_code, error.headers or {}
        elif isinstance(error, (httpx.HTTPStatusError, OpenAIStatusError, AnthropicStatusError)):
            status, headers = error.response.status_code, error.response.headers
        else:
            status, headers = 0, {}
        header = next(
            (value for key, value in headers.items() if key.casefold() == "retry-after"), None
        )
        # A 429 always defers; a 503 only when the provider said until when.
        if status == 429 or (status == 503 and header is not None):
            return _deadline(header, now=now)
        nested = error.__cause__ or error.__context__
        if nested is None:
            break
        error = nested
    return None


def _deadline(header: str | None, *, now: datetime) -> datetime:
    if header is not None:
        try:
            seconds = float(header)
            if math.isfinite(seconds) and seconds > 0:
                return now + timedelta(seconds=max(1, math.ceil(min(seconds, 31536000))))
        except ValueError:
            try:
                date = parsedate_to_datetime(header)
                if date.tzinfo is not None and date > now:
                    return date.astimezone(UTC)
            except ValueError, TypeError, OverflowError:
                return now + timedelta(minutes=settings.discussion_backoff_minutes)
    return now + timedelta(minutes=settings.discussion_backoff_minutes)
