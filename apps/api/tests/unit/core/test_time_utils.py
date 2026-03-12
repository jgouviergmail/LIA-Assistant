"""
Unit tests for time_utils.py helper functions.

Tests the centralized time formatting utilities:
- format_time_with_date_context: contextual time formatting (today/tomorrow/date)
- parse_datetime: robust datetime parsing
- convert_to_user_timezone: timezone conversion
- format_datetime_for_display: localized datetime formatting
- normalize_to_rfc3339: RFC 3339 normalization
- is_past/is_future: datetime comparison utilities
- Payload conversion utilities for Calendar, Email, Tasks, Drive, Weather
"""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from src.core.time_utils import (
    MAX_VALID_YEAR,
    MIN_VALID_YEAR,
    calculate_cache_age_seconds,
    convert_email_dates_in_payload,
    convert_event_dates_in_payload,
    convert_file_dates_in_payload,
    convert_task_dates_in_payload,
    convert_to_user_timezone,
    convert_weather_dates_in_payload,
    format_date_only,
    format_datetime_for_display,
    format_datetime_iso,
    format_time_only,
    get_current_datetime_context,
    is_future,
    is_past,
    normalize_to_rfc3339,
    now_in_timezone,
    now_utc,
    parse_datetime,
)


class TestFormatTimeWithDateContext:
    """Tests for format_time_with_date_context helper."""

    @pytest.fixture
    def paris_tz(self) -> ZoneInfo:
        """Paris timezone for tests."""
        return ZoneInfo("Europe/Paris")

    def test_same_day_returns_time_only(self, paris_tz: ZoneInfo) -> None:
        """Test that same day returns only HH:MM."""
        from src.core.time_utils import format_time_with_date_context

        reference = datetime(2026, 1, 20, 10, 0, tzinfo=paris_tz)
        target = datetime(2026, 1, 20, 14, 30, tzinfo=paris_tz)

        result = format_time_with_date_context(target, reference, "fr")

        assert result == "14:30"

    def test_tomorrow_french_returns_demain_prefix(self, paris_tz: ZoneInfo) -> None:
        """Test that tomorrow in French returns 'Demain HH:MM'."""
        from src.core.time_utils import format_time_with_date_context

        reference = datetime(2026, 1, 20, 10, 0, tzinfo=paris_tz)
        target = datetime(2026, 1, 21, 14, 30, tzinfo=paris_tz)

        result = format_time_with_date_context(target, reference, "fr")

        assert result == "Demain 14:30"

    def test_tomorrow_english_returns_tomorrow_prefix(self, paris_tz: ZoneInfo) -> None:
        """Test that tomorrow in English returns 'Tomorrow HH:MM'."""
        from src.core.time_utils import format_time_with_date_context

        reference = datetime(2026, 1, 20, 10, 0, tzinfo=paris_tz)
        target = datetime(2026, 1, 21, 14, 30, tzinfo=paris_tz)

        result = format_time_with_date_context(target, reference, "en")

        assert result == "Tomorrow 14:30"

    def test_other_date_french_returns_ddmm_format(self, paris_tz: ZoneInfo) -> None:
        """Test that other dates in French return 'dd/mm HH:MM' format."""
        from src.core.time_utils import format_time_with_date_context

        reference = datetime(2026, 1, 20, 10, 0, tzinfo=paris_tz)
        target = datetime(2026, 1, 25, 14, 30, tzinfo=paris_tz)

        result = format_time_with_date_context(target, reference, "fr")

        assert result == "25/01 14:30"

    def test_other_date_english_returns_mmdd_format(self, paris_tz: ZoneInfo) -> None:
        """Test that other dates in English return 'mm/dd HH:MM' format (US)."""
        from src.core.time_utils import format_time_with_date_context

        reference = datetime(2026, 1, 20, 10, 0, tzinfo=paris_tz)
        target = datetime(2026, 1, 25, 14, 30, tzinfo=paris_tz)

        result = format_time_with_date_context(target, reference, "en")

        assert result == "01/25 14:30"

    def test_no_reference_uses_current_time(self, paris_tz: ZoneInfo) -> None:
        """Test that None reference_dt uses current time."""
        from src.core.time_utils import format_time_with_date_context

        # Use a time far in the future (not today or tomorrow)
        target = datetime(2099, 12, 31, 23, 59, tzinfo=paris_tz)

        result = format_time_with_date_context(target, None, "fr")

        # Should include date since it's not today or tomorrow
        assert "31/12" in result
        assert "23:59" in result

    def test_spanish_uses_eu_format(self, paris_tz: ZoneInfo) -> None:
        """Test that Spanish uses EU date format (dd/mm)."""
        from src.core.time_utils import format_time_with_date_context

        reference = datetime(2026, 1, 20, 10, 0, tzinfo=paris_tz)
        target = datetime(2026, 1, 25, 14, 30, tzinfo=paris_tz)

        result = format_time_with_date_context(target, reference, "es")

        assert result == "25/01 14:30"

    def test_german_uses_eu_format(self, paris_tz: ZoneInfo) -> None:
        """Test that German uses EU date format (dd/mm)."""
        from src.core.time_utils import format_time_with_date_context

        reference = datetime(2026, 1, 20, 10, 0, tzinfo=paris_tz)
        target = datetime(2026, 1, 25, 14, 30, tzinfo=paris_tz)

        result = format_time_with_date_context(target, reference, "de")

        assert result == "25/01 14:30"

    def test_italian_uses_eu_format(self, paris_tz: ZoneInfo) -> None:
        """Test that Italian uses EU date format (dd/mm)."""
        from src.core.time_utils import format_time_with_date_context

        reference = datetime(2026, 1, 20, 10, 0, tzinfo=paris_tz)
        target = datetime(2026, 1, 25, 14, 30, tzinfo=paris_tz)

        result = format_time_with_date_context(target, reference, "it")

        assert result == "25/01 14:30"

    def test_chinese_uses_eu_format(self, paris_tz: ZoneInfo) -> None:
        """Test that Chinese uses EU date format (dd/mm)."""
        from src.core.time_utils import format_time_with_date_context

        reference = datetime(2026, 1, 20, 10, 0, tzinfo=paris_tz)
        target = datetime(2026, 1, 25, 14, 30, tzinfo=paris_tz)

        result = format_time_with_date_context(target, reference, "zh-CN")

        assert result == "25/01 14:30"

    def test_midnight_formats_correctly(self, paris_tz: ZoneInfo) -> None:
        """Test that midnight (00:00) formats correctly."""
        from src.core.time_utils import format_time_with_date_context

        reference = datetime(2026, 1, 20, 10, 0, tzinfo=paris_tz)
        target = datetime(2026, 1, 20, 0, 0, tzinfo=paris_tz)

        result = format_time_with_date_context(target, reference, "fr")

        assert result == "00:00"

    def test_end_of_day_formats_correctly(self, paris_tz: ZoneInfo) -> None:
        """Test that end of day (23:59) formats correctly."""
        from src.core.time_utils import format_time_with_date_context

        reference = datetime(2026, 1, 20, 10, 0, tzinfo=paris_tz)
        target = datetime(2026, 1, 21, 23, 59, tzinfo=paris_tz)

        result = format_time_with_date_context(target, reference, "fr")

        assert result == "Demain 23:59"


