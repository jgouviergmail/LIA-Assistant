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
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
    "UPCOMING_BIRTHDAYS",
    "OPEN_LOOPS",
    "DEPARTURE_ADVICE",
    "HABITS",
]
"""Canonical source labels for the decision structured output (ADR-135).

Free-text labels drifted in production ("USER_MEMORIES" vs "USER MEMORIES"),
making per-source statistics approximate. The Literal makes the LLM comply
(bench 2026-07-18: 8/8 valid) and the API reject any drift."""


class HeartbeatDecision(BaseModel):
    """Structured output from LLM decision phase.

    The LLM evaluates aggregated context and decides whether to proactively
    notify the user. If action="notify", a message_draft is provided for
    Phase 2 (personality-aware rewrite).
    """

    action: Literal["skip", "notify"] = Field(
        description="Whether to skip (no useful info) or notify the user"
    )
    reason: str = Field(description="Why this decision was made (logged for debugging/audit)")
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

    # Upcoming contact birthdays (P7) — {contact_name, days_until, age_at_next}
    # entries within the configured look-ahead (today + N days).
    upcoming_birthdays: list[dict[str, Any]] | None = None

    # Traffic-aware leave-by advice for the next located event (P6).
    departure_advice: dict[str, Any] | None = None

    # Nudge-worthy open loops (P5, ADR-139) — {id, subject, counterparty,
    # direction, due_local, days_open}. The ids travel to proactive_task for
    # the post-notification cooldown bump.
    open_loops: list[dict[str, Any]] | None = None

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
                self.upcoming_birthdays,
                self.open_loops,
                self.departure_advice,
                # Rhythm alone is context, not news: only a missed routine
                # makes the habits block a reason to notify by itself.
                (self.habits or {}).get("missed_routine"),
            )
        )

    def to_prompt_context(self) -> str:
        """Serialize context for the LLM decision prompt.

        Only includes sections with data. Returns a structured text block
        that the LLM can reason about.
        """
        sections: list[str] = []

        if self.user_local_time:
            sections.append(
                f"TIME: {self.day_of_week}, "
                f"{self.user_local_time.strftime('%d/%m/%Y %H:%M')} "
                f"({self.time_of_day})"
            )

        if self.wake_trigger:
            from src.domains.heartbeat.wake_context import fresh_section

            fresh = fresh_section(self.wake_trigger)
            if fresh:
                sections.append(fresh)

        if self.calendar_events:
            events_text = "\n".join(
                f"  - {e.get('summary', 'Untitled')} "
                f"({e.get('start', '?')} → {e.get('end', '?')})"
                + (f" @ {e['location']}" if e.get("location") else "")
                for e in self.calendar_events
            )
            sections.append(
                f"UPCOMING CALENDAR EVENTS (times in user's local timezone):\n{events_text}"
            )

        if self.pending_tasks:
            tasks_text = "\n".join(
                f"  - {t.get('title', 'Untitled')} (due: {t.get('due', 'no date')})"
                + (" [OVERDUE]" if t.get("overdue") else "")
                for t in self.pending_tasks
            )
            sections.append(f"PENDING TASKS:\n{tasks_text}")

        if self.unread_emails:
            emails_text = "\n".join(
                f"  - From: {e.get('from', '?')} — \"{e.get('subject', 'No subject')}\" "
                f"({e.get('date', '?')})"
                + (f" [{e['snippet'][:80]}...]" if e.get("snippet") else "")
                for e in self.unread_emails
            )
            sections.append(f"UNREAD EMAILS (received today):\n{emails_text}")

        if self.weather_current:
            temp = self.weather_current.get("main", {}).get("temp", "?")
            desc = self.weather_current.get("weather", [{}])[0].get("description", "?")
            wind = self.weather_current.get("wind", {}).get("speed", "?")
            location_suffix = ""
            if self.weather_location_city:
                src_label = (
                    "away from home" if self.weather_location_source == "last_known" else "at home"
                )
                location_suffix = f" in {self.weather_location_city} ({src_label})"
            sections.append(f"CURRENT WEATHER{location_suffix}: {desc}, {temp}°C, wind {wind} m/s")

        if self.weather_changes:
            changes_text = "\n".join(
                f"  - [{c.severity.upper()}] {c.description}" for c in self.weather_changes
            )
            sections.append(f"WEATHER CHANGES DETECTED:\n{changes_text}")

        if self.trending_interests:
            topics = ", ".join(i.get("topic", "?") for i in self.trending_interests)
            sections.append(f"USER INTERESTS (trending): {topics}")

        if self.user_memories:
            memories_text = "\n".join(f"  - {m}" for m in self.user_memories)
            sections.append(f"USER MEMORIES:\n{memories_text}")

        if self.journal_entries:
            journal_text = "\n".join(
                f"  - [{e.get('date', '?')} | {e.get('theme', '')} | {e.get('mood', '')}] "
                f"{e.get('title', 'Untitled')} — {e.get('content_preview', '')}"
                for e in self.journal_entries
            )
            sections.append(f"ASSISTANT JOURNAL ENTRIES (your own reflections):\n{journal_text}")

        if self.health_signals:
            lines: list[str] = []
            summary_today = self.health_signals.get("summary_today", {})
            for kind, payload in summary_today.items():
                lines.append(
                    f"  - today {kind}: {payload.get('value')} {payload.get('unit', '')} "
                    f"(updated {payload.get('last_update_minutes_ago', '?')} min ago)"
                )
            for kind, payload in self.health_signals.get("baseline_deltas_7d", {}).items():
                pct = payload.get("pct")
                mode = payload.get("mode")
                if pct is not None:
                    lines.append(
                        f"  - 7d {kind} vs baseline: {pct:+.1f}% (mode={mode}, "
                        f"baseline={payload.get('baseline_value')})"
                    )
            for variation in self.health_signals.get("recent_variations", []):
                lines.append(
                    f"  - {variation.get('kind')} trend: {variation.get('trend')} "
                    f"over {variation.get('days')} days "
                    f"(avg {variation.get('delta_pct')}%)"
                )
            for event in self.health_signals.get("notable_events", []):
                lines.append(
                    f"  - event: {event.get('event')} on {event.get('kind')} "
                    f"({event.get('days')} days)"
                )
            if lines:
                sections.append("HEALTH SIGNALS (factual, not medical):\n" + "\n".join(lines))

        if self.upcoming_birthdays:
            bday_lines = []
            for b in self.upcoming_birthdays:
                days = b.get("days_until")
                when = "TODAY" if days == 0 else f"in {days} day(s)"
                age = b.get("age_at_next")
                age_txt = f", turning {age}" if age else ""
                bday_lines.append(f"  - {b.get('contact_name', '?')} — {when}{age_txt}")
            sections.append("UPCOMING BIRTHDAYS:\n" + "\n".join(bday_lines))

        if self.departure_advice:
            da = self.departure_advice
            sections.append(
                "DEPARTURE ADVICE (traffic-aware): leave by "
                f"{da.get('leave_by_local', '?')} for '{da.get('event_title', '?')}' "
                f"at {da.get('event_start_local', '?')} — {da.get('eta_minutes', '?')} min "
                f"to {da.get('destination', '?')}"
            )

        if self.open_loops:
            loop_lines = []
            for ol in self.open_loops:
                due = f" (due {ol['due_local']})" if ol.get("due_local") else ""
                who = f" — {ol['counterparty']}" if ol.get("counterparty") else ""
                loop_lines.append(
                    f"  - [{ol.get('direction', '?')}] {ol.get('subject', '?')}{who}{due} "
                    f"(open for {ol.get('days_open', '?')} days)"
                )
            sections.append(
                "OPEN LOOPS (commitments being tracked for the user):\n" + "\n".join(loop_lines)
            )

        if self.habits:
            rhythm = self.habits.get("rhythm") or {}
            if rhythm:
                windows = "; ".join(
                    f"{name}: {', '.join(labels)}" for name, labels in rhythm.items()
                )
                sections.append(
                    "USER RHYTHM (learned activity windows — prefer notifying inside "
                    "them; the user's configured hour bounds always prevail): " + windows
                )
            missed = self.habits.get("missed_routine")
            if missed:
                schedule = (
                    f"weekly (weekday {missed.get('weekday')})"
                    if missed.get("shape") == "weekly"
                    else str(missed.get("shape", "?"))
                )
                sections.append(
                    "MISSED ROUTINE (learned recurring request whose usual slot passed "
                    f"today with no ask): '{missed.get('signature', '?')}' — usually "
                    f"{schedule} around {missed.get('trigger_label', '?')}. You may "
                    "offer ONCE to run it now, framed as a service ('want me to "
                    "prepare it?'), never as surveillance. Skip it whenever anything "
                    "else in this context is more valuable."
                )

        if self.hours_since_last_interaction is not None:
            sections.append(f"LAST INTERACTION: {self.hours_since_last_interaction:.1f} hours ago")

        if not sections:
            return "No context available."

        return "\n\n".join(sections)

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


