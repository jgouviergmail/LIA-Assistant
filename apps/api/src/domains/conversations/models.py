"""
Database models for conversations domain.
Manages conversation containers, messages, and audit trail for LangGraph persistence.
"""

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models import BaseModel, UUIDMixin
from src.infrastructure.database.session import Base

if TYPE_CHECKING:
    from src.domains.auth.models import User


class Conversation(BaseModel):
    """
    User conversation container for LangGraph checkpoints.

    One conversation per user (1:1 mapping via unique user_id).
    Stores conversation metadata and links to checkpoints via thread_id.

    Attributes:
        id: Conversation UUID (primary key)
        user_id: User UUID (unique, foreign key)
        title: Conversation title (auto-generated or user-defined)
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
        - thread_id in LangGraph = conversation.id for checkpoint retrieval
        - Soft delete pattern: deleted_at IS NULL = active conversation
    """

    __tablename__ = "conversations"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    message_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="conversations")
    messages: Mapped[list["ConversationMessage"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="ConversationMessage.created_at.desc()",
    )

    __table_args__ = (Index("ix_conversations_user_created", "user_id", "created_at"),)

    def __repr__(self) -> str:
        return (
            f"<Conversation(id={self.id}, user_id={self.user_id}, messages={self.message_count})>"
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
        - Indexed by (conversation_id, created_at DESC) for pagination
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

    # Relationship
    conversation: Mapped["Conversation"] = relationship(back_populates="messages")

    __table_args__ = (
        Index(
            "ix_conversation_messages_conv_created",
            "conversation_id",
            "created_at",
            postgresql_ops={"created_at": "DESC"},
        ),
    )

    def __repr__(self) -> str:
        return f"<ConversationMessage(id={self.id}, role={self.role}, conversation_id={self.conversation_id})>"


class ConversationAuditLog(Base, UUIDMixin):
    """
    Immutable audit log for conversation lifecycle events.

    Tracks conversation creation, reset, and deletion for compliance
    and debugging. Follows AdminAuditLog pattern (no TimestampMixin).

    Attributes:
        id: Audit log UUID (primary key)
        user_id: User UUID (foreign key)
        conversation_id: Conversation UUID (nullable)
        action: Action type ('created', 'reset', 'deleted')
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

    # Timestamp - only created_at (audit logs are immutable)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )

    __table_args__ = (Index("ix_conversation_audit_log_user_created", "user_id", "created_at"),)

    def __repr__(self) -> str:
        return f"<ConversationAuditLog(action={self.action}, user_id={self.user_id}, conversation_id={self.conversation_id})>"
