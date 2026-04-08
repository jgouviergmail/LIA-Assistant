"""
Unit tests for weather_tools.py date parsing functionality.

Tests the _parse_date_offset function which handles:
- Temporal references (today, demain, tomorrow)
- ISO date format (2026-01-22)
- ISO datetime format from calendar events (2026-01-22T14:00:00+01:00)
- Relative patterns (in X days, dans X jours)

Note: _parse_date_offset is a legacy wrapper around _calculate_target_date.
Both functions use user_timezone (default: "UTC") to determine "today".
Tests use a fixed timezone to ensure consistent behavior across environments.
"""

from datetime import UTC, date, datetime, timedelta

# Use a fixed timezone for tests to ensure consistent results
# Tests should NOT depend on the machine's local timezone
TEST_TIMEZONE = "UTC"


def _get_test_today() -> date:
    """Get today's date in the test timezone (UTC)."""
    return datetime.now(UTC).date()


class TestParseDateOffsetTemporalReferences:
    """Tests for temporal reference parsing (today, tomorrow, etc.)."""

    def test_none_returns_zero(self):
        """Test that None input returns offset 0 (today)."""
        from src.domains.agents.tools.weather_tools import _parse_date_offset

        assert _parse_date_offset(None) == 0

    def test_empty_string_returns_zero(self):
        """Test that empty string returns offset 0."""
        from src.domains.agents.tools.weather_tools import _parse_date_offset

        assert _parse_date_offset("") == 0
        assert _parse_date_offset("   ") == 0

    def test_today_references(self):
        """Test today references (English — post-semantic-pivot)."""
        from src.domains.agents.tools.weather_tools import _parse_date_offset

        today_refs = ["today", "now", "TODAY"]
        for ref in today_refs:
            assert _parse_date_offset(ref) == 0, f"Failed for '{ref}'"

    def test_tomorrow_references(self):
        """Test tomorrow references (English — post-semantic-pivot)."""
        from src.domains.agents.tools.weather_tools import _parse_date_offset

        tomorrow_refs = ["tomorrow", "Tomorrow", "TOMORROW"]
        for ref in tomorrow_refs:
            assert _parse_date_offset(ref) == 1, f"Failed for '{ref}'"

    def test_day_after_tomorrow_references(self):
        """Test day-after-tomorrow references (English — post-semantic-pivot)."""
        from src.domains.agents.tools.weather_tools import _parse_date_offset

        refs = ["after tomorrow", "day after tomorrow"]
        for ref in refs:
            assert _parse_date_offset(ref) == 2, f"Failed for '{ref}'"


class TestParseDateOffsetRelativePatterns:
    """Tests for relative day patterns (in X days, dans X jours)."""

    def test_in_x_days_english(self):
        """Test 'in X days' pattern."""
        from src.domains.agents.tools.weather_tools import _parse_date_offset

        assert _parse_date_offset("in 1 day") == 1
        assert _parse_date_offset("in 2 days") == 2
        assert _parse_date_offset("in 3 days") == 3
        assert _parse_date_offset("in 5 days") == 5

    def test_week_references_return_zero(self):
        """Test week references return 0 (show full week)."""
        from src.domains.agents.tools.weather_tools import _parse_date_offset

        week_refs = ["this week", "week"]
        for ref in week_refs:
            assert _parse_date_offset(ref) == 0, f"Failed for '{ref}'"


class TestParseDateOffsetIsoDate:
    """Tests for ISO date format (YYYY-MM-DD)."""

    def test_iso_date_today(self):
        """Test ISO date for today."""
        from src.domains.agents.tools.weather_tools import _parse_date_offset

        today = _get_test_today()
        iso_today = today.strftime("%Y-%m-%d")
        assert _parse_date_offset(iso_today, TEST_TIMEZONE) == 0

    def test_iso_date_tomorrow(self):
        """Test ISO date for tomorrow."""
        from src.domains.agents.tools.weather_tools import _parse_date_offset

        tomorrow = _get_test_today() + timedelta(days=1)
        iso_tomorrow = tomorrow.strftime("%Y-%m-%d")
        assert _parse_date_offset(iso_tomorrow, TEST_TIMEZONE) == 1

    def test_iso_date_five_days_ahead(self):
        """Test ISO date for 5 days ahead."""
        from src.domains.agents.tools.weather_tools import _parse_date_offset

        future = _get_test_today() + timedelta(days=5)
        iso_future = future.strftime("%Y-%m-%d")
        assert _parse_date_offset(iso_future, TEST_TIMEZONE) == 5

    def test_iso_date_past_returns_zero(self):
        """Test that past dates return 0 (can't request past weather)."""
        from src.domains.agents.tools.weather_tools import _parse_date_offset

        past = _get_test_today() - timedelta(days=5)
        iso_past = past.strftime("%Y-%m-%d")
        assert _parse_date_offset(iso_past, TEST_TIMEZONE) == 0


