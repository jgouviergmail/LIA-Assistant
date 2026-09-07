"""Coalescing callers that do not share a process.

:mod:`single_flight` shares work between callers on one event loop, which is
everything when a service runs as one process. This one does not: uvicorn
honours ``WEB_CONCURRENCY``, production sets it to 4, and the two requests of a
single page load therefore land on the same worker about one time in four —
measured on the deployed instance 2026-09-07, three overlapping pairs, none of
them joined, with the connectors opened up to five times for two page loads.

So one caller CLAIMS the work in Redis and the others wait for the result it
publishes. The published result is whatever the caller already shares — for the
briefing, the section cache the build fills anyway — so this seam moves no
payload through Redis of its own.

Three rules it does not bend:

- **The claim is released by its OWNER.** ``SET NX`` followed by an
  unconditional ``DELETE`` is forbidden (CLAUDE.md): a holder whose claim
  expired mid-build would delete the claim its successor had just taken. The
  release is a compare-and-delete on a token only this call knows.
- **Holding the claim is not proof the work is still needed.** The previous
  holder may have finished and released between this caller's read and its
  claim, so the holder LOOKS once before building. Waiting protects against a
  claim that is held; only looking protects against one just let go.
- **Waiting is bounded, and a waiter that times out BUILDS.** A holder that
  dies must not strand anyone. The budget buys a shared result; it never buys
  an empty answer.
- **Every failure falls back to building.** Redis unreachable, the claim
  unreadable, the script refused — each one lands on the behaviour this seam
  replaces, never on something worse.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any, NamedTuple, TypeVar

import structlog

from src.infrastructure.cache.redis import get_redis_cache

logger = structlog.get_logger(__name__)

T = TypeVar("T")

#: The family every claim key belongs to, declared in
#: ``infrastructure/cache/key_families.py`` (ADR-260) as ``USER_RUNTIME``: a
#: reset must never delete a claim held by a build in flight.
#:
#: The CALLER composes the whole key with it, rather than this module adding it
#: behind their back. A family is declared by whoever writes it, and a key
#: whose head only appears after a helper prepends it is a key no guard can
#: read — ``test_redis_key_family_guard`` caught exactly that.
CLAIM_PREFIX = "shared_flight"

#: Released explicitly; this only bounds a holder that died mid-build.
CLAIM_TTL_SECONDS = 30

#: How often a waiter looks for the published result.
POLL_INTERVAL_SECONDS = 0.02

#: Compare-and-delete: only the token that took the claim may drop it.
_RELEASE_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""


class SharedFlightResult[V](NamedTuple):
    """What the call produced, and how it got there.

    Attributes:
        value: The result — built here, or read from what the holder published.
        claimed: True when this caller held the claim and did the work.
        waited: True when this caller waited on someone else's claim, whether
            or not the wait paid off.
    """

    value: V
    claimed: bool
    waited: bool


async def run_shared_flight(
    key: str,
    *,
    build: Callable[[], Awaitable[T]],
    read_shared: Callable[[], Awaitable[T | None]],
    wait_budget_s: float,
) -> SharedFlightResult[T]:
    """Do the work once across processes, or take what another one published.

    Args:
        key: The FULL Redis key, ``CLAIM_PREFIX``-prefixed by the caller. It
            is what makes two calls the same work across workers, so
            everything that changes the result belongs in it.
        build: Does the work and publishes its result where ``read_shared``
            will find it.
        read_shared: Returns the published result, or None while there is none.
            Called by waiters only.
        wait_budget_s: How long a waiter may wait before doing the work itself.

    Returns:
        The value, and how this caller obtained it.

    Raises:
        Exception: Whatever ``build()`` raises — the claim is released first,
            so the next caller retries instead of waiting out the budget.
    """
    claim_key = key
    token = uuid.uuid4().hex
    redis = await _redis_or_none()

    if redis is None or not await _try_claim(redis, claim_key, token):
        if redis is None:
            # No claim could be taken and none can be waited on: this is the
            # behaviour that existed before the seam, which is the floor.
            return SharedFlightResult(value=await build(), claimed=False, waited=False)
        shared = await _wait_for(read_shared, wait_budget_s)
        if shared is not None:
            return SharedFlightResult(value=shared, claimed=False, waited=True)
        # The holder never published. Do the work rather than answer nothing.
        return SharedFlightResult(value=await build(), claimed=False, waited=True)

    # Holding the claim is not proof the work is still needed: the previous
    # holder may have finished and RELEASED between this caller's read and its
    # claim. Measured across two uvicorn processes sharing one Redis — four
    # rounds of five coalesced and the fifth built twice, for exactly that.
    # Waiting protects against a claim that is HELD; only looking protects
    # against one that has just been let go.
    try:
        already = await _read_published(read_shared)
        if already is not None:
            return SharedFlightResult(value=already, claimed=False, waited=False)
        value = await build()
    finally:
        await _release(redis, claim_key, token)
    return SharedFlightResult(value=value, claimed=True, waited=False)


async def _redis_or_none() -> Any | None:
    """The cache, or None when it cannot be reached."""
    try:
        return await get_redis_cache()
    except Exception as exc:  # noqa: BLE001 - a missing cache is not an outage
        logger.debug("shared_flight_no_cache", error_type=type(exc).__name__)
        return None


async def _try_claim(redis: Any, claim_key: str, token: str) -> bool:
    """Take the claim, or report that someone else holds it.

    Args:
        redis: The cache client.
        claim_key: The claim's key.
        token: This caller's owner token.

    Returns:
        True when the claim was taken. A cache failure returns True: building
        is the floor, and waiting on a claim we could not read would be worse.
    """
    try:
        return bool(await redis.set(claim_key, token, ex=CLAIM_TTL_SECONDS, nx=True))
    except Exception as exc:  # noqa: BLE001 - fall back to building
        logger.debug("shared_flight_claim_failed", error_type=type(exc).__name__)
        return True


async def _read_published(
    read_shared: Callable[[], Awaitable[T | None]],
) -> T | None:
    """What the caller can already see, or None — never an error.

    Args:
        read_shared: Returns the published result, or None.

    Returns:
        The published result, or None when there is none or the read failed.
    """
    try:
        return await read_shared()
    except Exception as exc:  # noqa: BLE001 - a failed read is "not yet"
        logger.debug("shared_flight_read_failed", error_type=type(exc).__name__)
        return None


async def _wait_for(read_shared: Callable[[], Awaitable[T | None]], budget_s: float) -> T | None:
    """Poll for the holder's published result until the budget runs out.

    Args:
        read_shared: Returns the published result, or None.
        budget_s: How long to wait.

    Returns:
        The published result, or None when it never arrived.
    """
    deadline = time.monotonic() + budget_s
    while True:
        shared = await _read_published(read_shared)
        if shared is not None:
            return shared
        if time.monotonic() >= deadline:
            return None
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def _release(redis: Any, claim_key: str, token: str) -> None:
    """Drop the claim, and only if this caller still owns it.

    Args:
        redis: The cache client.
        claim_key: The claim's key.
        token: The owner token this caller took it with.
    """
    with contextlib.suppress(Exception):
        await redis.eval(_RELEASE_SCRIPT, 1, claim_key, token)


__all__ = [
    "CLAIM_PREFIX",
    "CLAIM_TTL_SECONDS",
    "SharedFlightResult",
    "run_shared_flight",
]
