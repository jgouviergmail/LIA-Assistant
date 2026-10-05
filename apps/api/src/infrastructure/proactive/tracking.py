"""
Token Tracking for Proactive Tasks.

Provides utilities to track and persist token usage for proactive tasks,
following the same pattern as memory_extractor.py and reminder_notification.py.

Token tracking ensures:
- Accurate cost calculation per proactive task
- User statistics updated (lifetime and billing cycle)
- Audit trail via token_usage_logs
- Aggregation via message_token_summary

And the model's tokens are not the only euros a run spends: :func:`out_of_turn_spend`
is the door an out-of-turn surface opens around its WHOLE act so that what its
sources bill on the deployment's key — a Google Maps Platform call, an
embedding — reaches the same ledgers (ADR-272 amendment, 2026-09-20). It lives
here, in infrastructure, because a domain the chat already reads (the briefing)
cannot import the chat's tracker without closing a cycle.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Callable, Coroutine
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime
from decimal import Decimal
from functools import wraps
from typing import TYPE_CHECKING, Any, ParamSpec, TypeVar
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.context import current_tracker
from src.core.llm_usage import LLMBillingRecord
from src.infrastructure.cache.pricing_cache import get_cached_cost_usd_eur, get_cached_usd_eur_rate
from src.infrastructure.llm.usage_metadata import tokens_from_usage_metadata
from src.infrastructure.observability.logging import get_logger

if TYPE_CHECKING:
    from src.domains.chat.service import TrackingContext
    from src.infrastructure.llm.token_capture import TokenCaptureHandler
    from src.infrastructure.proactive.base import ProactiveTaskResult

logger = get_logger(__name__)

# Bound the final ledger write; do not hold a cancelling worker indefinitely.
_BILLING_SETTLE_SECONDS = 10.0
_BillingParams = ParamSpec("_BillingParams")
_BillingResult = TypeVar("_BillingResult")


def _shield_known_billing(
    function: Callable[_BillingParams, Coroutine[Any, Any, str | None]],
) -> Callable[_BillingParams, Coroutine[Any, Any, str | None]]:
    """The common funnel finishes its one write before cancellation escapes."""

    @wraps(function)
    async def settled(*args: _BillingParams.args, **kwargs: _BillingParams.kwargs) -> str | None:
        return await settle_known_billing(function(*args, **kwargs))

    return settled


async def settle_known_billing(
    work: Coroutine[Any, Any, _BillingResult],
) -> _BillingResult | None:
    """Finish a known bill through cancellation, then propagate cancellation."""
    pending = asyncio.create_task(work)
    deadline = asyncio.get_running_loop().time() + _BILLING_SETTLE_SECONDS
    cancellation: asyncio.CancelledError | None = None
    while True:
        try:
            async with asyncio.timeout(max(0.0, deadline - asyncio.get_running_loop().time())):
                result = await asyncio.shield(pending)
            break
        except asyncio.CancelledError as exc:
            cancellation = exc
            if pending.done():
                raise
        except TimeoutError:
            pending.cancel()
            with suppress(asyncio.CancelledError):
                await pending
            logger.error("llm_billing_settle_timeout")
            if cancellation is not None:
                raise cancellation from None
            return None
    if cancellation is not None:
        raise cancellation
    return result


async def bill_captured_usage(
    capture: TokenCaptureHandler,
    *,
    user_id: UUID | None,
    task_type: str,
    target_id: str,
    model_name: str,
    source: str,
    run_id: str | None = None,
    failed: bool = False,
    llm_type: str | None = None,
) -> str | None:
    """Persist only provider-reported attempts, with one owner per capture.

    Claiming precedes any await. A failed or cancelled persistence is never
    blindly replayed: it may already have committed before acknowledgement.
    """
    if user_id is None:
        return None
    records = capture.claim_billing_records(model_name)
    if not records:
        return None
    return await settle_known_billing(
        track_proactive_tokens(
            user_id=user_id,
            task_type=task_type,
            target_id=target_id,
            conversation_id=None,
            tokens_in=sum(r.tokens_in for r in records),
            tokens_out=sum(r.tokens_out for r in records),
            tokens_cache=sum(r.tokens_cache for r in records),
            tokens_cache_write=sum(r.tokens_cache_write for r in records),
            model_name=model_name,
            source=source,
            run_id=run_id,
            billing_records=records,
            failed=failed,
            llm_type=llm_type,
        )
    )


@asynccontextmanager
async def capture_spend_on_failure(
    capture: TokenCaptureHandler,
    *,
    user_id: UUID | None,
    task_type: str,
    target_id: str,
    model_name: str,
    source: str,
    run_id: str | None = None,
    llm_type: str | None = None,
) -> AsyncIterator[None]:
    """Close known paid attempts before propagating an unsuccessful operation."""
    try:
        yield
    except BaseException:
        try:
            await bill_captured_usage(
                capture,
                user_id=user_id,
                task_type=task_type,
                target_id=target_id,
                model_name=model_name,
                source=source,
                run_id=run_id,
                failed=True,
                llm_type=llm_type,
            )
        except BaseException as exc:
            logger.error("captured_llm_bill_failed", error_type=type(exc).__name__)
        raise


def out_of_turn_spend(run_id: str, user_id: UUID, session_id: str) -> TrackingContext:
    """The accounting an out-of-turn surface opens around its whole act.

    A ``TrackingContext`` on the surface's own run id, persisted when it
    exits — with whatever the act billed in ANY family (``pending_families``),
    so a run that called Google and no model still writes its rows. The
    model's tokens keep their own door (:func:`track_proactive_tokens`, same
    run id, additive UPSERT). One of the ``ACCOUNTING_DOORS`` the Google spend
    roads guard checks for.

    Args:
        run_id: The act's correlation key (the run everything it costs files under).
        user_id: The account that benefits.
        session_id: The synthetic session label of the summary row.

    Returns:
        An entered-by-the-caller tracker (``async with``).
    """
    # Runtime import: the chat service imports this package's siblings, and
    # the module-level edge would be a cycle for the domains that read it.
    from src.domains.chat.service import TrackingContext

    return TrackingContext(run_id, user_id, session_id, None)


def ambient_run_id() -> str | None:
    """The run the enclosing accounting files under, when one is open.

    A task's step runs inside the runner's :func:`out_of_turn_spend`, which
    publishes itself as the ambient tracker for the whole act: a spend the step
    bills through :func:`track_proactive_tokens` belongs to THAT run — the one
    its reads were collected in — never to a run of its own (ADR-324 decision
    31: a heartbeat's skip was filed apart from the sweep that read the
    sources for it).

    Returns:
        The ambient run id, or None outside any accounting.
    """
    tracker = current_tracker.get()
    return None if tracker is None else tracker.run_id


def generate_proactive_run_id(task_type: str, target_id: str) -> str:
    """Generate a unique run_id for a proactive task execution.

    Format: proactive_{task_type}_{target_id_prefix}_{random_hex}

    This is extracted as a standalone function so callers can pre-generate
    the run_id before dispatch (for metadata injection) and pass it to
    track_proactive_tokens() for consistent linkage.

    Args:
        task_type: Task type identifier (e.g., "interest", "heartbeat").
        target_id: Target identifier (truncated to 12 chars in the run_id).

    Returns:
        Unique run_id string.
    """
    return f"proactive_{task_type}_{target_id[:12]}_{uuid.uuid4().hex[:8]}"


async def _record_out_of_turn(
    user_id: UUID,
    task_type: str,
    run_id: str,
    source: str,
    *,
    failed: bool = False,
) -> None:
    """File one row in the decision register for a run LIA started itself.

    Measured 2026-09-07 by joining ``token_usage_logs`` to ``agent_decisions``
    on ``run_id``: every conversational surface was recorded in full — 24/24,
    22/22, 10/10 — while 228 proactive runs over fourteen days produced not one
    row. Nothing was failing; the registers follow the GRAPH, and these
    surfaces call the model directly.

    The account holder felt it as silence: the briefing read their mail every
    morning at their expense, and their register said nothing had happened
    since their last conversation.

    Never raises. The provider has already billed this call, and a register
    that can take a briefing down is worse than the gap it closes.

    Args:
        user_id: Account the work was done for.
        task_type: The surface (``briefing``, ``heartbeat``, ...).
        run_id: The run the cost was filed under; the row reuses it so the two
            records point at each other.
        source: Who asked, declared by the call site. This funnel is named for
            the plumbing, not for the initiative: the briefing is reached only
            from a request, a reminder is the person's own deferred
            instruction, and only a runner sweep is LIA's own idea.
        failed: Whether the run spent and then did not deliver — a generation
            broken after its model call, a notification that reached nobody.
    """
    try:
        from src.domains.agents.effects.decision_recorder import record_decision
        from src.domains.agents.effects.decisions import out_of_turn_decision
        from src.domains.agents.effects.models import DecisionOutcome

        decision = out_of_turn_decision(
            user_id=user_id, run_id=run_id, thread_id=run_id, source=source
        )
        # The work is done and paid for by the time this runs, so the outcome
        # is known. Leaving it at the ``interrupted`` default would file every
        # successful briefing as an interruption.
        decision.outcome = DecisionOutcome.FAILED if failed else DecisionOutcome.ANSWERED
        decision.route = task_type
        await record_decision(decision)
    except Exception as exc:  # noqa: BLE001 - observing must never break the observed
        logger.warning(
            "out_of_turn_decision_not_recorded",
            task_type=task_type,
            run_id=run_id,
            error_type=type(exc).__name__,
        )


@_shield_known_billing
async def track_proactive_tokens(
    user_id: UUID,
    task_type: str,
    target_id: str,
    conversation_id: UUID | None,
    tokens_in: int,
    tokens_out: int,
    tokens_cache: int = 0,
    model_name: str | None = None,
    *,
    source: str,
    db: AsyncSession | None = None,
    run_id: str | None = None,
    llm_type: str | None = None,
    tokens_cache_write: int = 0,
    failed: bool = False,
    started_at: float | None = None,
    billing_records: tuple[LLMBillingRecord, ...] = (),
) -> str | None:
    """
    Persist token usage from a proactive task.

    Follows the established pattern from memory_extractor.py:
    - Generates unique run_id for linking to token_usage_logs
    - Calculates cost via PricingCacheService
    - Persists via TrackingContext to:
        - token_usage_logs (detailed breakdown)
        - message_token_summary (aggregated per run)
        - user_statistics (cumulative per user)

    Args:
        user_id: User UUID
        task_type: Task type identifier (e.g., "interest", "birthday")
        target_id: Target identifier (e.g., interest_id, event_id)
        conversation_id: Conversation UUID for linking (optional)
        tokens_in: Input tokens consumed
        tokens_out: Output tokens generated
        tokens_cache: Cached tokens used (for cost calculation)
        model_name: LLM model used (for cost lookup)
        db: Optional external database session for transaction composition.
            When provided, uses this session and does NOT commit - caller
            is responsible for transaction management.
        source: Who asked — ``user``, ``scheduled`` or ``proactive``. Required
            and without a default on purpose: this funnel serves surfaces of all
            three kinds, and a default would file a page load LIA never chose to
            make as an initiative it took.
        run_id: Optional pre-generated run_id. When provided, uses it instead
            of generating a new one. Useful when the run_id must be known
            before tracking (e.g., for injection into archived message metadata).
        tokens_cache_write: The part of ``tokens_in`` Claude wrote to its
            prompt cache, owed the write surcharge (ADR-306). Every caller
            passes it -- ``test_cache_write_reaches_every_price``.
        failed: The run spent and did not deliver: it is billed all the same,
            and filed as ``failed`` in the decision register.

    Returns:
        run_id if tokens were tracked, None if no tokens to track

    Example:
        >>> # Standalone usage (creates own session)
        >>> run_id = await track_proactive_tokens(
        ...     user_id=user.id,
        ...     task_type="interest",
        ...     target_id=str(interest.id),
        ...     conversation_id=conversation.id,
        ...     tokens_in=500,
        ...     tokens_out=150,
        ...     model_name="gpt-4.1-mini",
        ... )
        >>>
        >>> # With pre-generated run_id (for metadata linkage)
        >>> rid = generate_proactive_run_id("heartbeat", target_id)
        >>> # ... inject rid into archived message metadata ...
        >>> await track_proactive_tokens(..., run_id=rid)
    """
    # Skip if no tokens to track
    if tokens_in == 0 and tokens_out == 0 and tokens_cache == 0 and not billing_records:
        logger.debug(
            "proactive_tokens_skip",
            task_type=task_type,
            user_id=str(user_id),
            reason="no_tokens",
        )
        return None

    # Use pre-generated run_id or generate a new one
    if run_id is None:
        run_id = generate_proactive_run_id(task_type, target_id)
    if started_at is None:
        started_at = datetime.now(UTC).timestamp()

    records = billing_records or _fallback_billing_record(
        task_type, model_name, started_at, tokens_in, tokens_out, tokens_cache, tokens_cache_write
    )
    cost_eur = sum(record.cost_eur for record in records)

    try:
        # Import here to avoid circular imports
        from src.domains.chat.service import TrackingContext

        async with TrackingContext(
            run_id=run_id,
            user_id=user_id,
            session_id=f"proactive_{task_type}_{target_id[:12]}",
            conversation_id=conversation_id,  # None when heartbeat skips (no notification sent)
            auto_commit=False,
            db=db,  # Pass external session for transaction composition
        ) as tracker:
            await _record_priced_attempts(
                tracker,
                f"proactive_{task_type}",
                llm_type,
                records,
            )
            await tracker.commit()

        await _record_out_of_turn(user_id, task_type, run_id, source, failed=failed)

        logger.info(
            "proactive_tokens_tracked",
            task_type=task_type,
            user_id=str(user_id),
            target_id=target_id[:12],
            run_id=run_id,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            tokens_cache=tokens_cache,
            cost_eur=cost_eur,
            model_name=model_name,
            external_session=db is not None,
        )

        return run_id

    except Exception as e:
        # Log error but don't fail the task - token tracking is not critical
        logger.error(
            "proactive_tokens_tracking_failed",
            task_type=task_type,
            user_id=str(user_id),
            target_id=target_id[:12],
            error=str(e),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )
        return None


def _fallback_billing_record(
    task_type: str,
    model_name: str | None,
    started_at: float,
    tokens_in: int,
    tokens_out: int,
    tokens_cache: int,
    tokens_cache_write: int,
) -> tuple[LLMBillingRecord, ...]:
    """Price one legacy reading atomically; retained attempts bypass this door."""
    from src.infrastructure.cache.pricing_cache import capture_pricing_snapshot

    snapshot = capture_pricing_snapshot()
    usd, eur = 0.0, 0.0
    if model_name:
        try:
            usd, eur = get_cached_cost_usd_eur(
                model=model_name,
                prompt_tokens=tokens_in,
                completion_tokens=tokens_out,
                cached_tokens=tokens_cache,
                cache_write_tokens=tokens_cache_write,
                at=datetime.fromtimestamp(started_at, UTC),
                snapshot=snapshot,
            )
        except Exception as exc:
            logger.warning(
                "proactive_tokens_cost_calculation_failed",
                task_type=task_type,
                model_name=model_name,
                error_type=type(exc).__name__,
            )
    return (
        LLMBillingRecord(
            model_name=model_name or "unknown",
            started_at=started_at,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            tokens_cache=tokens_cache,
            tokens_cache_write=tokens_cache_write,
            cost_usd=usd,
            cost_eur=eur,
            usd_to_eur_rate=get_cached_usd_eur_rate(snapshot),
        ),
    )


async def _record_priced_attempts(
    tracker: TrackingContext,
    node_name: str,
    llm_type: str | None,
    records: tuple[LLMBillingRecord, ...],
) -> None:
    """Persist each attempt once; aggregated display costs never re-price it."""
    for record in records:
        await tracker.record_node_tokens(
            node_name=node_name,
            model_name=record.model_name,
            llm_type=llm_type,
            prompt_tokens=record.tokens_in,
            completion_tokens=record.tokens_out,
            cached_tokens=record.tokens_cache,
            cache_write_tokens=record.tokens_cache_write,
            cost_usd=record.cost_usd,
            cost_eur=record.cost_eur,
            usd_to_eur_rate=Decimal(str(record.usd_to_eur_rate)),
            started_at=record.started_at,
            status=record.status,
            failure_kind=record.failure_kind,
        )


async def track_proactive_tokens_from_result(
    user_id: UUID,
    task_type: str,
    conversation_id: UUID | None,
    result: ProactiveTaskResult,
    *,
    source: str,
    db: AsyncSession | None = None,
) -> str | None:
    """
    Convenience wrapper to track tokens from a ProactiveTaskResult.

    Args:
        user_id: User UUID
        task_type: Task type identifier
        conversation_id: Conversation UUID for linking
        result: ProactiveTaskResult with token usage
        source: Who asked (see :func:`track_proactive_tokens`)
        db: Optional external database session (see track_proactive_tokens)

    Returns:
        run_id if tokens were tracked, None otherwise
    """
    return await track_proactive_tokens(
        user_id=user_id,
        task_type=task_type,
        target_id=result.target_id or "unknown",
        conversation_id=conversation_id,
        tokens_in=result.tokens_in,
        tokens_out=result.tokens_out,
        tokens_cache=result.tokens_cache,
        tokens_cache_write=result.tokens_cache_write,
        model_name=result.model_name,
        source=source,
        db=db,
        billing_records=result.billing_records,
    )


class TokenAccumulator:
    """
    Accumulator for tracking tokens across multiple LLM calls.

    Useful when a proactive task makes multiple LLM calls (e.g., fetch + format)
    and needs to aggregate token usage before final tracking.

    Example:
        >>> accumulator = TokenAccumulator(model_name="gpt-4.1-mini")
        >>>
        >>> # First LLM call (fetch from source)
        >>> result1 = await llm.invoke(fetch_prompt)
        >>> accumulator.add_from_usage_metadata(result1.usage_metadata)
        >>>
        >>> # Second LLM call (format for presentation)
        >>> result2 = await llm.invoke(format_prompt)
        >>> accumulator.add_from_usage_metadata(result2.usage_metadata)
        >>>
        >>> # Get totals for tracking
        >>> total_in, total_out, total_cache = accumulator.get_totals()
    """

    def __init__(self, model_name: str | None = None):
        """Initialize accumulator."""
        self.model_name = model_name
        self.tokens_in = 0
        self.tokens_out = 0
        self.tokens_cache = 0
        self.tokens_cache_write = 0
        self._call_count = 0
        self.billing_records: tuple[LLMBillingRecord, ...] = ()

    def add(
        self,
        tokens_in: int,
        tokens_out: int,
        tokens_cache: int = 0,
        model_name: str | None = None,
        tokens_cache_write: int = 0,
        *,
        started_at: float | None = None,
        billing_record: LLMBillingRecord | None = None,
    ) -> None:
        """
        Add token usage from an LLM call.

        Args:
            tokens_in: Input tokens
            tokens_out: Output tokens
            tokens_cache: Cached tokens
            model_name: Model name (updates if provided)
            tokens_cache_write: The part of ``tokens_in`` written to Claude's
                prompt cache (ADR-306).
        """
        self.tokens_in += tokens_in
        self.tokens_out += tokens_out
        self.tokens_cache += tokens_cache
        self.tokens_cache_write += tokens_cache_write
        self._call_count += 1
        if model_name:
            self.model_name = model_name
        if billing_record is not None:
            self.billing_records += (billing_record,)
        elif tokens_in or tokens_out or tokens_cache:
            from src.infrastructure.llm.token_capture import priced_call
            from src.infrastructure.llm.usage_metadata import UsageTokens

            self.billing_records += (
                priced_call(
                    UsageTokens(tokens_in, tokens_out, tokens_cache, tokens_cache_write),
                    self.model_name or "unknown",
                    started_at if started_at is not None else datetime.now(UTC).timestamp(),
                ),
            )

    def add_from_usage_metadata(
        self,
        usage_metadata: dict | None,
        *,
        started_at: float | None = None,
        model_name: str | None = None,
    ) -> None:
        """
        Add token usage from AIMessage.usage_metadata.

        Delegates to the one implementation that reads both provider
        spellings and subtracts the cache — this copy read only OpenAI's.

        Args:
            usage_metadata: usage_metadata dict from AIMessage
        """
        usage = tokens_from_usage_metadata(usage_metadata)
        if usage.is_empty:
            return
        self.add(
            tokens_in=usage.prompt,
            tokens_out=usage.completion,
            tokens_cache=usage.cached,
            tokens_cache_write=usage.cache_write,
            started_at=started_at,
            model_name=model_name,
        )

    def get_totals(self) -> tuple[int, int, int]:
        """
        Get total token counts.

        Returns:
            Tuple of (tokens_in, tokens_out, tokens_cache)
        """
        return self.tokens_in, self.tokens_out, self.tokens_cache

    @property
    def total_tokens(self) -> int:
        """Total tokens consumed, including prompt cache reads."""
        return self.tokens_in + self.tokens_out + self.tokens_cache

    @property
    def call_count(self) -> int:
        """Number of LLM calls tracked."""
        return self._call_count

    def to_result_dict(self) -> dict:
        """
        Get dict suitable for ProactiveTaskResult.

        Returns:
            Dict with tokens_in, tokens_out, tokens_cache, tokens_cache_write,
            model_name
        """
        return {
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "tokens_cache": self.tokens_cache,
            "tokens_cache_write": self.tokens_cache_write,
            "model_name": self.model_name,
            "billing_records": self.billing_records,
        }
