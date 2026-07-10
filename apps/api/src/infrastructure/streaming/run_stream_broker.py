"""
Redis Streams broker for detached chat runs (ADR-117).

One stream per run (``chat:run:{run_id}``) carries the serialized
ChatStreamChunk payloads in order, terminated by a broker-level end marker
(an envelope field, NOT a ChatStreamChunk type — the SSE chunk contract is
untouched). Producers XADD; subscribers XREAD with SHORT blocking windows.

Hard-kill hardening (2026-07 audit): every chunk XADD pipelines an
``EXPIRE NX`` so the stream key carries a safety TTL from its first entry —
a producer dying without its terminal marker (kill -9, OOM, power loss) can
no longer leak a TTL-less key. ``publish_end`` overwrites it with the short
post-terminal TTL, and the listener counter arms its TTL atomically (Lua).

CRITICAL (proven by the 2026-07 de-risking POC on redis-py 8.0.1): a
blocking XREAD whose block window exceeds the client socket_timeout raises
TimeoutError. :func:`subscribe` therefore polls with
``settings.background_runs_xread_block_ms`` (default 2s, socket_timeout 30s)
and yields a keepalive event on every empty window so SSE consumers can
emit heartbeats.
"""

import json
from collections.abc import AsyncGenerator
from dataclasses import dataclass, replace
from typing import Any, Literal, cast

from redis.asyncio import Redis

from src.core.config import settings
from src.core.constants import (
    REDIS_KEY_ACTIVE_RUN_PREFIX,
    REDIS_KEY_RUN_CANCEL_PREFIX,
    REDIS_KEY_RUN_LISTENERS_PREFIX,
    REDIS_KEY_RUN_STREAM_PREFIX,
)
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

# Envelope field names (broker-level protocol, invisible to the SSE contract)
_FIELD_CHUNK = "d"
_FIELD_END = "end"
_FIELD_STATUS = "status"

# Boy Scout fix (2026-07 audit): "cancelled" (Lot 3 user stop) was published
# as a terminal status without appearing here — the tuple is documentation
# (nothing validates against it), but a lying reference is a bug.
TERMINAL_STATUSES = ("completed", "error", "killed", "cancelled")

_XREAD_COUNT = 64

# Conditional refresh/release of the active-run lock (Lot 2, POC-L2-1):
# both compare the stream_id INSIDE the stored JSON value so a zombie
# producer (older stream_id) can never touch a newer run's lock.
_REFRESH_ACTIVE_RUN_LUA = """
local raw = redis.call('GET', KEYS[1])
if not raw then return 0 end
local ok, data = pcall(cjson.decode, raw)
if ok and data['stream_id'] == ARGV[1] then
    redis.call('EXPIRE', KEYS[1], ARGV[2])
    return 1
end
return 0
"""

_RELEASE_ACTIVE_RUN_LUA = """
local raw = redis.call('GET', KEYS[1])
if not raw then return 0 end
local ok, data = pcall(cjson.decode, raw)
if ok and data['stream_id'] == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
"""

# Floor-guarded decrement of the listener counter (never below 0)
_LISTENER_DECR_LUA = """
local v = tonumber(redis.call('GET', KEYS[1]) or '0')
if v > 0 then
    v = redis.call('DECR', KEYS[1])
else
    v = 0
end
redis.call('EXPIRE', KEYS[1], ARGV[1])
return v
"""

# Atomic increment + TTL arm of the listener counter (2026-07 hard-kill audit):
# INCR and EXPIRE as two separate calls left a crash window between them — a
# counter without TTL never decays, so has_listeners() stays true forever and
# voice synthesis (paid TTS) is wrongly triggered for absent listeners.
_LISTENER_INCR_LUA = """
local v = redis.call('INCR', KEYS[1])
redis.call('EXPIRE', KEYS[1], ARGV[1])
return v
"""


