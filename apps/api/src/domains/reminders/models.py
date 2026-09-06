"""
Reminder domain models.

Phase: Reminders with FCM notifications
Created: 2025-12-28
"""

from datetime import datetime
from enum import Enum
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.core.recurrence import RecurrenceSpec
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

    A reminder is deleted once it has no future left. That is not a special
    case for one-shot reminders — it is the ONE rule: the scheduler asks
    ``rearm_after`` what to arm next, and a ``None`` answer means the row has
    nothing more to do. A single occurrence answers ``None`` the first time,
    which is exactly the historical behaviour; a daily one answers tomorrow;
    a bounded series answers ``None`` after its last instant.

    That is why ``trigger_at`` stays NOT NULL, unlike a routine's
    ``next_trigger_at``: a reminder with no future does not exist.
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

    # Schedule — ONE authority (generic recurrence, `src/core/recurrence`).
    # `trigger_at` below stays the instant the poll reads; the spec is what
    # RE-ARMS it. A one-shot reminder carries `freq='once'`, so the two agree
    # by construction and no branch reads "is this recurring".
    recurrence: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="RecurrenceSpec: which calendar days, and which moments in them.",
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
        default=DEFAULT_USER_DISPLAY_TIMEZONE,
        doc="User timezone at creation time",
    )

    # Status. The scheduler queries are served by the partial indexes
    # ix_reminders_pending_trigger (WHERE status='pending') and
    # ix_reminders_processing, created in migration and owned there (they are
    # not expressible faithfully in the ORM). No plain full-column status index
    # exists in the schema, so this column carries no index=True.
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=ReminderStatus.PENDING.value,
        doc="pending → processing → pending again (re-armed) or the row is deleted",
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

    @property
    def recurrence_spec(self) -> RecurrenceSpec:
        """The stored schedule, parsed.

        A property rather than a column type: the row keeps plain JSONB, so a
        migration or an admin query never depends on the Python model.

        Returns:
            The recurrence this reminder follows.
        """
        return RecurrenceSpec.model_validate(self.recurrence)

    def __repr__(self) -> str:
        return f"<Reminder(id={self.id}, status={self.status}, trigger_at={self.trigger_at})>"
