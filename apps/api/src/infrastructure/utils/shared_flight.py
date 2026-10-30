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

**Owner liveness (opt-in, ``owner_liveness=True``).** A waiter that accepts
nothing but a complete published result paid the whole budget whenever the
owner published an incomplete one — a section failed, or a push invalidated it
at the owner's end — then rebuilt, every waiter on its own (spec 2026-10-21,
E12: measured on the briefing). With liveness the claim itself says whether
the owner is still working: the owner holds it through ``held_claim``, which
renews it and stops the build when it is lost; a waiter keeps waiting while it
is held, with a polling backoff, and the first waiter to find it gone without
a result takes it AGAIN and builds — the others wait for that one. The budget
becomes a hard ceiling rather than a timer.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any, NamedTuple, TypeVar

import structlog

from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.locks.redis_claim import ClaimLost, held_claim, release_claim, try_claim

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

#: Released explicitly; this only bounds a holder that died mid-build. Work
#: that may outlast it passes its own (``claim_ttl_s``): a claim that expires
#: mid-build lets the next caller build the same thing again.
CLAIM_TTL_SECONDS = 30

#: How often a waiter looks for the published result.
POLL_INTERVAL_SECONDS = 0.02

#: With owner liveness, the poll interval doubles up to this cap: a long build
#: (a slow source) must not cost hundreds of reads per waiter.
POLL_INTERVAL_CAP_SECONDS = 0.25

