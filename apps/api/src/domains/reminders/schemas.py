"""
Reminder domain Pydantic schemas.

Phase: Reminders with FCM notifications
Created: 2025-12-28
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.core.recurrence import RecurrenceSpec
from src.domains.reminders.models import ReminderStatus


class ReminderCreate(BaseModel):
    """Schema for creating a new reminder.

    `trigger_at` is the instant to ARM; `recurrence` is what to arm AFTERWARDS.
    Omitting the recurrence means "this happens once": the service derives that
    spec from the instant, by the same rule the migration used on existing
    rows, so there is one description of a single occurrence and not two.
    """

    content: str = Field(..., description="What to remind (interpreted)")
    original_message: str = Field(..., description="Original user message")
    trigger_at: datetime | None = Field(
        None, description="Local wall clock of a SINGLE firing; omit when sending a recurrence."
    )
    recurrence: RecurrenceSpec | None = Field(
        None, description="The schedule; its first occurrence IS the armed instant."
    )

    @model_validator(mode="after")
    def exactly_one_way_to_say_when(self) -> ReminderCreate:
        """One authority for when a reminder fires, never two.

        Both fields together could disagree — a recurrence saying "every day at
        08:00" beside an instant at 23:00 — and the row would then announce one
        time and ring at another until the first re-arm corrected it. The
        recurrence wins when it is present; sending both is refused rather than
        silently resolved.

        Returns:
            The validated instance.

        Raises:
            ValueError: When neither or both are supplied.
        """
        if (self.trigger_at is None) == (self.recurrence is None):
            raise ValueError("send either trigger_at (a single firing) or recurrence, not both")
        return self


class ReminderResponse(BaseModel):
    """Schema for reminder response."""

    id: UUID
    user_id: UUID
    content: str
    original_message: str
    trigger_at: datetime
    user_timezone: str
    status: ReminderStatus
    retry_count: int
    notification_error: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReminderListResponse(BaseModel):
    """Schema for listing reminders."""

    reminders: list[ReminderResponse]
    total: int


class ReminderStatusUpdate(BaseModel):
    """Schema for updating reminder status."""

    status: ReminderStatus
    notification_error: str | None = None


class ReminderUpdate(BaseModel):
    """Partial update of a reminder.

    `recurrence` is replaced WHOLE or left alone — a partial recurrence is a
    schedule nothing can interpret. Sending it as an explicit `null` is
    refused rather than silently ignored: the column cannot be empty, and
    "clear the schedule" has no meaning for a reminder that must fire.
    """

    content: str | None = Field(None, min_length=1, max_length=2000)
    trigger_at: datetime | None = Field(
        None, description="New instant to arm (local time); recomputed from the recurrence."
    )
    recurrence: RecurrenceSpec | None = Field(
        None, description="New recurrence, replaced whole; absent leaves it alone."
    )

    @model_validator(mode="before")
    @classmethod
    def refuse_an_explicit_null_recurrence(cls, data: object) -> object:
        """An absent field leaves the schedule; an explicit null is a mistake.

        Pydantic cannot tell the two apart on an optional field, and the column
        is NOT NULL — so a caller sending `"recurrence": null` would either be
        ignored (a change silently dropped) or write a null (a 500 at flush).
        Neither is an answer; the request is refused instead.

        Args:
            data: The raw payload.

        Returns:
            The payload, unchanged.

        Raises:
            ValueError: When `recurrence` is present and null.
        """
        if isinstance(data, dict) and "recurrence" in data and data["recurrence"] is None:
            raise ValueError("recurrence cannot be null — omit it to leave the schedule alone")
        return data
