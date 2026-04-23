"""Pydantic schemas for the Today briefing API contract.

All payload models are immutable (`frozen=True`) — the briefing is a read-only
snapshot, mutations are nonsensical here.

Status semantics (CardStatus):
- OK              : data present, render normally
- EMPTY           : connector OK but no data (positive empty state, e.g. "Inbox propre")
- ERROR           : recoverable failure (token expired, network) — show CTA
- NOT_CONFIGURED  : no connector for this section — frontend hides the card entirely
"""

from datetime import datetime
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

# =============================================================================
# Enums
# =============================================================================


class CardStatus(str, Enum):
    """Per-section status — drives the frontend rendering branch."""

    OK = "ok"
    EMPTY = "empty"
    ERROR = "error"
    NOT_CONFIGURED = "not_configured"


# =============================================================================
# Per-section payloads (UI-formatted strings, no raw timestamps)
# =============================================================================


class DailyForecastItem(BaseModel):
    """One day in the 5-day forecast (compact summary).

    Frontend derives the localized weekday label from ``date_iso`` via
    ``Intl.DateTimeFormat`` — the API does not pre-format it.
    """

    model_config = ConfigDict(frozen=True)

    date_iso: str = Field(..., description="Date 'YYYY-MM-DD' in user timezone")
    temp_min_c: float
    temp_max_c: float
    condition_code: str = Field(
        ..., description="OpenWeatherMap main condition code (most frequent of the day)"
    )
    icon_emoji: str = Field(..., description="Single emoji representing the dominant condition")


class WeatherData(BaseModel):
    """Weather payload, fully UI-ready (description already localized).

    Includes:
    - Current conditions (temp, description, emoji, location)
    - Today's expected min/max
    - Wind (speed km/h + cardinal direction)
    - Next 3 h precipitation probability
    - 5-day daily forecast (icon + min/max per day)
    - Optional short-term alert (rain start, etc.)
    """

    model_config = ConfigDict(frozen=True)

    temperature_c: float = Field(
        ..., description="Current temperature in Celsius (rounded one decimal)"
    )
    temperature_min_c: float | None = Field(
        None, description="Today's expected minimum temperature in Celsius (from forecast)"
    )
    temperature_max_c: float | None = Field(
        None, description="Today's expected maximum temperature in Celsius (from forecast)"
    )
    condition_code: str = Field(
        ..., description="OpenWeatherMap main condition code: 'Clear', 'Rain', 'Snow', etc."
    )
    description: str = Field(..., description="Localized humanized description (e.g. 'ensoleillé')")
    icon_emoji: str = Field(..., description="Single emoji representing the condition")
    location_city: str | None = Field(None, description="Resolved city name (reverse geocoded)")
    wind_speed_kmh: float | None = Field(
        None, description="Current wind speed in km/h (converted from m/s)"
    )
    wind_direction_cardinal: str | None = Field(
        None,
        description="Wind direction as cardinal point: N, NE, E, SE, S, SW, W, NW",
    )
    precipitation_probability: float | None = Field(
        None,
        description="Next 3 h precipitation probability (0.0 – 1.0), from forecast first slot",
    )
    forecast_alert: str | None = Field(
        None,
        description="Optional pre-formatted one-liner alert: 'Rain expected at 16:00'",
    )
    daily_forecast: list[DailyForecastItem] = Field(
        default_factory=list,
        description="5-day daily forecast (today + next 4 days), ordered chronologically",
    )


class AgendaEventItem(BaseModel):
    """Single calendar event — pre-formatted for display."""

    model_config = ConfigDict(frozen=True)

    title: str
    start_local: str = Field(
        ..., description="Pre-formatted local start time, e.g. '14:00' or '2026-04-23 09:00'"
    )
    end_local: str | None = Field(
        None,
        description="Pre-formatted local end time, e.g. '15:30'. None for events without an end.",
    )
    location: str | None = None


class AgendaData(BaseModel):
    model_config = ConfigDict(frozen=True)

    events: list[AgendaEventItem]


class MailItem(BaseModel):
    """Single email summary — pre-formatted for display.

    `sender_email` is the parsed email address (may be None if the from header
    couldn't be parsed). `sender_name` is the display name part if present.
    """

    model_config = ConfigDict(frozen=True)

    sender_name: str | None = Field(
        None, description="Sender display name (parsed from the From header)"
    )
    sender_email: str | None = Field(
        None, description="Sender email address (parsed from the From header)"
    )
    subject: str
    received_local: str = Field(..., description="Pre-formatted local received time")


