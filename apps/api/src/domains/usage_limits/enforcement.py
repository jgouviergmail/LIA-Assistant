"""Turning a blocking usage verdict into the one answer every door gives.

A verdict is computed in one place (:meth:`UsageLimitService.check_user_allowed`,
which asks the instance ceiling first and the per-account one after). Answering
it was written twice: the chat router named the instance pause with a stable
error code and a computable ``Retry-After``, while the shared LLM gate answered
with neither. Same refusal, two shapes — so a caller blocked at a chokepoint
could not tell "the deployment is paused until tomorrow" from "you are over
your own limit", and had nothing to wait on.

One raiser now, two callers, and the metric moves with it: a refusal that is
not counted is a refusal nobody can see.
"""

from __future__ import annotations

from typing import NoReturn

import structlog

from src.core.constants import INSTANCE_BUDGET_EXHAUSTED_ERROR_CODE
from src.domains.usage_limits.schemas import UsageLimitStatus

logger = structlog.get_logger(__name__)


def raise_for_blocked_verdict(verdict: object, *, layer: str) -> NoReturn:
    """Refuse the call the way every other door refuses it.

    Args:
        verdict: A ``UsageLimitCheckResult`` whose ``allowed`` is False.
        layer: Which door refused, for the enforcement metric.

    Raises:
        UsageLimitExceededError: 429, carrying the exceeded limit — plus, when
            the deployment itself is paused, the stable error code the frontend
            localizes on and the seconds until the UTC day rolls over.
    """
    from src.core.exceptions_domains import raise_usage_limit_exceeded
    from src.domains.usage_limits.instance_budget import seconds_until_next_utc_day
    from src.infrastructure.observability.metrics_usage_limits import (
        usage_limit_enforcement_total,
    )

    exceeded = getattr(verdict, "exceeded_limit", None)
    reason = getattr(verdict, "blocked_reason", None)
    is_instance_pause = getattr(verdict, "status", None) is UsageLimitStatus.BLOCKED_INSTANCE_BUDGET

    usage_limit_enforcement_total.labels(layer=layer, limit_type=exceeded or "unknown").inc()
    logger.warning(
        "usage_limit_blocked",
        layer=layer,
        limit=exceeded,
        instance_pause=is_instance_pause,
    )
    raise_usage_limit_exceeded(
        exceeded,
        reason,
        error_code=INSTANCE_BUDGET_EXHAUSTED_ERROR_CODE if is_instance_pause else None,
        # The ceiling resets on the UTC day boundary, so "come back tomorrow"
        # is a computable instant rather than a vague hope.
        retry_after_seconds=seconds_until_next_utc_day() if is_instance_pause else None,
    )


async def spend_blocked(user_id: object | None) -> bool:
    """Whether either ceiling refuses this account's next model call.

    The non-raising shape, for the paths that must DEGRADE rather than fail:
    a scheduler job still has a reminder to deliver, and a dashboard still has
    a page to render. They fall back to a written sentence instead of a model
    one, and say so accurately — logging a quota refusal as a "generation
    failed" would describe something the code did not do.

    Same verdict as :func:`enforce_usage_limit`, and the same shape as
    :func:`instance_spend.is_instance_spend_blocked`, which already answers
    this question for the calls that have no owner. One question, two ways to
    receive the answer, never two ways to compute it.

    Args:
        user_id: The account, or None when the call belongs to nobody.

    Returns:
        True when the caller must skip its model call.
    """
    from src.domains.usage_limits.service import UsageLimitService
    from src.infrastructure.llm.usage_guard import resolve_owner

    owner = resolve_owner(user_id)  # type: ignore[arg-type]
    if owner is None:
        return await UsageLimitService.instance_budget_block() is not None

    verdict = await UsageLimitService.check_user_allowed(owner)
    if verdict.allowed:
        return False
    logger.info(
        "model_call_skipped_usage_limit",
        user_id=str(owner),
        limit=verdict.exceeded_limit,
    )
    return True


__all__ = ["raise_for_blocked_verdict", "spend_blocked"]
