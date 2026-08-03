"""
Scheduled Actions Pydantic v2 schemas.

Input/output models for the scheduled actions CRUD API.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.core.constants import SCHEDULED_ACTION_OCCURRENCES_PREVIEW
from src.domains.scheduled_actions.models import (
    CONDITION_TYPE_CALENDAR_EVENT,
    CONDITION_TYPE_MAIL_MATCH,
    CONDITION_TYPES,
    TriggerKind,
)
from src.domains.scheduled_actions.schedule_helpers import (
    compute_next_triggers_utc,
    format_schedule_display,
)

# Weather-change kinds accepted by the condition (mirror of the briefing
# ForecastAlertKind values — a wrong kind would silently never fire).
WEATHER_CONDITION_KINDS: frozenset[str] = frozenset({"rain", "thunderstorm", "snow", "drizzle"})


class ConditionConfig(BaseModel):
    """Condition of a CONDITION-kind routine (N-07 phase 1).

    Per-type params, all bounded:
    - ``task_overdue``: no params — fires on a NEW overdue task;
    - ``weather_change``: ``kinds`` ⊆ WEATHER_CONDITION_KINDS (default: all);
    - ``mail_match``: ``query`` (2–120 chars) matched against today's unread
      subjects/senders;
    - ``document_added``: no params — fires on newly modified Drive files;
    - ``calendar_event``: ``within_hours`` (1–48, default 4) and optional
      ``query`` matched against event titles.
    """

    model_config = ConfigDict(frozen=True)

    type: str = Field(..., description="One of CONDITION_TYPES.")
    kinds: list[str] | None = Field(
        default=None, description="weather_change only: alert kinds to react to."
    )
    query: str | None = Field(
        default=None,
        min_length=2,
        max_length=120,
        description="mail_match (required) / calendar_event (optional) text filter.",
    )
    within_hours: int | None = Field(
        default=None, ge=1, le=48, description="calendar_event only: look-ahead window."
    )

    @model_validator(mode="after")
    def validate_per_type(self) -> "ConditionConfig":
        """Refuse unknown types and per-type nonsense at the API boundary."""
        if self.type not in CONDITION_TYPES:
            raise ValueError(f"Unknown condition type: {self.type}")
        if self.kinds is not None:
            unknown = [k for k in self.kinds if k not in WEATHER_CONDITION_KINDS]
            if unknown:
                raise ValueError(f"Unknown weather kinds: {unknown}")
        if self.type == CONDITION_TYPE_MAIL_MATCH and not (self.query and self.query.strip()):
            raise ValueError("mail_match requires a query")
        if self.within_hours is not None and self.type != CONDITION_TYPE_CALENDAR_EVENT:
            raise ValueError("within_hours only applies to calendar_event")
        return self


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
    # N-07 phase 1 — additive with time defaults, so the ADR-140 chat tool
    # (which builds this schema without the new fields) keeps its behavior.
    trigger_kind: TriggerKind = Field(
        default=TriggerKind.TIME,
        description="time = fire at every tick; condition = fire only when met.",
    )
    condition_config: ConditionConfig | None = Field(
        default=None, description="Required when trigger_kind is condition."
    )
    requires_approval: bool = Field(
        default=False,
        description="True = propose via notification instead of executing.",
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

    @model_validator(mode="after")
    def validate_condition(self) -> "ScheduledActionCreate":
        """A condition routine needs its condition; a time routine refuses one."""
        if self.trigger_kind is TriggerKind.CONDITION and self.condition_config is None:
            raise ValueError("condition_config is required when trigger_kind is condition")
        if self.trigger_kind is TriggerKind.TIME and self.condition_config is not None:
            raise ValueError("condition_config only applies to condition routines")
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
    trigger_kind: TriggerKind | None = Field(
        None, description="time = fire at every tick; condition = fire only when met."
    )
    condition_config: ConditionConfig | None = Field(
        None, description="New condition (kind/config coherence enforced in the service)."
    )
    requires_approval: bool | None = Field(
        None, description="True = propose via notification instead of executing."
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
    trigger_kind: str
    condition_config: dict | None
    requires_approval: bool
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

    # The next runs, as INSTANTS. Structured rather than pre-formatted: the
    # client renders them with `Intl` in the routine's OWN timezone (which it
    # already receives), so a traveller reads the hours the routine will really
    # fire at rather than their current wall clock. Never recomputed in the
    # browser — a second interpretation of the cron would be a second
    # authority, and the daylight-saving edges are exactly where the two would
    # disagree.
    next_occurrences: list[datetime] = Field(
        default_factory=list,
        description="Next runs in UTC (one per local day; DST duplicates removed).",
    )

    @model_validator(mode="after")
    def compute_schedule_display(self) -> "ScheduledActionResponse":
        """Compute the human-readable schedule and the upcoming runs."""
        if not self.schedule_display:
            self.schedule_display = format_schedule_display(
                self.days_of_week,
                self.trigger_hour,
                self.trigger_minute,
            )
        if not self.next_occurrences:
            self.next_occurrences = compute_next_triggers_utc(
                self.days_of_week,
                self.trigger_hour,
                self.trigger_minute,
                self.user_timezone,
                count=SCHEDULED_ACTION_OCCURRENCES_PREVIEW,
            )
        return self


class ScheduledActionListResponse(BaseModel):
    """Schema for listing scheduled actions."""

    scheduled_actions: list[ScheduledActionResponse]
    total: int
