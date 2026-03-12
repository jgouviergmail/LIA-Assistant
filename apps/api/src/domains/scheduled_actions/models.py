"""
Scheduled Actions domain models.

Stores user-defined recurring actions with day-of-week + time scheduling.
The scheduler polls for due actions using next_trigger_at (UTC).
"""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models import BaseModel

if TYPE_CHECKING:
    from src.domains.auth.models import User


class ScheduledActionStatus(str, Enum):
    """Status of a scheduled action."""

    ACTIVE = "active"  # Ready for execution
    EXECUTING = "executing"  # Currently running (locked by scheduler)
    ERROR = "error"  # Auto-disabled after max consecutive failures


class ScheduledAction(BaseModel):
    """
    Scheduled Action model.

    Stores user-defined recurring actions with cron-style scheduling.
    The scheduler computes next_trigger_at in UTC from days_of_week + trigger_hour/minute
    + user_timezone via APScheduler CronTrigger.

    Unlike reminders (one-shot, deleted after execution), scheduled actions persist
    and recalculate next_trigger_at after each execution.
    """

    __tablename__ = "scheduled_actions"

    # Foreign key to user
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Content
    title: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        doc="User-facing title - 'Recherche meteo'",
    )
    action_prompt: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Prompt sent to agent pipeline - 'recherche la meteo du jour'",
    )

    # Schedule (stored as explicit fields, CronTrigger built on-the-fly)
    days_of_week: Mapped[list[int]] = mapped_column(
        ARRAY(SmallInteger),
        nullable=False,
        doc="ISO weekdays: 1=Monday..7=Sunday",
    )
    trigger_hour: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        doc="Hour of execution (0-23) in user timezone",
    )
    trigger_minute: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        doc="Minute of execution (0-59) in user timezone",
    )
    user_timezone: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="Europe/Paris",
        doc="IANA timezone for schedule evaluation",
    )

    # Computed trigger time (UTC) - recalculated after each execution
    next_trigger_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        doc="Next execution time in UTC (computed from schedule + timezone)",
    )

    # Status
    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        doc="User toggle - False = paused",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=ScheduledActionStatus.ACTIVE.value,
        index=True,
        doc="active -> executing -> active (recurring cycle)",
    )

    # Execution tracking
    last_executed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="Last successful execution timestamp (UTC)",
    )
    execution_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        doc="Total successful executions",
    )
    consecutive_failures: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        doc="Consecutive failure count (reset on success)",
    )
    last_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Last execution error message",
    )

    # Relationship
    user: Mapped["User"] = relationship("User", back_populates="scheduled_actions", lazy="selectin")

    # Partial index for scheduler poll query (hot path)
    __table_args__ = (
        Index(
            "ix_scheduled_actions_due",
            "next_trigger_at",
            postgresql_where=("is_enabled = true AND status = 'active'"),
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<ScheduledAction(id={self.id}, title='{self.title}', "
            f"status={self.status}, next={self.next_trigger_at})>"
        )