class TestParseDateOffsetIsoDatetime:
    """Tests for ISO datetime format from calendar events."""

    def test_iso_datetime_with_timezone_offset(self):
        """Test ISO datetime with timezone offset (calendar event format)."""
        from src.domains.agents.tools.weather_tools import _parse_date_offset

        tomorrow = _get_test_today() + timedelta(days=1)
        iso_datetime = f"{tomorrow.strftime('%Y-%m-%d')}T14:00:00+01:00"
        assert _parse_date_offset(iso_datetime, TEST_TIMEZONE) == 1

    def test_iso_datetime_with_z_suffix(self):
        """Test ISO datetime with Z suffix (UTC)."""
        from src.domains.agents.tools.weather_tools import _parse_date_offset

        in_3_days = _get_test_today() + timedelta(days=3)
        iso_datetime = f"{in_3_days.strftime('%Y-%m-%d')}T09:30:00Z"
        assert _parse_date_offset(iso_datetime, TEST_TIMEZONE) == 3

    def test_iso_datetime_with_milliseconds(self):
        """Test ISO datetime with milliseconds."""
        from src.domains.agents.tools.weather_tools import _parse_date_offset

        in_2_days = _get_test_today() + timedelta(days=2)
        iso_datetime = f"{in_2_days.strftime('%Y-%m-%d')}T15:45:30.123456+02:00"
        assert _parse_date_offset(iso_datetime, TEST_TIMEZONE) == 2

    def test_iso_datetime_extracts_date_only(self):
        """Test that datetime extracts date only (time is ignored)."""
        from src.domains.agents.tools.weather_tools import _parse_date_offset

        # Same day, different times should return same offset
        tomorrow = _get_test_today() + timedelta(days=1)
        morning = f"{tomorrow.strftime('%Y-%m-%d')}T08:00:00+01:00"
        evening = f"{tomorrow.strftime('%Y-%m-%d')}T20:00:00+01:00"

        assert (
            _parse_date_offset(morning, TEST_TIMEZONE)
            == _parse_date_offset(evening, TEST_TIMEZONE)
            == 1
        )

    def test_iso_datetime_negative_offset_timezone(self):
        """Test ISO datetime with negative timezone offset."""
        from src.domains.agents.tools.weather_tools import _parse_date_offset

        in_4_days = _get_test_today() + timedelta(days=4)
        iso_datetime = f"{in_4_days.strftime('%Y-%m-%d')}T10:00:00-05:00"
        assert _parse_date_offset(iso_datetime, TEST_TIMEZONE) == 4


class TestParseDateOffsetEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_whitespace_handling(self):
        """Test that whitespace is properly trimmed."""
        from src.domains.agents.tools.weather_tools import _parse_date_offset

        assert _parse_date_offset("  tomorrow  ", TEST_TIMEZONE) == 1
        assert _parse_date_offset("\ttomorrow\n", TEST_TIMEZONE) == 1

    def test_unknown_reference_returns_zero(self):
        """Test that unknown references default to 0."""
        from src.domains.agents.tools.weather_tools import _parse_date_offset

        assert _parse_date_offset("gibberish", TEST_TIMEZONE) == 0
        assert _parse_date_offset("next month", TEST_TIMEZONE) == 0
        assert _parse_date_offset("xyz123", TEST_TIMEZONE) == 0

    def test_far_future_date(self):
        """Test a date far in the future (beyond API limits)."""
        from src.domains.agents.tools.weather_tools import _parse_date_offset

        far_future = _get_test_today() + timedelta(days=30)
        iso_future = far_future.strftime("%Y-%m-%d")
        # Should return 30, even though API only supports 5 days
        # Limit enforcement is done at the tool execution level
        assert _parse_date_offset(iso_future, TEST_TIMEZONE) == 30
