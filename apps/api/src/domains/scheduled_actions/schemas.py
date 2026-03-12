"""
Scheduled Actions Pydantic v2 schemas.

Input/output models for the scheduled actions CRUD API.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domains.scheduled_actions.schedule_helpers import format_schedule_display


class ScheduledActionCreate(BaseModel):
    """Schema for creating a new scheduled action."""

    title: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="User-facing title, e.g. 'Recherche météo'",
    )
    action_prompt: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Prompt sent to agent pipeline, e.g. 'recherche la météo du jour'",
    )
    days_of_week: list[int] = Field(
        ...,
        min_length=1,
        max_length=7,
        description="ISO weekdays: 1=Monday..7=Sunday",
    )
    trigger_hour: int = Field(
        ...,
        ge=0,
        le=23,
        description="Hour of execution (0-23) in user timezone",
    )
    trigger_minute: int = Field(
        ...,
        ge=0,
        le=59,
        description="Minute of execution (0-59) in user timezone",
    )

    @model_validator(mode="after")
    def validate_days(self) -> "ScheduledActionCreate":
        """Validate days_of_week contains valid ISO weekday numbers with no duplicates."""
        for d in self.days_of_week:
            if not (1 <= d <= 7):
                raise ValueError(f"Invalid day {d}: must be 1 (Mon) to 7 (Sun)")
        if len(self.days_of_week) != len(set(self.days_of_week)):
            raise ValueError("Duplicate days are not allowed")
        return self


class ScheduledActionUpdate(BaseModel):
    """Schema for updating a scheduled action (all fields optional)."""

    title: str | None = Field(
        None,
        min_length=1,
        max_length=200,
        description="User-facing title",
    )
    action_prompt: str | None = Field(
        None,
        min_length=1,
        max_length=2000,
        description="Prompt sent to agent pipeline",
    )
    days_of_week: list[int] | None = Field(
        None,
        min_length=1,
        max_length=7,
        description="ISO weekdays: 1=Monday..7=Sunday",
    )
    trigger_hour: int | None = Field(
        None,
        ge=0,
        le=23,
        description="Hour of execution (0-23) in user timezone",
    )
    trigger_minute: int | None = Field(
        None,
        ge=0,
        le=59,
        description="Minute of execution (0-59) in user timezone",
    )

    @model_validator(mode="after")
    def validate_days(self) -> "ScheduledActionUpdate":
        """Validate days_of_week if provided."""
        if self.days_of_week is not None:
            for d in self.days_of_week:
                if not (1 <= d <= 7):
                    raise ValueError(f"Invalid day {d}: must be 1 (Mon) to 7 (Sun)")
            if len(self.days_of_week) != len(set(self.days_of_week)):
                raise ValueError("Duplicate days are not allowed")
        return self


class ScheduledActionResponse(BaseModel):
    """Schema for a single scheduled action response."""

    id: UUID
    user_id: UUID
    title: str
    action_prompt: str
    days_of_week: list[int]
    trigger_hour: int
    trigger_minute: int
    user_timezone: str
    next_trigger_at: datetime
    is_enabled: bool
    status: str
    last_executed_at: datetime | None
    execution_count: int
    consecutive_failures: int
    last_error: str | None
    created_at: datetime
    updated_at: datetime

    # Computed field: human-readable schedule display
    schedule_display: str = ""

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def compute_schedule_display(self) -> "ScheduledActionResponse":
        """Compute human-readable schedule string from days/time fields."""
        if not self.schedule_display:
            self.schedule_display = format_schedule_display(
                self.days_of_week,
                self.trigger_hour,
                self.trigger_minute,
            )
        return self


class ScheduledActionListResponse(BaseModel):
    """Schema for listing scheduled actions."""

    scheduled_actions: list[ScheduledActionResponse]
    total: int