class TestParseDatetime:
    """Tests for parse_datetime helper."""

    def test_parse_iso8601_with_timezone(self) -> None:
        """Test parsing ISO 8601 with timezone."""
        from src.core.time_utils import parse_datetime

        result = parse_datetime("2026-01-20T14:30:00+01:00")

        assert result is not None
        assert result.hour == 14
        assert result.minute == 30

    def test_parse_iso8601_with_z_suffix(self) -> None:
        """Test parsing ISO 8601 with Z suffix."""
        from src.core.time_utils import parse_datetime

        result = parse_datetime("2026-01-20T14:30:00Z")

        assert result is not None
        assert result.hour == 14
        assert result.minute == 30

    def test_parse_none_returns_none(self) -> None:
        """Test that None input returns None."""
        from src.core.time_utils import parse_datetime

        result = parse_datetime(None)

        assert result is None

    def test_parse_datetime_object_returns_same(self) -> None:
        """Test that datetime input returns same object."""
        from datetime import UTC

        from src.core.time_utils import parse_datetime

        dt = datetime(2026, 1, 20, 14, 30, tzinfo=UTC)
        result = parse_datetime(dt)

        assert result is dt

    def test_parse_timestamp_milliseconds(self) -> None:
        """Test parsing Unix timestamp in milliseconds."""
        from src.core.time_utils import parse_datetime

        # 2026-01-20T14:30:00Z in milliseconds
        result = parse_datetime(1768933800000)

        assert result is not None
        assert result.year == 2026

    def test_parse_date_only(self) -> None:
        """Test parsing date-only format."""
        from src.core.time_utils import parse_datetime

        result = parse_datetime("2026-01-20")

        assert result is not None
        assert result.year == 2026
        assert result.month == 1
        assert result.day == 20
        assert result.hour == 0
        assert result.minute == 0

    def test_parse_invalid_returns_none(self) -> None:
        """Test that invalid input returns None."""
        from src.core.time_utils import parse_datetime

        result = parse_datetime("not a date")

        assert result is None

    def test_parse_rfc2822_format(self) -> None:
        """Test parsing RFC 2822 format (Gmail date header)."""
        from src.core.time_utils import parse_datetime

        result = parse_datetime("Sat, 03 Jan 2026 10:45:00 +0100")

        assert result is not None
        assert result.year == 2026
        assert result.month == 1
        assert result.day == 3

    def test_parse_timestamp_seconds(self) -> None:
        """Test parsing Unix timestamp in seconds."""
        from src.core.time_utils import parse_datetime

        # 2026-01-20T00:00:00Z in seconds
        result = parse_datetime(1768867200)

        assert result is not None
        assert result.year == 2026

    def test_parse_naive_datetime_adds_utc(self) -> None:
        """Test that naive datetime gets UTC timezone."""
        naive_dt = datetime(2026, 1, 20, 14, 30)
        result = parse_datetime(naive_dt)

        assert result is not None
        assert result.tzinfo == UTC

    def test_parse_string_timestamp_milliseconds(self) -> None:
        """Test parsing string timestamp in milliseconds."""
        result = parse_datetime("1768933800000")

        assert result is not None
        assert result.year == 2026

    def test_parse_string_timestamp_seconds(self) -> None:
        """Test parsing string timestamp in seconds."""
        result = parse_datetime("1768867200")

        assert result is not None
        assert result.year == 2026


