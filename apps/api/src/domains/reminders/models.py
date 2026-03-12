"""
Reminder domain models.

Phase: Reminders with FCM notifications
Created: 2025-12-28
"""

from datetime import datetime
from enum import Enum
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models import BaseModel


class ReminderStatus(str, Enum):
    """Status of a reminder."""

    PENDING = "pending"  # Awaiting notification
    PROCESSING = "processing"  # Being processed (locked)
    CANCELLED = "cancelled"  # Cancelled by user


class Reminder(BaseModel):
    """
    Reminder model.

    Stores user reminders with trigger time and notification status.
    All times are stored in UTC.

    Note: Reminders are deleted after successful notification (one-shot behavior).
    """

    __tablename__ = "reminders"

    # Foreign key to user
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Content
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="What the assistant understood - 'appeler le médecin'",
    )
    original_message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Exact user message - 'rappelle-moi d'appeler...'",
    )

    # Scheduling - ALWAYS IN UTC
    trigger_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        doc="When to send the reminder (UTC)",
    )
    user_timezone: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="Europe/Paris",
        doc="User timezone at creation time",
    )

    # Status with index for scheduler
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=ReminderStatus.PENDING.value,
        index=True,
        doc="pending → processing → cancelled (deleted after notification)",
    )

    # Retry tracking
    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        doc="Number of notification attempts",
    )

    # Audit fields (kept for retry logic)
    notification_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Error log if failed",
    )

    # Relationship
    user = relationship("User", back_populates="reminders", lazy="selectin")

    def __repr__(self) -> str:
        return f"<Reminder(id={self.id}, status={self.status}, trigger_at={self.trigger_at})>"
