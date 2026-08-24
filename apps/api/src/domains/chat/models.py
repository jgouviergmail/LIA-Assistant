"""
Database models for chat domain - token usage and message tracking.
"""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
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
        latency_ms: Wall time of the call in milliseconds (ADR-244)
        status: ``success`` / ``error`` (ADR-244)
        failure_kind: An ``LLM_FAILURE_KINDS`` member when the call failed
        llm_type: The configured slot the call was made for. Aggregates group
            by this and never by ``node_name``, whose values are unbounded.
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

    # Observation columns (ADR-244). Nullable with no backfill: they describe
    # calls made after the migration, and inventing history would be worse than
    # admitting its absence.
    latency_ms: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="Wall time of the LLM call in milliseconds"
    )
    status: Mapped[str | None] = mapped_column(String(16), nullable=True, comment="success / error")
    failure_kind: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        comment="LLM_FAILURE_KINDS member when status='error', NULL otherwise",
    )
    llm_type: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment=(
            "The configured slot from LLM_TYPES_REGISTRY. Aggregates group by "
            "this, never by node_name, whose values are unbounded free text"
        ),
    )

    __table_args__ = (
        Index("ix_token_usage_logs_user_created", "user_id", "created_at"),
        Index("ix_token_usage_logs_node_name", FIELD_NODE_NAME),
        # Lifetime-metrics aggregation (group by model_name, node_name over a
        # date range) and standalone created_at range scans, both stored with
        # created_at DESC (recent data is hit most). A covering INCLUDE variant
        # (ix_token_usage_logs_model_node_covering) is owned by the migration.
        # These DESC-ordered indexes are excluded from autogenerate comparison in
        # schema_drift (reflection can't be matched to postgresql_ops).
        Index(
            "ix_token_usage_logs_lifetime_aggregation",
            "model_name",
            FIELD_NODE_NAME,
            "created_at",
            postgresql_ops={"created_at": "DESC"},
        ),
        Index(
            "ix_token_usage_logs_created_at", "created_at", postgresql_ops={"created_at": "DESC"}
        ),
        # Controller window: the most recent calls of one (slot, model) pair.
        # node_name is deliberately absent — 101 distinct values were measured,
        # some carrying prompt fragments, so an index on it would be neither
        # selective nor safe to expose.
        Index(
            "ix_token_usage_logs_controller_window",
            "llm_type",
            "model_name",
            "created_at",
            postgresql_ops={"created_at": "DESC"},
        ),
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
    run_id: Mapped[str] = mapped_column(String(255))
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

    # Image Generation tracking (gpt-image-1, etc.)
    image_generation_requests: Mapped[int] = mapped_column(Integer, default=0)
    image_generation_cost_eur: Mapped[Decimal] = mapped_column(
        Numeric(10, 6), default=Decimal("0.0")
    )

    __table_args__ = (
        # Unique run_id (enforced by the constraint; its backing index serves lookups).
        UniqueConstraint("run_id", name="message_token_summary_run_id_key"),
        Index("ix_message_token_summary_user_created", "user_id", "created_at"),
    )


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

    user_id: Mapped[UUID] = mapped_column()

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

    # Lifetime Image Generation totals
    total_image_generation_requests: Mapped[int] = mapped_column(BigInteger, default=0)
    total_image_generation_cost_eur: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), default=Decimal("0.0")
    )

    # Current billing cycle Image Generation
    cycle_image_generation_requests: Mapped[int] = mapped_column(BigInteger, default=0)
    cycle_image_generation_cost_eur: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), default=Decimal("0.0")
    )

    # Lifetime STT (remote provider, e.g. ElevenLabs Scribe).
    # cost_eur is also added to total_cost_eur / cycle_cost_eur so the global
    # "Cost" tile and usage-limit checks naturally include STT.
    total_stt_audio_seconds: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.0"))
    total_stt_cost_eur: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0.0"))

    # Current billing cycle STT
    cycle_stt_audio_seconds: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.0"))
    cycle_stt_cost_eur: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0.0"))

    # Lifetime TTS (paid provider, e.g. OpenAI tts-1, ElevenLabs eleven_*).
    # cost_eur is also added to total_cost_eur / cycle_cost_eur so the global
    # "Cost" tile and usage-limit checks naturally include TTS. Mirror of STT.
    total_tts_characters: Mapped[Decimal] = mapped_column(Numeric(12, 0), default=Decimal("0"))
    total_tts_cost_eur: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0.0"))

    # Current billing cycle TTS
    cycle_tts_characters: Mapped[Decimal] = mapped_column(Numeric(12, 0), default=Decimal("0"))
    cycle_tts_cost_eur: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0.0"))

    last_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    # One statistics row per user (enforced by the constraint; its backing unique
    # index also serves user_id lookups).
    __table_args__ = (UniqueConstraint("user_id", name="user_statistics_user_id_key"),)

    def reset_cycle(self, cycle_start: datetime) -> None:
        """Start a new billing cycle: zero EVERY ``cycle_*`` counter.

        Single source of truth for cycle boundaries (audit wave 2, C2).
        The three call paths that can cross a boundary (message tracking,
        STT usage, dashboard read) must all call this method — hand-resetting
        a subset of counters leaks the other silos into the new cycle.

        Columns are discovered by introspection, so a future ``cycle_*``
        column is reset automatically without touching this method.

        Args:
            cycle_start: Start of the new billing cycle (timezone-aware UTC).
        """
        for column in self.__table__.columns:
            if not column.name.startswith("cycle_"):
                continue
            default = column.default.arg if column.default is not None else 0
            if callable(default):
                raise TypeError(
                    f"cycle_* columns must have scalar defaults, got callable " f"for {column.name}"
                )
            setattr(self, column.name, default)
        self.current_cycle_start = cycle_start