@pytest.mark.unit
class TestConvertToUserTimezone:
    """Tests for convert_to_user_timezone helper."""

    def test_convert_utc_to_paris(self) -> None:
        """Test converting UTC to Europe/Paris."""
        # During winter, Paris is UTC+1
        result = convert_to_user_timezone("2025-12-02T13:00:00Z", "Europe/Paris")
        assert result is not None
        assert result.hour == 14  # UTC+1
        assert str(result.tzinfo) == "Europe/Paris"

    def test_convert_utc_to_new_york(self) -> None:
        """Test converting UTC to America/New_York."""
        # During winter, New York is UTC-5
        result = convert_to_user_timezone("2025-12-02T18:00:00Z", "America/New_York")
        assert result is not None
        assert result.hour == 13  # UTC-5
        assert str(result.tzinfo) == "America/New_York"

    def test_convert_utc_to_tokyo(self) -> None:
        """Test converting UTC to Asia/Tokyo."""
        # Tokyo is UTC+9
        result = convert_to_user_timezone("2025-12-02T10:00:00Z", "Asia/Tokyo")
        assert result is not None
        assert result.hour == 19  # UTC+9
        assert str(result.tzinfo) == "Asia/Tokyo"

    def test_convert_with_invalid_timezone_returns_original(self) -> None:
        """Test that invalid timezone returns original datetime."""
        result = convert_to_user_timezone("2025-12-02T14:30:00Z", "Invalid/Timezone")
        assert result is not None
        # Should return the parsed datetime even with invalid timezone

    def test_convert_none_returns_none(self) -> None:
        """Test that None input returns None."""
        assert convert_to_user_timezone(None, "Europe/Paris") is None

    def test_convert_timestamp_to_timezone(self) -> None:
        """Test converting Unix timestamp to user timezone."""
        timestamp_ms = 1733149800000
        result = convert_to_user_timezone(timestamp_ms, "Asia/Tokyo")
        assert result is not None
        assert str(result.tzinfo) == "Asia/Tokyo"

    def test_convert_datetime_object(self) -> None:
        """Test converting datetime object to user timezone."""
        dt = datetime(2025, 12, 2, 14, 30, tzinfo=UTC)
        result = convert_to_user_timezone(dt, "Europe/Paris")
        assert result is not None
        assert str(result.tzinfo) == "Europe/Paris"


