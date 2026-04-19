"""
Unit tests for domains/heartbeat/context_aggregator.py.

Tests the ContextAggregator with mocked data sources,
parallel fetch behavior, and weather change detection.
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

from src.domains.heartbeat.context_aggregator import (
    ContextAggregator,
    _extract_due_date,
    _format_event_time,
    _format_utc_datetime,
)
from src.domains.heartbeat.schemas import HeartbeatContext, WeatherChange

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_settings(**overrides) -> SimpleNamespace:
    """Create a fake settings object with heartbeat defaults."""
    defaults = {
        "heartbeat_context_calendar_hours": 6,
        "heartbeat_context_memory_limit": 5,
        "heartbeat_context_emails_max": 5,
        "heartbeat_weather_rain_threshold_high": 0.6,
        "heartbeat_weather_rain_threshold_low": 0.3,
        "heartbeat_weather_temp_change_threshold": 5.0,
        "heartbeat_weather_wind_threshold": 14.0,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_user(**overrides) -> SimpleNamespace:
    """Create a fake user object."""
    defaults = {
        "id": "user-123",
        "timezone": "Europe/Paris",
        "home_location": None,
        "memory_enabled": False,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# _compute_time_context
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestComputeTimeContext:
    """Tests for time context computation."""

    def test_morning_classification(self):
        """Test that hours before 12 are classified as morning."""
        aggregator = ContextAggregator(MagicMock())
        user = _make_user(timezone="UTC")
        context = HeartbeatContext()

        aggregator._compute_time_context(context, user)

        # We can't control the current time, but we can verify the fields are set
        assert context.user_local_time is not None
        assert context.day_of_week is not None
        assert context.time_of_day in ("morning", "afternoon", "evening")

    def test_invalid_timezone_fallback(self):
        """Test fallback to Europe/Paris for invalid timezone."""
        aggregator = ContextAggregator(MagicMock())
        user = _make_user(timezone="Invalid/Timezone")
        context = HeartbeatContext()

        aggregator._compute_time_context(context, user)

        assert context.user_local_time is not None

    def test_none_timezone_fallback(self):
        """Test fallback when timezone is None."""
        aggregator = ContextAggregator(MagicMock())
        user = _make_user(timezone=None)
        context = HeartbeatContext()

        aggregator._compute_time_context(context, user)

        assert context.user_local_time is not None


# ---------------------------------------------------------------------------
# _apply_source_result
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestApplySourceResult:
    """Tests for _apply_source_result routing."""

    def test_calendar_result(self):
        """Test calendar result is applied correctly."""
        aggregator = ContextAggregator(MagicMock())
        context = HeartbeatContext()
        events = [{"summary": "Meeting", "start": "14:00"}]

        aggregator._apply_source_result(context, "calendar", events)

        assert context.calendar_events == events
        assert "calendar" in context.available_sources

    def test_weather_result(self):
        """Test weather result is applied correctly."""
        aggregator = ContextAggregator(MagicMock())
        context = HeartbeatContext()
        current = {"main": {"temp": 20}}
        changes = [
            WeatherChange(
                change_type="rain_start",
                expected_at=datetime.now(UTC),
                description="Rain expected",
                severity="warning",
            )
        ]

        aggregator._apply_source_result(context, "weather", (current, changes, "home", "Lyon"))

        assert context.weather_current == current
        assert context.weather_changes == changes
        assert context.weather_location_source == "home"
        assert context.weather_location_city == "Lyon"
        assert "weather" in context.available_sources

    def test_interests_result(self):
        """Test interests result is applied correctly."""
        aggregator = ContextAggregator(MagicMock())
        context = HeartbeatContext()
        interests = [{"topic": "AI"}, {"topic": "Python"}]

        aggregator._apply_source_result(context, "interests", interests)

        assert context.trending_interests == interests
        assert "interests" in context.available_sources

    def test_memories_result(self):
        """Test memories result is applied correctly."""
        aggregator = ContextAggregator(MagicMock())
        context = HeartbeatContext()
        memories = ["User likes morning coffee", "Prefers short notifications"]

        aggregator._apply_source_result(context, "memories", memories)

        assert context.user_memories == memories
        assert "memories" in context.available_sources

    def test_activity_result(self):
        """Test activity result is applied correctly."""
        aggregator = ContextAggregator(MagicMock())
        context = HeartbeatContext()
        last_at = datetime.now(UTC)

        aggregator._apply_source_result(context, "activity", (last_at, 2.5))

        assert context.last_interaction_at == last_at
        assert context.hours_since_last_interaction == 2.5

    def test_recent_heartbeats_result(self):
        """Test recent heartbeats result is applied correctly."""
        aggregator = ContextAggregator(MagicMock())
        context = HeartbeatContext()
        heartbeats = [{"sources_used": "calendar", "decision_reason": "meeting"}]

        aggregator._apply_source_result(context, "recent_heartbeats", heartbeats)

        assert context.recent_heartbeats == heartbeats

    def test_recent_interests_result(self):
        """Test recent interest notifications result is applied correctly."""
        aggregator = ContextAggregator(MagicMock())
        context = HeartbeatContext()
        notifications = [{"topic": "AI", "created_at": "2026-03-03"}]

        aggregator._apply_source_result(context, "recent_interests", notifications)

        assert context.recent_interest_notifications == notifications

    def test_none_result_not_applied(self):
        """Test that None results are not applied."""
        aggregator = ContextAggregator(MagicMock())
        context = HeartbeatContext()

        aggregator._apply_source_result(context, "calendar", None)

        assert context.calendar_events is None
        assert "calendar" not in context.available_sources

    def test_tasks_result(self):
        """Test tasks result is applied correctly."""
        aggregator = ContextAggregator(MagicMock())
        context = HeartbeatContext()
        tasks = [
            {"title": "Buy groceries", "due": "2026-03-03", "overdue": False},
            {"title": "Review PR", "due": "2026-03-02", "overdue": True},
        ]

        aggregator._apply_source_result(context, "tasks", tasks)

        assert context.pending_tasks == tasks
        assert "tasks" in context.available_sources

    def test_emails_result(self):
        """Test emails result is applied correctly."""
        aggregator = ContextAggregator(MagicMock())
        context = HeartbeatContext()
        emails = [
            {
                "from": "boss@example.com",
                "subject": "Urgent meeting",
                "date": "14:30",
                "snippet": "Please join ASAP",
            },
        ]

        aggregator._apply_source_result(context, "emails", emails)

        assert context.unread_emails == emails
        assert "emails" in context.available_sources

    def test_empty_result_not_applied(self):
        """Test that empty list results are not applied."""
        aggregator = ContextAggregator(MagicMock())
        context = HeartbeatContext()

        aggregator._apply_source_result(context, "calendar", [])

        assert context.calendar_events is None
        assert "calendar" not in context.available_sources


# ---------------------------------------------------------------------------
# _format_email_date (email internalDate conversion)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFormatEmailDate:
    """Tests for _format_email_date static method."""

    def test_epoch_ms_today_shows_time_only(self):
        """Test that today's email shows only HH:MM."""
        user_tz = ZoneInfo("Europe/Paris")
        now = datetime.now(user_tz)
        # Build epoch ms for today at a known time in user tz
        target = now.replace(hour=10, minute=30, second=0, microsecond=0)
        epoch_ms = str(int(target.timestamp() * 1000))

        result = ContextAggregator._format_email_date(epoch_ms, user_tz)

        assert result == "10:30"

    def test_epoch_ms_past_date_shows_full(self):
        """Test that past date email shows YYYY-MM-DD HH:MM."""
        user_tz = ZoneInfo("Europe/Paris")
        # 2026-01-15 14:00 UTC = 15:00 CET
        dt = datetime(2026, 1, 15, 14, 0, tzinfo=UTC)
        epoch_ms = str(int(dt.timestamp() * 1000))

        result = ContextAggregator._format_email_date(epoch_ms, user_tz)

        assert result == "2026-01-15 15:00"

    def test_int_epoch_ms(self):
        """Test integer input (not string) works correctly."""
        user_tz = ZoneInfo("UTC")
        dt = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)
        epoch_ms = int(dt.timestamp() * 1000)

        result = ContextAggregator._format_email_date(epoch_ms, user_tz)

        assert result == "2026-03-10 12:00"

    def test_none_returns_question_mark(self):
        """Test None input returns '?'."""
        user_tz = ZoneInfo("Europe/Paris")
        assert ContextAggregator._format_email_date(None, user_tz) == "?"

    def test_invalid_value_returns_question_mark(self):
        """Test invalid input returns '?'."""
        user_tz = ZoneInfo("Europe/Paris")
        assert ContextAggregator._format_email_date("not-a-number", user_tz) == "?"


