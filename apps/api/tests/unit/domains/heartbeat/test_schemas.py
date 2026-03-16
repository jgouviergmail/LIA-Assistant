"""
Unit tests for domains/heartbeat/schemas.py.

Tests Pydantic schemas and dataclass validation for the Heartbeat domain.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.domains.heartbeat.schemas import (
    HeartbeatContext,
    HeartbeatDecision,
    HeartbeatFeedbackRequest,
    HeartbeatHistoryResponse,
    HeartbeatNotificationResponse,
    HeartbeatSettingsResponse,
    HeartbeatSettingsUpdate,
    HeartbeatTarget,
    WeatherChange,
)

# ---------------------------------------------------------------------------
# HeartbeatDecision
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestHeartbeatDecision:
    """Tests for HeartbeatDecision structured output schema."""

    def test_valid_notify_decision(self):
        """Test valid notify decision with all fields."""
        decision = HeartbeatDecision(
            action="notify",
            reason="Upcoming meeting in 1 hour + rain expected",
            message_draft="You have a meeting at 2pm and it might rain.",
            priority="high",
            sources_used=["calendar", "weather"],
        )

        assert decision.action == "notify"
        assert decision.priority == "high"
        assert len(decision.sources_used) == 2

    def test_valid_skip_decision(self):
        """Test valid skip decision."""
        decision = HeartbeatDecision(
            action="skip",
            reason="No actionable information",
        )

        assert decision.action == "skip"
        assert decision.message_draft is None
        assert decision.priority == "low"
        assert decision.sources_used == []

    def test_invalid_action(self):
        """Test that invalid action is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            HeartbeatDecision(action="invalid", reason="test")

        assert "Input should be" in str(exc_info.value)

    def test_invalid_priority(self):
        """Test that invalid priority is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            HeartbeatDecision(
                action="notify",
                reason="test",
                priority="urgent",
            )

        assert "Input should be" in str(exc_info.value)

    def test_default_values(self):
        """Test default field values."""
        decision = HeartbeatDecision(action="skip", reason="nothing to report")

        assert decision.message_draft is None
        assert decision.priority == "low"
        assert decision.sources_used == []

    def test_notify_without_message_draft_rejected(self):
        """Test that notify action without message_draft is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            HeartbeatDecision(
                action="notify",
                reason="test reason",
                message_draft=None,
            )

        assert "message_draft" in str(exc_info.value)

    def test_notify_with_empty_message_draft_rejected(self):
        """Test that notify action with empty message_draft is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            HeartbeatDecision(
                action="notify",
                reason="test reason",
                message_draft="",
            )

        assert "message_draft" in str(exc_info.value)


# ---------------------------------------------------------------------------
# WeatherChange
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestWeatherChange:
    """Tests for WeatherChange dataclass."""

    def test_valid_weather_change(self):
        """Test creating a valid weather change."""
        now = datetime.now(UTC)
        change = WeatherChange(
            change_type="rain_start",
            expected_at=now + timedelta(hours=1),
            description="Rain expected around 15:00",
            severity="warning",
        )

        assert change.change_type == "rain_start"
        assert change.severity == "warning"

    def test_all_change_types(self):
        """Test all valid change types."""
        now = datetime.now(UTC)
        for change_type in ("rain_start", "rain_end", "temp_drop", "wind_alert"):
            change = WeatherChange(
                change_type=change_type,
                expected_at=now,
                description=f"Test {change_type}",
                severity="info",
            )
            assert change.change_type == change_type


# ---------------------------------------------------------------------------
# HeartbeatContext
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestHeartbeatContext:
    """Tests for HeartbeatContext dataclass."""

    def test_empty_context_not_meaningful(self):
        """Test that empty context has no meaningful data."""
        ctx = HeartbeatContext()

        assert not ctx.has_meaningful_context()

    def test_context_with_calendar_is_meaningful(self):
        """Test that context with calendar events is meaningful."""
        ctx = HeartbeatContext(
            calendar_events=[{"summary": "Meeting", "start": "14:00", "end": "15:00"}]
        )

        assert ctx.has_meaningful_context()

    def test_context_with_weather_is_meaningful(self):
        """Test that context with weather is meaningful."""
        ctx = HeartbeatContext(
            weather_current={"main": {"temp": 15}, "weather": [{"main": "Clear"}]}
        )

        assert ctx.has_meaningful_context()

    def test_context_with_weather_changes_is_meaningful(self):
        """Test that context with weather changes alone is meaningful."""
        ctx = HeartbeatContext(
            weather_changes=[
                WeatherChange(
                    change_type="rain_start",
                    expected_at=datetime.now(UTC),
                    description="Rain in 1h",
                    severity="warning",
                )
            ]
        )

        assert ctx.has_meaningful_context()

    def test_context_with_interests_is_meaningful(self):
        """Test that context with trending interests is meaningful."""
        ctx = HeartbeatContext(trending_interests=[{"topic": "AI"}])

        assert ctx.has_meaningful_context()

    def test_context_with_memories_is_meaningful(self):
        """Test that context with memories is meaningful."""
        ctx = HeartbeatContext(user_memories=["User prefers morning runs"])

        assert ctx.has_meaningful_context()

    def test_context_with_tasks_is_meaningful(self):
        """Test that context with pending tasks is meaningful."""
        ctx = HeartbeatContext(
            pending_tasks=[{"title": "Buy groceries", "due": "2026-03-03", "overdue": False}]
        )

        assert ctx.has_meaningful_context()

    def test_activity_alone_not_meaningful(self):
        """Test that activity data alone is not meaningful."""
        ctx = HeartbeatContext(
            last_interaction_at=datetime.now(UTC),
            hours_since_last_interaction=2.5,
        )

        assert not ctx.has_meaningful_context()

    def test_to_prompt_context_empty(self):
        """Test prompt context for empty context."""
        ctx = HeartbeatContext()

        assert ctx.to_prompt_context() == "No context available."

    def test_to_prompt_context_with_data(self):
        """Test prompt context includes relevant sections."""
        ctx = HeartbeatContext(
            user_local_time=datetime(2026, 3, 3, 14, 30, tzinfo=UTC),
            day_of_week="Monday",
            time_of_day="afternoon",
            calendar_events=[{"summary": "Team standup", "start": "15:00", "end": "15:30"}],
            weather_current={
                "main": {"temp": 18},
                "weather": [{"description": "partly cloudy"}],
                "wind": {"speed": 5},
            },
            hours_since_last_interaction=3.0,
        )

        prompt = ctx.to_prompt_context()

        assert "TIME:" in prompt
        assert "Monday" in prompt
        assert "afternoon" in prompt
        assert "CALENDAR" in prompt
        assert "Team standup" in prompt
        assert "WEATHER" in prompt
        assert "partly cloudy" in prompt
        assert "LAST INTERACTION" in prompt
        assert "3.0" in prompt

    def test_to_prompt_context_weather_changes(self):
        """Test prompt context includes weather changes."""
        ctx = HeartbeatContext(
            weather_changes=[
                WeatherChange(
                    change_type="rain_start",
                    expected_at=datetime.now(UTC),
                    description="Rain starting in 45 min",
                    severity="warning",
                )
            ]
        )

        prompt = ctx.to_prompt_context()

        assert "WEATHER CHANGES" in prompt
        assert "[WARNING]" in prompt
        assert "Rain starting in 45 min" in prompt

    def test_to_prompt_context_with_tasks(self):
        """Test prompt context includes pending tasks with overdue flag."""
        ctx = HeartbeatContext(
            pending_tasks=[
                {"title": "Buy groceries", "due": "2026-03-03", "overdue": False},
                {"title": "Review PR", "due": "2026-03-01", "overdue": True},
            ]
        )

        prompt = ctx.to_prompt_context()

        assert "PENDING TASKS" in prompt
        assert "Buy groceries" in prompt
        assert "Review PR" in prompt
        assert "[OVERDUE]" in prompt

    def test_context_with_emails_is_meaningful(self):
        """Test that context with unread emails is meaningful."""
        ctx = HeartbeatContext(
            unread_emails=[
                {"from": "boss@example.com", "subject": "Urgent", "date": "14:30", "snippet": ""}
            ]
        )

        assert ctx.has_meaningful_context()

    def test_to_prompt_context_with_emails(self):
        """Test prompt context includes unread emails section."""
        ctx = HeartbeatContext(
            unread_emails=[
                {
                    "from": "alice@example.com",
                    "subject": "Project update",
                    "date": "10:15",
                    "snippet": "Hi, just wanted to share the latest status",
                },
                {
                    "from": "bob@example.com",
                    "subject": "Lunch today?",
                    "date": "11:00",
                    "snippet": "",
                },
            ]
        )

        prompt = ctx.to_prompt_context()

        assert "UNREAD EMAILS (received today)" in prompt
        assert "alice@example.com" in prompt
        assert "Project update" in prompt
        assert "bob@example.com" in prompt
        assert "Lunch today?" in prompt

    def test_recent_heartbeats_summary_none(self):
        """Test summary is None when no recent heartbeats."""
        ctx = HeartbeatContext()

        assert ctx.recent_heartbeats_summary is None

    def test_recent_heartbeats_summary_with_data(self):
        """Test summary format with recent heartbeats."""
        ctx = HeartbeatContext(
            recent_heartbeats=[
                {
                    "sources_used": "calendar, weather",
                    "decision_reason": "Meeting + rain",
                    "created_at": "2026-03-03 10:00",
                }
            ]
        )

        summary = ctx.recent_heartbeats_summary

        assert summary is not None
        assert "calendar, weather" in summary
        assert "Meeting + rain" in summary

    def test_recent_interest_notifications_summary(self):
        """Test cross-type dedup summary."""
        ctx = HeartbeatContext(
            recent_interest_notifications=[{"topic": "AI", "created_at": "2026-03-03 09:00"}]
        )

        summary = ctx.recent_interest_notifications_summary

        assert summary is not None
        assert "AI" in summary

    def test_default_source_tracking(self):
        """Test default source tracking lists are empty."""
        ctx = HeartbeatContext()

        assert ctx.available_sources == []
        assert ctx.failed_sources == []


# ---------------------------------------------------------------------------
# HeartbeatTarget
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestHeartbeatTarget:
    """Tests for HeartbeatTarget dataclass."""

    def test_valid_target(self):
        """Test creating a valid target."""
        ctx = HeartbeatContext(calendar_events=[{"summary": "Meeting"}])
        decision = HeartbeatDecision(
            action="notify",
            reason="Upcoming meeting",
            message_draft="You have a meeting soon.",
            sources_used=["calendar"],
        )
        target = HeartbeatTarget(
            context=ctx,
            decision=decision,
            decision_tokens_in=100,
            decision_tokens_out=50,
        )

        assert target.decision.action == "notify"
        assert target.decision_tokens_in == 100
        assert target.decision_tokens_out == 50
        assert target.decision_tokens_cache == 0


# ---------------------------------------------------------------------------
# HeartbeatSettingsResponse / Update
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestHeartbeatSettingsResponse:
    """Tests for HeartbeatSettingsResponse schema."""

    def test_valid_settings(self):
        """Test valid settings response."""
        settings = HeartbeatSettingsResponse(
            heartbeat_enabled=True,
            heartbeat_min_per_day=1,
            heartbeat_max_per_day=3,
            heartbeat_push_enabled=True,
            heartbeat_notify_start_hour=9,
            heartbeat_notify_end_hour=22,
            available_sources=["calendar", "weather"],
        )

        assert settings.heartbeat_enabled is True
        assert settings.heartbeat_min_per_day == 1
        assert settings.heartbeat_max_per_day == 3
        assert settings.heartbeat_notify_start_hour == 9
        assert settings.heartbeat_notify_end_hour == 22
        assert len(settings.available_sources) == 2

    def test_empty_sources(self):
        """Test settings with no available sources."""
        settings = HeartbeatSettingsResponse(
            heartbeat_enabled=False,
            heartbeat_min_per_day=1,
            heartbeat_max_per_day=3,
            heartbeat_push_enabled=True,
            heartbeat_notify_start_hour=9,
            heartbeat_notify_end_hour=22,
            available_sources=[],
        )

        assert settings.available_sources == []


@pytest.mark.unit
class TestHeartbeatSettingsUpdate:
    """Tests for HeartbeatSettingsUpdate schema."""

    def test_partial_update_enabled_only(self):
        """Test partial update with enabled only."""
        update = HeartbeatSettingsUpdate(heartbeat_enabled=True)

        assert update.heartbeat_enabled is True
        assert update.heartbeat_max_per_day is None
        assert update.heartbeat_push_enabled is None

    def test_empty_update_valid(self):
        """Test that empty update is valid."""
        update = HeartbeatSettingsUpdate()

        assert update.heartbeat_enabled is None
        assert update.heartbeat_max_per_day is None

    def test_max_per_day_valid_range(self):
        """Test valid max_per_day range (1-8)."""
        for n in (1, 4, 8):
            update = HeartbeatSettingsUpdate(heartbeat_max_per_day=n)
            assert update.heartbeat_max_per_day == n

    def test_max_per_day_below_minimum(self):
        """Test that max_per_day below 1 is rejected."""
        with pytest.raises(ValidationError):
            HeartbeatSettingsUpdate(heartbeat_max_per_day=0)

    def test_max_per_day_above_maximum(self):
        """Test that max_per_day above 8 is rejected."""
        with pytest.raises(ValidationError):
            HeartbeatSettingsUpdate(heartbeat_max_per_day=9)

    def test_notify_hours_valid_range(self):
        """Test valid notification hour range (0-23)."""
        update = HeartbeatSettingsUpdate(
            heartbeat_notify_start_hour=0,
            heartbeat_notify_end_hour=23,
        )
        assert update.heartbeat_notify_start_hour == 0
        assert update.heartbeat_notify_end_hour == 23

    def test_notify_start_hour_too_high(self):
        """Test that start hour above 23 is rejected."""
        with pytest.raises(ValidationError):
            HeartbeatSettingsUpdate(heartbeat_notify_start_hour=24)

    def test_notify_end_hour_negative(self):
        """Test that negative end hour is rejected."""
        with pytest.raises(ValidationError):
            HeartbeatSettingsUpdate(heartbeat_notify_end_hour=-1)


# ---------------------------------------------------------------------------
# HeartbeatFeedbackRequest
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestHeartbeatFeedbackRequest:
    """Tests for HeartbeatFeedbackRequest schema."""

    def test_thumbs_up(self):
        """Test thumbs_up feedback."""
        req = HeartbeatFeedbackRequest(feedback="thumbs_up")
        assert req.feedback == "thumbs_up"

    def test_thumbs_down(self):
        """Test thumbs_down feedback."""
        req = HeartbeatFeedbackRequest(feedback="thumbs_down")
        assert req.feedback == "thumbs_down"

    def test_invalid_feedback(self):
        """Test invalid feedback value is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            HeartbeatFeedbackRequest(feedback="neutral")

        assert "Input should be" in str(exc_info.value)


