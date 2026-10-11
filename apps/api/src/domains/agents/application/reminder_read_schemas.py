"""Bounded reminder management reads never claim to be notification history."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domains.reminders.read_models import ReminderDetail


class ReminderRead(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    reminder_id: UUID | None = None
    after_id: UUID | None = None
    limit: int = Field(default=5, ge=1, le=50, strict=True)

    @model_validator(mode="after")
    def refuse_mixed_selection(self) -> ReminderRead:
        if self.reminder_id is not None and self.after_id is not None:
            raise ValueError("Choose one reminder or a page continuation")
        return self


class ReminderProjection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reminders: list[ReminderDetail]
    returned_count: int = Field(ge=0)
    total_available: int = Field(ge=0)
    truncated: bool
    next_cursor: UUID | None = None