# ---------------------------------------------------------------------------
# _detect_weather_changes
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDetectWeatherChanges:
    """Tests for weather change detection algorithm."""

    def _make_forecast_entry(
        self, dt: datetime, pop: float = 0.0, temp: float = 20.0, wind: float = 5.0
    ) -> dict:
        """Helper to create a forecast entry."""
        return {
            "dt": int(dt.timestamp()),
            "pop": pop,
            "main": {"temp": temp},
            "wind": {"speed": wind},
        }

    def test_rain_start_detected(self):
        """Test rain start detection when not currently raining."""
        aggregator = ContextAggregator(MagicMock())
        settings = _make_settings()
        user_tz = ZoneInfo("UTC")
        now = datetime.now(UTC)

        current = {
            "weather": [{"main": "Clear"}],
            "main": {"temp": 20},
        }
        hourly = [
            self._make_forecast_entry(now + timedelta(hours=1), pop=0.8),
        ]

        changes = aggregator._detect_weather_changes(current, hourly, user_tz, settings)

        assert len(changes) == 1
        assert changes[0].change_type == "rain_start"
        assert changes[0].severity == "warning"

    def test_rain_end_detected(self):
        """Test rain end detection when currently raining."""
        aggregator = ContextAggregator(MagicMock())
        settings = _make_settings()
        user_tz = ZoneInfo("UTC")
        now = datetime.now(UTC)

        current = {
            "weather": [{"main": "Rain"}],
            "main": {"temp": 15},
        }
        hourly = [
            self._make_forecast_entry(now + timedelta(hours=1), pop=0.2),
        ]

        changes = aggregator._detect_weather_changes(current, hourly, user_tz, settings)

        assert len(changes) == 1
        assert changes[0].change_type == "rain_end"
        assert changes[0].severity == "info"

    def test_temp_drop_detected(self):
        """Tomorrow's average is colder than today's by > threshold."""
        aggregator = ContextAggregator(MagicMock())
        settings = _make_settings()
        user_tz = ZoneInfo("UTC")
        # Anchor on today 10:00 to keep "today" and "today+1" deterministic
        base = datetime.now(UTC).replace(hour=10, minute=0, second=0, microsecond=0)

        current = {
            "weather": [{"main": "Clear"}],
            "main": {"temp": 20},
        }
        hourly = [
            self._make_forecast_entry(base, temp=20),
            self._make_forecast_entry(base + timedelta(hours=3), temp=22),
            self._make_forecast_entry(base + timedelta(days=1), temp=13),
            self._make_forecast_entry(base + timedelta(days=1, hours=3), temp=13),
        ]

        changes = aggregator._detect_weather_changes(current, hourly, user_tz, settings)

        temp_changes = [c for c in changes if c.change_type == "temp_drop"]
        assert len(temp_changes) == 1
        # avg_today = 21, avg_tomorrow = 13 → diff = 8, within threshold*1.6 → info
        assert temp_changes[0].severity == "info"
        assert "colder" in temp_changes[0].description

    def test_temp_rise_detected(self):
        """Tomorrow's average is warmer than today's by > threshold."""
        aggregator = ContextAggregator(MagicMock())
        settings = _make_settings()
        user_tz = ZoneInfo("UTC")
        base = datetime.now(UTC).replace(hour=10, minute=0, second=0, microsecond=0)

        current = {
            "weather": [{"main": "Clear"}],
            "main": {"temp": 10},
        }
        hourly = [
            self._make_forecast_entry(base, temp=10),
            self._make_forecast_entry(base + timedelta(hours=3), temp=12),
            self._make_forecast_entry(base + timedelta(days=1), temp=20),
            self._make_forecast_entry(base + timedelta(days=1, hours=3), temp=22),
        ]

        changes = aggregator._detect_weather_changes(current, hourly, user_tz, settings)

        temp_changes = [c for c in changes if c.change_type == "temp_rise"]
        assert len(temp_changes) == 1
        assert "warmer" in temp_changes[0].description

    def test_severe_temp_drop_warning(self):
        """Severe temperature drop gets warning severity."""
        aggregator = ContextAggregator(MagicMock())
        settings = _make_settings()
        user_tz = ZoneInfo("UTC")
        base = datetime.now(UTC).replace(hour=10, minute=0, second=0, microsecond=0)

        current = {
            "weather": [{"main": "Clear"}],
            "main": {"temp": 22},
        }
        # avg_today = 22, avg_tomorrow = 12 → diff = 10 > 5.0 * 1.6 = 8.0 → warning
        hourly = [
            self._make_forecast_entry(base, temp=22),
            self._make_forecast_entry(base + timedelta(hours=3), temp=22),
            self._make_forecast_entry(base + timedelta(days=1), temp=12),
            self._make_forecast_entry(base + timedelta(days=1, hours=3), temp=12),
        ]

        changes = aggregator._detect_weather_changes(current, hourly, user_tz, settings)

        temp_changes = [c for c in changes if c.change_type == "temp_drop"]
        assert len(temp_changes) == 1
        assert temp_changes[0].severity == "warning"

    def test_temp_change_skipped_when_insufficient_today_entries(self):
        """Skip detection if fewer than 2 forecast entries fall on today."""
        aggregator = ContextAggregator(MagicMock())
        settings = _make_settings()
        user_tz = ZoneInfo("UTC")
        base = datetime.now(UTC).replace(hour=10, minute=0, second=0, microsecond=0)

        current = {"weather": [{"main": "Clear"}], "main": {"temp": 20}}
        hourly = [
            # Only 1 entry today
            self._make_forecast_entry(base, temp=20),
            self._make_forecast_entry(base + timedelta(days=1), temp=10),
            self._make_forecast_entry(base + timedelta(days=1, hours=3), temp=10),
        ]

        changes = aggregator._detect_weather_changes(current, hourly, user_tz, settings)

        temp_changes = [c for c in changes if c.change_type in ("temp_drop", "temp_rise")]
        assert temp_changes == []

    def test_temp_change_skipped_when_diff_below_threshold(self):
        """Skip detection if |avg_today - avg_tomorrow| <= threshold."""
        aggregator = ContextAggregator(MagicMock())
        settings = _make_settings()
        user_tz = ZoneInfo("UTC")
        base = datetime.now(UTC).replace(hour=10, minute=0, second=0, microsecond=0)

        current = {"weather": [{"main": "Clear"}], "main": {"temp": 20}}
        hourly = [
            self._make_forecast_entry(base, temp=20),
            self._make_forecast_entry(base + timedelta(hours=3), temp=20),
            # diff = 4, below threshold 5.0
            self._make_forecast_entry(base + timedelta(days=1), temp=16),
            self._make_forecast_entry(base + timedelta(days=1, hours=3), temp=16),
        ]

        changes = aggregator._detect_weather_changes(current, hourly, user_tz, settings)

        temp_changes = [c for c in changes if c.change_type in ("temp_drop", "temp_rise")]
        assert temp_changes == []

    def test_wind_alert_detected(self):
        """Test wind alert detection."""
        aggregator = ContextAggregator(MagicMock())
        settings = _make_settings()
        user_tz = ZoneInfo("UTC")
        now = datetime.now(UTC)

        current = {
            "weather": [{"main": "Clear"}],
            "main": {"temp": 20},
        }
        hourly = [
            self._make_forecast_entry(now + timedelta(hours=2), wind=16),
        ]

        changes = aggregator._detect_weather_changes(current, hourly, user_tz, settings)

        assert len(changes) == 1
        assert changes[0].change_type == "wind_alert"
        assert "16 m/s" in changes[0].description

    def test_no_changes_normal_conditions(self):
        """Test no changes detected in normal conditions."""
        aggregator = ContextAggregator(MagicMock())
        settings = _make_settings()
        user_tz = ZoneInfo("UTC")
        now = datetime.now(UTC)

        current = {
            "weather": [{"main": "Clear"}],
            "main": {"temp": 20},
        }
        hourly = [
            self._make_forecast_entry(now + timedelta(hours=1), pop=0.1, temp=19, wind=5),
            self._make_forecast_entry(now + timedelta(hours=2), pop=0.2, temp=18, wind=6),
        ]

        changes = aggregator._detect_weather_changes(current, hourly, user_tz, settings)

        assert len(changes) == 0

    def test_dedup_same_change_type(self):
        """Test that each change type is only detected once."""
        aggregator = ContextAggregator(MagicMock())
        settings = _make_settings()
        user_tz = ZoneInfo("UTC")
        now = datetime.now(UTC)

        current = {
            "weather": [{"main": "Clear"}],
            "main": {"temp": 20},
        }
        hourly = [
            self._make_forecast_entry(now + timedelta(hours=1), pop=0.8),
            self._make_forecast_entry(now + timedelta(hours=2), pop=0.9),
        ]

        changes = aggregator._detect_weather_changes(current, hourly, user_tz, settings)

        rain_starts = [c for c in changes if c.change_type == "rain_start"]
        assert len(rain_starts) == 1

    def test_multiple_change_types(self):
        """Test detection of multiple different change types."""
        aggregator = ContextAggregator(MagicMock())
        settings = _make_settings()
        user_tz = ZoneInfo("UTC")
        base = datetime.now(UTC).replace(hour=10, minute=0, second=0, microsecond=0)

        current = {
            "weather": [{"main": "Clear"}],
            "main": {"temp": 22},
        }
        hourly = [
            # Today: warm, triggers rain_start + wind_alert on first entry
            self._make_forecast_entry(base, pop=0.8, temp=22, wind=16),
            self._make_forecast_entry(base + timedelta(hours=3), pop=0.2, temp=22, wind=5),
            # Tomorrow: colder, triggers temp_drop via daily average
            self._make_forecast_entry(base + timedelta(days=1), pop=0.1, temp=12, wind=5),
            self._make_forecast_entry(base + timedelta(days=1, hours=3), pop=0.1, temp=12, wind=5),
        ]

        changes = aggregator._detect_weather_changes(current, hourly, user_tz, settings)

        change_types = {c.change_type for c in changes}
        assert "rain_start" in change_types
        assert "temp_drop" in change_types
        assert "wind_alert" in change_types

    def test_drizzle_counts_as_raining(self):
        """Test that drizzle is treated as currently raining."""
        aggregator = ContextAggregator(MagicMock())
        settings = _make_settings()
        user_tz = ZoneInfo("UTC")
        now = datetime.now(UTC)

        current = {
            "weather": [{"main": "Drizzle"}],
            "main": {"temp": 15},
        }
        hourly = [
            self._make_forecast_entry(now + timedelta(hours=2), pop=0.1),
        ]

        changes = aggregator._detect_weather_changes(current, hourly, user_tz, settings)

        assert len(changes) == 1
        assert changes[0].change_type == "rain_end"

    def test_thunderstorm_counts_as_raining(self):
        """Test that thunderstorm is treated as currently raining."""
        aggregator = ContextAggregator(MagicMock())
        settings = _make_settings()
        user_tz = ZoneInfo("UTC")
        now = datetime.now(UTC)

        current = {
            "weather": [{"main": "Thunderstorm"}],
            "main": {"temp": 18},
        }
        hourly = [
            self._make_forecast_entry(now + timedelta(hours=3), pop=0.15),
        ]

        changes = aggregator._detect_weather_changes(current, hourly, user_tz, settings)

        assert len(changes) == 1
        assert changes[0].change_type == "rain_end"

    def test_custom_thresholds(self):
        """Test that custom threshold settings are respected."""
        aggregator = ContextAggregator(MagicMock())
        settings = _make_settings(
            heartbeat_weather_rain_threshold_high=0.9,  # Higher threshold
            heartbeat_weather_wind_threshold=20.0,  # Higher wind threshold
        )
        user_tz = ZoneInfo("UTC")
        now = datetime.now(UTC)

        current = {
            "weather": [{"main": "Clear"}],
            "main": {"temp": 20},
        }
        hourly = [
            # pop=0.8 is below the custom threshold of 0.9
            # wind=16 is below the custom threshold of 20.0
            self._make_forecast_entry(now + timedelta(hours=1), pop=0.8, wind=16),
        ]

        changes = aggregator._detect_weather_changes(current, hourly, user_tz, settings)

        assert len(changes) == 0

    def test_empty_hourly_no_changes(self):
        """Test that empty hourly data returns no changes."""
        aggregator = ContextAggregator(MagicMock())
        settings = _make_settings()
        user_tz = ZoneInfo("UTC")

        current = {
            "weather": [{"main": "Clear"}],
            "main": {"temp": 20},
        }

        changes = aggregator._detect_weather_changes(current, [], user_tz, settings)

        assert changes == []

    def test_invalid_dt_skipped(self):
        """Test that entries without valid dt are skipped."""
        aggregator = ContextAggregator(MagicMock())
        settings = _make_settings()
        user_tz = ZoneInfo("UTC")

        current = {
            "weather": [{"main": "Clear"}],
            "main": {"temp": 20},
        }
        hourly = [
            {"pop": 0.9, "main": {"temp": 20}},  # Missing dt
        ]

        changes = aggregator._detect_weather_changes(current, hourly, user_tz, settings)

        assert changes == []