# ---------------------------------------------------------------------------
# HeartbeatNotificationResponse
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestHeartbeatNotificationResponse:
    """Tests for HeartbeatNotificationResponse schema."""

    def test_valid_response(self):
        """Test creating a valid notification response."""
        now = datetime.now(UTC)
        response = HeartbeatNotificationResponse(
            id=uuid4(),
            created_at=now,
            content="You have a meeting in 30 minutes.",
            sources_used=["calendar"],
            priority="medium",
            user_feedback=None,
        )

        assert response.content == "You have a meeting in 30 minutes."
        assert response.sources_used == ["calendar"]
        assert response.user_feedback is None

    def test_response_with_feedback(self):
        """Test notification response with user feedback."""
        now = datetime.now(UTC)
        response = HeartbeatNotificationResponse(
            id=uuid4(),
            created_at=now,
            content="Rain expected soon.",
            sources_used=["weather"],
            priority="high",
            user_feedback="thumbs_up",
        )

        assert response.user_feedback == "thumbs_up"


# ---------------------------------------------------------------------------
# HeartbeatHistoryResponse
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestHeartbeatHistoryResponse:
    """Tests for HeartbeatHistoryResponse schema."""

    def test_empty_history(self):
        """Test empty history response."""
        history = HeartbeatHistoryResponse(notifications=[], total=0)

        assert len(history.notifications) == 0
        assert history.total == 0

    def test_history_with_notifications(self):
        """Test history with notification entries."""
        now = datetime.now(UTC)
        notif = HeartbeatNotificationResponse(
            id=uuid4(),
            created_at=now,
            content="Test notification",
            sources_used=["calendar"],
            priority="low",
            user_feedback=None,
        )
        history = HeartbeatHistoryResponse(notifications=[notif], total=1)

        assert len(history.notifications) == 1
        assert history.total == 1
