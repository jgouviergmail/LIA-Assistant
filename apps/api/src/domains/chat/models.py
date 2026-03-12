"""
Database models for chat domain - token usage and message tracking.
"""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from src.core.field_names import FIELD_NODE_NAME
from src.infrastructure.database.models import BaseModel


class TokenUsageLog(BaseModel):
    """
    Audit trail for token usage per LLM node call.

    Immutable logs for detailed tracking and billing verification.
    One record per LLM call (node execution).

    Attributes:
        user_id: User who triggered the LLM call
        run_id: LangGraph run ID (links to MessageTokenSummary for aggregation)
        node_name: LangGraph node name (router, response, contacts_agent, etc.)
        model_name: LLM model used (gpt-4.1-mini, gpt-4-turbo, etc.)
        prompt_tokens: Number of input tokens
        completion_tokens: Number of output tokens
        cached_tokens: Number of cached input tokens (prompt caching)
        cost_usd: Estimated cost in USD at time of call
        cost_eur: Estimated cost in EUR at time of call
        usd_to_eur_rate: Exchange rate used for conversion (for audit)
        created_at: Timestamp of LLM call
    """

    __tablename__ = "token_usage_logs"

    user_id: Mapped[UUID] = mapped_column(index=True)
    run_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    node_name: Mapped[str] = mapped_column(String(100))
    model_name: Mapped[str] = mapped_column(String(100))

    # Token counts
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cached_tokens: Mapped[int] = mapped_column(Integer, default=0)

    # Cost tracking
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0.0"))
    cost_eur: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0.0"))
    usd_to_eur_rate: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("1.0"))

    __table_args__ = (
        Index("ix_token_usage_logs_user_created", "user_id", "created_at"),
        Index("ix_token_usage_logs_node_name", FIELD_NODE_NAME),
    )


class MessageTokenSummary(BaseModel):
    """
    Aggregated token usage per user message (SSE request).

    One record per chat message, aggregating all LLM nodes called.
    Links to user, session, conversation, and LangGraph run_id for traceability.

    For detailed per-node/per-model breakdown, JOIN with token_usage_logs via run_id.

    Attributes:
        user_id: User who sent the message
        session_id: Chat session identifier
        run_id: LangGraph run ID (unique per message, links to token_usage_logs)
        conversation_id: Conversation UUID (nullable for historical data)
        total_prompt_tokens: Sum of all prompt tokens across nodes
        total_completion_tokens: Sum of all completion tokens across nodes
        total_cached_tokens: Sum of all cached tokens across nodes
        total_cost_eur: Total cost in EUR for this message
        created_at: Timestamp of message
    """

    __tablename__ = "message_token_summary"

    user_id: Mapped[UUID] = mapped_column(index=True)
    session_id: Mapped[str] = mapped_column(String(255), index=True)
    run_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    conversation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Aggregated token counts
    total_prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_cached_tokens: Mapped[int] = mapped_column(Integer, default=0)

    # Total cost (LLM only, Google API cost tracked separately)
    total_cost_eur: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0.0"))

    # Google API tracking (Places, Routes, Geocoding, Static Maps)
    google_api_requests: Mapped[int] = mapped_column(Integer, default=0)
    google_api_cost_eur: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0.0"))

    __table_args__ = (Index("ix_message_token_summary_user_created", "user_id", "created_at"),)


class UserStatistics(BaseModel):
    """
    Pre-calculated user statistics cache for dashboard.

    Avoids expensive SUM() queries on millions of rows.
    Updated incrementally after each message.

    Attributes:
        user_id: User UUID (unique)

        # Lifetime totals
        total_prompt_tokens: All-time prompt tokens
        total_completion_tokens: All-time completion tokens
        total_cached_tokens: All-time cached tokens
        total_cost_eur: All-time cost in EUR
        total_messages: All-time user messages sent

        # Current billing cycle (monthly from signup date)
        current_cycle_start: Start date of current billing cycle
        cycle_prompt_tokens: Prompt tokens this cycle
        cycle_completion_tokens: Completion tokens this cycle
        cycle_cached_tokens: Cached tokens this cycle
        cycle_cost_eur: Cost in EUR this cycle
        cycle_messages: Messages sent this cycle

        last_updated_at: Last update timestamp
    """

    __tablename__ = "user_statistics"

    user_id: Mapped[UUID] = mapped_column(unique=True, index=True)

    # Lifetime totals
    total_prompt_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    total_completion_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    total_cached_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    total_cost_eur: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0.0"))
    total_messages: Mapped[int] = mapped_column(BigInteger, default=0)

    # Lifetime Google API totals
    total_google_api_requests: Mapped[int] = mapped_column(BigInteger, default=0)
    total_google_api_cost_eur: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), default=Decimal("0.0")
    )

    # Current billing cycle
    current_cycle_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    cycle_prompt_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    cycle_completion_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    cycle_cached_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    cycle_cost_eur: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0.0"))
    cycle_messages: Mapped[int] = mapped_column(BigInteger, default=0)

    # Current billing cycle Google API
    cycle_google_api_requests: Mapped[int] = mapped_column(BigInteger, default=0)
    cycle_google_api_cost_eur: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), default=Decimal("0.0")
    )

    last_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