@dataclass(frozen=True)
class RunStreamEvent:
    """One event delivered to a run-stream subscriber.

    Attributes:
        kind: ``"chunk"`` (payload = ChatStreamChunk JSON), ``"keepalive"``
            (empty block window — emit an SSE heartbeat), or ``"end"``
            (payload = terminal status, stream is over).
        payload: See ``kind``.
        is_replay: True while the subscriber is catching up on entries that
            already existed when it attached (Lot 2 reattach): consumers
            skip pacing and voice payloads on these, and the SSE layer
            emits a ``: replay-end`` transport comment at the boundary.
    """

    kind: Literal["chunk", "keepalive", "end"]
    payload: str
    is_replay: bool = False


def run_stream_key(run_id: str) -> str:
    """Build the Redis Stream key for a run.

    Args:
        run_id: Unique run identifier (also the SSE correlation id).

    Returns:
        The namespaced Redis key.
    """
    return f"{REDIS_KEY_RUN_STREAM_PREFIX}{run_id}"


def encode_chunk_entry(chunk_json: str) -> dict[str, str]:
    """Encode a serialized ChatStreamChunk as a stream entry.

    Args:
        chunk_json: The chunk serialized via ``ChatStreamChunk.model_dump_json()``.

    Returns:
        Entry fields for XADD.
    """
    return {_FIELD_CHUNK: chunk_json}


def encode_end_entry(status: str) -> dict[str, str]:
    """Encode the terminal marker entry.

    Args:
        status: One of :data:`TERMINAL_STATUSES`.

    Returns:
        Entry fields for XADD.
    """
    return {_FIELD_END: "1", _FIELD_STATUS: status}


def decode_entry(fields: dict[str, str]) -> RunStreamEvent:
    """Decode a raw stream entry into a :class:`RunStreamEvent`.

    The end marker takes precedence over a chunk payload (fail-closed: a
    malformed dual entry must still terminate the subscriber).

    Args:
        fields: Raw entry fields as returned by XREAD/XRANGE.

    Returns:
        The decoded event (``kind`` is ``"chunk"`` or ``"end"``).

    Raises:
        ValueError: If the entry carries neither a chunk nor an end marker.
    """
    if fields.get(_FIELD_END) == "1":
        return RunStreamEvent(kind="end", payload=fields.get(_FIELD_STATUS, "completed"))
    if _FIELD_CHUNK in fields:
        return RunStreamEvent(kind="chunk", payload=fields[_FIELD_CHUNK])
    raise ValueError(f"Unknown run-stream entry fields: {sorted(fields)}")


async def publish_chunk(redis: Redis, run_id: str, chunk_json: str) -> None:
    """Append one serialized chunk to the run stream (capped MAXLEN).

    Hard-kill hardening (2026-07 audit): every XADD is pipelined with an
    ``EXPIRE NX`` (same round-trip) so the stream key carries the safety TTL
    from its very first entry and re-arms itself if the key is ever
    re-created. Without it, a producer dying before ``publish_end`` (kill
    -9, OOM, power loss) left a TTL-less key that the AOF persisted across
    reboots. NX never overwrites an existing TTL, so the short post-terminal
    TTL armed by :func:`publish_end` stays authoritative.

    Args:
        redis: Redis client.
        run_id: Run identifier.
        chunk_json: The chunk serialized via ``ChatStreamChunk.model_dump_json()``.
    """
    key = run_stream_key(run_id)
    pipe = redis.pipeline(transaction=False)
    # cast: redis-py stubs type xadd's field dict with an invariant union key
    # type that rejects the (perfectly valid) dict[str, str].
    pipe.xadd(
        key,
        cast(dict[Any, Any], encode_chunk_entry(chunk_json)),
        maxlen=settings.background_runs_stream_maxlen,
        approximate=True,
    )
    pipe.expire(key, settings.background_runs_stream_safety_ttl_seconds, nx=True)
    await pipe.execute()


