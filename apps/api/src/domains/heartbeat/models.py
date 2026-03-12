"""
SQLAlchemy model for the Heartbeat domain.

Models:
- HeartbeatNotification: Audit trail for sent heartbeat proactive notifications.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models import UUIDMixin
from src.infrastructure.database.session import Base


class HeartbeatNotification(Base, UUIDMixin):
    """
    Audit trail for sent heartbeat proactive notifications.

    Tracks notifications sent to users with content, sources used,
    decision reasoning, and user feedback.

    NOTE: This is an audit table — no updated_at column.
    Notifications are immutable once created (except user_feedback).

    Attributes:
        user_id: Reference to user
        run_id: Unique ID linking to token tracking
        content: The notification message sent to the user
        content_hash: SHA256 hash for exact deduplication
        sources_used: JSON list of source types used (e.g. ["calendar", "weather"])
        decision_reason: LLM's reason for deciding to notify
        priority: Notification priority level (low, medium, high)
        user_feedback: User's feedback if provided (thumbs_up, thumbs_down)
        tokens_in: Input tokens consumed (decision + message phases)
        tokens_out: Output tokens consumed (decision + message phases)
        model_name: LLM model used for message generation
        created_at: Timestamp of notification creation
    """

    __tablename__ = "heartbeat_notifications"

    # Audit timestamp (no updated_at for immutable audit records)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Foreign keys
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Token tracking linkage
    run_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
    )

    # Content
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    content_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    # Context metadata
    sources_used: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="JSON list of source types used (e.g. calendar, weather).",
    )
    decision_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="LLM's reason for deciding to notify.",
    )
    priority: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        server_default="low",
        comment="Notification priority: low, medium, high.",
    )

    # User feedback
    user_feedback: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="User feedback: thumbs_up or thumbs_down.",
    )

    # Token tracking
    tokens_in: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    tokens_out: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    model_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    __table_args__ = (Index("ix_heartbeat_notifications_user_created", "user_id", "created_at"),)

    def __repr__(self) -> str:
        return (
            f"<HeartbeatNotification(id={self.id}, priority={self.priority}, "
            f"feedback={self.user_feedback})>"
        )
