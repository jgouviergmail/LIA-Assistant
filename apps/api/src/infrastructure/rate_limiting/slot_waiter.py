"""Wait — briefly — for a distributed rate-limit slot.

``RedisRateLimiter.acquire`` answers yes or no and returns. That is the right
shape for an HTTP guard, where a rejected request should be rejected now. It is
the wrong shape for background work against a provider quota, where the honest
answer is "in a moment": the work is not unwelcome, it is early.

This module is the missing half, and it is deliberately thin — it composes the
existing limiter rather than adding a second one, so there stays exactly one
sliding-window implementation, one Lua script and one set of Redis metrics.

Three properties decide whether this prevents an outage or causes one:

**It is a shaper, never a gate.** The wait is bounded and a caller that waited
its share proceeds anyway. Throttling our own work into oblivion would be a
worse failure than the provider 429 it was meant to avoid.

**It fails open.** Redis is an optimisation here, not a dependency: if it is
unreachable the answer is "no slot", immediately, and the caller carries on.
An assistant that stopped embedding because a cache was down would have turned
a degraded provider into a degraded product.

**Off costs nothing.** A non-positive limit means disabled and never touches
Redis at all, so an operator turning the shaper off does not pay a round-trip
per call to learn that.
"""

from __future__ import annotations

import asyncio
import time
from enum import StrEnum

import structlog

from src.infrastructure.rate_limiting.redis_limiter import get_rate_limiter

logger = structlog.get_logger(__name__)

#: How often to re-probe while waiting. Small enough that a freed slot is taken
#: promptly, large enough that a queue of waiters does not become its own load
#: on Redis.
DEFAULT_POLL_SECONDS = 0.25

#: Never poll faster than this. A caller passing 0 would otherwise spin on Redis
#: for the whole budget — turning a shaper meant to REDUCE load into load.
MIN_POLL_SECONDS = 0.01


class SlotOutcome(StrEnum):
    """Why the shaper let this call through — the four are not interchangeable.

    A boolean would collapse them, and the two failure cases call for opposite
    operator actions: ``EXPIRED`` means the shaper is holding and the budget (or
    the provider quota) needs raising, while ``UNAVAILABLE`` means it is not
    shaping at all and Redis needs looking at.
    """

    #: A slot was taken; the caller is within budget.
    ACQUIRED = "acquired"
    #: The shaper is switched off; nothing was asked of Redis.
    DISABLED = "disabled"
    #: The caller waited its whole budget and is proceeding anyway.
    EXPIRED = "expired"
    #: The limiter could not be reached; shaping was skipped, not enforced.
    UNAVAILABLE = "unavailable"


async def wait_for_slot(
    key: str,
    max_calls: int,
    window_seconds: int,
    *,
    timeout_seconds: float,
    poll_seconds: float = DEFAULT_POLL_SECONDS,
) -> SlotOutcome:
    """Try to take a rate-limit slot, waiting up to ``timeout_seconds``.

    Args:
        key: Limiter key. Use the resource the QUOTA belongs to — a provider
            quota is global, so keying it per user would shape nothing.
        max_calls: Calls allowed per window; zero or less disables the shaper.
        window_seconds: Width of the sliding window.
        timeout_seconds: Total time this call may spend waiting. Zero means a
            single non-blocking probe.
        poll_seconds: Delay between probes.

    Returns:
        The outcome. NONE of them is a refusal to proceed — what to do with a
        :attr:`SlotOutcome.EXPIRED` is the caller's decision, and for every
        caller so far the answer is "go ahead anyway".
    """
    if max_calls <= 0:
        return SlotOutcome.DISABLED

    deadline = time.monotonic() + max(0.0, timeout_seconds)
    interval = max(MIN_POLL_SECONDS, poll_seconds)

    try:
        limiter = await get_rate_limiter()
    except Exception as exc:  # noqa: BLE001 — shaping is best-effort by design
        logger.debug("slot_waiter_limiter_unavailable", key=key, error=str(exc))
        return SlotOutcome.UNAVAILABLE

    while True:
        try:
            if await limiter.acquire(key, max_calls, window_seconds):
                return SlotOutcome.ACQUIRED
        except Exception as exc:  # noqa: BLE001 — see module docstring: fail open
            logger.debug("slot_waiter_probe_failed", key=key, error=str(exc))
            return SlotOutcome.UNAVAILABLE

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            logger.debug(
                "slot_waiter_timed_out",
                key=key,
                max_calls=max_calls,
                window_seconds=window_seconds,
                waited_seconds=round(timeout_seconds, 3),
            )
            return SlotOutcome.EXPIRED

        await asyncio.sleep(min(interval, remaining))
