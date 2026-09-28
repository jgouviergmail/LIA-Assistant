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

A claim guarding work that can outlive its TTL is HELD (:func:`held_claim`):
re-armed while the work runs, the work stopped at the keeper's next refresh
once another holder has it — or once it outlives the longest hold allowed —,
released by its token on every exit that still owns it. A claim key is
logged above DEBUG, so it names identifiers, never content.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
import uuid
from collections.abc import AsyncIterator, Callable
from typing import Any, Literal

import structlog

from src.infrastructure.async_utils import write_through_cancellation

logger = structlog.get_logger(__name__)

#: A held claim is re-armed this many times per TTL: a refresh that fails fast
#: leaves the next one inside the TTL. One that times out uses a whole period,
#: so the next lands as the claim expires — and takes it back if nobody did.
_REFRESHES_PER_TTL = 3

#: How many times the unwind awaits the release: it waits through one
#: cancellation fewer, and the next leaves the release to finish on its own (a
#: shutdown is never held open for it).
_SETTLE_ATTEMPTS = 3

#: The name of a held claim's keeper task — what a test finds it by.
KEEPER_TASK_NAME = "redis_claim_keeper"


#: Why a held claim stopped protecting its work.
ClaimLossReason = Literal["taken_over", "hold_exhausted"]


class ClaimLost(Exception):
    """A held claim stopped protecting the work it guarded.

    Attributes:
        reason: ``taken_over`` — another holder has the claim; ``hold_exhausted``
            — the work outlived the longest hold it was allowed.
    """

    def __init__(self, key: str, reason: ClaimLossReason) -> None:
        super().__init__(f"{key}: {reason}")
        self.reason: ClaimLossReason = reason


#: Delete the key only if it still holds the caller's token.
RELEASE_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""

#: Give the key a new TTL only if it still holds the caller's token.
REFRESH_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    redis.call('set', KEYS[1], ARGV[1], 'EX', ARGV[2])
    return 1
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


async def refresh_claim(redis: Any, key: str, token: str, *, ttl_seconds: int) -> bool:
    """Extend the claim's life, and only if this caller still owns it.

    Args:
        redis: The cache client.
        key: The claim's key.
        token: The owner token the claim was taken with.
        ttl_seconds: The claim's new life from now.

    Returns:
        True when the claim was this caller's and now lives ``ttl_seconds``;
        False when a successor holds it.

    Raises:
        Exception: Whatever the cache raised — the caller decides what a
            failure means (a live extension is refused, never assumed).
    """
    return bool(await redis.eval(REFRESH_SCRIPT, 1, key, token, ttl_seconds))


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


async def _keep_claim(
    redis: Any,
    key: str,
    token: str,
    *,
    ttl_seconds: int,
    refresh_seconds: float,
    max_hold_seconds: float | None,
    on_stop: Callable[[ClaimLossReason], None],
) -> None:
    """Re-arm a held claim until cancelled; report once why it stopped.

    A refusal is two situations, and telling them apart is the whole job. The
    key EXPIRED and nobody took it — a cache outage longer than the refresh
    margin — and the holder takes it back with its own token: aborting healthy
    work over a hiccup would be worse than the hiccup. Or ANOTHER token holds
    it: a successor runs, which is what the claim exists to prevent, and the
    holder must stop. A cache that cannot be reached, or answers slower than a
    refresh period, decides nothing; the next refresh tries again. And a hold
    has an end: work still running past ``max_hold_seconds`` is stopped, so a
    wedged holder never keeps the claim for the life of its process.
    """
    deadline = None if max_hold_seconds is None else time.monotonic() + max_hold_seconds
    while True:
        await asyncio.sleep(refresh_seconds)
        if deadline is not None and time.monotonic() >= deadline:
            logger.warning("redis_claim_hold_exhausted", key=key, max_hold_seconds=max_hold_seconds)
            on_stop("hold_exhausted")
            return
        try:
            if await asyncio.wait_for(
                refresh_claim(redis, key, token, ttl_seconds=ttl_seconds), refresh_seconds
            ):
                continue
            if await asyncio.wait_for(
                try_claim(redis, key, token, ttl_seconds=ttl_seconds), refresh_seconds
            ):
                logger.info("redis_claim_retaken", key=key)
                continue
        except Exception as exc:  # noqa: BLE001 — an unreachable or slow cache: keep trying
            logger.warning("redis_claim_refresh_failed", key=key, error_type=type(exc).__name__)
            continue
        logger.warning("redis_claim_lost", key=key)
        on_stop("taken_over")
        return


def _refresh_period(ttl_seconds: int, refresh_seconds: float | None) -> float:
    """The refresh period: a third of the TTL by default, always inside it.

    Raises:
        ValueError: A period that would let the claim expire between two
            refreshes, or never wait.
    """
    period = ttl_seconds / _REFRESHES_PER_TTL if refresh_seconds is None else refresh_seconds
    if not 0 < period < ttl_seconds:
        raise ValueError(f"refresh_seconds must lie strictly between 0 and {ttl_seconds}")
    return period