# ---------------------------------------------------------------------------
# API Schemas — Settings
# ---------------------------------------------------------------------------


class HeartbeatSettingsResponse(BaseModel):
    """User heartbeat settings response with source availability indicators."""

    heartbeat_enabled: bool = Field(description="Whether heartbeat is enabled")
    heartbeat_min_per_day: int = Field(ge=1, le=8, description="Minimum notifications per day")
    heartbeat_max_per_day: int = Field(ge=1, le=8, description="Maximum notifications per day")
    heartbeat_push_enabled: bool = Field(
        description="Whether push notifications (FCM/Telegram) are enabled"
    )
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


class HeartbeatSettingsUpdate(BaseModel):
    """Partial update for heartbeat settings."""

    heartbeat_enabled: bool | None = None
    heartbeat_min_per_day: int | None = Field(None, ge=1, le=8)
    heartbeat_max_per_day: int | None = Field(None, ge=1, le=8)
    heartbeat_push_enabled: bool | None = None
    heartbeat_notify_start_hour: int | None = Field(None, ge=0, le=23)
    heartbeat_notify_end_hour: int | None = Field(None, ge=0, le=23)
    # `None` means "not part of this PATCH" — an empty LIST means "I refuse
    # nothing", which is a different, storable answer.
    heartbeat_disabled_sources: list[str] | None = Field(
        None, description="Full replacement of the refused-source set."
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
