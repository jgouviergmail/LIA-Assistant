"""A send or a create happens once per submission (ADR-369, ADR-221).

The page mints one key per submission (a composer, a « New task » form); the
route claims it in Redis BEFORE the provider is called, with an owner token
(``infrastructure/locks/redis_claim``: ``SET NX``, compare-and-act). What became
of the submission is then written under that token:

- ``done`` — with the id the provider gave, so a replay can name it;
- ``unknown`` — the answer was lost (a timeout once the request left, a
  cancellation): the act may have happened, and the key is KEPT so a second
  click is told so rather than sending again;
- nothing — a CERTAIN failure (the provider answered a refusal, the request
  never left) frees the key, and the person may try again.

A second submission with the same key never reaches the provider: it is
refused with ``already_submitted`` and the stored outcome. The registers do not
record it (owner decision D5): the act is the person's, not LIA's.

The cache is a guard, never a gate: when Redis cannot be reached the submission
runs unguarded and a counter says so (ADR-254 doctrine — our own throttle is
never the reason a request fails).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from enum import Enum
from typing import Any, Final, TypeVar
from uuid import UUID, uuid4

import structlog

from src.core.config import settings
from src.core.constants import REDIS_KEY_WORKBENCH_IDEMPOTENCY_PREFIX
from src.domains.workbench.errors import ALREADY_SUBMITTED, OUTCOME_UNKNOWN, refusal_for, refuse
from src.infrastructure.async_utils import write_through_cancellation
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.locks.redis_claim import release_claim, try_claim
from src.infrastructure.observability.metrics_workbench import (
    workbench_idempotency_replays_total,
    workbench_idempotency_unguarded_total,
)

logger = structlog.get_logger(__name__)

T = TypeVar("T")

#: Re-deliveries of a cancellation the « unknown » write survives.
_SETTLE_ATTEMPTS: Final = 3

#: Write the outcome only if the key still holds the claimant's token.
SETTLE_SCRIPT: Final = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    redis.call('set', KEYS[1], ARGV[2], 'EX', ARGV[3])
    return 1
end
return 0
"""


class SubmissionOutcome(str, Enum):
    """What became of a submission, as a replay is told."""

    PENDING = "pending"
    DONE = "done"
    UNKNOWN = "unknown"


def submission_key(user_id: UUID, key: UUID) -> str:
    """The Redis key of one submission of one account."""
    return f"{REDIS_KEY_WORKBENCH_IDEMPOTENCY_PREFIX}{user_id}:{key}"


def _nothing_to_record(_: Any) -> dict[str, str]:
    return {}


async def run_once(
    user_id: UUID,
    key: UUID,
    operation: Callable[[], Awaitable[T]],
    *,
    tool: str,
    record: Callable[[T], dict[str, str]] = _nothing_to_record,
) -> T:
    """Run ``operation`` once for this submission, whatever is clicked twice.

    Args:
        user_id: The account submitting.
        key: The page's key for this submission.
        operation: The provider call — a factory, never an awaitable.
        tool: The workbench tool (a metric label).
        record: What a replay may name of the result (ids, never content).

    Returns:
        The operation's result.

    Raises:
        BaseAPIException: ``already_submitted`` for a key already claimed.
        Exception: Whatever the operation raised, after the key was settled.
    """
    redis_key = submission_key(user_id, key)
    token = uuid4().hex
    ttl = settings.workbench_idempotency_ttl_seconds
    try:
        redis = await get_redis_cache()
        claimed = await try_claim(redis, redis_key, token, ttl_seconds=ttl)
    except Exception as error:  # the cache is a guard, never a gate
        workbench_idempotency_unguarded_total.labels(tool=tool).inc()
        logger.warning(
            "workbench_idempotency_unguarded", tool=tool, error_type=type(error).__name__
        )
        return await operation()
    if not claimed:
        await _refuse_replay(redis, redis_key, tool)
    try:
        result = await operation()
    except BaseException as error:
        await _settle_failure(redis, redis_key, token, ttl, error)
        raise
    await _settle(
        redis, redis_key, token, ttl, {"state": SubmissionOutcome.DONE.value, **record(result)}
    )
    return result


async def _refuse_replay(redis: Any, redis_key: str, tool: str) -> None:
    """Tell a second submission what became of the first."""
    try:
        stored = await redis.get(redis_key)
    except Exception:  # unreadable: the first is still the only one that may run
        stored = None
    facts = _stored_outcome(stored)
    workbench_idempotency_replays_total.labels(tool=tool, outcome=facts["outcome"]).inc()
    refuse(ALREADY_SUBMITTED, **facts)


def _stored_outcome(stored: object) -> dict[str, Any]:
    """What a stored value says became of the submission; « pending » when unreadable.

    A bare token is a claim still running. A settled outcome is JSON; anything
    else — corrupted, from another writer — reads as « pending », the answer
    that never invites a second send.
    """
    pending: dict[str, Any] = {"outcome": SubmissionOutcome.PENDING.value}
    if not isinstance(stored, (str, bytes)) or stored[:1] not in ("{", b"{"):
        return pending
    try:
        written = json.loads(stored)
    except ValueError:
        return pending
    if not isinstance(written, dict):
        return pending
    state = written.pop("state", None)
    if state not in {outcome.value for outcome in SubmissionOutcome}:
        return pending
    ids = {key: value for key, value in written.items() if isinstance(value, str)}
    return {"outcome": state, **ids}


async def _settle_failure(
    redis: Any, redis_key: str, token: str, ttl: int, error: BaseException
) -> None:
    """Keep the key as « unknown » when the act may have happened, free it otherwise."""
    if isinstance(error, asyncio.CancelledError):
        payload = {"state": SubmissionOutcome.UNKNOWN.value}
        await write_through_cancellation(
            lambda: _settle(redis, redis_key, token, ttl, payload),
            attempts=_SETTLE_ATTEMPTS,
            label="workbench_idempotency_settle",
        )
        return
    if refusal_for(error, act=True)[0] == OUTCOME_UNKNOWN:
        await _settle(redis, redis_key, token, ttl, {"state": SubmissionOutcome.UNKNOWN.value})
        return
    await release_claim(redis, redis_key, token)


async def _settle(
    redis: Any, redis_key: str, token: str, ttl: int, payload: dict[str, Any]
) -> None:
    """Write the outcome under the claimant's token; a failure leaves it pending."""
    try:
        await redis.eval(SETTLE_SCRIPT, 1, redis_key, token, json.dumps(payload), ttl)
    except Exception as error:  # still claimed: a replay reads « pending », never a resend
        logger.warning("workbench_idempotency_settle_failed", error_type=type(error).__name__)