@pytest.mark.unit
class TestFormatDatetimeForDisplay:
    """Tests for format_datetime_for_display helper."""

    def test_format_french_locale_with_time(self) -> None:
        """Test formatting with French locale including time."""
        result = format_datetime_for_display(
            "2025-12-02T14:30:00Z",
            "Europe/Paris",
            "fr",
        )
        assert "2025" in result
        assert "15:30" in result  # UTC+1

    def test_format_english_locale_with_time(self) -> None:
        """Test formatting with English locale including time."""
        result = format_datetime_for_display(
            "2025-12-02T14:30:00Z",
            "UTC",
            "en",
        )
        assert "2025" in result
        assert "14:30" in result

    def test_format_without_time(self) -> None:
        """Test formatting without time component."""
        result = format_datetime_for_display(
            "2025-12-02T14:30:00Z",
            "UTC",
            "fr",
            include_time=False,
        )
        assert "14:30" not in result

    def test_format_without_day_name(self) -> None:
        """Test formatting without day of week name."""
        result = format_datetime_for_display(
            "2025-12-02T14:30:00Z",
            "UTC",
            "en",
            include_day_name=False,
        )
        day_names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        assert not any(result.lower().startswith(day) for day in day_names)

    def test_format_chinese_locale(self) -> None:
        """Test formatting with Chinese locale."""
        result = format_datetime_for_display(
            "2025-12-02T14:30:00Z",
            "Asia/Shanghai",
            "zh-CN",
        )
        # Chinese format includes year and special characters
        assert "2025" in result or "年" in result

    def test_format_invalid_datetime_returns_fallback(self) -> None:
        """Test that invalid datetime returns fallback string."""
        result = format_datetime_for_display(
            "invalid",
            "UTC",
            "fr",
        )
        assert result == "Date inconnue"

    def test_format_none_returns_fallback(self) -> None:
        """Test that None returns fallback string."""
        result = format_datetime_for_display(
            None,
            "UTC",
            "fr",
        )
        assert result == "Date inconnue"

    def test_format_spanish_locale(self) -> None:
        """Test formatting with Spanish locale."""
        result = format_datetime_for_display(
            "2025-12-02T14:30:00Z",
            "Europe/Madrid",
            "es",
        )
        assert "2025" in result

    def test_format_german_locale(self) -> None:
        """Test formatting with German locale."""
        result = format_datetime_for_display(
            "2025-12-02T14:30:00Z",
            "Europe/Berlin",
            "de",
        )
        assert "2025" in result

    def test_format_italian_locale(self) -> None:
        """Test formatting with Italian locale."""
        result = format_datetime_for_display(
            "2025-12-02T14:30:00Z",
            "Europe/Rome",
            "it",
        )
        assert "2025" in result


@pytest.mark.unit
class TestFormatDatetimeIso:
    """Tests for format_datetime_iso helper."""

    def test_format_iso_basic(self) -> None:
        """Test basic ISO formatting."""
        result = format_datetime_iso("2025-12-02T14:30:00Z", "UTC")
        assert result is not None
        assert "2025-12-02" in result
        assert "14:30:00" in result

    def test_format_iso_with_timezone_conversion(self) -> None:
        """Test ISO formatting with timezone conversion."""
        result = format_datetime_iso("2025-12-02T14:30:00Z", "Europe/Paris")
        assert result is not None
        # Should include timezone offset
        assert "+" in result or "Z" in result

    def test_format_iso_none_returns_none(self) -> None:
        """Test that None input returns None."""
        assert format_datetime_iso(None, "UTC") is None

    def test_format_iso_invalid_returns_none(self) -> None:
        """Test that invalid input returns None."""
        assert format_datetime_iso("invalid", "UTC") is None


