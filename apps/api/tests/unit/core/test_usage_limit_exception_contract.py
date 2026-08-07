"""The 429 contract distinguishes a personal quota from an instance pause.

The chat entry point rejects with HTTP 429 before opening the SSE stream, so
that layer must carry the same distinction the stream does — otherwise a
visitor of a paused demonstrator is told to "contact your administrator".

What must hold:
- the historical shape is untouched when no error code is supplied (a plain
  string detail), so every existing caller and client keeps working;
- an instance pause ships a STRUCTURED detail carrying the code, the same way
  the 409 active-run contract does;
- it also ships ``Retry-After`` in seconds until the next UTC day: the answer
  to "when can I come back" is computable, so it should not be a guess.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.core.constants import (
    INSTANCE_BUDGET_EXHAUSTED_ERROR_CODE,
    INSTANCE_DAILY_BUDGET_LIMIT_NAME,
)
from src.core.exceptions import UsageLimitExceededError
from src.domains.usage_limits.instance_budget import seconds_until_next_utc_day

pytestmark = pytest.mark.unit


def test_the_historical_shape_is_a_plain_string_detail() -> None:
    error = UsageLimitExceededError(limit_name="cycle_tokens", reason="quota reached")
    assert error.status_code == 429
    assert error.detail == "quota reached"
    assert error.headers is None or "Retry-After" not in error.headers


def test_an_instance_pause_ships_a_structured_detail() -> None:
    error = UsageLimitExceededError(
        limit_name=INSTANCE_DAILY_BUDGET_LIMIT_NAME,
        reason="Instance daily budget exhausted",
        error_code=INSTANCE_BUDGET_EXHAUSTED_ERROR_CODE,
        retry_after_seconds=3600,
    )
    assert isinstance(error.detail, dict)
    assert error.detail["error_code"] == INSTANCE_BUDGET_EXHAUSTED_ERROR_CODE
    assert error.detail["limit"] == INSTANCE_DAILY_BUDGET_LIMIT_NAME
    assert error.headers is not None
    assert error.headers["Retry-After"] == "3600"


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (datetime(2026, 8, 6, 0, 0, tzinfo=UTC), 86400),
        (datetime(2026, 8, 6, 23, 59, 30, tzinfo=UTC), 30),
        (datetime(2026, 8, 6, 12, 0, tzinfo=UTC), 43200),
    ],
)
def test_seconds_until_next_utc_day_is_exact(now: datetime, expected: int) -> None:
    assert seconds_until_next_utc_day(now) == expected


def test_seconds_until_next_utc_day_never_returns_zero() -> None:
    # A zero would tell the client to retry immediately into the same refusal.
    assert seconds_until_next_utc_day(datetime(2026, 8, 6, 23, 59, 59, 999999, tzinfo=UTC)) >= 1