# The waiter's clock and sleep, injectable in tests (the claim keeper keeps its own).
_now = time.monotonic
_sleep = asyncio.sleep


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
    claim_ttl_s: int = CLAIM_TTL_SECONDS,
    owner_liveness: bool = False,
    read_settled: Callable[[], Awaitable[T | None]] | None = None,
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
        claim_ttl_s: How long the claim outlives a holder that died — longer
            than the work itself may take. With ``owner_liveness`` it is
            renewed while the work runs, so it bounds a dead holder only.
        owner_liveness: Wait while the owner's claim is held (up to the
            budget, now a hard ceiling); build once it is gone without a
            result, one re-claiming waiter at a time.
        read_settled: With ``owner_liveness``, what a WAITER may accept: a
            result the owner settled without completing it (a failure it
            recorded). The owner's own look still requires ``read_shared``,
            so the next owner retries what failed. Defaults to ``read_shared``.

    Returns:
        The value, and how this caller obtained it.

    Raises:
        Exception: Whatever ``build()`` raises — the claim is released first,
            so the next caller retries instead of waiting out the budget.
    """
    claim_key = key
    token = uuid.uuid4().hex
    redis = await _redis_or_none()

    if redis is not None and owner_liveness:
        return await _run_with_liveness(
            redis,
            claim_key,
            token,
            build=build,
            read_shared=read_shared,
            read_settled=read_settled or read_shared,
            wait_budget_s=wait_budget_s,
            claim_ttl_s=claim_ttl_s,
        )
    if redis is None or not await _try_claim(redis, claim_key, token, claim_ttl_s):
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


async def _run_with_liveness(
    redis: Any,
    claim_key: str,
    token: str,
    *,
    build: Callable[[], Awaitable[T]],
    read_shared: Callable[[], Awaitable[T | None]],
    read_settled: Callable[[], Awaitable[T | None]],
    wait_budget_s: float,
    claim_ttl_s: int,
) -> SharedFlightResult[T]:
    """Claim and build, or wait while the owner's claim is held, then re-claim.

    A waiter first looks for a SETTLED result (which may record a failure the
    owner met), then tries the claim: that fails while the owner holds it, and
    succeeds for exactly one waiter once the owner released it without a
    result (or died and its claim expired) — the others keep waiting for that
    waiter's result.

    Args:
        redis: The cache client.
        claim_key: The claim's key.
        token: This caller's owner token.
        build: Does the work and publishes it.
        read_shared: Returns the complete published result, or None (the
            owner's look before it builds).
        read_settled: Returns what a waiter may accept, or None.
        wait_budget_s: The hard ceiling on waiting.
        claim_ttl_s: The claim's life, renewed while the owner builds.

    Returns:
        The value, and how this caller obtained it.
    """
    if await _try_claim(redis, claim_key, token, claim_ttl_s):
        return await _build_as_live_owner(
            redis, claim_key, token, build, read_shared, claim_ttl_s, waited=False
        )
    deadline = _now() + wait_budget_s
    interval = POLL_INTERVAL_SECONDS
    while True:
        shared = await _read_published(read_settled)
        if shared is not None:
            return SharedFlightResult(value=shared, claimed=False, waited=True)
        if _now() >= deadline:
            # The ceiling: a holder that is alive but never finishes must not
            # strand anyone. Building is the floor, never an empty answer.
            return SharedFlightResult(value=await build(), claimed=False, waited=True)
        await _sleep(interval)
        interval = min(interval * 2, POLL_INTERVAL_CAP_SECONDS)
        if await _try_claim(redis, claim_key, token, claim_ttl_s):
            # A waiter taking the claim over: the owner it waited for may have
            # settled the result between this caller's read and its claim, and
            # that result is what this waiter came for (measured across four
            # real processes: the failed section was re-read without this).
            return await _build_as_live_owner(
                redis, claim_key, token, build, read_settled, claim_ttl_s, waited=True
            )


async def _build_as_live_owner(
    redis: Any,
    claim_key: str,
    token: str,
    build: Callable[[], Awaitable[T]],
    read_shared: Callable[[], Awaitable[T | None]],
    claim_ttl_s: int,
    *,
    waited: bool,
) -> SharedFlightResult[T]:
    """Look once, then build while the claim is kept alive; released by its token.

    A claim lost mid-build stops the build: what a successor published is taken,
    and only when nothing is there does this caller build without the claim.

    Args:
        redis: The cache client.
        claim_key: The claim's key, already taken with ``token``.
        token: The owner token.
        build: Does the work and publishes it.
        read_shared: Returns what this owner accepts instead of building: the
            complete result for a fresh owner, the settled one for a waiter
            that took the claim over.
        claim_ttl_s: The claim's life, renewed on every refresh.
        waited: Whether this caller waited before taking the claim.

    Returns:
        The value, and how this caller obtained it.

    Raises:
        Exception: Whatever ``build()`` raises, once the claim is released.
    """
    try:
        async with held_claim(redis, claim_key, token, ttl_seconds=claim_ttl_s):
            already = await _read_published(read_shared)
            if already is not None:
                return SharedFlightResult(value=already, claimed=False, waited=waited)
            value = await build()
    except ClaimLost as lost:
        # The claim stopped protecting the build (a successor holds it): the
        # build was stopped. What the successor already published is taken;
        # building without the claim is the floor, never the first resort.
        logger.info("shared_flight_claim_lost", reason=lost.reason)
        successor = await _read_published(read_shared)
        if successor is not None:
            return SharedFlightResult(value=successor, claimed=False, waited=waited)
        return SharedFlightResult(value=await build(), claimed=False, waited=waited)
    return SharedFlightResult(value=value, claimed=True, waited=waited)


async def _redis_or_none() -> Any | None:
    """The cache, or None when it cannot be reached."""
    try:
        return await get_redis_cache()
    except Exception as exc:  # noqa: BLE001 - a missing cache is not an outage
        logger.debug("shared_flight_no_cache", error_type=type(exc).__name__)
        return None


async def _try_claim(redis: Any, claim_key: str, token: str, ttl_seconds: int) -> bool:
    """Take the claim, or report that someone else holds it.

    Args:
        redis: The cache client.
        claim_key: The claim's key.
        token: This caller's owner token.
        ttl_seconds: How long the claim outlives a holder that died.

    Returns:
        True when the claim was taken. A cache failure returns True: building
        is the floor, and waiting on a claim we could not read would be worse.
    """
    try:
        return await try_claim(redis, claim_key, token, ttl_seconds=ttl_seconds)
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
    await release_claim(redis, claim_key, token)


__all__ = [
    "CLAIM_PREFIX",
    "CLAIM_TTL_SECONDS",
    "POLL_INTERVAL_CAP_SECONDS",
    "SharedFlightResult",
    "run_shared_flight",
]
