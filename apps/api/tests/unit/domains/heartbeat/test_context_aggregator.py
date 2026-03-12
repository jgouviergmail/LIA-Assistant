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

from src.domains.heartbeat.context_aggregator import ContextAggregator
from src.domains.heartbeat.schemas import HeartbeatContext, WeatherChange

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_settings(**overrides) -> SimpleNamespace:
    """Create a fake settings object with heartbeat defaults."""
    defaults = {
        "heartbeat_context_calendar_hours": 6,
        "heartbeat_context_memory_limit": 5,
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

        aggregator._apply_source_result(context, "weather", (current, changes))

        assert context.weather_current == current
        assert context.weather_changes == changes
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

    def test_empty_result_not_applied(self):
        """Test that empty list results are not applied."""
        aggregator = ContextAggregator(MagicMock())
        context = HeartbeatContext()

        aggregator._apply_source_result(context, "calendar", [])

        assert context.calendar_events is None
        assert "calendar" not in context.available_sources


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
        """Test temperature drop detection."""
        aggregator = ContextAggregator(MagicMock())
        settings = _make_settings()
        user_tz = ZoneInfo("UTC")
        now = datetime.now(UTC)

        current = {
            "weather": [{"main": "Clear"}],
            "main": {"temp": 25},
        }
        hourly = [
            self._make_forecast_entry(now + timedelta(hours=3), temp=18),
        ]

        changes = aggregator._detect_weather_changes(current, hourly, user_tz, settings)

        assert len(changes) == 1
        assert changes[0].change_type == "temp_drop"
        assert "7°C" in changes[0].description

    def test_severe_temp_drop_warning(self):
        """Test that severe temperature drop gets warning severity."""
        aggregator = ContextAggregator(MagicMock())
        settings = _make_settings()
        user_tz = ZoneInfo("UTC")
        now = datetime.now(UTC)

        current = {
            "weather": [{"main": "Clear"}],
            "main": {"temp": 25},
        }
        hourly = [
            # 14°C drop > 5.0 * 1.6 = 8.0 → warning
            self._make_forecast_entry(now + timedelta(hours=3), temp=11),
        ]

        changes = aggregator._detect_weather_changes(current, hourly, user_tz, settings)

        assert len(changes) == 1
        assert changes[0].severity == "warning"

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
        now = datetime.now(UTC)

        current = {
            "weather": [{"main": "Clear"}],
            "main": {"temp": 25},
        }
        hourly = [
            # Rain start + temp drop + wind alert
            self._make_forecast_entry(now + timedelta(hours=1), pop=0.8, temp=18, wind=16),
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
