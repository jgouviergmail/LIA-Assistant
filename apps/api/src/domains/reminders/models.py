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
        doc="What the assistant understood - 'call the doctor'",
    )
    original_message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Exact user message - 'remind me to call...'",
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

    # A postponed copy remembers when the person first asked (ADR-268
    # amendment 2026-11-16). NULL on every reminder a person created; set only
    # on the one-shot copy a snooze created, which is also what tells the
    # message it is a reminder coming back rather than a new request.
    first_asked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When the person first asked; set only on a copy a snooze created.",
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


class ReminderFiring(BaseModel):
    """One occurrence of a reminder that rang, kept while it can be postponed.

    ADR-268 first refused a snooze because a press could not say WHICH
    occurrence it meant: a one-shot reminder is deleted the instant it fires,
    and a series has already moved to its next instant. This row is that
    occurrence (ADR-268 amendment 2026-11-16). The notification names it, a
    press acts on it, and it is purged once ``REMINDER_SNOOZE_WINDOW_HOURS``
    have passed since it rang.

    It COPIES what rang rather than pointing at it: the reminder it came from
    is usually gone already (``reminder_id`` is SET NULL by that deletion), and
    a postponement must still know what to say.
    """

    __tablename__ = "reminder_firings"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reminder_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("reminders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="The reminder that rang, while it exists: a series, or a one-shot not yet deleted.",
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="What rang, copied: the reminder may already be gone.",
    )
    original_message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="The person's own request, copied for the postponed copy's message.",
    )
    asked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="When the person first asked for it (carried to a postponed copy).",
    )
    fired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        comment="When it rang; the snooze window and the purge count from it.",
    )
    snoozed_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="The instant it was postponed to; NULL while it was not.",
    )

    def __repr__(self) -> str:
        return f"<ReminderFiring(id={self.id}, fired_at={self.fired_at})>"
