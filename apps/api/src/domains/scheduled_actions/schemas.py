"""
Scheduled Actions Pydantic v2 schemas.

Input/output models for the scheduled actions CRUD API.
"""

from datetime import date as calendar_date
from datetime import datetime
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.core.config import settings
from src.core.constants import (
    OUT_OF_TURN_EXECUTION_MODE_DEFAULT,
    RECURRENCE_ROUTINE_LIMITS,
    SCHEDULED_ACTION_OCCURRENCES_PREVIEW,
    ExecutionMode,
)
from src.core.i18n import resolve_language
from src.core.recurrence import RecurrenceSpec, occurrences, week_slots
from src.core.time_utils import now_utc
from src.domains.connectors.models import ConnectorType
from src.domains.scheduled_actions.condition_ledger import ConditionCheckError, ConditionLedger
from src.domains.scheduled_actions.models import (
    CONDITION_TYPE_CALENDAR_EVENT,
    CONDITION_TYPE_DOCUMENT_ADDED,
    CONDITION_TYPE_MAIL_MATCH,
    CONDITION_TYPE_TASK_OVERDUE,
    CONDITION_TYPE_WEATHER_CHANGE,
    CONDITION_TYPES,
    ScheduledRunOutcome,
    TriggerKind,
)
from src.domains.scheduled_actions.trigger import (
    TriggerPlan,
    check_minutes,
    published_check_minutes,
    schedule_sentence,
)

# Weather-change kinds accepted by the condition (mirror of the briefing
# ForecastAlertKind values — a wrong kind would silently never fire).
WEATHER_CONDITION_KINDS: frozenset[str] = frozenset({"rain", "thunderstorm", "snow", "drizzle"})

#: The parameters each condition type actually READS (``until`` aside, which
#: every type reads). A parameter absent from its type's set is not « unused »:
#: it would be accepted, stored, shown and DROPPED — the trap ADR-268 closed
#: for recurrence selectors, closed here the same way (ADR-322).
CONDITION_PARAMS_READ_BY: dict[str, frozenset[str]] = {
    CONDITION_TYPE_TASK_OVERDUE: frozenset(),
    CONDITION_TYPE_WEATHER_CHANGE: frozenset({"kinds"}),
    CONDITION_TYPE_MAIL_MATCH: frozenset({"query"}),
    CONDITION_TYPE_DOCUMENT_ADDED: frozenset(),
    CONDITION_TYPE_CALENDAR_EVENT: frozenset({"query", "within_hours"}),
}
if set(CONDITION_PARAMS_READ_BY) != set(CONDITION_TYPES):  # pragma: no cover - boot guard
    raise RuntimeError("CONDITION_PARAMS_READ_BY must cover exactly CONDITION_TYPES")


