"""Public reminder views shared by the management routes and native readers."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.core.constants import REMINDER_OCCURRENCES_PREVIEW
from src.core.recurrence import RecurrenceSpec, describe, occurrences
from src.core.time_utils import now_utc
from src.domains.reminders.models import Reminder


class PendingReminderItem(BaseModel):
    """One reminder that has not fired yet, as the HUB reads it.

    Deliberately thin, and still so: the hub shows what is coming and offers a
    cancel. The management screen reads `ReminderDetail` below, which carries
    the schedule. Keeping the two apart stops a badge count from paying for a
    recurrence description it never renders.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(description="The reminder — the id the cancel route takes.")
    content: str = Field(description="What the reader asked to be reminded of.")
    trigger_at: datetime = Field(description="UTC instant it will fire.")


class PendingReminderPage(BaseModel):
    """One page of pending reminders, and the EXACT total behind it.

    This can never be a history: a reminder is DELETED once notified, so the
    only thing there is to list is the future (ADR-185 for the total).
    """

    reminders: list[PendingReminderItem]
    total: int = Field(ge=0, description="Exact count of reminders still waiting.")


class ReminderDetail(BaseModel):
    """One reminder, as the MANAGEMENT screen reads it.

    Everything the hub item carries, plus what a reader needs to understand and
    change a schedule: the recurrence itself, the sentence the server composed
    for it, and the instants it will actually fire at.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    content: str
    trigger_at: datetime = Field(description="UTC instant of the NEXT firing.")
    user_timezone: str = Field(description="IANA zone the wall clock is read in.")
    recurrence: RecurrenceSpec
    schedule_display: str = Field(default="", description="The schedule, in the reader's words.")
    times_of_day: list[str] = Field(default_factory=list, description="`HH:MM`, ascending.")
    runs_per_day: int = Field(default=0, description="Most times a served day fires.")
    next_occurrences: list[datetime] = Field(default_factory=list)
    created_at: datetime

    @classmethod
    def of(cls, reminder: Reminder, language: str) -> ReminderDetail:
        """Render one reminder for the management screen.

        The derived fields are computed HERE rather than stored: a schedule
        sentence held in a column would be right in one language and stale in
        the other five.

        Args:
            reminder: The row to render.
            language: The reader's language, for the sentence.

        Returns:
            The rendered reminder.
        """
        spec = reminder.recurrence_spec
        return cls(
            id=reminder.id,
            content=reminder.content,
            trigger_at=reminder.trigger_at,
            user_timezone=reminder.user_timezone,
            recurrence=spec,
            schedule_display=describe(spec, language),
            times_of_day=[f"{m.hour:02d}:{m.minute:02d}" for m in spec.times.materialise()],
            runs_per_day=spec.per_day(),
            next_occurrences=occurrences(
                spec,
                reminder.user_timezone,
                after=now_utc(),
                count=REMINDER_OCCURRENCES_PREVIEW,
            ),
            created_at=reminder.created_at,
        )


class ReminderDetailPage(BaseModel):
    """One page of the caller's reminders, and the EXACT total behind it."""

    reminders: list[ReminderDetail]
    total: int = Field(ge=0, description="Exact count of reminders still waiting.")
