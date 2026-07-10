"""Integration tests: active-run lock, subscriber presence, replay boundary.

ADR-117 Lot 2 — semantics proven by POC-L2-1 (lock) and the Lot 1 broker
(streams), exercised here against real Redis.
"""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest
from redis.asyncio import Redis

from src.core.config import settings
from src.infrastructure.streaming.run_stream_broker import (
    _LISTENER_INCR_LUA,
    active_run_key,
    get_active_run,
    has_listeners,
    listener_decr,
    listener_incr,
    listeners_key,
    publish_chunk,
    publish_end,
    refresh_active_run,
    register_active_run,
    release_active_run,
    run_stream_key,
    subscribe,
)

pytestmark = pytest.mark.integration


@pytest.fixture
async def redis_client():
    """Real Redis client (same decode mode as get_redis_cache). Skips if down."""
    try:
        redis = Redis.from_url(str(settings.redis_url), decode_responses=True)
        await redis.ping()
        yield redis
        await redis.aclose()
    except Exception as e:  # noqa: BLE001 — environment guard, not logic
        pytest.skip(f"Redis not available: {e}")


class TestActiveRunLock:
    async def test_acquire_refuse_get_roundtrip(self, redis_client) -> None:
        conv = f"conv_{uuid.uuid4().hex[:8]}"
        try:
            assert await register_active_run(redis_client, conv, run_id="R1", stream_id="S1")
            # Second run refused while the first holds the lock
            assert not await register_active_run(redis_client, conv, run_id="R2", stream_id="S2")
            active = await get_active_run(redis_client, conv)
            assert active == {"run_id": "R1", "stream_id": "S1"}
            # TTL armed
            assert await redis_client.ttl(active_run_key(conv)) > 0
        finally:
            await redis_client.delete(active_run_key(conv))

    async def test_refresh_owner_only(self, redis_client) -> None:
        conv = f"conv_{uuid.uuid4().hex[:8]}"
        try:
            await register_active_run(redis_client, conv, run_id="R1", stream_id="S1")
            assert await refresh_active_run(redis_client, conv, "S1") is True
            # A zombie (older stream) cannot refresh a newer run's lock
            assert await refresh_active_run(redis_client, conv, "S_old") is False
        finally:
            await redis_client.delete(active_run_key(conv))

    async def test_release_is_zombie_safe(self, redis_client) -> None:
        conv = f"conv_{uuid.uuid4().hex[:8]}"
        try:
            await register_active_run(redis_client, conv, run_id="R1", stream_id="S1")
            await release_active_run(redis_client, conv, "S_zombie")  # no-op
            assert await get_active_run(redis_client, conv) is not None
            await release_active_run(redis_client, conv, "S1")  # owner
            assert await get_active_run(redis_client, conv) is None
        finally:
            await redis_client.delete(active_run_key(conv))

    async def test_corrupt_value_reads_as_no_active_run(self, redis_client) -> None:
        conv = f"conv_{uuid.uuid4().hex[:8]}"
        try:
            await redis_client.set(active_run_key(conv), "not-json")
            assert await get_active_run(redis_client, conv) is None
        finally:
            await redis_client.delete(active_run_key(conv))


class TestListenerPresence:
    async def test_incr_decr_floor_and_has_listeners(self, redis_client) -> None:
        stream_id = f"s_{uuid.uuid4().hex[:8]}"
        try:
            assert await has_listeners(redis_client, stream_id) is False
            assert await listener_incr(redis_client, stream_id) == 1
            assert await listener_incr(redis_client, stream_id) == 2
            assert await has_listeners(redis_client, stream_id) is True
            assert await listener_decr(redis_client, stream_id) == 1
            assert await listener_decr(redis_client, stream_id) == 0
            # Floor: a spurious extra decrement never goes negative
            assert await listener_decr(redis_client, stream_id) == 0
            assert await has_listeners(redis_client, stream_id) is False
        finally:
            await redis_client.delete(listeners_key(stream_id))

    async def test_incr_arms_ttl_atomically(self, redis_client) -> None:
        """Hard-kill audit: the counter must NEVER exist without a TTL.

        The old INCR-then-EXPIRE pair left a crash window producing an
        immortal counter (has_listeners() true forever -> paid TTS for
        nobody). The single Lua eval closes the window structurally: one
        atomic script sets both the count and the TTL.
        """
        stream_id = f"s_{uuid.uuid4().hex[:8]}"
        key = listeners_key(stream_id)
        try:
            assert await listener_incr(redis_client, stream_id) == 1
            ttl = await redis_client.ttl(key)
            assert 0 < ttl <= settings.background_runs_listener_ttl_seconds
        finally:
            await redis_client.delete(key)

    async def test_incr_lua_script_sets_count_and_ttl_in_one_eval(self, redis_client) -> None:
        """The Lua script itself is the atomicity proof: a single EVAL call
        (executed atomically by Redis) leaves both the incremented count and
        the armed TTL — there is no longer an 'between INCR and EXPIRE'
        state to be interrupted in."""
        key = f"test:listeners:{uuid.uuid4().hex[:8]}"
        try:
            result = await redis_client.eval(_LISTENER_INCR_LUA, 1, key, "30")
            assert int(result) == 1
            ttl = await redis_client.ttl(key)
            assert 0 < ttl <= 30
        finally:
            await redis_client.delete(key)