@pytest.mark.unit
class TestFormatTimeOnly:
    """Tests for format_time_only helper."""

    def test_format_time_basic(self) -> None:
        """Test basic time formatting."""
        result = format_time_only("2025-12-02T14:30:00Z", "UTC")
        assert result == "14:30"

    def test_format_time_with_timezone_conversion(self) -> None:
        """Test time formatting with timezone conversion."""
        # UTC 14:30 -> Paris 15:30 (winter, UTC+1)
        result = format_time_only("2025-12-02T14:30:00Z", "Europe/Paris")
        assert result == "15:30"

    def test_format_time_invalid_returns_fallback(self) -> None:
        """Test that invalid datetime returns fallback."""
        result = format_time_only("invalid", "UTC")
        assert result == "--:--"

    def test_format_time_none_returns_fallback(self) -> None:
        """Test that None returns fallback."""
        result = format_time_only(None, "UTC")
        assert result == "--:--"

    def test_format_time_midnight(self) -> None:
        """Test formatting midnight."""
        result = format_time_only("2025-12-02T00:00:00Z", "UTC")
        assert result == "00:00"

    def test_format_time_end_of_day(self) -> None:
        """Test formatting end of day."""
        result = format_time_only("2025-12-02T23:59:00Z", "UTC")
        assert result == "23:59"


@pytest.mark.unit
class TestFormatDateOnly:
    """Tests for format_date_only helper."""

    def test_format_date_basic_french(self) -> None:
        """Test basic date formatting in French."""
        result = format_date_only("2025-12-02T14:30:00Z", "UTC", "fr")
        assert "2025" in result

    def test_format_date_basic_english(self) -> None:
        """Test basic date formatting in English."""
        result = format_date_only("2025-12-02T14:30:00Z", "UTC", "en")
        assert "2025" in result

    def test_format_date_excludes_time(self) -> None:
        """Test that date formatting excludes time."""
        result = format_date_only("2025-12-02T14:30:00Z", "UTC", "fr")
        assert "14:30" not in result


@pytest.mark.unit
class TestNormalizeToRfc3339:
    """Tests for normalize_to_rfc3339 helper."""

    def test_normalize_date_only(self) -> None:
        """Test normalizing date-only string."""
        result = normalize_to_rfc3339("2026-01-27")
        assert result == "2026-01-27T00:00:00Z"

    def test_normalize_datetime_without_timezone(self) -> None:
        """Test normalizing datetime without timezone."""
        result = normalize_to_rfc3339("2026-01-27T14:00:00")
        assert result == "2026-01-27T14:00:00Z"

    def test_normalize_datetime_with_z_unchanged(self) -> None:
        """Test that datetime with Z is unchanged."""
        result = normalize_to_rfc3339("2026-01-27T14:00:00Z")
        assert result == "2026-01-27T14:00:00Z"

    def test_normalize_datetime_with_positive_offset_unchanged(self) -> None:
        """Test that datetime with positive offset is unchanged."""
        result = normalize_to_rfc3339("2026-01-27T14:00:00+01:00")
        assert result == "2026-01-27T14:00:00+01:00"

    def test_normalize_datetime_with_negative_offset_unchanged(self) -> None:
        """Test that datetime with negative offset is unchanged."""
        result = normalize_to_rfc3339("2026-01-27T14:00:00-05:00")
        assert result == "2026-01-27T14:00:00-05:00"

    def test_normalize_none_returns_none(self) -> None:
        """Test that None returns None."""
        assert normalize_to_rfc3339(None) is None

    def test_normalize_empty_string_returns_none(self) -> None:
        """Test that empty string returns None."""
        assert normalize_to_rfc3339("") is None


@pytest.mark.unit
class TestNowUtc:
    """Tests for now_utc helper."""

    def test_now_utc_returns_datetime(self) -> None:
        """Test that now_utc returns a datetime."""
        result = now_utc()
        assert isinstance(result, datetime)

    def test_now_utc_is_timezone_aware(self) -> None:
        """Test that now_utc returns timezone-aware datetime."""
        result = now_utc()
        assert result.tzinfo is not None
        assert result.tzinfo == UTC

    def test_now_utc_is_current(self) -> None:
        """Test that now_utc returns approximately current time."""
        before = datetime.now(UTC)
        result = now_utc()
        after = datetime.now(UTC)
        assert before <= result <= after


