"""The wake queue against a REAL Redis (ADR-261, plan test T15/T17).

Two properties are Redis's, not ours, and a mock proves neither:

* **a storm is ONE wake** — fifty notifications for the same (user, provider)
  leave a single payload, dated by the FIRST, because the payload is written
  with ``SET NX`` and its TTL is the staleness bound;
* **two sweeps never serve the same user** — the pending set is drained with
  ``SPOP``, so concurrent workers split the queue instead of duplicating a
  decision (a duplicated wake would be a duplicated notification).
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio

from src.core.constants import REDIS_KEY_WAKE_PENDING
from src.domains.push_channels.wake import (
    cooldown_key,
    enqueue_wake,
    payload_key,
    pop_wakes,
    try_acquire_wake_cooldown,
)
from src.infrastructure.cache.redis import get_redis_cache

pytestmark = pytest.mark.integration

PROVIDERS = ("google_gmail", "google_calendar", "google_drive")


@pytest_asyncio.fixture
async def redis():  # type: ignore[no-untyped-def]
    client = await get_redis_cache()
    yield client


async def _cleanup(redis, user_ids: list[uuid.UUID]) -> None:  # type: ignore[no-untyped-def]
    for user_id in user_ids:
        await redis.srem(REDIS_KEY_WAKE_PENDING, str(user_id))
        await redis.delete(cooldown_key(user_id))
        for provider in PROVIDERS:
            await redis.delete(payload_key(user_id, provider))


async def test_a_notification_storm_is_one_wake_dated_by_the_first(redis) -> None:  # type: ignore[no-untyped-def]
    user_id = uuid.uuid4()
    try:
        first = await enqueue_wake(redis, user_id, "google_gmail", ttl_seconds=300, history_id=1000)
        started = datetime.now(UTC)
        await asyncio.sleep(0.05)
        rest = [
            await enqueue_wake(redis, user_id, "google_gmail", ttl_seconds=300, history_id=1000 + n)
            for n in range(1, 50)
        ]

        assert first is True
        assert not any(rest), "a storm must queue exactly one payload"

        payloads = await pop_wakes(redis, 10, PROVIDERS)
        assert len(payloads) == 1
        # Dated by the FIRST notification: the staleness bound measures how
        # long the user has been waiting, not how recently the storm ended.
        assert payloads[0].enqueued_at <= started
        assert payloads[0].history_id == 1000
    finally:
        await _cleanup(redis, [user_id])


async def test_two_concurrent_sweeps_split_the_queue_and_never_share_a_user(redis) -> None:  # type: ignore[no-untyped-def]
    user_ids = [uuid.uuid4() for _ in range(12)]
    try:
        for user_id in user_ids:
            await enqueue_wake(redis, user_id, "google_gmail", ttl_seconds=300)

        left, right = await asyncio.gather(
            pop_wakes(redis, 12, PROVIDERS),
            pop_wakes(redis, 12, PROVIDERS),
        )
        served_left = {p.user_id for p in left}
        served_right = {p.user_id for p in right}

        assert served_left & served_right == set(), "two sweeps served the same user"
        assert served_left | served_right == set(user_ids), "a queued wake was lost"
        # And the queue is empty afterwards: payloads are deleted on read.
        assert await pop_wakes(redis, 12, PROVIDERS) == []
    finally:
        await _cleanup(redis, user_ids)


async def test_the_cooldown_admits_one_wake_per_window(redis) -> None:  # type: ignore[no-untyped-def]
    user_id = uuid.uuid4()
    try:
        assert await try_acquire_wake_cooldown(redis, user_id, minutes=5) is True
        assert await try_acquire_wake_cooldown(redis, user_id, minutes=5) is False
        # Concurrently, exactly one caller wins.
        await redis.delete(cooldown_key(user_id))
        results = await asyncio.gather(
            *(try_acquire_wake_cooldown(redis, user_id, minutes=5) for _ in range(8))
        )
        assert sum(results) == 1
    finally:
        await _cleanup(redis, [user_id])
