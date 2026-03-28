"""
Token Tracking for Proactive Tasks.

Provides utilities to track and persist token usage for proactive tasks,
following the same pattern as memory_extractor.py and reminder_notification.py.

Token tracking ensures:
- Accurate cost calculation per proactive task
- User statistics updated (lifetime and billing cycle)
- Audit trail via token_usage_logs
- Aggregation via message_token_summary
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.cache.pricing_cache import get_cached_cost_usd_eur
from src.infrastructure.observability.logging import get_logger

if TYPE_CHECKING:
    from src.infrastructure.proactive.base import ProactiveTaskResult

logger = get_logger(__name__)


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


async def track_proactive_tokens(
    user_id: UUID,
    task_type: str,
    target_id: str,
    conversation_id: UUID | None,
    tokens_in: int,
    tokens_out: int,
    tokens_cache: int = 0,
    model_name: str | None = None,
    db: AsyncSession | None = None,
    run_id: str | None = None,
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
        run_id: Optional pre-generated run_id. When provided, uses it instead
            of generating a new one. Useful when the run_id must be known
            before tracking (e.g., for injection into archived message metadata).

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
    if tokens_in == 0 and tokens_out == 0:
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

    # Calculate cost
    cost_usd, cost_eur = 0.0, 0.0
    if model_name:
        try:
            cost_usd, cost_eur = get_cached_cost_usd_eur(
                model=model_name,
                prompt_tokens=tokens_in,
                completion_tokens=tokens_out,
                cached_tokens=tokens_cache,
            )
        except Exception as e:
            logger.warning(
                "proactive_tokens_cost_calculation_failed",
                task_type=task_type,
                model_name=model_name,
                error=str(e),
            )

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
            await tracker.record_node_tokens(
                node_name=f"proactive_{task_type}",
                model_name=model_name or "unknown",
                prompt_tokens=tokens_in,
                completion_tokens=tokens_out,
                cached_tokens=tokens_cache,
                cost_usd=cost_usd,
                cost_eur=cost_eur,
            )
            await tracker.commit()

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


async def track_proactive_tokens_from_result(
    user_id: UUID,
    task_type: str,
    conversation_id: UUID | None,
    result: ProactiveTaskResult,
    db: AsyncSession | None = None,
) -> str | None:
    """
    Convenience wrapper to track tokens from a ProactiveTaskResult.

    Args:
        user_id: User UUID
        task_type: Task type identifier
        conversation_id: Conversation UUID for linking
        result: ProactiveTaskResult with token usage
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
        model_name=result.model_name,
        db=db,
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
        self._call_count = 0

    def add(
        self,
        tokens_in: int,
        tokens_out: int,
        tokens_cache: int = 0,
        model_name: str | None = None,
    ) -> None:
        """
        Add token usage from an LLM call.

        Args:
            tokens_in: Input tokens
            tokens_out: Output tokens
            tokens_cache: Cached tokens
            model_name: Model name (updates if provided)
        """
        self.tokens_in += tokens_in
        self.tokens_out += tokens_out
        self.tokens_cache += tokens_cache
        self._call_count += 1
        if model_name:
            self.model_name = model_name

    def add_from_usage_metadata(self, usage_metadata: dict | None) -> None:
        """
        Add token usage from AIMessage.usage_metadata.

        Handles OpenAI's format where input_tokens includes cached tokens.

        Args:
            usage_metadata: usage_metadata dict from AIMessage
        """
        if not usage_metadata:
            return

        # Extract tokens (handle OpenAI format)
        raw_input = usage_metadata.get("input_tokens", 0)
        output = usage_metadata.get("output_tokens", 0)
        cached = usage_metadata.get("input_token_details", {}).get("cache_read", 0)

        # OpenAI's input_tokens includes cached tokens
        input_tokens = raw_input - cached

        self.add(
            tokens_in=input_tokens,
            tokens_out=output,
            tokens_cache=cached,
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
        """Total tokens consumed (input + output)."""
        return self.tokens_in + self.tokens_out

    @property
    def call_count(self) -> int:
        """Number of LLM calls tracked."""
        return self._call_count

    def to_result_dict(self) -> dict:
        """
        Get dict suitable for ProactiveTaskResult.

        Returns:
            Dict with tokens_in, tokens_out, tokens_cache, model_name
        """
        return {
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "tokens_cache": self.tokens_cache,
            "model_name": self.model_name,
        }
