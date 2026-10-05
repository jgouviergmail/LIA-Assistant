"""Journal call accounting and the Settings cost projection."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from langchain_core.messages import AIMessage

from src.core.llm_usage import LLMBillingRecord
from src.infrastructure.llm.token_capture import TokenCaptureHandler
from src.infrastructure.llm.usage_metadata import UsageTokens, sum_usage, tokens_from_response
from src.infrastructure.observability.logging import get_logger

if TYPE_CHECKING:
    from src.domains.chat.service import TrackingContext

logger = get_logger(__name__)


# =============================================================================
# Token Persistence (same pattern as _persist_memory_tokens)
# =============================================================================


def _journal_conversation_id(conversation_id: str | None) -> UUID | None:
    """Keep the optional conversation link without rejecting known spend."""
    if not conversation_id:
        return None
    try:
        return UUID(conversation_id)
    except ValueError:
        logger.debug("journal_invalid_conversation_id", conversation_id=conversation_id)
        return None


def _journal_usage(records: tuple[LLMBillingRecord, ...], result: AIMessage | None) -> UsageTokens:
    """Project counters from the owned attempts, or the legacy direct reply."""
    if not records:
        return tokens_from_response(result)
    return sum_usage(
        UsageTokens(
            record.tokens_in, record.tokens_out, record.tokens_cache, record.tokens_cache_write
        )
        for record in records
    )


async def _record_journal_attempts(
    tracker: TrackingContext,
    records: tuple[LLMBillingRecord, ...],
    *,
    node_name: str,
    duration_ms: float,
    requested_model: str | None,
    failed: bool,
) -> None:
    """Preserve each captured attempt's price, timestamp and failure evidence."""
    for record in records:
        await tracker.record_node_tokens(
            node_name=node_name,
            model_name=record.model_name,
            prompt_tokens=record.tokens_in,
            completion_tokens=record.tokens_out,
            cached_tokens=record.tokens_cache,
            cache_write_tokens=record.tokens_cache_write,
            cost_usd=record.cost_usd,
            cost_eur=record.cost_eur,
            usd_to_eur_rate=Decimal(str(record.usd_to_eur_rate)),
            started_at=record.started_at,
            duration_ms=duration_ms if len(records) == 1 else 0.0,
            requested_model=requested_model,
            llm_type=node_name,
            status="error" if failed else record.status,
            failure_kind=record.failure_kind,
        )


async def _persist_journal_tokens(
    user_id: str,
    session_id: str,
    conversation_id: str | None,
    result: AIMessage | None,
    model_name: str,
    parent_run_id: str | None = None,
    node_name: str = "journal_extraction",
    duration_ms: float = 0.0,
    started_at: float | None = None,
    requested_model: str | None = None,
    capture: TokenCaptureHandler | None = None,
    failed: bool = False,
) -> None:
    """Persist token usage from journal LLM call to database.

    Uses TrackingContext for real cost calculation and dashboard integration.
    Same pattern as memory_extractor._persist_memory_tokens().

    Args:
        user_id: User ID for statistics
        session_id: Session/thread ID
        conversation_id: Conversation UUID (optional)
        result: AIMessage with usage_metadata
        model_name: LLM model used
        parent_run_id: UPSERT into parent message's summary if provided
        node_name: Node name for cost attribution
    """
    from src.domains.chat.service import TrackingContext

    try:
        records = capture.claim_billing_records(model_name) if capture else ()
        # A callback capture owns all attempts; a second settlement must not
        # re-read the final AIMessage and bill the same reply again.
        if capture is not None and not records:
            return
        usage = _journal_usage(records, result)
        if not records and usage.is_empty:
            return

        run_id = parent_run_id or f"journal_{uuid.uuid4().hex[:12]}"

        async with TrackingContext(
            run_id=run_id,
            user_id=UUID(user_id),
            session_id=session_id,
            conversation_id=_journal_conversation_id(conversation_id),
            auto_commit=False,
        ) as tracker:
            if records:
                await _record_journal_attempts(
                    tracker,
                    records,
                    node_name=node_name,
                    duration_ms=duration_ms,
                    requested_model=requested_model,
                    failed=failed,
                )
            else:
                await tracker.record_node_tokens(
                    node_name=node_name,
                    model_name=model_name,
                    prompt_tokens=usage.prompt,
                    completion_tokens=usage.completion,
                    cached_tokens=usage.cached,
                    cache_write_tokens=usage.cache_write,
                    duration_ms=duration_ms,
                    started_at=started_at,
                    requested_model=requested_model,
                )
            await tracker.commit()

        logger.info(
            "journal_tokens_persisted",
            user_id=user_id,
            node_name=node_name,
            input_tokens=usage.prompt,
            output_tokens=usage.completion,
            model_name=model_name,
        )

    except Exception as e:
        logger.error(
            "journal_tokens_persistence_failed",
            user_id=user_id,
            error=str(e),
            exc_info=True,
        )


# =============================================================================
# User Cost Update
# =============================================================================


def _journal_cost_projection(
    result: AIMessage,
    model_name: str,
    started_at: float | None,
    capture: TokenCaptureHandler | None,
) -> tuple[UsageTokens, float, datetime | None] | None:
    """Calculate the Settings projection from frozen records when available."""
    records = capture.get_billing_records(model_name) if capture else ()
    if not records and not getattr(result, "usage_metadata", None):
        return None
    tokens = _journal_usage(records, result)
    if records:
        return (
            tokens,
            sum(record.cost_eur for record in records),
            datetime.fromtimestamp(min(record.started_at for record in records), UTC),
        )
    from src.infrastructure.cache.pricing_cache import get_cached_cost_usd_eur

    billed_at = datetime.fromtimestamp(started_at, UTC) if started_at is not None else None
    _, cost_eur = get_cached_cost_usd_eur(
        model=model_name,
        prompt_tokens=tokens.prompt,
        completion_tokens=tokens.completion,
        cached_tokens=tokens.cached,
        cache_write_tokens=tokens.cache_write,
        at=billed_at,
    )
    return tokens, cost_eur, billed_at


async def _update_user_last_cost(
    user_id: str,
    result: AIMessage,
    model_name: str,
    source: str = "extraction",
    started_at: float | None = None,
    capture: TokenCaptureHandler | None = None,
) -> None:
    """Update user's journal_last_cost_* fields for Settings UI display.

    Args:
        user_id: User ID
        result: AIMessage with usage_metadata
        model_name: LLM model used
        source: 'extraction' or 'consolidation'
    """
    from src.infrastructure.database import get_db_context

    try:
        projection = _journal_cost_projection(result, model_name, started_at, capture)
        if projection is None:
            return
        tokens, cost_eur, billed_at = projection

        from src.domains.users.models import User

        async with get_db_context() as db:
            from sqlalchemy import select

            result_user = await db.execute(select(User).where(User.id == UUID(user_id)))
            user = result_user.scalar_one_or_none()
            if user:
                user.journal_last_cost_tokens_in = tokens.prompt + tokens.cached
                user.journal_last_cost_tokens_out = tokens.completion
                user.journal_last_cost_eur = Decimal(str(cost_eur))
                user.journal_last_cost_at = billed_at or datetime.now(UTC)
                user.journal_last_cost_source = source
                await db.commit()

    except Exception as e:
        logger.warning(
            "journal_user_cost_update_failed",
            user_id=user_id,
            error=str(e),
        )
