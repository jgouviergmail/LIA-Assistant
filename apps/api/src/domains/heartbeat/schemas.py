"""
Heartbeat Autonome domain schemas.

Schemas:
- HeartbeatDecision: Structured LLM output for decision phase
- HeartbeatTarget: Internal transport between select_target → generate_content
- HeartbeatContext: Aggregated context from multiple sources
- Settings & History API schemas
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, get_args
from uuid import UUID

import structlog
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.core.llm_usage import LLMBillingRecord
from src.domains.heartbeat.context_prompt import render_context
from src.domains.heartbeat.sms_context import repair_sms_ids
from src.domains.sms.summary import SmsSignal

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# LLM Structured Output
# ---------------------------------------------------------------------------


HeartbeatSourceLabel = Literal[
    "UPCOMING_CALENDAR_EVENTS",
    "PENDING_TASKS",
    "UNREAD_EMAILS",
    "CURRENT_WEATHER",
    "WEATHER_CHANGES",
    "USER_INTERESTS",
    "USER_MEMORIES",
    "JOURNAL_ENTRIES",
    "HEALTH_SIGNALS",
    "SMS",
    "UPCOMING_BIRTHDAYS",
    "OPEN_LOOPS",
    "DEPARTURE_ADVICE",
    "HABITS",
    "WORKBOARD",
    "ANTICIPATED_MOMENT",
]
"""Canonical source labels for the decision structured output (ADR-135).

