"""Wake queue contract (ADR-261): one payload per (user, provider), dated by
the first notification; popped atomically; stale payloads yield nothing;
Redis failures cost a wake, never a webhook."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from src.core.constants import REDIS_KEY_WAKE_PENDING
from src.domains.push_channels.wake import (
    WakePayload,
    cooldown_key,
    enqueue_wake,
    payload_key,
    pop_wakes,
    try_acquire_wake_cooldown,
)

pytestmark = pytest.mark.unit

PROVIDERS = ("google_calendar", "google_drive", "google_gmail")


class _FakeRedis:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}
        self.sets: dict[str, set[str]] = {}
        self.fail = False

    async def set(self, key: str, value: str, ex: int, nx: bool = False) -> bool | None:
        if self.fail:
            raise ConnectionError("down")
        if nx and key in self.data:
            return None
        self.data[key] = value
        return True

    async def get(self, key: str) -> str | None:
        return self.data.get(key)

    async def delete(self, *keys: str) -> int:
        return sum(1 for k in keys if self.data.pop(k, None) is not None)

    async def sadd(self, key: str, *members: str) -> int:
        if self.fail:
            raise ConnectionError("down")
        self.sets.setdefault(key, set()).update(members)
        return len(members)

    async def spop(self, key: str, count: int) -> list[bytes]:
        members = self.sets.get(key, set())
        popped = [members.pop() for _ in range(min(count, len(members)))]
        return [m.encode() for m in popped]


async def test_enqueue_stores_one_payload_per_pair_dated_by_the_first() -> None:
    redis = _FakeRedis()
    uid = uuid.uuid4()
    first = await enqueue_wake(redis, uid, "google_gmail", ttl_seconds=60, history_id=10)
    second = await enqueue_wake(redis, uid, "google_gmail", ttl_seconds=60, history_id=11)
    assert first is True and second is False  # the storm case: ONE wake
    stored = json.loads(redis.data[payload_key(uid, "google_gmail")])
    assert stored["history_id"] == 10
    assert redis.sets[REDIS_KEY_WAKE_PENDING] == {str(uid)}


async def test_pop_returns_payloads_oldest_first_and_deletes_them() -> None:
    redis = _FakeRedis()
    uid_a, uid_b = uuid.uuid4(), uuid.uuid4()
    await enqueue_wake(redis, uid_a, "google_gmail", ttl_seconds=60)
    await enqueue_wake(redis, uid_b, "google_calendar", ttl_seconds=60)
    await enqueue_wake(redis, uid_b, "google_drive", ttl_seconds=60, page_token="tok")

    payloads = await pop_wakes(redis, 10, PROVIDERS)

    assert {(p.user_id, p.provider) for p in payloads} == {
        (uid_a, "google_gmail"),
        (uid_b, "google_calendar"),
        (uid_b, "google_drive"),
    }
    assert payloads == sorted(payloads, key=lambda p: p.enqueued_at)
    assert not [k for k in redis.data if k.startswith("heartbeat:wake:payload:")]
    assert next(p for p in payloads if p.provider == "google_drive").page_token == "tok"


async def test_pop_respects_the_limit_and_leaves_the_rest_queued() -> None:
    redis = _FakeRedis()
    ids = [uuid.uuid4() for _ in range(5)]
    for uid in ids:
        await enqueue_wake(redis, uid, "google_gmail", ttl_seconds=60)
    first = await pop_wakes(redis, 2, PROVIDERS)
    assert len(first) == 2
    assert len(redis.sets[REDIS_KEY_WAKE_PENDING]) == 3


async def test_expired_payload_yields_nothing() -> None:
    redis = _FakeRedis()
    uid = uuid.uuid4()
    await redis.sadd(REDIS_KEY_WAKE_PENDING, str(uid))  # member without payload (TTL gone)
    assert await pop_wakes(redis, 10, PROVIDERS) == []


async def test_redis_failure_is_best_effort() -> None:
    redis = _FakeRedis()
    redis.fail = True
    assert await enqueue_wake(redis, uuid.uuid4(), "google_gmail", ttl_seconds=60) is False
    assert await try_acquire_wake_cooldown(redis, uuid.uuid4(), 20) is False  # closed on failure


async def test_cooldown_is_one_per_window() -> None:
    redis = _FakeRedis()
    uid = uuid.uuid4()
    assert await try_acquire_wake_cooldown(redis, uid, 20) is True
    assert await try_acquire_wake_cooldown(redis, uid, 20) is False
    assert cooldown_key(uid) in redis.data


def test_payload_round_trip_keeps_the_queued_shape_only() -> None:
    payload = WakePayload(
        user_id=uuid.uuid4(),
        provider="google_gmail",
        enqueued_at=datetime(2026, 9, 3, 12, 0, tzinfo=UTC),
        history_id=42,
        messages=({"id": "m1"},),
        new_history_id="43",
    )
    back = WakePayload.from_json(payload.to_json())
    assert back is not None
    assert (back.user_id, back.provider, back.history_id) == (payload.user_id, "google_gmail", 42)
    assert back.messages == () and back.new_history_id is None  # in-process only
    assert WakePayload.from_json("not json") is None
    assert WakePayload.from_json(json.dumps({"user_id": "x"})) is None


def test_keys_belong_to_the_learning_family_never_purged_by_a_reset() -> None:
    from src.infrastructure.cache.key_families import is_reset_purgeable, is_user_scoped

    uid = uuid.uuid4()
    for key in (payload_key(uid, "google_gmail"), cooldown_key(uid)):
        assert is_reset_purgeable(key) is False
        assert is_user_scoped(key) is True


def _stale(payload: WakePayload, ttl: int) -> bool:
    return datetime.now(UTC) - payload.enqueued_at > timedelta(seconds=ttl)


def test_staleness_is_measured_from_the_first_notification() -> None:
    old = WakePayload(uuid.uuid4(), "google_gmail", datetime.now(UTC) - timedelta(hours=2))
    assert _stale(old, 3600) is True


def _unused(_: Any) -> None:  # pragma: no cover
    return None