async def publish_end(redis: Redis, run_id: str, status: str) -> None:
    """Append the terminal marker and arm the stream TTL.

    Args:
        redis: Redis client.
        run_id: Run identifier.
        status: One of :data:`TERMINAL_STATUSES`.
    """
    key = run_stream_key(run_id)
    pipe = redis.pipeline(transaction=False)
    # cast: same redis-py stub invariance workaround as publish_chunk
    pipe.xadd(
        key,
        cast(dict[Any, Any], encode_end_entry(status)),
        maxlen=settings.background_runs_stream_maxlen,
        approximate=True,
    )
    # No NX: the short post-terminal TTL deliberately overwrites the safety TTL.
    pipe.expire(key, settings.background_runs_stream_ttl_seconds)
    await pipe.execute()
    logger.debug("run_stream_end_published", run_id=run_id, status=status)


async def subscribe(
    redis: Redis,
    run_id: str,
    from_id: str = "0-0",
) -> AsyncGenerator[RunStreamEvent, None]:
    """Read the run stream from ``from_id``, then follow the live tail.

    Yields :class:`RunStreamEvent` items in order; yields a ``"keepalive"``
    event on every empty block window; returns after yielding the ``"end"``
    event.

    Args:
        redis: Redis client (its socket_timeout must exceed the block
            window — enforced by settings bounds).
        run_id: Run identifier.
        from_id: Redis stream id to read after (``"0-0"`` = full replay).

    Yields:
        RunStreamEvent: Chunk, keepalive, or terminal end event.
    """
    key = run_stream_key(run_id)
    last_id = from_id
    block_ms = settings.background_runs_xread_block_ms
    # Replay boundary snapshot (Lot 2): entries at or below the CURRENT tail
    # id existed before this subscriber attached — they are replay.
    tail = cast(
        list[tuple[str, dict[str, str]]],
        await redis.xrevrange(key, max="+", min="-", count=1),
    )
    replay_boundary = _stream_entry_id_tuple(tail[0][0]) if tail else (0, 0)
    while True:
        # cast: redis-py stubs return a loose union for xread; with
        # decode_responses=True the shape is [(stream_key, [(id, fields)])].
        response = cast(
            list[tuple[str, list[tuple[str, dict[str, str]]]]],
            await redis.xread({key: last_id}, block=block_ms, count=_XREAD_COUNT),
        )
        if not response:
            yield RunStreamEvent(kind="keepalive", payload="")
            continue
        for _stream_key, entries in response:
            for entry_id, fields in entries:
                last_id = entry_id
                event = decode_entry(fields)
                if _stream_entry_id_tuple(entry_id) <= replay_boundary:
                    event = replace(event, is_replay=True)
                yield event
                if event.kind == "end":
                    return


def _stream_entry_id_tuple(entry_id: str) -> tuple[int, int]:
    """Parse a Redis stream entry id (``ms-seq``) into a comparable tuple.

    String comparison is NOT safe ("999-1" > "1000-1" lexicographically);
    numeric tuples are.
    """
    ms, _, seq = entry_id.partition("-")
    return (int(ms), int(seq or 0))


# =============================================================================
# Active-run registry (Lot 2): one lock per conversation, heartbeat-kept
# =============================================================================


def active_run_key(conversation_id: str) -> str:
    """Redis key of the per-conversation active-run lock."""
    return f"{REDIS_KEY_ACTIVE_RUN_PREFIX}{conversation_id}"


def listeners_key(stream_id: str) -> str:
    """Redis key of the per-stream subscriber-presence counter."""
    return f"{REDIS_KEY_RUN_LISTENERS_PREFIX}{stream_id}"


async def register_active_run(
    redis: Redis,
    conversation_id: str,
    *,
    run_id: str,
    stream_id: str,
) -> bool:
    """Acquire the conversation's active-run lock (SET NX EX).

    Args:
        redis: Redis client.
        conversation_id: Conversation UUID string (lock scope).
        run_id: Billing/correlation id of the run.
        stream_id: Transport id (stream key suffix) — the lock owner token.

    Returns:
        True if acquired; False when another run is already active (the
        caller answers HTTP 409 with the current run info).
    """
    payload = json.dumps({"run_id": run_id, "stream_id": stream_id})
    acquired = await redis.set(
        active_run_key(conversation_id),
        payload,
        nx=True,
        ex=settings.background_runs_active_ttl_seconds,
    )
    return bool(acquired)