Free-text labels drifted in production ("USER_MEMORIES" vs "USER MEMORIES"),
making per-source statistics approximate. The Literal is published to the model
as the schema's enum, and what comes back is held to it by REPAIR, never by
refusal (``HeartbeatDecision.keep_canonical_source_labels``): refusing cost the
whole decision — production 2026-10-17, three ticks of five for one account;
replayed on five model families, 6 calls of 120 cited a section that has no
label (``USER RHYTHM``, the recent notifications)."""

_SOURCE_LABELS: frozenset[str] = frozenset(get_args(HeartbeatSourceLabel))


def _canonical_source_label(raw: object) -> str | None:
    """The canonical label ``raw`` spells, whatever its case and separators.

    Args:
        raw: One item the model wrote in ``sources_used``.

    Returns:
        The label of :data:`HeartbeatSourceLabel` it spells, or None when it
        names no source.
    """
    if not isinstance(raw, str):
        return None
    label = "_".join(raw.replace("-", " ").split()).upper()
    return label if label in _SOURCE_LABELS else None


class HeartbeatDecision(BaseModel):
    """Structured output from LLM decision phase.

    The LLM evaluates aggregated context and decides whether to proactively
    notify the user. If action="notify", a message_draft is provided for
    Phase 2 (personality-aware rewrite).
    """

    action: Literal["skip", "notify"] = Field(
        description="Whether to skip (no useful info) or notify the user"
    )
    reason: str = Field(
        description="Why this decision was made (kept with the notification when one is sent)"
    )
    message_draft: str | None = Field(
        None,
        description="Draft notification message (required when action=notify)",
    )
    priority: Literal["low", "medium", "high"] = Field(
        default="low",
        description="Notification priority level",
    )
    sources_used: list[HeartbeatSourceLabel] = Field(
        default_factory=list,
        description="Which context sources contributed (exact labels only)",
    )
    interest_topic: str | None = Field(
        None,
        description=(
            "EXACT topic string copied from the USER INTERESTS list, ONLY when "
            "the notification centers on that interest; null otherwise."
        ),
    )
    # ADR-214: the offer bookkeeping (≤ 1 offer per day, 7-day cooldown, mute
    # after 2 ignored offers) used to key on ``"HABITS" in sources_used`` —
    # a label the model chose freely: measured 2026-09-11, an offer about the
    # learned « email » routine was labelled UNREAD_EMAILS and the budget was
    # never charged. The offer is now DECLARED, on its own field, and the
    # source label stays what it is: an audit trail.
    habit_offered: bool = Field(
        default=False,
        description=(
            "true ONLY when message_draft offers to run the learned routine "
            "listed under MISSED ROUTINE; false otherwise."
        ),
    )

    sms_actionable: bool = Field(
        default=False,
        description="True only for a concrete useful action or fact from an offered SMS, never receipt alone.",
    )
    sms_message_ids: list[UUID] = Field(
        default_factory=list,
        description="Exact offered SMS IDs actually used for that useful fact; empty otherwise.",
    )

    @field_validator("sms_message_ids", mode="before")
    @classmethod
    def keep_valid_sms_ids(cls, value: object) -> list[UUID]:
        return repair_sms_ids(value)

    @field_validator("sources_used", mode="before")
    @classmethod
    def keep_canonical_source_labels(cls, value: Any) -> Any:
        """Repair a label's spelling and drop a label that names no source.

        The labels are an audit trail (an offer is declared by
        ``habit_offered``): a word outside the vocabulary must never cost the
        decision it annotates. A section the prompt shows without a label of
        its own is dropped, never mapped — ``USER RHYTHM`` is context, and
        filing it as ``HABITS`` would read as an offer nobody declared.

        Args:
            value: What the model wrote for the field.

        Returns:
            The canonical labels in their order; anything but a list, a single
            label or null is returned unchanged, so a wrong type stays an error.
        """
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            return value
        kept = [label for label in map(_canonical_source_label, value) if label is not None]
        if len(kept) < len(value):
            logger.info(
                "heartbeat_source_labels_dropped",
                dropped=len(value) - len(kept),
                kept=len(kept),
            )
            logger.debug("heartbeat_source_labels_dropped_values", labels=value)
        return kept

    @model_validator(mode="after")
    def validate_message_draft_on_notify(self) -> HeartbeatDecision:
        """Ensure message_draft is provided when action is 'notify'."""
        if self.action == "notify" and not self.message_draft:
            msg = "message_draft is required when action='notify'"
            raise ValueError(msg)
        return self


# ---------------------------------------------------------------------------
# Context Aggregation
# ---------------------------------------------------------------------------


@dataclass
class WeatherChange:
    """A detected weather transition (notable change).

    Represents an actionable weather change such as rain starting/stopping,
    significant temperature drops, or wind alerts.
    """

    change_type: str  # rain_start | rain_end | temp_drop | temp_rise | wind_alert
    expected_at: datetime  # When the change is expected
    description: str  # Human-readable description for the LLM prompt
    severity: str  # info | warning


@dataclass
class HeartbeatContext:
    """Aggregated context from multiple sources for LLM decision.

    Each source is independently failable — None means the source was
    unavailable or returned no data. The LLM only sees sections with data.
    """

    # ADR-261: the push provider that woke this decision (None = periodic tick).
    wake_trigger: str | None = None
    # Why the decision is being taken at THIS instant (ADR-281). Not a
    # fetched source: the sweep places it, exactly like ``wake_trigger``.
    moment: Any | None = None

    # Calendar
    calendar_events: list[dict[str, Any]] | None = None

    # Weather — current conditions + detected transitions
    weather_current: dict[str, Any] | None = None
    weather_changes: list[WeatherChange] | None = None

    # Weather location provenance (Phase 3): "home" or "last_known".
    # ``weather_location_city`` is the reverse-geocoded city name shown in
    # notification content so the user understands where the forecast is from.
    weather_location_source: Literal["home", "last_known"] | None = None
    weather_location_city: str | None = None

    # Tasks — pending Google Tasks (due soon or overdue)
    pending_tasks: list[dict[str, Any]] | None = None

    # Emails — today's unread inbox emails (any provider)
    unread_emails: list[dict[str, str]] | None = None

    # Interests — trending topics (names only)
    trending_interests: list[dict[str, str]] | None = None

    # Memories — relevant user memories from LangGraph Store
    user_memories: list[str] | None = None

    # Journals — relevant assistant journal entries (semantic search)
    journal_entries: list[dict[str, str]] | None = None

    # Health signals — per-kind summary + baseline deltas + recent variations.
    # Populated by the Health Metrics aggregator source when the user has
    # opted into assistant integrations. Never contains raw sensor values —
    # only deltas, trends, and freshness metadata.
    health_signals: dict[str, Any] | None = None

    sms: SmsSignal | None = None

    # Upcoming contact birthdays (P7) — {contact_name, days_until, age_at_next}
    # entries within the configured look-ahead (today + N days).
    upcoming_birthdays: list[dict[str, Any]] | None = None

    # Traffic-aware leave-by advice for the next located event (P6).
    departure_advice: dict[str, Any] | None = None

    # Nudge-worthy open loops (P5, ADR-139) — {id, subject, counterparty,
    # direction, due_local, days_open}. The ids travel to proactive_task for
    # the post-notification cooldown bump.
    open_loops: list[dict[str, Any]] | None = None

    # ADR-276 D14: tickets overdue, due soon, or waiting on the person.
    workboard: list[dict[str, Any]] | None = None

    # Learned habits block (ADR-214) — {"rhythm": {class: [window labels]},
    # "missed_routine": {habit_id, signature, shape, trigger_label, weekday}}.
    # The habit_id travels to proactive_task for the post-notification offer
    # bookkeeping (cooldown + stop rule), open_loops precedent.
    habits: dict[str, Any] | None = None

    # Activity
    last_interaction_at: datetime | None = None
    hours_since_last_interaction: float | None = None

    # Time context (always available)
    user_local_time: datetime | None = None
    day_of_week: str | None = None
    time_of_day: str | None = None  # morning | afternoon | evening

    # Recent notification history (anti-redundancy cross-type)
    recent_heartbeats: list[dict[str, str]] | None = None
    recent_interest_notifications: list[dict[str, str]] | None = None
    # Other proactive surfaces delivered in the same window (P10): fired
    # reminders, scheduled-action results, telephony call reports. Entries
    # carry {kind, created_at, content} so the decision LLM can detect a
    # same-topic multi-surface pile-up.
    recent_other_notifications: list[dict[str, str]] | None = None

    # Source tracking
    available_sources: list[str] = field(default_factory=list)
    failed_sources: list[str] = field(default_factory=list)

    def has_meaningful_context(self) -> bool:
        """Check if at least one source returned useful data."""
        return any(
            (
                self.calendar_events,
                self.pending_tasks,
                self.unread_emails,
                self.weather_current,
                self.weather_changes,
                self.trending_interests,
                self.user_memories,
                self.journal_entries,
                self.health_signals,
                self.sms,
                self.upcoming_birthdays,
                self.open_loops,
                self.workboard,
                self.departure_advice,
                # Rhythm alone is context, not news: only a missed routine
                # makes the habits block a reason to notify by itself.
                (self.habits or {}).get("missed_routine"),
                # A moment IS the reason this decision is being taken now: it
                # must never be dropped by the « nothing to say » shortcut.
                self.moment,
            )
        )

    def to_prompt_context(self) -> str:
        return render_context(self)

    @property
    def recent_heartbeats_summary(self) -> str | None:
        """Format recent heartbeats for the LLM prompt.

        Renders the CONTENT the user actually received (ADR-135) rather than
        sources + decision reason: topic-level anti-repetition needs to see
        what was said, not which source said it.
        """
        if not self.recent_heartbeats:
            return None
        lines = []
        for hb in self.recent_heartbeats:
            sent_at = hb.get("created_at", "?")
            content = hb.get("content") or hb.get("decision_reason") or "?"
            lines.append(f"  - [{sent_at}] {content}")
        return "\n".join(lines)

    @property
    def recent_interest_notifications_summary(self) -> str | None:
        """Format recent interest notifications for cross-type dedup."""
        if not self.recent_interest_notifications:
            return None
        lines = []
        for n in self.recent_interest_notifications:
            topic = n.get("topic", "?")
            created_at = n.get("created_at", "?")
            lines.append(f"  - [{created_at}] Topic: {topic}")
        return "\n".join(lines)

    @property
    def recent_other_notifications_summary(self) -> str | None:
        """Format other proactive surfaces (reminders, automations, calls).

        P10 — content excerpts, same rationale as ``recent_heartbeats_summary``
        (ADR-135): topic-level anti-repetition needs to see what was delivered,
        whatever the surface that delivered it.
        """
        if not self.recent_other_notifications:
            return None
        lines = []
        for n in self.recent_other_notifications:
            kind = n.get("kind", "?")
            created_at = n.get("created_at", "?")
            content = n.get("content", "?")
            lines.append(f"  - [{created_at}] ({kind}) {content}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Internal Target (select_target → generate_content transport)
# ---------------------------------------------------------------------------


@dataclass
class HeartbeatTarget:
    """Validated target from LLM decision: context + decision + decision tokens.

    Carries all state needed by generate_content() to produce the final message.
    """

    context: HeartbeatContext
    decision: HeartbeatDecision
    decision_tokens_in: int = 0
    decision_tokens_out: int = 0
    decision_tokens_cache: int = 0
    #: The part of ``decision_tokens_in`` Claude wrote to its prompt cache.
    decision_tokens_cache_write: int = 0
    billing_records: tuple[LLMBillingRecord, ...] = ()


# ---------------------------------------------------------------------------
# API Schemas — Settings
# ---------------------------------------------------------------------------


class HeartbeatSettingsResponse(BaseModel):
    """User heartbeat settings response with source availability indicators."""

    heartbeat_enabled: bool = Field(description="Whether heartbeat is enabled")
    heartbeat_notify_start_hour: int = Field(
        ge=0, le=23, description="Start hour for notification window (0-23)"
    )
    heartbeat_notify_end_hour: int = Field(
        ge=0, le=23, description="End hour for notification window (0-23)"
    )
    available_sources: list[str] = Field(
        description="Connected data sources (calendar, tasks, emails, weather, interests, memories)"
    )
    # Availability and permission are DIFFERENT questions: a source can be
    # connected and refused, or unavailable and permitted. Conflating them is
    # what forced "disconnect the connector" as the only way to stop being
    # interrupted (ADR-197).
    disabled_sources: list[str] = Field(
        default_factory=list,
        description="Sources the user refuses to be interrupted from (empty = none).",
    )
    all_sources: list[str] = Field(
        default_factory=list,
        description=(
            "Every source that can be toggled, in display order. Published so "
            "the client never re-declares the vocabulary the server enforces."
        ),
    )
    # A switch that is ON and yields nothing is worse than one that is off:
    # `fetch_departure_advice` returns None without calendar events, so
    # refusing `calendar` silently neutralises `departure`. Enforced here,
    # therefore published here (ADR-184).
    source_dependencies: dict[str, list[str]] = Field(
        default_factory=dict,
        description=(
            "Sources whose result requires another source. A dependency the "
            "user refused makes the dependent switch a no-op, so the panel "
            "can say so instead of leaving a live control that does nothing."
        ),
    )
    moment_kinds_disabled: list[str] = Field(
        default_factory=list,
        description=(
            "Kinds of anticipated moment the user refuses. The refusal set, so an "
            "empty list means every kind is allowed (ADR-281)."
        ),
    )
    all_moment_kinds: list[str] = Field(
        default_factory=list,
        description=(
            "Every kind of moment, in display order. Published so the panel never "
            "re-declares a vocabulary it does not enforce."
        ),
    )
    moment_kind_dependencies: dict[str, list[str]] = Field(
        default_factory=dict,
        description=(
            "Kinds that would yield nothing on this account, and the connector "
            "category each is waiting for (ADR-184)."
        ),
    )


class HeartbeatSettingsUpdate(BaseModel):
    """Partial update for heartbeat settings."""

    heartbeat_enabled: bool | None = None
    heartbeat_notify_start_hour: int | None = Field(None, ge=0, le=23)
    heartbeat_notify_end_hour: int | None = Field(None, ge=0, le=23)
    # `None` means "not part of this PATCH" — an empty LIST means "I refuse
    # nothing", which is a different, storable answer.
    heartbeat_disabled_sources: list[str] | None = Field(
        None, description="Full replacement of the refused-source set."
    )
    moment_kinds_disabled: list[str] | None = Field(
        None,
        description=(
            "Full replacement of the refused moment kinds. Unknown values are "
            "dropped rather than stored."
        ),
    )


# ---------------------------------------------------------------------------
# API Schemas — History & Feedback
# ---------------------------------------------------------------------------


class HeartbeatNotificationResponse(BaseModel):
    """Single heartbeat notification for API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    content: str
    sources_used: list[str]  # Parsed from JSON string
    priority: str
    user_feedback: str | None
    # ADR-261: tick (periodic runner) or push (a Google push notification woke
    # the decision) — the timeline says so.
    trigger: str = "tick"

    @classmethod
    def from_model(cls, notification: Any) -> HeartbeatNotificationResponse:
        """Create from ORM model, parsing JSON sources_used."""
        try:
            sources = json.loads(notification.sources_used)
        except json.JSONDecodeError, TypeError:
            sources = []
        return cls(
            id=notification.id,
            created_at=notification.created_at,
            content=notification.content,
            sources_used=sources,
            priority=notification.priority,
            user_feedback=notification.user_feedback,
            trigger=str(getattr(notification, "trigger", None) or "tick"),
        )


class HeartbeatHistoryResponse(BaseModel):
    """Paginated list of heartbeat notifications."""

    notifications: list[HeartbeatNotificationResponse]
    total: int


class HeartbeatFeedbackRequest(BaseModel):
    """User feedback on a heartbeat notification."""

    feedback: Literal["thumbs_up", "thumbs_down"]