class MailsData(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[MailItem]
    total_unread_today: int


class BirthdayItem(BaseModel):
    """Upcoming birthday entry — pre-computed days_until + age."""

    model_config = ConfigDict(frozen=True)

    contact_name: str
    date_iso: str = Field(
        ...,
        description="ISO 8601 date: 'YYYY-MM-DD' if year known, '--MM-DD' otherwise",
    )
    days_until: int = Field(..., ge=0, description="Days from today to next occurrence")
    age_at_next: int | None = Field(
        None,
        description="Age the contact will turn at the next birthday. None when birth year unknown.",
    )


class BirthdaysData(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[BirthdayItem]


class ReminderItem(BaseModel):
    """Active reminder — pre-formatted local trigger time."""

    model_config = ConfigDict(frozen=True)

    content: str
    trigger_at_local: str = Field(
        ..., description="Pre-formatted local time, e.g. 'today 14:30' or 'tomorrow 09:00'"
    )


class RemindersData(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[ReminderItem]


# Health kinds match HEALTH_KINDS registry (steps + heart_rate at v1.17.x).
HealthKind = Literal["steps", "heart_rate"]


class HealthSummaryItem(BaseModel):
    """One health metric kind summary — TODAY's value + rolling-window average.

    Semantics per kind:
    - steps: ``value_today`` = total steps today, ``value_avg_window`` = average
      daily steps over the last ``window_days`` days
    - heart_rate: ``value_today`` = average bpm of today's samples,
      ``value_avg_window`` = average bpm over the last ``window_days`` days
    """

    model_config = ConfigDict(frozen=True)

    kind: HealthKind
    value_today: float | None = Field(
        None,
        description="Today's value (kind-specific aggregation: SUM for steps, AVG for HR). None if no samples today.",
    )
    value_avg_window: float | None = Field(
        None,
        description="Per-day average over the rolling window. None if window is empty.",
    )
    unit: str
    window_days: int = Field(..., description="Length of the rolling window (typically 14)")
    days_with_data: int = Field(
        ..., description="Number of days in the window with at least one sample"
    )


class HealthData(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[HealthSummaryItem]


# Tagged union for the per-card payload.
SectionPayload = Annotated[
    WeatherData | AgendaData | MailsData | BirthdaysData | RemindersData | HealthData | None,
    Field(description="Section-specific payload. None if status != OK."),
]


# =============================================================================
# Generic envelopes
# =============================================================================


class CardSection(BaseModel):
    """Generic envelope — same shape for all 6 cards.

    Note: not frozen because we deserialize from Redis and the frontend may
    serialize back via model_dump_json. Frozen Pydantic models still support
    serialization but writing tests is easier with mutable internals here.
    """

    model_config = ConfigDict(from_attributes=True)

    status: CardStatus
    data: SectionPayload = None
    generated_at: datetime = Field(
        ..., description="When this section was last fetched/computed (UTC)."
    )
    error_code: str | None = Field(
        None, description="Stable error code for frontend CTA mapping (see constants.py)."
    )
    error_message: str | None = Field(None, description="Localized human-readable error message.")


class LLMUsage(BaseModel):
    """Token usage + EUR cost summary for a single LLM call.

    Surfaced alongside greeting / synthesis text so the UI can display the
    real consumption of each briefing LLM call next to the timestamp.
    """

    model_config = ConfigDict(frozen=True)

    tokens_in: int = Field(0, ge=0, description="Input/prompt tokens (excluding cached).")
    tokens_out: int = Field(0, ge=0, description="Output/completion tokens.")
    tokens_cache: int = Field(0, ge=0, description="Cached input tokens (when supported).")
    cost_eur: float = Field(
        0.0,
        ge=0.0,
        description="Computed cost in EUR using the active pricing cache.",
    )
    model_name: str | None = Field(None, description="Model identifier used for the call.")


class TextSection(BaseModel):
    """Greeting or synthesis text — generated by the briefing LLM."""

    model_config = ConfigDict(frozen=True)

    text: str
    generated_at: datetime
    usage: LLMUsage | None = Field(
        None,
        description="Token + cost breakdown for this LLM call. None when no LLM call was made (e.g. fallback greeting).",
    )


class CardsBundle(BaseModel):
    """All 6 cards bundled. Frontend iterates and hides NOT_CONFIGURED."""

    model_config = ConfigDict(frozen=True)

    weather: CardSection
    agenda: CardSection
    mails: CardSection
    birthdays: CardSection
    reminders: CardSection
    health: CardSection


class BriefingResponse(BaseModel):
    """Complete briefing payload — returned by GET /briefing/today.

    Kept for backward compatibility and refresh endpoint. Prefer the split
    endpoints (`/briefing/cards` + `/briefing/synthesis`) for non-blocking UI.
    """

    model_config = ConfigDict(frozen=True)

    greeting: TextSection = Field(
        ..., description="LLM-generated single-sentence greeting in user's language."
    )
    synthesis: TextSection | None = Field(
        None,
        description=(
            "LLM-generated 2-3 sentence synthesis. None when fewer than "
            "BRIEFING_SYNTHESIS_MIN_CARDS_WITH_DATA cards have OK data."
        ),
    )
    cards: CardsBundle


class CardsResponse(BaseModel):
    """Cards-only payload — returned by GET /briefing/cards.

    Fast endpoint (no LLM): the dashboard cards grid renders as soon as this
    response arrives, without waiting for the LLM-generated greeting + synthesis.
    """

    model_config = ConfigDict(frozen=True)

    cards: CardsBundle


class SynthesisResponse(BaseModel):
    """LLM payload — returned by GET /briefing/synthesis.

    Slow endpoint (LLM-bound, ~1-3 s). Reads the cards from cache to feed the
    LLM context. Frontend calls this in parallel with /briefing/cards so the
    page renders progressively.
    """

    model_config = ConfigDict(frozen=True)

    greeting: TextSection = Field(..., description="LLM-generated single-sentence greeting.")
    synthesis: TextSection | None = Field(
        None,
        description=("LLM-generated 2-3 sentence synthesis. None when too few cards have data."),
    )


# =============================================================================
# Request schemas
# =============================================================================


# Allowed section names for refresh — must match SECTION_* constants.
RefreshSectionLiteral = Literal[
    "weather", "agenda", "mails", "birthdays", "reminders", "health", "all"
]


class RefreshRequest(BaseModel):
    """Payload for POST /briefing/refresh."""

    model_config = ConfigDict(frozen=True)

    sections: list[RefreshSectionLiteral] = Field(
        ...,
        min_length=1,
        max_length=7,
        description="Sections to force-refresh; 'all' bypasses every cache.",
    )
