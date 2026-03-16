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
    sources_used: list[str] = Field(
        default_factory=list,
        description="Which context sources contributed to this decision",
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

    # Calendar
    calendar_events: list[dict[str, Any]] | None = None

    # Weather — current conditions + detected transitions
    weather_current: dict[str, Any] | None = None
    weather_changes: list[WeatherChange] | None = None

    # Tasks — pending Google Tasks (due soon or overdue)
    pending_tasks: list[dict[str, Any]] | None = None

    # Emails — today's unread inbox emails (any provider)
    unread_emails: list[dict[str, str]] | None = None

    # Interests — trending topics (names only)
    trending_interests: list[dict[str, str]] | None = None

    # Memories — relevant user memories from LangGraph Store
    user_memories: list[str] | None = None

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
                f"TIME: {self.day_of_week}, {self.user_local_time.strftime('%H:%M')} "
                f"({self.time_of_day})"
            )

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
            sections.append(f"CURRENT WEATHER: {desc}, {temp}°C, wind {wind} m/s")

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

        if self.hours_since_last_interaction is not None:
            sections.append(f"LAST INTERACTION: {self.hours_since_last_interaction:.1f} hours ago")

        if not sections:
            return "No context available."

        return "\n\n".join(sections)

    @property
    def recent_heartbeats_summary(self) -> str | None:
        """Format recent heartbeats for the LLM prompt."""
        if not self.recent_heartbeats:
            return None
        lines = []
        for hb in self.recent_heartbeats:
            sources = hb.get("sources_used", "?")
            reason = hb.get("decision_reason", "?")
            sent_at = hb.get("created_at", "?")
            lines.append(f"  - [{sent_at}] Sources: {sources} — {reason}")
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


class HeartbeatSettingsUpdate(BaseModel):
    """Partial update for heartbeat settings."""

    heartbeat_enabled: bool | None = None
    heartbeat_min_per_day: int | None = Field(None, ge=1, le=8)
    heartbeat_max_per_day: int | None = Field(None, ge=1, le=8)
    heartbeat_push_enabled: bool | None = None
    heartbeat_notify_start_hour: int | None = Field(None, ge=0, le=23)
    heartbeat_notify_end_hour: int | None = Field(None, ge=0, le=23)


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

    @classmethod
    def from_model(cls, notification: Any) -> HeartbeatNotificationResponse:
        """Create from ORM model, parsing JSON sources_used."""
        try:
            sources = json.loads(notification.sources_used)
        except (json.JSONDecodeError, TypeError):
            sources = []
        return cls(
            id=notification.id,
            created_at=notification.created_at,
            content=notification.content,
            sources_used=sources,
            priority=notification.priority,
            user_feedback=notification.user_feedback,
        )


class HeartbeatHistoryResponse(BaseModel):
    """Paginated list of heartbeat notifications."""

    notifications: list[HeartbeatNotificationResponse]
    total: int


class HeartbeatFeedbackRequest(BaseModel):
    """User feedback on a heartbeat notification."""

    feedback: Literal["thumbs_up", "thumbs_down"]