async def refresh_active_run(redis: Redis, conversation_id: str, stream_id: str) -> bool:
    """Heartbeat: re-arm the lock TTL if this stream still owns it.

    Returns:
        True when refreshed; False when the lock is gone or owned by a
        newer run (the producer should stop heartbeating).
    """
    result = await redis.eval(
        _REFRESH_ACTIVE_RUN_LUA,
        1,
        active_run_key(conversation_id),
        stream_id,
        str(settings.background_runs_active_ttl_seconds),
    )
    return bool(result == 1)


async def release_active_run(redis: Redis, conversation_id: str, stream_id: str) -> None:
    """Release the lock — only if this stream still owns it (zombie-safe)."""
    await redis.eval(
        _RELEASE_ACTIVE_RUN_LUA,
        1,
        active_run_key(conversation_id),
        stream_id,
    )


async def get_active_run(redis: Redis, conversation_id: str) -> dict[str, str] | None:
    """Read the active run of a conversation.

    Returns:
        ``{"run_id": ..., "stream_id": ...}`` or None when no run is active.
    """
    raw = await redis.get(active_run_key(conversation_id))
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


# =============================================================================
# Subscriber presence (Lot 2): voice synthesis is skipped with no listeners
# =============================================================================


async def listener_incr(redis: Redis, stream_id: str) -> int:
    """Register one subscriber on the stream (atomic counter + TTL arm).

    Single Lua eval (same style as :data:`_LISTENER_DECR_LUA`): INCR and
    EXPIRE as two separate calls left a crash window that produced a
    TTL-less counter — permanently >0, so voice synthesis (paid TTS) was
    wrongly triggered for absent listeners.
    """
    result = await redis.eval(
        _LISTENER_INCR_LUA,
        1,
        listeners_key(stream_id),
        str(settings.background_runs_listener_ttl_seconds),
    )
    return int(result)


def cancel_key(stream_id: str) -> str:
    """Redis key of the per-stream user-cancellation signal (Lot 3)."""
    return f"{REDIS_KEY_RUN_CANCEL_PREFIX}{stream_id}"


async def request_cancel(redis: Redis, stream_id: str) -> None:
    """Signal the run's producer (possibly on another worker) to cancel.

    The producer polls this key every
    ``background_runs_cancel_poll_seconds``; the TTL self-cleans a signal
    whose producer already died. Idempotent.
    """
    await redis.set(cancel_key(stream_id), "1", ex=settings.background_runs_cancel_ttl_seconds)
    logger.info("run_cancel_requested", stream_id=stream_id)


async def is_cancel_requested(redis: Redis, stream_id: str) -> bool:
    """True when a user cancellation was requested for this run."""
    return bool(await redis.exists(cancel_key(stream_id)))


async def clear_cancel(redis: Redis, stream_id: str) -> None:
    """Best-effort removal of a consumed cancel signal."""
    await redis.delete(cancel_key(stream_id))


async def listener_touch(redis: Redis, stream_id: str) -> None:
    """Re-arm the presence counter TTL for a long-lived subscriber.

    The TTL is armed at INCR time only — without periodic touches, a
    subscriber attached longer than the TTL would silently vanish from the
    count and voice synthesis would be wrongly skipped mid-run. Called by
    the SSE relay loop every ~TTL/3.
    """
    await redis.expire(listeners_key(stream_id), settings.background_runs_listener_ttl_seconds)


async def listener_decr(redis: Redis, stream_id: str) -> int:
    """Unregister one subscriber (floor-guarded — never below zero)."""
    result = await redis.eval(
        _LISTENER_DECR_LUA,
        1,
        listeners_key(stream_id),
        str(settings.background_runs_listener_ttl_seconds),
    )
    return int(result)


async def has_listeners(redis: Redis, stream_id: str) -> bool:
    """True when at least one subscriber is currently attached."""
    raw = await redis.get(listeners_key(stream_id))
    try:
        return int(raw or 0) > 0
    except (TypeError, ValueError):
        return False