@pytest.mark.unit
class TestNowInTimezone:
    """Tests for now_in_timezone helper."""

    def test_now_in_paris(self) -> None:
        """Test getting current time in Paris."""
        result = now_in_timezone("Europe/Paris")
        assert result.tzinfo is not None
        assert str(result.tzinfo) == "Europe/Paris"

    def test_now_in_tokyo(self) -> None:
        """Test getting current time in Tokyo."""
        result = now_in_timezone("Asia/Tokyo")
        assert result.tzinfo is not None
        assert str(result.tzinfo) == "Asia/Tokyo"

    def test_now_in_new_york(self) -> None:
        """Test getting current time in New York."""
        result = now_in_timezone("America/New_York")
        assert result.tzinfo is not None
        assert str(result.tzinfo) == "America/New_York"

    def test_now_in_invalid_timezone_uses_default(self) -> None:
        """Test that invalid timezone falls back to default."""
        result = now_in_timezone("Invalid/Timezone")
        assert result.tzinfo is not None
        # Should use default timezone

    def test_now_in_none_uses_default(self) -> None:
        """Test that None timezone uses default."""
        result = now_in_timezone(None)
        assert result.tzinfo is not None


@pytest.mark.unit
class TestIsPast:
    """Tests for is_past helper."""

    def test_past_date_returns_true(self) -> None:
        """Test that past date returns True."""
        assert is_past("2020-01-01T00:00:00Z") is True

    def test_future_date_returns_false(self) -> None:
        """Test that future date returns False."""
        assert is_past("2099-01-01T00:00:00Z") is False

    def test_none_returns_false(self) -> None:
        """Test that None returns False."""
        assert is_past(None) is False

    def test_invalid_returns_false(self) -> None:
        """Test that invalid date returns False."""
        assert is_past("invalid") is False

    def test_with_custom_reference(self) -> None:
        """Test is_past with custom reference datetime."""
        reference = datetime(2025, 6, 1, tzinfo=UTC)
        assert is_past("2025-01-01T00:00:00Z", reference) is True
        assert is_past("2025-12-01T00:00:00Z", reference) is False

    def test_with_naive_reference(self) -> None:
        """Test is_past with naive reference datetime."""
        reference = datetime(2025, 6, 1)  # Naive
        # Should still work - reference gets UTC timezone
        result = is_past("2025-01-01T00:00:00Z", reference)
        assert result is True


@pytest.mark.unit
class TestIsFuture:
    """Tests for is_future helper."""

    def test_future_date_returns_true(self) -> None:
        """Test that future date returns True."""
        assert is_future("2099-01-01T00:00:00Z") is True

    def test_past_date_returns_false(self) -> None:
        """Test that past date returns False."""
        assert is_future("2020-01-01T00:00:00Z") is False

    def test_none_returns_false(self) -> None:
        """Test that None returns False."""
        assert is_future(None) is False

    def test_invalid_returns_false(self) -> None:
        """Test that invalid date returns False."""
        assert is_future("invalid") is False

    def test_with_custom_reference(self) -> None:
        """Test is_future with custom reference datetime."""
        reference = datetime(2025, 6, 1, tzinfo=UTC)
        assert is_future("2025-12-01T00:00:00Z", reference) is True
        assert is_future("2025-01-01T00:00:00Z", reference) is False


@pytest.mark.unit
class TestCalculateCacheAgeSeconds:
    """Tests for calculate_cache_age_seconds helper."""

    def test_calculate_age_recent(self) -> None:
        """Test calculating age of recent cache."""
        recent = (datetime.now(UTC) - timedelta(seconds=60)).isoformat()
        result = calculate_cache_age_seconds(recent)
        # Allow 2 seconds tolerance
        assert 58 <= result <= 62

    def test_calculate_age_with_z_suffix(self) -> None:
        """Test calculating age with Z suffix timestamp."""
        recent = (datetime.now(UTC) - timedelta(seconds=120)).strftime("%Y-%m-%dT%H:%M:%SZ")
        result = calculate_cache_age_seconds(recent)
        assert 118 <= result <= 122

    def test_calculate_age_invalid_returns_zero(self) -> None:
        """Test that invalid timestamp returns 0 (fail-safe)."""
        result = calculate_cache_age_seconds("invalid")
        assert result == 0

    def test_calculate_age_old_cache(self) -> None:
        """Test calculating age of old cache."""
        old = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        result = calculate_cache_age_seconds(old)
        # Should be around 3600 seconds
        assert 3598 <= result <= 3602


