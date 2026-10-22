"""Digit-only provider timestamps cannot become an ISO date on Python 3.14."""

from datetime import UTC, datetime

import pytest

from src.core.time_parsing import parse_datetime

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1792030500000", datetime(2026, 10, 15, 2, 15, tzinfo=UTC)),
        ("1792072200000", datetime(2026, 10, 15, 13, 50, tzinfo=UTC)),
        ("1792030500", datetime(2026, 10, 15, 2, 15, tzinfo=UTC)),
    ],
)
def test_numeric_provider_timestamp_keeps_its_instant(value: str, expected: datetime) -> None:
    assert parse_datetime(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("20261015", datetime(2026, 10, 15, tzinfo=UTC)),
        ("2026-10-15", datetime(2026, 10, 15, tzinfo=UTC)),
        ("2026-10-15T02:15:00Z", datetime(2026, 10, 15, 2, 15, tzinfo=UTC)),
        ("Thu, 15 Oct 2026 04:15:00 +0200", datetime(2026, 10, 15, 2, 15, tzinfo=UTC)),
    ],
)
def test_supported_calendar_and_mail_dates_keep_their_instant(
    value: str, expected: datetime
) -> None:
    assert parse_datetime(value) == expected
