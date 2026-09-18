"""An owner-token claim in Redis: SET NX to take, compare-and-delete to release.

The one implementation of the shape CLAUDE.md requires of every distributed
claim — ``SET NX`` followed by an unconditional ``DELETE`` is forbidden,
because a slow holder whose claim expired would delete the claim its
successor has just taken. ``shared_flight`` carried this as two private
helpers; the sandbox egress ruleset writer (ADR-298) needed the same pair
plus a bounded wait, so the primitive moved here.

The primitives tell the truth: :func:`try_claim` PROPAGATES a cache failure,
because callers disagree on what it means — a shared flight builds anyway,
an egress run must be refused. :func:`release_claim` swallows one: a claim
that could not be released expires by its TTL, and there is nothing more a
caller could do.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
import uuid
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

#: Delete the key only if it still holds the caller's token.
RELEASE_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""


async def try_claim(redis: Any, key: str, token: str, *, ttl_seconds: int) -> bool:
    """Take the claim, or report that someone else holds it.

    Args:
        redis: The cache client.
        key: The claim's key.
        token: This caller's owner token.
        ttl_seconds: How long the claim survives a holder that never releases.

    Returns:
        True when the claim was taken.

    Raises:
        Exception: Whatever the cache raised — the caller decides what a
            failure means.
    """
    return bool(await redis.set(key, token, ex=ttl_seconds, nx=True))


async def release_claim(redis: Any, key: str, token: str) -> bool:
    """Drop the claim, and only if this caller still owns it.

    Args:
        redis: The cache client.
        key: The claim's key.
        token: The owner token the claim was taken with.

    Returns:
        True when the claim was this caller's and is now released; False when
        a successor holds it, or when the cache could not be reached (the
        claim then expires by its TTL).
    """
    # A failed release is not an error the caller can act on.
    with contextlib.suppress(Exception):
        return bool(await redis.eval(RELEASE_SCRIPT, 1, key, token))
    return False


async def acquire_claim(
    redis: Any,
    key: str,
    *,
    ttl_seconds: int,
    wait_seconds: float,
    poll_seconds: float,
) -> str | None:
    """Wait for the claim within a budget.

    Args:
        redis: The cache client.
        key: The claim's key.
        ttl_seconds: TTL of the claim once taken.
        wait_seconds: How long to keep trying.
        poll_seconds: Pause between two attempts.

    Returns:
        The owner token to release with, or None when the budget ran out.

    Raises:
        Exception: Whatever the cache raised on an attempt.
    """
    token = uuid.uuid4().hex
    deadline = time.monotonic() + wait_seconds
    while True:
        if await try_claim(redis, key, token, ttl_seconds=ttl_seconds):
            return token
        if time.monotonic() >= deadline:
            logger.debug("redis_claim_wait_exhausted", key=key, wait_seconds=wait_seconds)
            return None
        await asyncio.sleep(poll_seconds)


__all__ = ["RELEASE_SCRIPT", "acquire_claim", "release_claim", "try_claim"]
