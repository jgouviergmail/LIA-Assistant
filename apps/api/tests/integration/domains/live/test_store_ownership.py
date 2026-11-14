"""Real Redis interleavings must never let an old Live task overwrite a successor."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import uuid4

import pytest
from redis.asyncio import Redis

from src.core.conversation_execution import ExecutionRevoked
from src.domains.live.session_store import LiveSessionRecord, LiveSessionStore
from tests.fixtures.conversation_executions import redis_client as redis_client

pytestmark = pytest.mark.integration


def record() -> LiveSessionRecord:
    now = datetime.now(UTC)
    return LiveSessionRecord(
        session_id=uuid4().hex,
        user_id=uuid4(),
        provider="gemini",
        model="fixture",
        run_id=uuid4().hex,
        started_at=now,
        expires_at=now + timedelta(minutes=10),
        token=uuid4().hex,
    )


@pytest.mark.parametrize("operation", ["extend", "release"])
async def test_a_successor_survives_a_delayed_old_record_command(
    redis_client: Redis, monkeypatch: pytest.MonkeyPatch, operation: Literal["extend", "release"]
) -> None:
    store = LiveSessionStore(redis_client)
    first = record()
    next_record = replace(first, session_id=uuid4().hex, token=uuid4().hex)
    assert await store.claim(first, ttl_seconds=60)
    paused, proceed = asyncio.Event(), asyncio.Event()
    original_set, original_delete = redis_client.set, redis_client.delete

    async def delayed_set(key: str, value: str, *, ex: int) -> object:
        if key == store._record_key(first.user_id) and value == first.to_json():
            paused.set()
            await proceed.wait()
        return await original_set(key, value, ex=ex)

    async def delayed_delete(*keys: str) -> object:
        if store._record_key(first.user_id) in keys:
            paused.set()
            await proceed.wait()
        return await original_delete(*keys)

    monkeypatch.setattr(redis_client, "set", delayed_set)
    if operation == "release":
        monkeypatch.setattr(redis_client, "delete", delayed_delete)
    act = asyncio.create_task(
        store.extend(first, ttl_seconds=120)
        if operation == "extend"
        else store.release(first.user_id, first.token)
    )
    observed = asyncio.create_task(paused.wait())
    try:
        # An atomic implementation has no split command to pause; it finishes
        # first. Both legal orderings must preserve the successor below.
        await asyncio.wait_for(
            asyncio.wait((act, observed), return_when=asyncio.FIRST_COMPLETED), 5
        )
        await original_delete(store._claim_key(first.user_id))
        assert await store.claim(next_record, ttl_seconds=60)
        proceed.set()
        await act
        assert await store.get(first.user_id) == next_record
    finally:
        proceed.set()
        observed.cancel()
        await asyncio.gather(act, observed, return_exceptions=True)


async def test_a_record_whose_token_disagrees_with_the_claim_is_never_read(
    redis_client: Redis,
) -> None:
    store = LiveSessionStore(redis_client)
    first = record()
    assert await store.claim(first, ttl_seconds=60)
    await redis_client.set(store._claim_key(first.user_id), uuid4().hex, ex=60)
    assert await store.get(first.user_id) is None


async def test_a_stale_session_cannot_append_turns_or_read_successor_recaps(
    redis_client: Redis,
) -> None:
    store = LiveSessionStore(redis_client)
    first = record()
    second = replace(first, session_id=uuid4().hex, token=uuid4().hex)
    assert await store.claim(first, ttl_seconds=60)
    assert await store.release(first.user_id, first.token)
    assert await store.claim(second, ttl_seconds=60)
    with pytest.raises(ExecutionRevoked):
        await store.append_turns(first, [("user", "old")], ttl_seconds=60, max_rows=2)
    with pytest.raises(ExecutionRevoked):
        await store.relays(first)
    assert await store.turns(second) == []
    assert await store.relays(second) == []


async def test_concurrent_turns_obey_the_whole_session_bound(redis_client: Redis) -> None:
    store = LiveSessionStore(redis_client)
    current = record()
    assert await store.claim(current, ttl_seconds=60)
    kept = await asyncio.gather(
        *(
            store.append_turns(current, [("user", str(index))], ttl_seconds=60, max_rows=3)
            for index in range(12)
        )
    )
    rows = await store.turns(current)
    assert sum(kept) == len(rows) == 3


async def test_two_readers_cannot_consume_the_same_offer_nonce(redis_client: Redis) -> None:
    store = LiveSessionStore(redis_client)
    current = replace(record(), nonce="synthetic-single-use", nonce_until=datetime.now(UTC))
    assert await store.claim(current, ttl_seconds=60)
    first, second = await asyncio.gather(store.get(current.user_id), store.get(current.user_id))
    assert first is not None and second is not None
    consumed = await asyncio.gather(
        *(
            store.rewrite(replace(item, nonce=None, nonce_until=None), now=datetime.now(UTC))
            for item in (first, second)
        )
    )
    assert sum(consumed) == 1
