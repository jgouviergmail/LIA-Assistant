"""
Database models for conversations domain.
Manages conversation containers, messages, and audit trail for LangGraph persistence.
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    and_,
    column,
    false,
    func,
    or_,
    text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.constants import CONVERSATION_TITLE_MAX_LENGTH, CONVERSATION_TITLE_WHITESPACE
from src.core.conversation_target import ConversationKind
from src.infrastructure.database.models import BaseModel, UUIDMixin
from src.infrastructure.database.session import Base

if TYPE_CHECKING:
    from src.domains.users.models import User


class Conversation(BaseModel):
    """
    User conversation container for LangGraph checkpoints.

    One permanent main conversation and independently titled secondary ones.
    Business identity survives a reset; runtime_id names its current checkpoints.

    Attributes:
        id: Conversation UUID (primary key)
        user_id: Owning user UUID (foreign key)
        title: Conversation title (auto-generated or user-defined)
        title_auto: True while an annex waits for its first message to name it
        message_count: Number of messages in conversation
        total_tokens: Total tokens consumed in conversation
        deleted_at: Soft delete timestamp (nullable)
        created_at: Creation timestamp
        updated_at: Last update timestamp

    Relationships:
        user: User who owns this conversation
        messages: List of archived messages for UI display

    Notes:
        - LangGraph checkpoints are stored separately in checkpoints table
        - LangGraph thread_id names runtime_id, not a historical business FK
        - Soft delete pattern: deleted_at IS NULL = active conversation
    """

    __tablename__ = "conversations"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str | None] = mapped_column(String(CONVERSATION_TITLE_MAX_LENGTH), nullable=True)
    # ADR-378 amendment 2026-11-12: an annex created without a title waits for
    # its first message under a placeholder. A flag rather than a title compared
    # to that placeholder: the person may type the very same words, and a title
    # they typed is never replaced. SQL `comment=` mirrors the migration EXACTLY.
    title_auto: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=false(),
        nullable=False,
        comment="True while an annex waits for its first message to give it its title.",
    )
    kind: Mapped[ConversationKind] = mapped_column(
        SAEnum(
            ConversationKind,
            name="conversation_kind",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda kinds: [kind.value for kind in kinds],
            validate_strings=True,
        ),
        default=ConversationKind.MAIN,
        server_default="main",
        nullable=False,
    )
    revision: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0", nullable=False)
    runtime_id: Mapped[UUID] = mapped_column(default=uuid4, nullable=False)
    message_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    # Relationships
    user: Mapped[User] = relationship(back_populates="conversations")
    messages: Mapped[list[ConversationMessage]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="ConversationMessage.created_at.desc()",
    )

    __table_args__ = (
        UniqueConstraint("runtime_id", name="uq_conversations_runtime_id"),
        # A soft-deleted legacy main is reactivated, never replaced.
        Index(
            "uq_conversations_primary_user",
            "user_id",
            unique=True,
            postgresql_where=text("kind = 'main'"),
        ),
        CheckConstraint("revision >= 0", name="ck_conversations_revision"),
        CheckConstraint(
            or_(
                column("kind") != ConversationKind.SECONDARY.value,
                and_(
                    column("title").is_not(None),
                    func.length(func.btrim(column("title"), CONVERSATION_TITLE_WHITESPACE)) > 0,
                ),
            ),
            name="ck_conversations_secondary_title",
        ),
        Index("ix_conversations_user_created", "user_id", "created_at"),
        # DAU/WAU observability range scans (group-by-user after a date filter).
        Index("ix_conversations_created_at", "created_at"),
        Index("ix_conversations_updated_at", "updated_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<Conversation(id={self.id}, user_id={self.user_id}, messages={self.message_count})>"
        )


class ConversationCreationReceipt(BaseModel):
    """A content-free creation receipt retained until account removal.

    The result UUID deliberately has no conversation FK: a late retry of an
    already deleted annex must report retirement rather than create a new one.
    """

    __tablename__ = "conversation_creation_receipts"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    request_id: Mapped[UUID] = mapped_column(nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    conversation_id: Mapped[UUID] = mapped_column(nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "request_id", name="uq_conversation_creation_attempt"),
    )


class ConversationMessage(BaseModel):
    """
    Message archival for fast UI display.

    Stores individual messages (user/assistant/system) for quick retrieval
    without deserializing LangGraph checkpoints.

    Attributes:
        id: Message UUID (primary key)
        conversation_id: Conversation UUID (foreign key)
        role: Message role ('user', 'assistant', 'system')
        content: Message text content
        metadata: Optional JSONB metadata (run_id, intention, etc.)
        created_at: Message timestamp
        updated_at: Last update timestamp

    Relationships:
        conversation: Parent conversation

    Notes:
        - Separate from LangGraph state for performance
        - Indexed by (conversation_id, created_at, id) for deterministic pagination
        - Cascade delete: deleted when conversation is deleted
    """

    __tablename__ = "conversation_messages"

    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    message_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # STT cost attribution (user messages produced by a remote STT provider).
    # All five columns are NULL for assistant messages and for user messages
    # produced by the local Sherpa pipeline (which is free).
    stt_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    stt_audio_duration_seconds: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    stt_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    stt_cost_eur: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    stt_usd_to_eur_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)

    # TTS cost attribution (assistant messages synthesised by a paid TTS
    # provider). All six columns are NULL for user messages, free providers
    # (Edge), and assistant messages synthesised before TTS billing landed.
    tts_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    tts_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tts_characters: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tts_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    tts_cost_eur: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    tts_usd_to_eur_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)

    # ADR-276: a row of an out-of-turn run (a workboard ticket LIA executes).
    # It is archived like any turn — archive-first needs it, and the decision
    # register points at it — and the chat READ is what leaves it out.
    hidden: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
        comment="Row of an out-of-turn run: kept in full, excluded from the chat read.",
    )

    # Relationship
    conversation: Mapped[Conversation] = relationship(back_populates="messages")

    __table_args__ = (
        Index(
            "ix_conversation_messages_history_position",
            "conversation_id",
            "created_at",
            "id",
        ),
        Index(
            "ix_conversation_messages_run_position",
            "conversation_id",
            text("(message_metadata ->> 'run_id')"),
            "created_at",
            "id",
        ),
        Index(
            "ix_conversation_messages_stt_provider",
            "stt_provider",
            postgresql_where="stt_provider IS NOT NULL",
        ),
        Index(
            "ix_conversation_messages_tts_provider",
            "tts_provider",
            postgresql_where="tts_provider IS NOT NULL",
        ),
        # The rows an out-of-turn run wrote (ADR-276). Two readers need exactly
        # this small set once a minute for ever — the retention sweep and the
        # volume gauges — and the vast majority of a conversation is visible,
        # so the index carries only what they read.
        Index(
            "ix_conversation_messages_hidden",
            "created_at",
            postgresql_where="hidden",
        ),
    )

    def __repr__(self) -> str:
        return f"<ConversationMessage(id={self.id}, role={self.role}, conversation_id={self.conversation_id})>"


class ConversationAuditLog(Base, UUIDMixin):
    """
    Immutable audit log for conversation lifecycle events.

    Tracks conversation creation, renaming, reset, and deletion for compliance
    and debugging. Follows AdminAuditLog pattern (no TimestampMixin).

    Attributes:
        id: Audit log UUID (primary key)
        user_id: User UUID (foreign key)
        conversation_id: Conversation UUID (nullable)
        action: Action type ('created', 'renamed', 'titled', 'reset', 'deleted');
            'titled' is the automatic title an annex took from its first message
        message_count_at_action: Message count at action time (nullable)
        metadata: Optional JSONB metadata (total_tokens, reason, etc.)
        created_at: Action timestamp (immutable, no updated_at)

    Notes:
        - Immutable: no updates after creation
        - No TimestampMixin: only created_at field
        - Useful for GDPR compliance and support debugging
    """

    __tablename__ = "conversation_audit_log"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    conversation_id: Mapped[UUID | None] = mapped_column(nullable=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    message_count_at_action: Mapped[int | None] = mapped_column(Integer, nullable=True)
    audit_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # Timestamp - only created_at (audit logs are immutable). Per-user history
    # is served by the (user_id, created_at) composite below; no standalone
    # created_at index exists in the schema, so this column carries no
    # index=True (a created_at-only scan is not an access pattern here).
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    __table_args__ = (Index("ix_conversation_audit_log_user_created", "user_id", "created_at"),)

    def __repr__(self) -> str:
        return f"<ConversationAuditLog(action={self.action}, user_id={self.user_id}, conversation_id={self.conversation_id})>"
