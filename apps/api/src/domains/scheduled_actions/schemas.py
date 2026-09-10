"""
Scheduled Actions Pydantic v2 schemas.

Input/output models for the scheduled actions CRUD API.
"""

from datetime import date as calendar_date
from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.core.constants import (
    OUT_OF_TURN_EXECUTION_MODE_DEFAULT,
    RECURRENCE_ROUTINE_LIMITS,
    SCHEDULED_ACTION_OCCURRENCES_PREVIEW,
    ExecutionMode,
)
from src.core.i18n import DEFAULT_LANGUAGE
from src.core.recurrence import RecurrenceSpec, describe, occurrences, week_slots
from src.core.time_utils import now_utc
from src.domains.scheduled_actions.models import (
    CONDITION_TYPE_CALENDAR_EVENT,
    CONDITION_TYPE_MAIL_MATCH,
    CONDITION_TYPES,
    ScheduledRunOutcome,
    TriggerKind,
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
    def validate_per_type(self) -> ConditionConfig:
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


class ScheduledActionWeekSlot(BaseModel):
    """One instant of the CURRENT week, carried by the routine itself.

    The weekly grid draws its chips from these, never from a second request:
    an empty grid is a blocking regression (owner arbitration 2026-09-06), and
    a monthly or stepped recurrence cannot be positioned by the browser without
    re-reading the schedule — the second authority ADR-265 forbids.

    `/scheduled-actions/week` still carries the run OUTCOMES. The division is
    the point: position always arrives with the cards, and losing the outcomes
    costs a colour, never a chip.
    """

    model_config = ConfigDict(frozen=True)

    day: int = Field(..., ge=1, le=7, description="ISO weekday in the routine's zone.")
    date: calendar_date = Field(..., description="The local calendar date.")
    slot_at: datetime = Field(..., description="The instant it fires at (UTC).")
    hour: int = Field(..., ge=0, le=23, description="Local hour — the grid row.")
    minute: int = Field(..., ge=0, le=59, description="Local minute.")


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
    recurrence: RecurrenceSpec = Field(
        ...,
        description="Which calendar days the routine serves, and the moments inside them.",
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
    execution_mode: ExecutionMode = Field(
        default=OUT_OF_TURN_EXECUTION_MODE_DEFAULT,
        description="How LIA runs it: react (autonomous loop) or pipeline.",
    )

    @model_validator(mode="after")
    def validate_against_routine_limits(self) -> ScheduledActionCreate:
        """Refuse a recurrence beyond what a ROUTINE may ask.

        The cap is INJECTED rather than owned by the recurrence model: a
        routine runs the full agent pipeline on every occurrence while a
        reminder only sends a notification, and one engine serves both.

        Returns:
            The validated instance.

        Raises:
            ValidationError: Pydantic wraps the ``RecurrenceError`` raised when
                the recurrence exceeds ``RECURRENCE_ROUTINE_LIMITS``.
        """
        self.recurrence.validate_against(RECURRENCE_ROUTINE_LIMITS)
        return self

    @model_validator(mode="after")
    def validate_condition(self) -> ScheduledActionCreate:
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
    recurrence: RecurrenceSpec | None = Field(
        None, description="New recurrence; absent leaves the schedule alone."
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
    execution_mode: ExecutionMode | None = Field(
        None, description="react (autonomous loop) or pipeline; the next firing reads it."
    )

    @model_validator(mode="before")
    @classmethod
    def refuse_an_explicit_null_recurrence(cls, data: object) -> object:
        """An explicit ``null`` is not an absent field.

        Omitting ``recurrence`` means "leave the schedule alone"; sending
        ``null`` means "set it to nothing", which the column forbids. Without
        this, ``exclude_unset`` kept the key and the service wrote NULL into a
        NOT NULL column — a 500 where a 422 belongs.

        Args:
            data: The raw payload.

        Returns:
            The payload, unchanged.

        Raises:
            ValueError: When ``recurrence`` is present and null.
        """
        if isinstance(data, dict) and "recurrence" in data and data["recurrence"] is None:
            raise ValueError("recurrence cannot be null — omit it to leave the schedule alone")
        return data

    @model_validator(mode="after")
    def validate_against_routine_limits(self) -> ScheduledActionUpdate:
        """Refuse a new recurrence beyond what a routine may ask.

        Returns:
            The validated instance.

        Raises:
            ValidationError: On a recurrence over the routine cap.
        """
        if self.recurrence is not None:
            self.recurrence.validate_against(RECURRENCE_ROUTINE_LIMITS)
        return self


class ScheduledActionResponse(BaseModel):
    """Schema for a single scheduled action response."""

    id: UUID
    user_id: UUID
    title: str
    action_prompt: str
    recurrence: RecurrenceSpec
    user_timezone: str
    trigger_kind: str
    condition_config: dict | None
    requires_approval: bool
    execution_mode: str
    next_trigger_at: datetime | None
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
        description="Next runs in UTC, from the engine that arms them.",
    )

    # The moments of a served day, `HH:MM`, MATERIALISED here. The browser
    # never expands a `mode: "every"` step itself — that would be a second
    # reading of the schedule, and the two would disagree at the DST edges.
    times_of_day: list[str] = Field(
        default_factory=list,
        description="The moments a served day fires at, HH:MM, in the routine's zone.",
    )
    # An UPPER BOUND, never an exact count: a clock change makes the real
    # number differ on one day a year (24 declared, 23 served in spring).
    runs_per_day: int = Field(default=0, description="Most times a served day fires.")
    # The CURRENT week's instants, so the grid ALWAYS has something to draw.
    # Owner arbitration 2026-09-06: an empty grid is a blocking regression, and
    # a monthly or stepped recurrence cannot be positioned by the browser
    # without re-reading the schedule. `/week` keeps the run outcomes, whose
    # absence costs a colour and never a chip.
    #
    # Measured 2026-09-06 on a full listing of 20 routines (the per-user cap):
    # 9.9 ms for the ordinary shape (one moment a day), 75 ms for the absolute
    # worst case (twelve moments a day, seven days, a four-year-old anchor).
    # The listing is polled every 30 s, so that ceiling is paid rarely and buys
    # a grid that never comes up empty.
    week_slots: list[ScheduledActionWeekSlot] = Field(
        default_factory=list,
        description="Every instant of the current week, in the routine's zone.",
    )

    @model_validator(mode="after")
    def compute_schedule_display(self) -> ScheduledActionResponse:
        """Fill the sentence, the moments and the upcoming runs."""
        if not self.schedule_display:
            self.schedule_display = describe(self.recurrence, DEFAULT_LANGUAGE)
        if not self.times_of_day:
            self.times_of_day = [
                f"{moment.hour:02d}:{moment.minute:02d}"
                for moment in self.recurrence.times.materialise()
            ]
        if not self.runs_per_day:
            self.runs_per_day = self.recurrence.per_day()
        if not self.next_occurrences:
            self.next_occurrences = occurrences(
                self.recurrence,
                self.user_timezone,
                after=now_utc(),
                count=SCHEDULED_ACTION_OCCURRENCES_PREVIEW,
            )
        if not self.week_slots:
            zone = ZoneInfo(self.user_timezone)
            self.week_slots = [
                ScheduledActionWeekSlot(
                    day=local.isoweekday(),
                    date=local.date(),
                    slot_at=slot,
                    hour=local.hour,
                    minute=local.minute,
                )
                for slot, local in (
                    (slot, slot.astimezone(zone))
                    for slot in week_slots(self.recurrence, self.user_timezone)
                )
            ]
        return self


class ScheduledActionListResponse(BaseModel):
    """Schema for listing scheduled actions."""

    scheduled_actions: list[ScheduledActionResponse]
    total: int


# =============================================================================
# The current week (ADR-265)
# =============================================================================


class ScheduledActionWeekCell(BaseModel):
    """One configured day of the current week for one routine."""

    day: int = Field(..., ge=1, le=7, description="ISO weekday in the routine's zone.")
    date: calendar_date = Field(..., description="The local calendar date.")
    slot_at: datetime = Field(..., description="The instant the routine fires at (UTC).")
    hour: int = Field(..., ge=0, le=23, description="Local hour of that instant.")
    minute: int = Field(..., ge=0, le=59, description="Local minute of that instant.")
    outcome: ScheduledRunOutcome | None = Field(
        None,
        description=(
            "How the LAST run serving this slot ended; null = no run served it "
            "(not yet due, or the tick never happened)."
        ),
    )
    run_at: datetime | None = Field(None, description="When that run started (UTC).")
    error: str | None = Field(None, description="Its error message, for a failure.")
    manual: bool | None = Field(None, description="Whether the user started that run.")


class ScheduledActionWeek(BaseModel):
    """The current week of one routine, drawn by the client cell by cell."""

    id: UUID = Field(..., description="The routine.")
    timezone: str = Field(..., description="The zone the days and the week are read in.")
    week_start: calendar_date = Field(..., description="The local Monday.")
    today: int = Field(..., ge=1, le=7, description="ISO weekday of now, in that zone.")
    cells: list[ScheduledActionWeekCell] = Field(
        default_factory=list, description="One per configured day, Monday first."
    )


class ScheduledActionWeekResponse(BaseModel):
    """Every routine's current week — the facts the timeline colours from.

    Computed server-side from the same cron engine that arms the runs, so the
    browser never re-reads a schedule; it only paints.
    """

    actions: list[ScheduledActionWeek]
    generated_at: datetime = Field(..., description="When this was computed (UTC).")
