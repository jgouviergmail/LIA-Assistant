"""Strict creation input; the source owns clock resolution and recurring limits."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictStr

from src.core.recurrence import DailyTimes, RecurrenceSpec, SeriesEnd, TimeOfDay
from src.domains.reminders.schemas import ReminderCreate


class ReminderTimeOfDay(TimeOfDay):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ReminderDailyTimes(DailyTimes):
    model_config = ConfigDict(extra="forbid", frozen=True)
    at: tuple[ReminderTimeOfDay, ...] = ()
    start: ReminderTimeOfDay | None = None
    end: ReminderTimeOfDay | None = None


class ReminderSeriesEnd(SeriesEnd):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ReminderRecurrence(RecurrenceSpec):
    model_config = ConfigDict(extra="forbid", frozen=True)
    times: ReminderDailyTimes
    end: ReminderSeriesEnd = Field(default_factory=ReminderSeriesEnd)


class ReminderCreateRequest(ReminderCreate):
    model_config = ConfigDict(extra="forbid", frozen=True)
    content: StrictStr = Field(min_length=1, max_length=2000)
    original_message: StrictStr = Field(min_length=1, max_length=2000)
    recurrence: ReminderRecurrence | None = None


class ReminderCreationValues(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: UUID
    user_timezone: StrictStr
    trigger_at: datetime
    recurrence: ReminderRecurrence
    configuration: ReminderCreateRequest


class ReminderCreatePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    reminder_to_create: ReminderCreationValues