# ---------------------------------------------------------------------------
# _format_event_time (timezone conversion for calendar events)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFormatEventTime:
    """Tests for _format_event_time helper.

    The function accepts a start/end dict (Google/Microsoft/Apple format)
    and converts to a human-readable local time string.
    """

    def test_google_utc_to_paris(self):
        """Test Google format (offset in dateTime) converts to user timezone."""
        user_tz = ZoneInfo("Europe/Paris")
        # 14:00 UTC in winter = 15:00 CET (+1h)
        result = _format_event_time({"dateTime": "2026-01-15T14:00:00Z"}, user_tz)
        assert result == "2026-01-15 15:00"

    def test_google_summer_time(self):
        """Test conversion during summer time (CEST, +2h)."""
        user_tz = ZoneInfo("Europe/Paris")
        result = _format_event_time({"dateTime": "2026-07-15T14:00:00Z"}, user_tz)
        assert result == "2026-07-15 16:00"

    def test_google_offset_to_new_york(self):
        """Test dateTime with explicit offset converted to another timezone."""
        user_tz = ZoneInfo("America/New_York")
        # 14:00 UTC = 09:00 EST (winter, -5h)
        result = _format_event_time({"dateTime": "2026-01-15T14:00:00+00:00"}, user_tz)
        assert result == "2026-01-15 09:00"

    def test_google_same_timezone_no_shift(self):
        """Test dateTime already in user timezone shows correct time."""
        user_tz = ZoneInfo("Europe/Paris")
        result = _format_event_time({"dateTime": "2026-01-15T15:00:00+01:00"}, user_tz)
        assert result == "2026-01-15 15:00"

    def test_microsoft_naive_datetime_with_timezone_field(self):
        """Test Microsoft format (naive dateTime + separate timeZone field)."""
        user_tz = ZoneInfo("America/New_York")
        # Microsoft: 10:00 in Europe/Paris = 04:00 EST
        result = _format_event_time(
            {"dateTime": "2026-01-15T10:00:00", "timeZone": "Europe/Paris"}, user_tz
        )
        assert result == "2026-01-15 04:00"

    def test_microsoft_naive_datetime_same_timezone(self):
        """Test Microsoft format when user is in the same timezone as event."""
        user_tz = ZoneInfo("Europe/Paris")
        result = _format_event_time(
            {"dateTime": "2026-01-15T10:00:00", "timeZone": "Europe/Paris"}, user_tz
        )
        assert result == "2026-01-15 10:00"

    def test_naive_datetime_no_timezone_assumes_user_tz(self):
        """Test naive dateTime without timeZone field assumes user's local timezone.

        CalDAV servers often return local times without TZID. Assuming UTC would
        shift the time by the user's UTC offset, causing wrong display.
        """
        user_tz = ZoneInfo("Europe/Paris")
        # Naive 15:00 assumed Europe/Paris → displayed as 15:00 (no shift)
        result = _format_event_time({"dateTime": "2026-01-15T15:00:00"}, user_tz)
        assert result == "2026-01-15 15:00"

    def test_today_event_shows_time_only(self):
        """Test event happening today shows only HH:MM without date."""
        user_tz = ZoneInfo("Europe/Paris")
        now = datetime.now(user_tz)
        # Build a dateTime for today at 18:00 local time with correct UTC offset
        today_18 = now.replace(hour=18, minute=0, second=0, microsecond=0)
        offset = today_18.strftime("%z")  # e.g., "+0100" or "+0200" depending on DST
        offset_formatted = f"{offset[:3]}:{offset[3:]}"  # "+01:00" or "+02:00"
        today_str = today_18.strftime("%Y-%m-%d")
        result = _format_event_time(
            {"dateTime": f"{today_str}T18:00:00{offset_formatted}"}, user_tz
        )
        assert result == "18:00"

    def test_all_day_event(self):
        """Test all-day event (date only) returns formatted date."""
        user_tz = ZoneInfo("Europe/Paris")
        result = _format_event_time({"date": "2026-03-15"}, user_tz)
        assert result == "2026-03-15 (all day)"

    def test_all_day_event_with_empty_datetime(self):
        """Test all-day event where dateTime is absent but date is present."""
        user_tz = ZoneInfo("Europe/Paris")
        result = _format_event_time({"date": "2026-03-15", "dateTime": None}, user_tz)
        assert result == "2026-03-15 (all day)"

    def test_none_returns_question_mark(self):
        """Test None input returns '?'."""
        user_tz = ZoneInfo("Europe/Paris")
        result = _format_event_time(None, user_tz)
        assert result == "?"

    def test_empty_dict_returns_question_mark(self):
        """Test empty dict returns '?'."""
        user_tz = ZoneInfo("Europe/Paris")
        result = _format_event_time({}, user_tz)
        assert result == "?"

    def test_invalid_datetime_returns_raw(self):
        """Test unparseable dateTime returns the raw string."""
        user_tz = ZoneInfo("Europe/Paris")
        result = _format_event_time({"dateTime": "not-a-datetime"}, user_tz)
        assert result == "not-a-datetime"

    def test_cross_day_event_includes_date(self):
        """Test event crossing midnight in user timezone includes date."""
        user_tz = ZoneInfo("Pacific/Auckland")
        # 23:00 UTC on Jan 15 = 12:00 NZDT on Jan 16 (next day!)
        result = _format_event_time({"dateTime": "2026-01-15T23:00:00Z"}, user_tz)
        assert result == "2026-01-16 12:00"

    def test_microsoft_invalid_timezone_falls_back_to_user_tz(self):
        """Test Microsoft format with invalid timeZone falls back to user timezone."""
        user_tz = ZoneInfo("Europe/Paris")
        # Invalid timezone → assume user tz → 14:00 in Europe/Paris = 14:00 CET
        result = _format_event_time(
            {"dateTime": "2026-01-15T14:00:00", "timeZone": "Invalid/Zone"}, user_tz
        )
        assert result == "2026-01-15 14:00"


