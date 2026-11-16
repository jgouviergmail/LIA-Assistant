"""A delivery outbox reads a server's ``Retry-After`` through one bounded door.

What a remote server answers is not ours: a vendor's quota or a person's own ntfy
server may state any delay, in seconds or as a date, or something neither. The
outbox stores the delay as ``DeliveryResult.retry_after_seconds``, which refuses
anything outside one second and one day — so a delay read without bounds is a
``ValueError`` waiting in the worker.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import pytest

from src.core.constants import (
    DELIVERY_RETRY_AFTER_DEFAULT_SECONDS,
    DELIVERY_RETRY_AFTER_MAX_SECONDS,
)
from src.domains.ingestion.delivery_types import DeliveryDisposition, DeliveryResult
from src.infrastructure.utils.retry_after import delivery_retry_delay

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("value", [None, "", "   "])
def test_no_stated_delay_is_the_outbox_default(value: str | None) -> None:
    assert delivery_retry_delay(value) == DELIVERY_RETRY_AFTER_DEFAULT_SECONDS


def test_a_delay_in_seconds_is_kept() -> None:
    assert delivery_retry_delay("120") == 120


def test_a_delay_shorter_than_the_floor_waits_the_floor() -> None:
    assert delivery_retry_delay("5") == DELIVERY_RETRY_AFTER_DEFAULT_SECONDS


def test_a_delay_longer_than_a_day_waits_a_day() -> None:
    assert delivery_retry_delay("99999999999999999999") == DELIVERY_RETRY_AFTER_MAX_SECONDS


@pytest.mark.parametrize(
    "value",
    [
        "²",  # a digit for str.isdigit(), not for int()
        "soon",
        "-30",
        "1.5",
        "Wed, 99 Foo 2026 25:00:00 GMT",
    ],
)
def test_what_reads_as_no_delay_waits_the_default(value: str) -> None:
    assert delivery_retry_delay(value) == DELIVERY_RETRY_AFTER_DEFAULT_SECONDS


def test_a_date_is_read_as_the_time_left_until_it() -> None:
    in_two_hours = datetime.now(UTC) + timedelta(hours=2)

    delay = delivery_retry_delay(format_datetime(in_two_hours, usegmt=True))

    assert 7200 - 5 <= delay <= 7200


def test_a_date_already_past_waits_the_floor() -> None:
    an_hour_ago = datetime.now(UTC) - timedelta(hours=1)

    assert delivery_retry_delay(format_datetime(an_hour_ago, usegmt=True)) == (
        DELIVERY_RETRY_AFTER_DEFAULT_SECONDS
    )


@pytest.mark.parametrize("value", [None, "1", "120", "99999999999999999999", "²"])
def test_every_delay_read_is_one_the_outbox_accepts(value: str | None) -> None:
    result = DeliveryResult(
        DeliveryDisposition.RETRYABLE, retry_after_seconds=delivery_retry_delay(value)
    )

    assert 1 <= result.retry_after_seconds <= DELIVERY_RETRY_AFTER_MAX_SECONDS