class TestStreamSafetyTTL:
    """Hard-kill audit: the stream key must always carry a TTL.

    Before, EXPIRE was armed at publish_end only — a producer dying without
    its terminal marker (kill -9, OOM, power loss) leaked a TTL-less key
    that the AOF persisted across reboots.
    """

    async def test_first_chunk_arms_safety_ttl(self, redis_client) -> None:
        stream_id = f"s_{uuid.uuid4().hex[:8]}"
        key = run_stream_key(stream_id)
        try:
            await publish_chunk(redis_client, stream_id, json.dumps({"i": 0}))
            ttl = await redis_client.ttl(key)
            assert 0 < ttl <= settings.background_runs_stream_safety_ttl_seconds
        finally:
            await redis_client.delete(key)

    async def test_subsequent_chunks_do_not_rearm_ttl(self, redis_client) -> None:
        """EXPIRE NX semantics: an existing TTL is never overwritten, so the
        leak bound counts from stream CREATION, not from the last chunk."""
        stream_id = f"s_{uuid.uuid4().hex[:8]}"
        key = run_stream_key(stream_id)
        try:
            await publish_chunk(redis_client, stream_id, json.dumps({"i": 0}))
            await redis_client.expire(key, 100)  # simulate an aged TTL
            await publish_chunk(redis_client, stream_id, json.dumps({"i": 1}))
            assert await redis_client.ttl(key) <= 100  # NX did not re-arm
        finally:
            await redis_client.delete(key)

    async def test_end_marker_overwrites_with_short_ttl(self, redis_client) -> None:
        """publish_end keeps its historical invariant: the short
        post-terminal TTL replaces the safety TTL (no NX there)."""
        stream_id = f"s_{uuid.uuid4().hex[:8]}"
        key = run_stream_key(stream_id)
        try:
            await publish_chunk(redis_client, stream_id, json.dumps({"i": 0}))
            await publish_end(redis_client, stream_id, "completed")
            ttl = await redis_client.ttl(key)
            assert 0 < ttl <= settings.background_runs_stream_ttl_seconds
        finally:
            await redis_client.delete(key)


class TestReplayBoundary:
    async def test_backlog_flagged_replay_live_tail_not(self, redis_client) -> None:
        stream_id = f"s_{uuid.uuid4().hex[:8]}"
        try:
            # Backlog: 3 chunks exist BEFORE the subscriber attaches
            for i in range(3):
                await publish_chunk(redis_client, stream_id, json.dumps({"i": i}))

            async def producer_tail() -> None:
                await asyncio.sleep(0.3)  # subscriber attached by then
                await publish_chunk(redis_client, stream_id, json.dumps({"i": 99}))
                await publish_end(redis_client, stream_id, "completed")

            tail_task = asyncio.create_task(producer_tail())
            flags: list[tuple[int | str, bool]] = []
            async for event in subscribe(redis_client, stream_id):
                if event.kind == "chunk":
                    flags.append((json.loads(event.payload)["i"], event.is_replay))
                elif event.kind == "end":
                    flags.append(("end", event.is_replay))
            await tail_task

            assert flags == [(0, True), (1, True), (2, True), (99, False), ("end", False)]
        finally:
            await redis_client.delete(run_stream_key(stream_id))

    async def test_fresh_stream_has_no_replay_phase(self, redis_client) -> None:
        stream_id = f"s_{uuid.uuid4().hex[:8]}"
        try:

            async def producer() -> None:
                await asyncio.sleep(0.3)
                await publish_chunk(redis_client, stream_id, json.dumps({"i": 0}))
                await publish_end(redis_client, stream_id, "completed")

            task = asyncio.create_task(producer())
            replay_flags = [
                event.is_replay
                async for event in subscribe(redis_client, stream_id)
                if event.kind != "keepalive"
            ]
            await task
            assert replay_flags == [False, False]
        finally:
            await redis_client.delete(run_stream_key(stream_id))
