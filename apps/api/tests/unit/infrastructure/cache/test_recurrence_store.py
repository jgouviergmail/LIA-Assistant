"""Recurrence store: the forget surface and the one per-day append rule.

The conversation reset no longer touches ``recurrence:{uid}:*``; the explicit
"forget everything" surface must, or the candidates under observation would
come back from data the user asked to forget (ADR-260).

A day keeps ONE hour per clock hour (ADR-375): the first five asks of a busy
day used to fill the day and bias every hour descriptor toward the morning.
"""

from __future__ import annotations

import fnmatch

import pytest

from src.infrastructure.cache import recurrence_store

pytestmark = pytest.mark.unit

UID = "00000000-0000-4000-8000-000000000001"
OTHER = "00000000-0000-4000-8000-000000000002"


class _FakeRedis:
    def __init__(self, keys: list[str]) -> None:
        self.data = dict.fromkeys(keys, "1")

    def scan_iter(self, match: str) -> object:
        async def _iter() -> object:
            for key in list(self.data):
                if fnmatch.fnmatchcase(key, match):
                    yield key.encode()

        return _iter()

    async def delete(self, *keys: str) -> int:
        removed = 0
        for key in keys:
            if key in self.data:
                del self.data[key]
                removed += 1
        return removed


async def test_delete_user_ledger_removes_only_that_user() -> None:
    redis = _FakeRedis(
        [
            recurrence_store.redis_key(UID, "email"),
            recurrence_store.redis_key(UID, "web_search"),
            recurrence_store.redis_key(OTHER, "event"),
            f"presence:{UID}:2026-09-03:14",
        ]
    )

    deleted = await recurrence_store.delete_user_ledger(redis, UID)

    assert deleted == 2
    assert set(redis.data) == {
        recurrence_store.redis_key(OTHER, "event"),
        f"presence:{UID}:2026-09-03:14",
    }


async def test_delete_user_ledger_on_empty_ledger_is_zero_without_a_delete_call() -> None:
    redis = _FakeRedis([])
    assert await recurrence_store.delete_user_ledger(redis, UID) == 0


def test_add_day_hour_keeps_one_hour_per_clock_hour() -> None:
    data: dict[str, object] = {"days": {}}
    for hour in (10.1, 10.5, 11.2, 14.0, 14.3, 18.0):
        recurrence_store.add_day_hour(data, "2026-11-03", hour, cap=24)

    assert data["days"] == {"2026-11-03": [10.1, 11.2, 14.0, 18.0]}


def test_add_day_hour_reports_whether_it_stored() -> None:
    data: dict[str, object] = {"days": {"2026-11-03": [9.0]}}

    assert recurrence_store.add_day_hour(data, "2026-11-03", 9.75, cap=24) is False
    assert recurrence_store.add_day_hour(data, "2026-11-03", 10.25, cap=24) is True
    assert data["days"] == {"2026-11-03": [9.0, 10.25]}


def test_add_day_hour_respects_the_cap_on_distinct_hours() -> None:
    data: dict[str, object] = {"days": {}}
    for hour in range(8, 20):
        recurrence_store.add_day_hour(data, "2026-11-03", float(hour), cap=4)

    assert data["days"] == {"2026-11-03": [8.0, 9.0, 10.0, 11.0]}


def test_add_day_hour_rounds_to_the_stored_precision() -> None:
    data: dict[str, object] = {"days": {}}
    recurrence_store.add_day_hour(data, "2026-11-03", 7.123456, cap=24)

    assert data["days"] == {"2026-11-03": [7.12]}


def test_add_day_hour_bins_the_value_it_stores() -> None:
    """The clock hour checked is the clock hour of the value kept (9.999 is kept as 10.0)."""
    data: dict[str, object] = {"days": {"2026-11-03": [9.1]}}

    assert recurrence_store.add_day_hour(data, "2026-11-03", 9.999, cap=24) is True
    assert recurrence_store.add_day_hour(data, "2026-11-03", 10.2, cap=24) is False
    assert data["days"] == {"2026-11-03": [9.1, 10.0]}


class _GetRedis:
    def __init__(self, raw: str | None) -> None:
        self.raw = raw

    async def get(self, key: str) -> str | None:
        return self.raw


@pytest.mark.parametrize(
    "raw",
    [None, "not json", "[1, 2]", '{"days": {}, "suggested_at": 1762560000}'],
)
async def test_every_read_has_one_shape_and_no_stamp_nobody_reads(raw: str | None) -> None:
    """ADR-375 retired the chat suggestion's cooldown, the only reader of
    ``suggested_at``: what is stored is read (ADR-268), so a read neither
    invents nor carries it, and a missing, broken or legacy-stamped key
    reads as the same shape a caller can append to."""
    data = await recurrence_store.load(_GetRedis(raw), "recurrence:x:email")
    assert data == {"days": {}, "origin": recurrence_store.ORIGIN_LIVE, "intents": {}}
