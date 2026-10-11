"""Strict sparse reminder deltas compose the source settings contract."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator, model_validator

from src.domains.agents.application.reminder_create_schemas import ReminderRecurrence
from src.domains.agents.application.reminder_removal_schemas import ReminderSnapshot
from src.domains.reminders.schemas import ReminderUpdate
from src.domains.reminders.service import ReminderConfiguration


class ReminderUpdateChanges(ReminderUpdate):
    model_config = ConfigDict(extra="forbid", frozen=True)
    content: StrictStr | None = Field(None, min_length=1, max_length=2000)
    recurrence: ReminderRecurrence | None = None

    @field_validator("content", "trigger_at", "recurrence", mode="before")
    @classmethod
    def refuse_explicit_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("Omit a reminder setting rather than clearing it")
        return value

    @field_validator("trigger_at", mode="before")
    @classmethod
    def require_explicit_datetime(cls, value: object) -> object:
        if not isinstance(value, str | datetime):
            raise ValueError("Use an explicit date and time rather than a numeric timestamp")
        return value

    @model_validator(mode="after")
    def require_one_unambiguous_delta(self) -> ReminderUpdateChanges:
        if not self.model_fields_set:
            raise ValueError("Choose at least one reminder setting")
        if self.trigger_at is not None and self.recurrence is not None:
            raise ValueError("Choose an instant or a recurrence, never both")
        return self

    @property
    def changes_schedule(self) -> bool:
        return self.trigger_at is not None or self.recurrence is not None


class ReminderUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    reminder_id: UUID
    changes: ReminderUpdateChanges


class ReminderConfigurationValues(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    content: StrictStr
    trigger_at: datetime
    user_timezone: StrictStr
    recurrence: ReminderRecurrence

    @classmethod
    def of(cls, configuration: ReminderConfiguration) -> ReminderConfigurationValues:
        return cls(
            content=configuration.content,
            trigger_at=configuration.trigger_at,
            user_timezone=configuration.user_timezone,
            recurrence=ReminderRecurrence.model_validate(
                configuration.recurrence.model_dump(mode="json")
            ),
        )


class ReminderUpdateValues(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    expected: ReminderSnapshot
    requested_timezone: StrictStr
    configuration: ReminderConfigurationValues
    changes: ReminderUpdateChanges


class ReminderUpdatePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    reminder_configuration: ReminderUpdateValues
