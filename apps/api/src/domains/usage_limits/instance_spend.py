"""Recording model spend that belongs to the deployment, not to an account.

Three kinds of call have no account behind them: self-diagnosis reads the
instance's own incidents, a broadcast is translated once for every recipient,
and personality or skill descriptions are catalogue content an administrator
edits. Attaching any of them to a person would charge a quota at random, so
they must stay out of :class:`UserStatistics` — the owner's rule, applied the
right way round.

What was missing is the other half. « No account » had been read as « no
ledger », and the instance's daily ceiling reads
:class:`InstanceDailyBudget`, which these paths never touched. Measured
2026-09-07: 84 personality translations recorded nowhere at all, and a
self-diagnosis allowance of 1.00 USD per day — against a whole-instance
average of 0.42 € — that no deployment ceiling could see.

The shape deliberately mirrors ``track_proactive_tokens``: called after the
work with the totals, never raising, silent on zero. One idiom for out-of-turn
spend, so the next author has a pattern to copy rather than a choice to make.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import structlog

from src.core.llm_usage import LLMBillingRecord
from src.infrastructure.cache.pricing_cache import PricingCacheData, get_cached_cost_usd_eur
from src.infrastructure.database.session import get_db_context
from src.infrastructure.llm.usage_metadata import (
    UsageTokens,
    model_name_of_response,
    sum_usage,
    tokens_from_response,
)

if TYPE_CHECKING:
    from src.infrastructure.llm.token_capture import TokenCaptureHandler

logger = structlog.get_logger(__name__)


async def is_instance_spend_blocked() -> bool:
    """Has the deployment exhausted today's ceiling?

    Delegates to the one implementation that already resolves the effective
    ceiling — the smallest of the deployment bound and the operator setting —
    and queries the ledger. A second resolution here would be a second opinion
    on the same question, which is how two ceilings come to disagree.

    Returns:
        True when the caller must skip its model call, False otherwise
        (including when no ceiling is configured at all).
    """
    from src.domains.usage_limits.service import UsageLimitService

    decision = await UsageLimitService.instance_budget_block()
    if decision is None:
        return False
    # The verdict's code is logged where it is decided (`instance_daily_budget_blocked`);
    # a `blocked_reason` field may hold an administrator's words (ADR-317).
    logger.warning(
        "instance_spend_blocked",
        limit=decision.exceeded_limit,
        status=decision.status.value,
    )
    return True


async def record_instance_llm_spend(
    *,
    surface: str,
    model_name: str | None,
    tokens_in: int,
    tokens_out: int,
    tokens_cache: int = 0,
    tokens_cache_write: int = 0,
    started_at: float | None = None,
    pricing_snapshot: PricingCacheData | None = None,
    billing_records: tuple[LLMBillingRecord, ...] = (),
) -> None:
    """Add one account-less model call to the instance's daily ledger.

    Args:
        surface: What spent, for the log line (e.g. ``personality_translation``).
        model_name: Model actually used, for the price lookup.
        tokens_in: Prompt tokens consumed.
        tokens_out: Completion tokens produced.
        tokens_cache: Cached prompt tokens, priced separately.
        tokens_cache_write: The part of ``tokens_in`` Claude wrote to its
            prompt cache, owed the write surcharge (ADR-306).
    """
    if tokens_in <= 0 and tokens_out <= 0 and tokens_cache <= 0 and not billing_records:
        return

    cost_eur = (
        sum((Decimal(str(record.cost_eur)) for record in billing_records), Decimal(0))
        if billing_records
        else _price(
            surface=surface,
            model_name=model_name,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            tokens_cache=tokens_cache,
            tokens_cache_write=tokens_cache_write,
            started_at=started_at,
            pricing_snapshot=pricing_snapshot,
        )
    )
    if cost_eur <= 0:
        return

    from src.infrastructure.proactive.tracking import settle_known_billing

    persisted = await settle_known_billing(
        _persist_instance_cost(surface, cost_eur, started_at, billing_records)
    )
    if not persisted:
        return

    logger.info(
        "instance_spend_recorded",
        surface=surface,
        model_name=model_name,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_eur=str(cost_eur),
    )


async def _persist_instance_cost(
    surface: str,
    cost_eur: Decimal,
    started_at: float | None,
    billing_records: tuple[LLMBillingRecord, ...],
) -> bool:
    """Commit known account-less spend under its own call-start UTC day."""
    from src.domains.usage_limits.instance_budget import InstanceBudgetService

    try:
        async with get_db_context() as db:
            if billing_records:
                for record in billing_records:
                    await InstanceBudgetService.record_spend(
                        db,
                        cost_eur=Decimal(str(record.cost_eur)),
                        now=datetime.fromtimestamp(record.started_at, UTC),
                    )
            else:
                await InstanceBudgetService.record_spend(
                    db,
                    cost_eur=cost_eur,
                    now=datetime.fromtimestamp(started_at, UTC) if started_at is not None else None,
                )
            await db.commit()
        return True
    except Exception as exc:  # noqa: BLE001 — accounting never breaks its caller
        logger.error("instance_spend_record_failed", surface=surface, error_type=type(exc).__name__)
        return False


async def record_instance_llm_call(
    *,
    surface: str,
    model_name: str | None,
    response: object,
    started_at: float | None = None,
    pricing_snapshot: PricingCacheData | None = None,
    capture: TokenCaptureHandler | None = None,
) -> None:
    """Record one account-less call straight from the model's answer.

    The one-line form for the common case, so a call site never re-implements
    the provider normalisation — the arithmetic that existed in seven
    disagreeing copies before :mod:`src.infrastructure.llm.usage_metadata`.

    Args:
        surface: What spent, for the log line.
        model_name: Model actually used, for the price lookup.
        response: The message the model returned.
    """
    records: tuple[LLMBillingRecord, ...] = ()
    if capture is not None:
        from src.infrastructure.cache.pricing_cache import capture_pricing_snapshot

        capture.ensure_response_record(
            response,
            model_name=model_name or "unknown",
            started_at=started_at if started_at is not None else datetime.now(UTC).timestamp(),
            snapshot=(
                pricing_snapshot if pricing_snapshot is not None else capture_pricing_snapshot()
            ),
        )
        records = capture.claim_billing_records(model_name or "unknown")
    if capture is None:
        usage = tokens_from_response(response)
    else:
        usage = sum_usage(
            UsageTokens(r.tokens_in, r.tokens_out, r.tokens_cache, r.tokens_cache_write)
            for r in records
        )
    await record_instance_llm_spend(
        surface=surface,
        model_name=model_name_of_response(response) or model_name,
        tokens_in=usage.prompt,
        tokens_out=usage.completion,
        tokens_cache=usage.cached,
        tokens_cache_write=usage.cache_write,
        started_at=started_at,
        pricing_snapshot=pricing_snapshot,
        billing_records=records,
    )


def _price(
    *,
    surface: str,
    model_name: str | None,
    tokens_in: int,
    tokens_out: int,
    tokens_cache: int,
    tokens_cache_write: int,
    started_at: float | None = None,
    pricing_snapshot: PricingCacheData | None = None,
) -> Decimal:
    """Cost of one call in euros, or zero when it cannot be priced.

    A model we cannot price must not become a model that spends nothing in
    silence, so the failure is logged rather than swallowed — an unpriced
    family is exactly how a ceiling stops bounding what it thinks it bounds.

    Args:
        surface: What spent, for the log line.
        model_name: Model actually used.
        tokens_in: Prompt tokens consumed.
        tokens_out: Completion tokens produced.
        tokens_cache: Cached prompt tokens.
        tokens_cache_write: The part of ``tokens_in`` written to Claude's
            prompt cache.

    Returns:
        The cost in euros, or ``Decimal("0")``.
    """
    if not model_name:
        logger.warning(
            "instance_spend_unpriced",
            surface=surface,
            reason="no_model_name",
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )
        return Decimal("0")
    try:
        _cost_usd, cost_eur = get_cached_cost_usd_eur(
            model=model_name,
            prompt_tokens=tokens_in,
            completion_tokens=tokens_out,
            cached_tokens=tokens_cache,
            cache_write_tokens=tokens_cache_write,
            at=datetime.fromtimestamp(started_at, UTC) if started_at is not None else None,
            snapshot=pricing_snapshot,
        )
    except Exception as exc:  # noqa: BLE001 — an unpriced call is still a call
        logger.warning(
            "instance_spend_unpriced",
            surface=surface,
            model_name=model_name,
            error_type=type(exc).__name__,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )
        return Decimal("0")
    return Decimal(str(cost_eur))


__all__ = [
    "is_instance_spend_blocked",
    "record_instance_llm_call",
    "record_instance_llm_spend",
]