@pytest.mark.unit
class TestGetCurrentDatetimeContext:
    """Tests for get_current_datetime_context helper."""

    def test_context_includes_timezone_in_parentheses(self) -> None:
        """Test that context includes timezone in parentheses."""
        result = get_current_datetime_context("Europe/Paris", "fr")
        assert "Europe/Paris" in result
        assert "(" in result and ")" in result

    def test_context_with_utc(self) -> None:
        """Test context with UTC timezone."""
        result = get_current_datetime_context("UTC", "en")
        assert "UTC" in result

    def test_context_invalid_timezone_uses_utc(self) -> None:
        """Test that invalid timezone falls back to UTC."""
        result = get_current_datetime_context("Invalid/Zone", "fr")
        assert "UTC" in result


@pytest.mark.unit
class TestConvertEventDatesInPayload:
    """Tests for convert_event_dates_in_payload helper."""

    def test_convert_event_with_datetime(self) -> None:
        """Test converting event with dateTime fields."""
        event = {
            "start": {"dateTime": "2025-12-02T14:30:00Z"},
            "end": {"dateTime": "2025-12-02T15:30:00Z"},
        }
        result = convert_event_dates_in_payload(event, "Europe/Paris", "fr")

        assert "formatted" in result["start"]
        assert "formatted" in result["end"]
        assert "2025" in result["start"]["formatted"]

    def test_convert_allday_event(self) -> None:
        """Test converting all-day event (date only)."""
        event = {
            "start": {"date": "2025-12-02"},
            "end": {"date": "2025-12-03"},
        }
        result = convert_event_dates_in_payload(event, "Europe/Paris", "fr")

        assert "formatted" in result["start"]
        assert "formatted" in result["end"]

    def test_convert_event_with_metadata(self) -> None:
        """Test converting event with created/updated metadata."""
        event = {
            "start": {"dateTime": "2025-12-02T14:30:00Z"},
            "end": {"dateTime": "2025-12-02T15:30:00Z"},
            "created": "2025-11-01T10:00:00Z",
            "updated": "2025-11-15T12:00:00Z",
        }
        result = convert_event_dates_in_payload(event, "Europe/Paris", "fr")

        assert result["created"] is not None
        assert result["updated"] is not None

    def test_convert_event_empty_start_end(self) -> None:
        """Test converting event with missing start/end."""
        event = {}
        result = convert_event_dates_in_payload(event, "UTC", "en")
        assert result == event  # Should return unchanged


@pytest.mark.unit
class TestConvertEmailDatesInPayload:
    """Tests for convert_email_dates_in_payload helper."""

    def test_convert_email_internal_date(self) -> None:
        """Test converting email internalDate (milliseconds)."""
        email = {
            "id": "test123",
            "internalDate": "1733149800000",
        }
        result = convert_email_dates_in_payload(email, "Europe/Paris", "fr")

        assert "date_formatted" in result
        assert "date_iso" in result

    def test_convert_email_extracts_headers(self) -> None:
        """Test that email headers are extracted to top level."""
        email = {
            "id": "test123",
            "internalDate": "1733149800000",
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "Test Subject"},
                    {"name": "From", "value": "sender@example.com"},
                    {"name": "To", "value": "recipient@example.com"},
                    {"name": "Cc", "value": "cc@example.com"},
                    {"name": "Date", "value": "Mon, 2 Dec 2025 14:30:00 +0000"},
                ]
            },
        }
        result = convert_email_dates_in_payload(email, "UTC", "en")

        assert result.get("subject") == "Test Subject"
        assert result.get("from") == "sender@example.com"
        assert result.get("to") == "recipient@example.com"
        assert result.get("cc") == "cc@example.com"
        assert result.get("date") == "Mon, 2 Dec 2025 14:30:00 +0000"

    def test_convert_email_does_not_overwrite_existing(self) -> None:
        """Test that existing fields are not overwritten."""
        email = {
            "id": "test123",
            "internalDate": "1733149800000",
            "subject": "Existing Subject",
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "Header Subject"},
                ]
            },
        }
        result = convert_email_dates_in_payload(email, "UTC", "en")

        # Existing subject should not be overwritten
        assert result.get("subject") == "Existing Subject"