class ConditionConfig(BaseModel):
    """Condition of a CONDITION-kind routine (N-07, ADR-322).

    Per-type params, all bounded, each refused on a type that does not read it:
    - ``task_overdue``: no params — fires on a NEW overdue task;
    - ``weather_change``: ``kinds`` ⊆ WEATHER_CONDITION_KINDS (default: all);
    - ``mail_match``: ``query`` (2–120 chars) matched against the unread
      inbox's subjects and senders;
    - ``document_added``: no params — fires on a Drive file newly in the
      recent list;
    - ``calendar_event``: ``within_hours`` (1–48, default 4) and optional
      ``query`` matched against event titles.

    ``until`` — the last local day watched, that day included — applies to
    every type: a condition routine has no schedule, so this is its only end.
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
    until: calendar_date | None = Field(
        default=None,
        description="Last local day watched, included; absent = no end.",
    )

    @field_validator("kinds")
    @classmethod
    def one_order_for_the_kinds(cls, kinds: list[str] | None) -> list[str] | None:
        """The kinds as a SET, in one order: another order is not another condition.

        Stored as sent, ticking « snow » then « rain » made a condition the
        service read as new, whose ledger started over (ADR-322).

        Args:
            kinds: The kinds as sent.

        Returns:
            The same kinds, sorted, each once; ``None`` stays ``None``.
        """
        return sorted(set(kinds)) if kinds is not None else None

    @model_validator(mode="after")
    def validate_per_type(self) -> ConditionConfig:
        """Refuse unknown types and per-type nonsense at the API boundary."""
        if self.type not in CONDITION_TYPES:
            raise ValueError(f"Unknown condition type: {self.type}")
        stray = [
            name
            for name in ("kinds", "query", "within_hours")
            if getattr(self, name) is not None and name not in CONDITION_PARAMS_READ_BY[self.type]
        ]
        if stray:
            raise ValueError(f"{', '.join(stray)} does not apply to {self.type}")
        unknown = [k for k in self.kinds or [] if k not in WEATHER_CONDITION_KINDS]
        if unknown:
            raise ValueError(f"Unknown weather kinds: {unknown}")
        if self.type == CONDITION_TYPE_MAIL_MATCH and not (self.query and self.query.strip()):
            raise ValueError("mail_match requires a query")
        return self

    def stored(self) -> dict[str, object]:
        """The JSONB value: a NEW dict, JSON-typed (a date is its ISO string).

        Returns:
            The condition as the column stores it, absent parameters omitted.
        """
        return self.model_dump(mode="json", exclude_none=True)


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
        description="User-facing title, e.g. 'Weather lookup'",
    )
    action_prompt: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Prompt sent to agent pipeline, e.g. 'look up today's weather'",
    )
    recurrence: RecurrenceSpec | None = Field(
        default=None,
        description=(
            "time routines only (required): which calendar days the routine "
            "serves, and the moments inside them. A condition routine has none."
        ),
    )
    # N-07 phase 1 — additive with time defaults, so the ADR-140 chat tool
    # (which builds this schema without the new fields) keeps its behavior.
    trigger_kind: TriggerKind = Field(
        default=TriggerKind.TIME,
        description=(
            "time = runs on its recurrence; condition = checked by the system, "
            "runs on a new fact (ADR-322)."
        ),
    )
    condition_config: ConditionConfig | None = Field(
        default=None, description="condition routines only (required)."
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
        if self.recurrence is not None:
            self.recurrence.validate_against(RECURRENCE_ROUTINE_LIMITS)
        return self

    @model_validator(mode="after")
    def validate_trigger_mode(self) -> ScheduledActionCreate:
        """One clock per routine: a schedule, or a condition — never both.

        Returns:
            The validated instance.

        Raises:
            ValueError: When the fields do not match the chosen mode.
        """
        refusal = trigger_mode_refusal(
            self.trigger_kind.value,
            has_recurrence=self.recurrence is not None,
            has_condition=self.condition_config is not None,
        )
        if refusal:
            raise ValueError(refusal)
        return self


def trigger_mode_refusal(kind: str, *, has_recurrence: bool, has_condition: bool) -> str | None:
    """Why a routine's fields do not match its mode, or ``None`` when they do.

    ONE rule for the create schema and the service's update (which sees the
    stored half of the pair the schema cannot): a time routine runs on its
    recurrence and carries no condition; a condition routine runs on the
    system's checks and carries no recurrence (ADR-322). The same rule is the
    table's CHECK constraint.

    Args:
        kind: The resulting ``trigger_kind``.
        has_recurrence: Whether the resulting row has a recurrence.
        has_condition: Whether the resulting row has a condition.

    Returns:
        The refusal, worded for the API caller, or ``None``.
    """
    if kind == TriggerKind.CONDITION.value:
        if not has_condition:
            return "condition_config is required when trigger_kind is condition"
        if has_recurrence:
            return "a condition routine has no recurrence: the system checks it"
        return None
    if not has_recurrence:
        return "recurrence is required when trigger_kind is time"
    if has_condition:
        return "condition_config only applies to condition routines"
    return None


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
        None,
        description=(
            "time = runs on its recurrence; condition = checked by the system. "
            "Switching to condition drops the recurrence; switching to time "
            "drops the condition and needs a recurrence."
        ),
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
        ``null`` means "set it to nothing". A routine loses its schedule by
        becoming a condition routine (``trigger_kind``), which the service
        applies to the WHOLE row (ADR-322) — a bare null would leave a time
        routine with no clock, which the table's CHECK refuses: a 500 where a
        422 belongs.

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
    recurrence: RecurrenceSpec | None
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

    # A condition routine's clock and its last check (ADR-322). The interval is
    # the one APPLIED — published because it is enforced (ADR-184); the check
    # fields come from the ledger, whose facts themselves are never served.
    check_interval_minutes: int | None = Field(
        default=None, description="condition routines: how often the system checks, in minutes."
    )
    last_checked_at: datetime | None = Field(
        default=None, description="condition routines: when the condition was last checked."
    )
    last_check_error: ConditionCheckError | None = Field(
        default=None,
        description=(
            "condition routines: why the last check could not read its source — "
            "not_configured (nothing to read) or unavailable (it did not answer)."
        ),
    )
    condition_state: dict | None = Field(
        default=None, exclude=True, description="The fact ledger, read here and never served."
    )

    @model_validator(mode="after")
    def compute_schedule_display(self) -> ScheduledActionResponse:
        """Fill the sentence, the moments, the upcoming runs and the last check."""
        plan = TriggerPlan(
            action_id=self.id,
            trigger_kind=self.trigger_kind,
            recurrence=self.recurrence,
            condition_config=self.condition_config,
            timezone=self.user_timezone,
        )
        if not self.schedule_display:
            self.schedule_display = schedule_sentence(plan, resolve_language())
        if plan.is_condition:
            ledger = ConditionLedger.read(self.condition_state)
            self.check_interval_minutes = check_minutes(plan)
            self.last_checked_at = ledger.last_checked_at
            self.last_check_error = ledger.last_check_error
            return self
        if self.recurrence is not None:
            self._fill_schedule(self.recurrence)
        return self

    def _fill_schedule(self, recurrence: RecurrenceSpec) -> None:
        """The moments, the next runs and the week of a scheduled routine."""
        if not self.times_of_day:
            self.times_of_day = [
                f"{moment.hour:02d}:{moment.minute:02d}"
                for moment in recurrence.times.materialise()
            ]
        if not self.runs_per_day:
            self.runs_per_day = recurrence.per_day()
        if not self.next_occurrences:
            self.next_occurrences = occurrences(
                recurrence,
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
                    for slot in week_slots(recurrence, self.user_timezone)
                )
            ]


class WeatherConditionRule(BaseModel):
    """When a weather routine fires, exactly as the executor applies it (ADR-184)."""

    horizon_hours: int = Field(
        description="A change is announced when it is due within this many hours."
    )
    min_precipitation_percent: int = Field(
        description="A forecast hour counts only when its precipitation probability is "
        "STRICTLY above this percentage."
    )
    source: Literal["google_weather"] = Field(
        default=ConnectorType.GOOGLE_WEATHER.value,
        description="The one forecast source read, whatever weather provider the person chose.",
    )


def published_weather_rule() -> WeatherConditionRule:
    """The weather rule as the settings define it — the executor's own reading."""
    return WeatherConditionRule(
        horizon_hours=settings.scheduled_actions_weather_horizon_hours,
        min_precipitation_percent=settings.scheduled_actions_weather_min_precipitation_percent,
    )


class ScheduledActionListResponse(BaseModel):
    """Schema for listing scheduled actions.

    Also publishes the clock of a condition routine NOT YET created (ADR-322):
    the studio states it before the person saves, and these are the values the
    executor enforces — never a copy typed into the browser (ADR-184).
    """

    scheduled_actions: list[ScheduledActionResponse]
    total: int
    condition_check_minutes: dict[str, int] = Field(
        default_factory=published_check_minutes,
        description="How often the system checks each condition type, in minutes.",
    )
    condition_max_fires_per_day: int = Field(
        default_factory=lambda: settings.scheduled_actions_condition_max_fires_per_day,
        description="Most runs one condition routine may start in one local day.",
    )
    weather_condition_rule: WeatherConditionRule = Field(
        default_factory=published_weather_rule,
        description="When a weather-change routine fires: horizon, probability floor, source.",
    )


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
