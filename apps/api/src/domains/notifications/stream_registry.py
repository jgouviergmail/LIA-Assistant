"""Per-user SSE stream registry — newest-wins capacity protection.

Incident 2026-08-14/15: one client's EventSource churn (mobile network)
accumulated dozens of half-dead ``/notifications/stream`` connections, each
pinning a pooled Redis pub/sub connection, until ``MaxConnectionsError``
degraded every Redis-backed path for hours (SSE, caches, rate limiting,
scheduler leadership).

This module bounds concurrent notification streams per user with a Redis
ZSET (``sse:streams:{user_id}`` → member = stream id, score = registration
time). The policy is **newest wins**: a new stream always registers and the
oldest beyond the cap is trimmed — the new connection is never refused,
because EventSource cannot read an HTTP status (a refusal shows up as a bare
``onerror`` and triggers a blind retry loop, the exact trap measured on the
inactive-account 403s in 2026-08). An evicted stream discovers its eviction
at its next keepalive tick and closes itself with a ``superseded`` event.

Deliberately NOT a distributed lock (no owner token, no fencing — systemic
rule scope): nothing durable is claimed, the worst race (two workers
registering concurrently) transiently leaves ``cap + 1`` members until the
next registration trims again. Every failure mode is fail-open: a Redis
outage degrades to "no cap", it never kills a live stream.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import structlog

from src.core.constants import SSE_STREAMS_KEY_PREFIX

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = structlog.get_logger(__name__)


def _key(user_id: str) -> str:
    """ZSET key holding one user's live stream ids."""
    return f"{SSE_STREAMS_KEY_PREFIX}:{user_id}"


async def register_stream(
    redis: Redis,
    user_id: str,
    stream_id: str,
    *,
    cap: int,
    ttl_seconds: int,
) -> None:
    """Register a new stream and trim the user's set to the ``cap`` newest.

    Fail-open: a Redis failure is logged and swallowed — the stream runs
    uncapped rather than not at all.

    Args:
        redis: Cache Redis client.
        user_id: Owner of the stream.
        stream_id: Unique id of this stream (uuid hex).
        cap: Maximum concurrent streams kept for this user.
        ttl_seconds: Registry TTL — refreshed on keepalives, so an orphaned
            ZSET (worker crash) expires on its own.
    """
    key = _key(user_id)
    try:
        # time.time() as score: monotonic enough (µs resolution) to order
        # registrations; never persisted as a datetime.
        await redis.zadd(key, {stream_id: time.time()})
        # Keep the `cap` highest scores: drop ranks [0, -(cap+1)].
        await redis.zremrangebyrank(key, 0, -(cap + 1))
        await redis.expire(key, ttl_seconds)
    except Exception as exc:  # noqa: BLE001 — fail-open capacity guard
        logger.warning(
            "sse_stream_register_failed",
            user_id=user_id,
            error=str(exc),
            error_type=type(exc).__name__,
        )


async def stream_is_active(redis: Redis, user_id: str, stream_id: str) -> bool:
    """Whether this stream still holds a slot (False = evicted by a newer one).

    Fail-open: an unreachable Redis must never evict a live stream.

    Args:
        redis: Cache Redis client.
        user_id: Owner of the stream.
        stream_id: The stream's unique id.

    Returns:
        True when the stream is still registered (or Redis is unreachable).
    """
    try:
        return await redis.zscore(_key(user_id), stream_id) is not None
    except Exception as exc:  # noqa: BLE001 — fail-open capacity guard
        logger.debug("sse_stream_active_check_failed", user_id=user_id, error=str(exc))
        return True


async def refresh_registry(redis: Redis, user_id: str, *, ttl_seconds: int) -> None:
    """Extend the registry TTL (called on each keepalive tick). Fail-open.

    Args:
        redis: Cache Redis client.
        user_id: Owner of the registry to refresh.
        ttl_seconds: New TTL.
    """
    try:
        await redis.expire(_key(user_id), ttl_seconds)
    except Exception as exc:  # noqa: BLE001 — fail-open capacity guard
        logger.debug("sse_stream_registry_refresh_failed", user_id=user_id, error=str(exc))


async def unregister_stream(redis: Redis, user_id: str, stream_id: str) -> int:
    """Remove a closing stream and report how many remain for this user.

    The caller uses the remaining count to decide whether the shared
    per-user SSE marker (OAuth-health dedup) may be deleted. On Redis
    failure the safe verdict is "streams remain" (a positive count): the
    marker then simply expires by TTL instead of being deleted early.

    Args:
        redis: Cache Redis client.
        user_id: Owner of the stream.
        stream_id: The stream's unique id.

    Returns:
        Number of streams still registered for the user (1 on failure).
    """
    key = _key(user_id)
    try:
        await redis.zrem(key, stream_id)
        return int(await redis.zcard(key))
    except Exception as exc:  # noqa: BLE001 — fail-open capacity guard
        logger.debug("sse_stream_unregister_failed", user_id=user_id, error=str(exc))
        return 1