@pytest.mark.unit
class TestConvertTaskDatesInPayload:
    """Tests for convert_task_dates_in_payload helper."""

    def test_convert_task_due_date(self) -> None:
        """Test converting task due date."""
        task = {
            "due": "2025-12-02T00:00:00Z",
        }
        result = convert_task_dates_in_payload(task, "Europe/Paris", "fr")

        assert "due_formatted" in result

    def test_convert_task_completed_date(self) -> None:
        """Test converting task completed date."""
        task = {
            "completed": "2025-12-01T14:30:00Z",
        }
        result = convert_task_dates_in_payload(task, "Europe/Paris", "fr")

        assert "completed_formatted" in result

    def test_convert_task_all_dates(self) -> None:
        """Test converting task with all date fields."""
        task = {
            "due": "2025-12-02T00:00:00Z",
            "completed": "2025-12-01T14:30:00Z",
            "created": "2025-11-01T10:00:00Z",
            "updated": "2025-11-15T12:00:00Z",
        }
        result = convert_task_dates_in_payload(task, "Europe/Paris", "fr")

        assert "due_formatted" in result
        assert "completed_formatted" in result
        assert "created_formatted" in result
        assert "updated_formatted" in result


@pytest.mark.unit
class TestConvertFileDatesInPayload:
    """Tests for convert_file_dates_in_payload helper."""

    def test_convert_file_modified_time(self) -> None:
        """Test converting file modifiedTime."""
        file = {
            "modifiedTime": "2025-12-02T14:30:00Z",
        }
        result = convert_file_dates_in_payload(file, "Europe/Paris", "fr")

        assert "modifiedTime_formatted" in result

    def test_convert_file_created_time(self) -> None:
        """Test converting file createdTime."""
        file = {
            "createdTime": "2025-11-01T10:00:00Z",
        }
        result = convert_file_dates_in_payload(file, "Europe/Paris", "fr")

        assert "createdTime_formatted" in result

    def test_convert_file_all_times(self) -> None:
        """Test converting file with all time fields."""
        file = {
            "modifiedTime": "2025-12-02T14:30:00Z",
            "createdTime": "2025-11-01T10:00:00Z",
            "viewedByMeTime": "2025-12-01T14:30:00Z",
        }
        result = convert_file_dates_in_payload(file, "Europe/Paris", "fr")

        assert "modifiedTime_formatted" in result
        assert "createdTime_formatted" in result
        assert result["viewedByMeTime"] is not None


@pytest.mark.unit
class TestConvertWeatherDatesInPayload:
    """Tests for convert_weather_dates_in_payload helper."""

    def test_convert_weather_timestamp(self) -> None:
        """Test converting weather dt timestamp."""
        weather = {
            "dt": 1733149800,  # Unix timestamp in seconds
        }
        result = convert_weather_dates_in_payload(weather, "Europe/Paris", "fr")

        assert "dt_formatted" in result

    def test_convert_weather_sunrise_sunset(self) -> None:
        """Test converting sunrise/sunset times."""
        weather = {
            "dt": 1733149800,
            "sys": {
                "sunrise": 1733123400,
                "sunset": 1733156400,
            },
        }
        result = convert_weather_dates_in_payload(weather, "Europe/Paris", "fr")

        assert "sunrise_formatted" in result["sys"]
        assert "sunset_formatted" in result["sys"]

    def test_convert_weather_without_sys(self) -> None:
        """Test converting weather without sys object."""
        weather = {
            "dt": 1733149800,
        }
        result = convert_weather_dates_in_payload(weather, "UTC", "en")

        assert "dt_formatted" in result


@pytest.mark.unit
class TestDateValidationConstants:
    """Tests for date validation range constants."""

    def test_min_valid_year_is_1990(self) -> None:
        """Test that MIN_VALID_YEAR is 1990."""
        assert MIN_VALID_YEAR == 1990

    def test_max_valid_year_is_2100(self) -> None:
        """Test that MAX_VALID_YEAR is 2100."""
        assert MAX_VALID_YEAR == 2100

    def test_valid_year_range(self) -> None:
        """Test that the valid year range is reasonable."""
        assert MIN_VALID_YEAR < MAX_VALID_YEAR
        assert MAX_VALID_YEAR - MIN_VALID_YEAR > 100  # At least 100 years range