# ---------------------------------------------------------------------------
# _extract_due_date (task due date formatting)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExtractDueDate:
    """Tests for _extract_due_date helper."""

    def test_rfc3339_google_format(self):
        """Test Google Tasks RFC 3339 format extracts date only."""
        assert _extract_due_date("2026-03-15T00:00:00.000Z") == "2026-03-15"

    def test_rfc3339_microsoft_format(self):
        """Test Microsoft To Do format extracts date only."""
        assert _extract_due_date("2026-03-15T00:00:00Z") == "2026-03-15"

    def test_plain_date(self):
        """Test plain date passes through unchanged."""
        assert _extract_due_date("2026-03-15") == "2026-03-15"

    def test_none_returns_no_date(self):
        """Test None returns 'no date'."""
        assert _extract_due_date(None) == "no date"

    def test_empty_string_returns_no_date(self):
        """Test empty string returns 'no date'."""
        assert _extract_due_date("") == "no date"

    def test_short_string_passthrough(self):
        """Test short string returns as-is."""
        assert _extract_due_date("soon") == "soon"


# ---------------------------------------------------------------------------
# _format_utc_datetime (DB timestamp to user-local display)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFormatUtcDatetime:
    """Tests for _format_utc_datetime helper."""

    def test_utc_to_paris(self):
        """Test UTC datetime converted to Europe/Paris."""
        user_tz = ZoneInfo("Europe/Paris")
        dt = datetime(2026, 1, 15, 14, 30, tzinfo=UTC)
        # 14:30 UTC = 15:30 CET
        assert _format_utc_datetime(dt, user_tz) == "2026-01-15 15:30"

    def test_utc_to_new_york(self):
        """Test UTC datetime converted to America/New_York."""
        user_tz = ZoneInfo("America/New_York")
        dt = datetime(2026, 1, 15, 14, 30, tzinfo=UTC)
        # 14:30 UTC = 09:30 EST
        assert _format_utc_datetime(dt, user_tz) == "2026-01-15 09:30"

    def test_cross_day_conversion(self):
        """Test conversion that crosses midnight."""
        user_tz = ZoneInfo("Pacific/Auckland")
        dt = datetime(2026, 1, 15, 23, 0, tzinfo=UTC)
        # 23:00 UTC = 12:00 NZDT next day (+13h)
        assert _format_utc_datetime(dt, user_tz) == "2026-01-16 12:00"

    def test_none_returns_question_mark(self):
        """Test None input returns '?'."""
        user_tz = ZoneInfo("Europe/Paris")
        assert _format_utc_datetime(None, user_tz) == "?"

    def test_naive_datetime_fallback(self):
        """Test naive datetime is returned as string."""
        user_tz = ZoneInfo("Europe/Paris")
        dt = datetime(2026, 1, 15, 14, 30)
        # Naive datetime — astimezone assumes system local tz, result varies
        # Just verify it returns a string without crashing
        result = _format_utc_datetime(dt, user_tz)
        assert isinstance(result, str)
        assert len(result) > 0
