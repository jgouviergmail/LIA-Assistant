"""
Pydantic schemas for chat domain API contracts.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.core.field_names import (
    FIELD_COST_EUR,
    FIELD_GOOGLE_API_COST_EUR,
    FIELD_GOOGLE_API_REQUESTS,
    FIELD_IMAGE_GENERATION_COST_EUR,
    FIELD_IMAGE_GENERATION_REQUESTS,
    FIELD_MESSAGE_COUNT,
    FIELD_TOKENS_CACHE,
    FIELD_TOKENS_IN,
    FIELD_TOKENS_OUT,
)


class UserStatisticsResponse(BaseModel):
    """
    Response schema for user statistics (dashboard).

    Contains both lifetime and current billing cycle metrics.
    Cost fields include LLM + Google API combined for accurate billing display.
    """

    model_config = ConfigDict(from_attributes=True)

    # User info
    user_id: UUID

    # Lifetime totals
    # total_since is populated by the service layer from ``user.created_at``
    # (the ORM statistics row does not carry it). A default keeps model_validate
    # working when constructing the response from ``UserStatistic``.
    total_since: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Start of the lifetime totals (the user's account creation date).",
    )
    total_prompt_tokens: int = Field(description="All-time prompt tokens")
    total_completion_tokens: int = Field(description="All-time completion tokens")
    total_cached_tokens: int = Field(description="All-time cached tokens")
    total_cost_eur: Decimal = Field(description="All-time cost in EUR (LLM + Google API)")
    total_messages: int = Field(description="All-time messages sent")
    total_google_api_requests: int = Field(default=0, description="All-time Google API requests")
    total_google_api_cost_eur: Decimal = Field(
        default=Decimal("0"), description="All-time Google API cost in EUR"
    )

    # Current billing cycle
    current_cycle_start: datetime = Field(description="Start of current billing cycle")
    cycle_prompt_tokens: int = Field(description="Prompt tokens this cycle")
    cycle_completion_tokens: int = Field(description="Completion tokens this cycle")
    cycle_cached_tokens: int = Field(description="Cached tokens this cycle")
    cycle_cost_eur: Decimal = Field(description="Cost in EUR this cycle (LLM + Google API)")
    cycle_messages: int = Field(description="Messages sent this cycle")
    cycle_google_api_requests: int = Field(default=0, description="Google API requests this cycle")
    cycle_google_api_cost_eur: Decimal = Field(
        default=Decimal("0"), description="Google API cost in EUR this cycle"
    )

    last_updated_at: datetime = Field(description="Last statistics update")


class TokenUsageSummary(BaseModel):
    """
    Summary of token usage for a single message.

    Used in SSE "done" chunk metadata.
    """

    tokens_in: int = Field(description="Total prompt tokens across all nodes")
    tokens_out: int = Field(description="Total completion tokens across all nodes")
    tokens_cache: int = Field(description="Total cached tokens across all nodes")
    cost_eur: float = Field(description="Total cost in EUR")
    message_count: int = Field(description="Number of user messages (always 1 per request)")
    google_api_requests: int = Field(default=0, description="Number of Google API requests")


@dataclass(frozen=True)
class TokenSummaryDTO:
    """
    Internal DTO for token summary data (PHASE 3.1.1 - Token Tracking Refactoring).

    Eliminates 15+ duplicate dictionary constructions across SSE error handlers
    and HITL flows. Provides type-safe abstraction with factory methods.

    This is an INTERNAL data structure (dataclass), separate from TokenUsageSummary
    which is a Pydantic model for API contracts.

    Design Decisions:
        - frozen=True: Immutable for safety (summaries shouldn't change after creation)
        - Factory methods: Explicit construction from different sources
        - to_metadata(): Convert to dict for SSE metadata (backward compatible)
        - to_dict(): Alias for compatibility with existing code

    Usage:
        >>> # From in-memory tracker
        >>> summary = TokenSummaryDTO.from_tracker(tracker)

        >>> # From DB query result
        >>> summary = TokenSummaryDTO.from_dict(db_result)

        >>> # Zero fallback for error paths
        >>> summary = TokenSummaryDTO.zero()

        >>> # Convert to SSE metadata
        >>> chunk = ChatStreamChunk(type="done", content="", metadata=summary.to_metadata())
    """

    tokens_in: int
    tokens_out: int
    tokens_cache: int
    cost_eur: float  # LLM token cost only (consolidation in to_metadata)
    message_count: int
    google_api_requests: int = 0
    google_api_cost_eur: float = 0.0
    image_generation_requests: int = 0
    image_generation_cost_eur: float = 0.0

    @classmethod
    def from_tracker(cls, tracker: Any) -> "TokenSummaryDTO":
        """
        Create DTO from TrackingContext in-memory aggregation.

        Args:
            tracker: TrackingContext instance with in-memory node records

        Returns:
            TokenSummaryDTO with aggregated values from tracker

        Example:
            >>> summary = TokenSummaryDTO.from_tracker(tracker)
            >>> assert summary.tokens_in > 0
        """
        mem_summary = tracker.get_summary()
        return cls(
            tokens_in=mem_summary[FIELD_TOKENS_IN],
            tokens_out=mem_summary[FIELD_TOKENS_OUT],
            tokens_cache=mem_summary[FIELD_TOKENS_CACHE],
            cost_eur=mem_summary[FIELD_COST_EUR],
            message_count=mem_summary[FIELD_MESSAGE_COUNT],
            google_api_requests=mem_summary.get(FIELD_GOOGLE_API_REQUESTS, 0),
            google_api_cost_eur=mem_summary.get(FIELD_GOOGLE_API_COST_EUR, 0.0),
            image_generation_requests=mem_summary.get(FIELD_IMAGE_GENERATION_REQUESTS, 0),
            image_generation_cost_eur=mem_summary.get(FIELD_IMAGE_GENERATION_COST_EUR, 0.0),
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TokenSummaryDTO":
        """
        Create DTO from dictionary (DB query result or API response).

        Args:
            data: Dictionary with token summary keys

        Returns:
            TokenSummaryDTO with values from dict

        Example:
            >>> db_result = await tracker.get_aggregated_summary_from_db()
            >>> summary = TokenSummaryDTO.from_dict(db_result)
        """
        return cls(
            tokens_in=data.get(FIELD_TOKENS_IN, 0),
            tokens_out=data.get(FIELD_TOKENS_OUT, 0),
            tokens_cache=data.get(FIELD_TOKENS_CACHE, 0),
            cost_eur=data.get(FIELD_COST_EUR, 0.0),
            message_count=data.get(FIELD_MESSAGE_COUNT, 0),
            google_api_requests=data.get(FIELD_GOOGLE_API_REQUESTS, 0),
            google_api_cost_eur=data.get(FIELD_GOOGLE_API_COST_EUR, 0.0),
            image_generation_requests=data.get(FIELD_IMAGE_GENERATION_REQUESTS, 0),
            image_generation_cost_eur=data.get(FIELD_IMAGE_GENERATION_COST_EUR, 0.0),
        )

    @classmethod
    def zero(cls) -> "TokenSummaryDTO":
        """
        Create zero-valued DTO for error fallback paths.

        Returns:
            TokenSummaryDTO with all zeros

        Example:
            >>> summary = TokenSummaryDTO.zero()
            >>> assert summary.tokens_in == 0
            >>> assert summary.cost_eur == 0.0
        """
        return cls(
            tokens_in=0,
            tokens_out=0,
            tokens_cache=0,
            cost_eur=0.0,
            message_count=0,
            google_api_requests=0,
        )

    def to_metadata(self) -> dict[str, Any]:
        """
        Convert to SSE metadata dictionary (backward compatible).

        Returns:
            Dict with token summary keys for ChatStreamChunk metadata

        Example:
            >>> summary = TokenSummaryDTO.zero()
            >>> metadata = summary.to_metadata()
            >>> assert "tokens_in" in metadata
            >>> assert "cost_eur" in metadata
        """
        # Consolidate all costs (LLM tokens + Google API + image generation)
        # into cost_eur so the frontend shows the true total
        total_cost = self.cost_eur + self.google_api_cost_eur + self.image_generation_cost_eur
        return {
            FIELD_TOKENS_IN: self.tokens_in,
            FIELD_TOKENS_OUT: self.tokens_out,
            FIELD_TOKENS_CACHE: self.tokens_cache,
            FIELD_COST_EUR: total_cost,
            FIELD_MESSAGE_COUNT: self.message_count,
            FIELD_GOOGLE_API_REQUESTS: self.google_api_requests,
        }

    def to_dict(self) -> dict[str, Any]:
        """
        Alias for to_metadata() for compatibility.

        Returns:
            Dict with token summary keys
        """
        return self.to_metadata()