def _loss_of(
    body: asyncio.Task[Any] | None,
    baseline: int,
    stopped: list[ClaimLossReason],
    key: str,
    *,
    cancelled: bool,
) -> ClaimLost | None:
    """What an exit of the held block is: the claim's loss, or None.

    Only once the keeper stopped the block, and its cancellation request is
    then withdrawn. A cancellation that leaves another request pending is
    somebody else's — a shutdown, a caller's timeout — and stays one; any
    other exit (a return, a failure the block made of the keeper's
    cancellation) is the loss.

    Args:
        body: The block's task.
        baseline: The cancellation requests the task carried in.
        stopped: Why the keeper stopped the block, when it did.
        key: The claim's key.
        cancelled: Whether the block exits on a cancellation.

    Returns:
        The :class:`ClaimLost` to raise, or None when the exit is not the loss.
    """
    if not stopped or body is None:
        return None
    if body.uncancel() > baseline and cancelled:
        return None
    return ClaimLost(key, stopped[0])


async def _settle(
    keeper: asyncio.Task[None], redis: Any, key: str, token: str, stopped: list[ClaimLossReason]
) -> None:
    """End the keeper, then release the claim unless its successor holds it.

    The keeper is the block's own task: it is awaited before the claim ends,
    so whatever it does until it stops lands before the release. A command it
    had already sent to the cache when it was cancelled is not ordered by
    this — only the TTL bounds that one.
    """
    await asyncio.wait({keeper})
    if stopped[:1] == ["taken_over"]:
        return
    if not await release_claim(redis, key, token):
        logger.warning("redis_claim_not_released", key=key)


@contextlib.asynccontextmanager
async def held_claim(
    redis: Any,
    key: str,
    token: str,
    *,
    ttl_seconds: int,
    refresh_seconds: float | None = None,
    max_hold_seconds: float | None = None,
) -> AsyncIterator[None]:
    """Keep a TAKEN claim alive while a block runs, then release it by its token.

    A TTL is a crash bound, not a duration: work longer than it (a chat turn
    runs minutes, its claim lives two) would otherwise lose the claim in the
    middle and let a successor run beside it. The keeper stops the block by
    cancelling it — the block runs in the caller's task — at its first refresh
    after the claim is lost: both may run for up to one refresh period while
    the cache answers, and for as long as it does not (an unreachable cache
    decides nothing). Only the keeper's own cancellation becomes
    :class:`ClaimLost`: any other (a shutdown, a caller's timeout) propagates
    untouched, even when both land in the same step — once the claim is
    released. A block that swallows the keeper's cancellation, or turns it into
    another failure, still ends on ``ClaimLost``.

    Args:
        redis: The cache client.
        key: The claim's key, already taken with ``token`` — an identifier,
            since it is logged.
        token: The owner token.
        ttl_seconds: The claim's life, renewed on every refresh.
        refresh_seconds: Time between two refreshes, strictly inside the TTL;
            a third of the TTL when absent.
        max_hold_seconds: The longest the block may hold the claim; unbounded
            when absent.

    Yields:
        Nothing; the claim is held while the block runs.

    Raises:
        ValueError: ``refresh_seconds`` would let the claim expire between two
            refreshes.
        ClaimLost: The claim stopped protecting the block; ``reason`` says why.
    """
    refresh = _refresh_period(ttl_seconds, refresh_seconds)
    body = asyncio.current_task()
    baseline = body.cancelling() if body is not None else 0
    stopped: list[ClaimLossReason] = []

    def _stop(reason: ClaimLossReason) -> None:
        stopped.append(reason)
        if body is not None:
            body.cancel()

    keeper = asyncio.create_task(
        _keep_claim(
            redis,
            key,
            token,
            ttl_seconds=ttl_seconds,
            refresh_seconds=refresh,
            max_hold_seconds=max_hold_seconds,
            on_stop=_stop,
        ),
        name=KEEPER_TASK_NAME,
    )
    try:
        yield
    except asyncio.CancelledError:
        loss = _loss_of(body, baseline, stopped, key, cancelled=True)
        if loss is None:
            raise
        raise loss from None
    except Exception as exc:
        # The block turned the keeper's cancellation into another failure, or
        # failed before it was delivered.
        loss = _loss_of(body, baseline, stopped, key, cancelled=False)
        if loss is None:
            raise
        raise loss from exc
    else:
        # Decided BEFORE the settle, as on the two other exits: a cancellation
        # landing during the release must find the keeper's request withdrawn,
        # or the task carries two where one is the caller's — and a timeout
        # whose deadline falls there cannot recognise its own.
        loss = _loss_of(body, baseline, stopped, key, cancelled=False)
    finally:
        keeper.cancel()
        # ONE task that every re-delivered cancellation awaits: a cancellation
        # arriving now is the caller's and propagates — once the claim is
        # released, never instead of it.
        if await write_through_cancellation(
            lambda: _settle(keeper, redis, key, token, stopped),
            attempts=_SETTLE_ATTEMPTS,
            label="redis_claim_settle",
        ):
            raise asyncio.CancelledError
    if loss is not None:
        # The block swallowed the keeper's cancellation and returned: its later
        # effects ran unprotected, which is still a lost claim.
        raise loss


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


__all__ = [
    "REFRESH_SCRIPT",
    "RELEASE_SCRIPT",
    "ClaimLossReason",
    "ClaimLost",
    "acquire_claim",
    "held_claim",
    "refresh_claim",
    "release_claim",
    "try_claim",
]
