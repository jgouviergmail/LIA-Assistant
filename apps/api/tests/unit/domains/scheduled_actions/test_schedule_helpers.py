"""
Unit tests for schedule_helpers.

Tests compute_next_trigger_utc, validate_days_of_week, format_schedule_display.
"""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from src.domains.scheduled_actions.schedule_helpers import (
    compute_next_trigger_utc,
    format_schedule_display,
    validate_days_of_week,
)


class TestComputeNextTriggerUtc:
    """Tests for compute_next_trigger_utc."""

    def test_basic_next_trigger(self) -> None:
        """Should return a future UTC datetime."""
        result = compute_next_trigger_utc(
            days_of_week=[1, 3, 5],  # Mon, Wed, Fri
            hour=19,
            minute=30,
            user_timezone="Europe/Paris",
        )
        assert result is not None
        assert result.tzinfo is not None
        assert result > datetime.now(UTC)

    def test_every_day(self) -> None:
        """Should handle all 7 days."""
        result = compute_next_trigger_utc(
            days_of_week=[1, 2, 3, 4, 5, 6, 7],
            hour=8,
            minute=0,
            user_timezone="Europe/Paris",
        )
        assert result is not None

    def test_single_day(self) -> None:
        """Should handle a single day."""
        result = compute_next_trigger_utc(
            days_of_week=[6],  # Saturday only
            hour=10,
            minute=0,
            user_timezone="America/New_York",
        )
        assert result is not None
        # Should land on a Saturday
        local_result = result.astimezone(ZoneInfo("America/New_York"))
        assert local_result.isoweekday() == 6

    def test_different_timezone(self) -> None:
        """Different timezones should produce different UTC times for the same local time."""
        paris = compute_next_trigger_utc(
            days_of_week=[1, 2, 3, 4, 5, 6, 7],
            hour=12,
            minute=0,
            user_timezone="Europe/Paris",
        )
        tokyo = compute_next_trigger_utc(
            days_of_week=[1, 2, 3, 4, 5, 6, 7],
            hour=12,
            minute=0,
            user_timezone="Asia/Tokyo",
        )
        # Same local time but different UTC offsets
        assert paris != tokyo

    def test_with_reference_after(self) -> None:
        """Should compute next trigger after the given reference time."""
        reference = datetime(2026, 1, 5, 12, 0, 0, tzinfo=UTC)  # Monday noon UTC
        result = compute_next_trigger_utc(
            days_of_week=[1],  # Monday
            hour=19,
            minute=30,
            user_timezone="Europe/Paris",
            after=reference,
        )
        assert result > reference

    def test_midnight_boundary(self) -> None:
        """Should handle midnight correctly."""
        result = compute_next_trigger_utc(
            days_of_week=[1, 2, 3, 4, 5],
            hour=0,
            minute=0,
            user_timezone="Europe/Paris",
        )
        assert result is not None

    def test_end_of_day(self) -> None:
        """Should handle 23:59 correctly."""
        result = compute_next_trigger_utc(
            days_of_week=[1],
            hour=23,
            minute=59,
            user_timezone="Europe/Paris",
        )
        assert result is not None

    def test_returns_utc_timezone(self) -> None:
        """Must return datetime in UTC, not in user timezone."""
        result = compute_next_trigger_utc(
            days_of_week=[1, 2, 3, 4, 5, 6, 7],
            hour=12,
            minute=0,
            user_timezone="Europe/Paris",
        )
        # Verify the tzinfo is UTC, not Europe/Paris
        assert result.tzinfo == UTC

    def test_utc_offset_is_correct(self) -> None:
        """19:30 Paris (CET, UTC+1) should be stored as 18:30 UTC in winter."""
        # Use a known Monday in January (winter, CET = UTC+1)
        reference = datetime(2026, 1, 5, 10, 0, 0, tzinfo=UTC)  # Monday 10:00 UTC
        result = compute_next_trigger_utc(
            days_of_week=[1],  # Monday
            hour=19,
            minute=30,
            user_timezone="Europe/Paris",
            after=reference,
        )
        # 19:30 Paris = 18:30 UTC (CET is UTC+1 in winter)
        assert result.hour == 18
        assert result.minute == 30
        assert result.tzinfo == UTC


class TestValidateDaysOfWeek:
    """Tests for validate_days_of_week."""

    def test_valid_single_day(self) -> None:
        assert validate_days_of_week([1]) is True

    def test_valid_all_days(self) -> None:
        assert validate_days_of_week([1, 2, 3, 4, 5, 6, 7]) is True

    def test_valid_weekdays(self) -> None:
        assert validate_days_of_week([1, 2, 3, 4, 5]) is True

    def test_empty_list(self) -> None:
        assert validate_days_of_week([]) is False

    def test_invalid_day_zero(self) -> None:
        assert validate_days_of_week([0]) is False

    def test_invalid_day_eight(self) -> None:
        assert validate_days_of_week([8]) is False

    def test_duplicates(self) -> None:
        assert validate_days_of_week([1, 1, 2]) is False

    def test_mixed_valid_invalid(self) -> None:
        assert validate_days_of_week([1, 8]) is False


class TestFormatScheduleDisplay:
    """Tests for format_schedule_display."""

    def test_french_specific_days(self) -> None:
        result = format_schedule_display([1, 3, 5], 19, 30, "fr")
        assert result == "Lun, Mer, Ven à 19:30"

    def test_english_specific_days(self) -> None:
        result = format_schedule_display([1, 3, 5], 19, 30, "en")
        assert result == "Mon, Wed, Fri at 19:30"

    def test_french_every_day(self) -> None:
        result = format_schedule_display([1, 2, 3, 4, 5, 6, 7], 8, 0, "fr")
        assert result == "Tous les jours à 08:00"

    def test_english_every_day(self) -> None:
        result = format_schedule_display([1, 2, 3, 4, 5, 6, 7], 8, 0, "en")
        assert result == "Every day at 08:00"

    def test_french_weekdays(self) -> None:
        result = format_schedule_display([1, 2, 3, 4, 5], 9, 0, "fr")
        assert result == "Lun-Ven à 09:00"

    def test_english_weekdays(self) -> None:
        result = format_schedule_display([1, 2, 3, 4, 5], 9, 0, "en")
        assert result == "Mon-Fri at 09:00"

    def test_french_weekend(self) -> None:
        result = format_schedule_display([6, 7], 10, 30, "fr")
        assert result == "Sam-Dim à 10:30"

    def test_single_day(self) -> None:
        result = format_schedule_display([3], 14, 0, "fr")
        assert result == "Mer à 14:00"

    def test_time_zero_padded(self) -> None:
        result = format_schedule_display([1], 0, 5, "fr")
        assert result == "Lun à 00:05"

    def test_unsorted_days_are_sorted(self) -> None:
        result = format_schedule_display([5, 1, 3], 12, 0, "en")
        assert result == "Mon, Wed, Fri at 12:00"
