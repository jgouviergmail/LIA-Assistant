"""
Time utilities for datetime handling and timezone conversion.

=============================================================================
DATETIME DOCTRINE - MANDATORY RULES FOR THE ENTIRE APPLICATION
=============================================================================

FUNDAMENTAL PRINCIPLE:
    This module (time_utils.py) is the SINGLE source of truth for all
    date/time handling. No other module should manipulate datetimes directly
    without going through these utilities.

RULE 1 - STORAGE:
    All dates are stored in UTC (ISO 8601 with 'Z' or '+00:00').
    Never store naive datetimes in the database or cache.

RULE 2 - PROCESSING:
    All datetime manipulation MUST use AWARE datetimes (with tzinfo).
    Use datetime.now(UTC) instead of datetime.now().

RULE 3 - DISPLAY:
    All dates shown to the user MUST be converted to their configured
    timezone via convert_to_user_timezone() or format_datetime_for_display().

RULE 4 - COMPARISONS:
    NEVER compare aware datetimes with naive datetimes.
    Use is_past(), is_future(), or compare two aware datetimes.

RULE 5 - PARSING:
    Use parse_datetime() to parse any format.
    This function ALWAYS returns an aware datetime (UTC by default).

ANTI-PATTERNS TO AVOID:
    ❌ datetime.now() - use datetime.now(UTC)
    ❌ dt.replace(tzinfo=None) - loses timezone information
    ❌ dt.replace(tzinfo=tz) on aware datetime - use dt.astimezone(tz)
    ❌ pytz.localize() - use ZoneInfo + replace(tzinfo=) on naive only
    ❌ Direct manipulation without going through this module

MAIN FUNCTIONS:
    - parse_datetime(input) → aware datetime (UTC)
    - convert_to_user_timezone(input, tz) → aware datetime (user tz)
    - format_datetime_for_display(input, tz, locale) → localized str
    - format_datetime_iso(input, tz) → ISO str with offset
    - now_utc() → datetime.now(UTC)
    - is_past(dt) / is_future(dt) → safe comparison
=============================================================================
"""

import datetime as dt
import re
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

import structlog

from src.core.config import settings
from src.core.i18n_dates import (
    _extract_language,
    get_day_name,
    get_month_name,
    get_time_connector,
)

logger = structlog.get_logger(__name__)

# Valid date range for emails/calendar events (sanity check)
MIN_VALID_YEAR = 1990  # No emails before internet era
MAX_VALID_YEAR = 2100  # Reasonable future limit

# ISO 8601 datetime pattern with timezone (e.g., 2026-02-06T08:30:00+01:00)
# Matches: YYYY-MM-DDTHH:MM:SS[.microseconds](Z|+HH:MM|-HH:MM)
ISO_DATETIME_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)


def get_prompt_datetime_formatted() -> str:
    """
    Get current datetime formatted for agent prompt injection.

    Uses centralized settings for timezone and format configuration.
    This function replaces the duplicated _get_current_datetime_formatted()
    functions that were copied across 10+ agent builder files.

    Returns:
        Formatted datetime string based on settings.prompt_datetime_format
        in settings.prompt_timezone

    Example:
        >>> get_prompt_datetime_formatted()
        "dimanche 07 décembre 2025, 18:30"

    Used by:
        - All agent builders via create_agent_config_from_settings()
        - ChatPromptTemplate.partial(current_datetime=get_prompt_datetime_formatted)
    """
    from src.core.config import get_settings

    settings = get_settings()
    tz = ZoneInfo(settings.prompt_timezone)
    return datetime.now(tz).strftime(settings.prompt_datetime_format)


def calculate_cache_age_seconds(cached_at: str) -> int:
    """
    Calculate cache age in seconds from ISO 8601 timestamp (UTC).

    Args:
        cached_at: ISO 8601 timestamp string in UTC (e.g., "2025-01-26T14:30:00.123456Z")

    Returns:
        Age in seconds (rounded to nearest integer).
        Returns 0 if parsing fails (fail-safe behavior).

    Example:
        >>> age = calculate_cache_age_seconds("2025-01-26T14:30:00Z")
        >>> # Returns: 120 (if current time is 14:32:00 UTC)

    Note:
        Handles both formats:
        - With 'Z' suffix: "2025-01-26T14:30:00Z"
        - With timezone: "2025-01-26T14:30:00+00:00"

    Used by:
        - google_contacts_tools.py: Cache age calculation for contact data
    """
    try:
        # Normalize 'Z' to '+00:00' for fromisoformat
        cached_dt = datetime.fromisoformat(cached_at.replace("Z", "+00:00"))
        now_dt = datetime.now(UTC)
        delta = now_dt - cached_dt
        return int(delta.total_seconds())
    except Exception as e:
        logger.warning(
            "cache_age_calculation_failed",
            cached_at=cached_at,
            error=str(e),
            error_type=type(e).__name__,
        )
        return 0  # Fail-safe: assume fresh data


def get_current_datetime_context(
    timezone_str: str = "UTC", language: str = settings.default_language
) -> str:
    """
    Get current datetime formatted for LLM context.

    Uses i18n_dates module for proper localization across all supported languages
    (fr, en, es, de, it, zh-CN).

    Args:
        timezone_str: Timezone string (e.g., "Europe/Paris", "UTC")
        language: Language code (e.g., "fr", "en", "es", "de", "it", "zh-CN")

    Returns:
        Formatted datetime string (e.g., "lundi 30 novembre 2025, 14:30 (Europe/Paris)")
    """
    try:
        tz: ZoneInfo | dt.timezone = ZoneInfo(timezone_str)
    except Exception:
        logger.warning("invalid_timezone", timezone=timezone_str)
        tz = UTC
        timezone_str = "UTC"

    now = datetime.now(tz)

    # Use i18n_dates for proper localization (supports all 6 languages)
    lang = _extract_language(language)
    day_name = get_day_name(now.weekday(), language)
    month_name = get_month_name(now.month, language)

    # Format based on language
    if lang == "zh-CN":
        # Chinese: "2025年11月30日 星期一 14:30 (Europe/Paris)"
        date_str = f"{now.year}年{now.month}月{now.day}日 {day_name} {now.strftime('%H:%M')}"
    else:
        # Western languages: "lundi 30 novembre 2025, 14:30 (Europe/Paris)"
        date_str = f"{day_name} {now.day:02d} {month_name} {now.year}, {now.strftime('%H:%M')}"

    return f"{date_str} ({timezone_str})"


def normalize_to_rfc3339(dt_str: str | None) -> str | None:
    """
    Normalize datetime/date string to RFC 3339 format with timezone.

    Google APIs (Calendar, Tasks) require RFC 3339 format with timezone suffix.
    LLM may output various formats that need normalization.

    Handles:
    - Date only: "2026-01-27" -> "2026-01-27T00:00:00Z"
    - Datetime without timezone: "2026-01-27T14:00:00" -> "2026-01-27T14:00:00Z"
    - Datetime with Z: "2026-01-27T14:00:00Z" -> unchanged
    - Datetime with offset: "2026-01-27T14:00:00+01:00" -> unchanged

    Args:
        dt_str: Datetime or date string in various formats

    Returns:
        RFC 3339 formatted string with timezone, or None if input is None

    Examples:
        >>> normalize_to_rfc3339("2026-01-27")
        "2026-01-27T00:00:00Z"
        >>> normalize_to_rfc3339("2026-01-27T14:00:00")
        "2026-01-27T14:00:00Z"
        >>> normalize_to_rfc3339("2026-01-27T14:00:00Z")
        "2026-01-27T14:00:00Z"
        >>> normalize_to_rfc3339("2026-01-27T14:00:00+01:00")
        "2026-01-27T14:00:00+01:00"
    """
    if not dt_str:
        return None

    # Already has 'Z' suffix - fully valid RFC 3339
    if dt_str.endswith("Z"):
        return dt_str

    # Check for +HH:MM or -HH:MM offset at the end (e.g., +01:00 or -05:00)
    if len(dt_str) >= 6:
        suffix = dt_str[-6:]
        if suffix[0] in "+-" and suffix[3] == ":":
            return dt_str  # Already has timezone offset

    # Check if it's a date-only format (YYYY-MM-DD, 10 chars)
    if len(dt_str) == 10 and dt_str[4] == "-" and dt_str[7] == "-":
        return f"{dt_str}T00:00:00Z"

    # Datetime without timezone - add Z suffix
    if "T" in dt_str:
        return f"{dt_str}Z"

    # Fallback: return as-is (shouldn't happen with valid input)
    return dt_str


# =============================================================================
# USER-INPUT DATETIME NORMALIZATION
# =============================================================================


def _has_explicit_timezone(dt_str: str) -> bool:
    """Check if a datetime string carries explicit timezone information.

    Args:
        dt_str: ISO 8601 datetime string

    Returns:
        True if the string contains ``Z``, ``+HH:MM``, or ``-HH:MM`` offset.
    """
    stripped = dt_str.rstrip()
    if stripped.endswith("Z"):
        return True
    if len(stripped) >= 6 and stripped[-6] in "+-" and stripped[-3] == ":":
        return True
    return False


def normalize_user_datetime(dt_str: str | None, user_timezone: str) -> str | None:
    """Normalize a user-provided datetime to the correct timezone offset.

    LLM tool calls express user intent in the user's local timezone. The LLM
    may produce either a naive datetime (no offset) or one with the WRONG offset
    (e.g. +01:00 for a date that should be +02:00 due to DST). This function
    always re-localizes to the user's timezone using the correct offset for the
    target date.

    Args:
        dt_str: ISO 8601 datetime string (may be naive or aware).
        user_timezone: User's IANA timezone (e.g., ``"Europe/Paris"``).

    Returns:
        ISO string with the correct offset for the target date, or ``None``
        if *dt_str* is ``None`` or unparseable.

    Examples:
        >>> normalize_user_datetime("2026-03-26T21:00:00", "Europe/Paris")
        '2026-03-26T21:00:00+01:00'

        >>> # LLM sent +01:00 but 29 mars is CEST (+02:00) → corrected
        >>> normalize_user_datetime("2026-03-29T15:00:00+01:00", "Europe/Paris")
        '2026-03-29T15:00:00+02:00'

        >>> normalize_user_datetime("2026-03-26T21:00:00Z", "Europe/Paris")
        '2026-03-26T22:00:00+01:00'
    """
    if not dt_str:
        return None

    try:
        dt = datetime.fromisoformat(dt_str)
    except (ValueError, TypeError):
        logger.warning(
            "normalize_user_datetime_parse_failed",
            input=dt_str[:50],
        )
        return dt_str

    try:
        user_tz = ZoneInfo(user_timezone)

        if dt.tzinfo is not None:
            # Aware datetime: the LLM may have used the wrong offset (e.g. CET
            # instead of CEST). Strip the offset and re-localize using the
            # user's timezone, which picks the correct offset for the target date.
            # The hour value is treated as local time (user intent), not UTC.
            naive = dt.replace(tzinfo=None)
            result = naive.replace(tzinfo=user_tz)
            if result.isoformat() != dt_str:
                logger.debug(
                    "normalize_user_datetime_offset_corrected",
                    original=dt_str,
                    corrected=result.isoformat(),
                    timezone=user_timezone,
                )
            return result.isoformat()
        else:
            # Naive datetime: attach user's timezone
            return dt.replace(tzinfo=user_tz).isoformat()
    except Exception as e:
        logger.warning(
            "normalize_user_datetime_tz_failed",
            input=dt_str[:50],
            timezone=user_timezone,
            error=str(e),
        )
        return dt_str


# =============================================================================
# TIMEZONE CONVERSION UTILITIES
# =============================================================================


def parse_datetime(dt_input: str | int | datetime | None) -> datetime | None:
    """
    Parse various datetime formats into a timezone-aware datetime object.

    Handles:
    - ISO 8601 strings: "2025-12-02T14:30:00+01:00", "2025-12-02T14:30:00Z"
    - Unix timestamps in milliseconds (Gmail internalDate format)
    - Unix timestamps in seconds
    - datetime objects (returned as-is if timezone-aware)

    Args:
        dt_input: Datetime in various formats

    Returns:
        Timezone-aware datetime object, or None if parsing fails

    Examples:
        >>> parse_datetime("2025-12-02T14:30:00+01:00")
        datetime(2025, 12, 2, 14, 30, tzinfo=...)

        >>> parse_datetime(1733142600000)  # milliseconds
        datetime(2025, 12, 2, 13, 30, tzinfo=UTC)

        >>> parse_datetime("2025-12-02")  # date only
        datetime(2025, 12, 2, 0, 0, tzinfo=UTC)
    """
    if dt_input is None:
        return None

    try:
        if isinstance(dt_input, datetime):
            if dt_input.tzinfo is None:
                return dt_input.replace(tzinfo=UTC)
            return dt_input

        if isinstance(dt_input, int):
            # Distinguish between seconds and milliseconds
            # Timestamps after year 2001 in seconds: > 1_000_000_000
            # Timestamps after year 2001 in milliseconds: > 1_000_000_000_000
            if dt_input > 1_000_000_000_000:
                # Milliseconds (Gmail internalDate format)
                return datetime.fromtimestamp(dt_input / 1000, tz=UTC)
            else:
                # Seconds
                return datetime.fromtimestamp(dt_input, tz=UTC)

        if isinstance(dt_input, str):
            # Handle 'Z' suffix (UTC)
            normalized = dt_input.replace("Z", "+00:00")

            # Try ISO 8601 format first
            try:
                dt = datetime.fromisoformat(normalized)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=UTC)
                return dt
            except ValueError:
                pass

            # Try RFC 2822 format (Gmail date header): "Sat, 03 Jan 2026 10:45:00 +0100"
            # Also handles: "03 Jan 2026 10:45:00 +0100" (without day name)
            import email.utils

            try:
                parsed_tuple = email.utils.parsedate_tz(dt_input)
                if parsed_tuple:
                    # parsedate_tz returns (y, m, d, H, M, S, weekday, yearday, dst, tz_offset_seconds)
                    # tz_offset_seconds is the offset from UTC in seconds (can be None)
                    timestamp = email.utils.mktime_tz(parsed_tuple)
                    return datetime.fromtimestamp(timestamp, tz=UTC)
            except (TypeError, ValueError, OverflowError):
                pass

            # Try date-only format (e.g., "2025-12-02")
            if len(dt_input) == 10 and dt_input.count("-") == 2:
                dt = datetime.strptime(dt_input, "%Y-%m-%d")
                return dt.replace(tzinfo=UTC)

            # Try as numeric string (milliseconds)
            if dt_input.isdigit():
                ts = int(dt_input)
                if ts > 1_000_000_000_000:
                    return datetime.fromtimestamp(ts / 1000, tz=UTC)
                else:
                    return datetime.fromtimestamp(ts, tz=UTC)

    except Exception as e:
        logger.warning(
            "datetime_parse_failed",
            input=str(dt_input)[:50],
            error=str(e),
        )

    return None


def _validate_date_range(
    dt: datetime | None,
    original_input: str | int | datetime | None,
    context: str = "unknown",
) -> datetime | None:
    """
    Validate that a parsed datetime is within reasonable bounds.

    Logs warning if date is outside MIN_VALID_YEAR-MAX_VALID_YEAR range
    but still returns the parsed date (for debugging).

    Args:
        dt: Parsed datetime to validate
        original_input: Original input value for logging
        context: Context string for debugging (e.g., "email_internalDate")

    Returns:
        The same datetime (validation is for logging, not filtering)
    """
    if dt is None:
        return None

    if dt.year < MIN_VALID_YEAR or dt.year > MAX_VALID_YEAR:
        logger.warning(
            "datetime_out_of_range",
            parsed_year=dt.year,
            parsed_date=dt.isoformat(),
            original_input=str(original_input)[:100],
            context=context,
            min_valid_year=MIN_VALID_YEAR,
            max_valid_year=MAX_VALID_YEAR,
        )

    return dt


def convert_to_user_timezone(
    dt_input: str | int | datetime | None,
    user_timezone: str = "UTC",
) -> datetime | None:
    """
    Convert a datetime to the user's timezone.

    Args:
        dt_input: Datetime in various formats (ISO string, timestamp, datetime)
        user_timezone: User's IANA timezone (e.g., "Europe/Paris")

    Returns:
        Datetime object in user's timezone, or None if parsing fails

    Examples:
        >>> convert_to_user_timezone("2025-12-02T13:30:00Z", "Europe/Paris")
        datetime(2025, 12, 2, 14, 30, tzinfo=ZoneInfo('Europe/Paris'))
    """
    dt = parse_datetime(dt_input)
    if dt is None:
        return None

    try:
        user_tz = ZoneInfo(user_timezone)
        return dt.astimezone(user_tz)
    except Exception as e:
        logger.warning(
            "timezone_conversion_failed",
            timezone=user_timezone,
            error=str(e),
        )
        return dt  # Return original if conversion fails


def format_datetime_for_display(
    dt_input: str | int | datetime | None,
    user_timezone: str = "UTC",
    locale: str = "fr",
    include_time: bool = True,
    include_day_name: bool = True,
) -> str:
    """
    Format a datetime for user display with timezone and locale support.

    Produces human-readable, localized date strings like:
    - French: "lundi 02 décembre 2025 à 14:30"
    - English: "Monday 02 December 2025 at 14:30"
    - Chinese: "2025年12月2日 星期一 14:30"

    Args:
        dt_input: Datetime in various formats
        user_timezone: User's IANA timezone
        locale: User's locale (e.g., "fr", "en", "zh-CN")
        include_time: Whether to include time component
        include_day_name: Whether to include day of week name

    Returns:
        Formatted datetime string, or "Date inconnue" if parsing fails

    Examples:
        >>> format_datetime_for_display("2025-12-02T14:30:00+01:00", "Europe/Paris", "fr")
        "lundi 02 décembre 2025 à 14:30"

        >>> format_datetime_for_display(1733142600000, "America/New_York", "en")
        "Monday 02 December 2025 at 08:30"
    """
    dt = convert_to_user_timezone(dt_input, user_timezone)
    if dt is None:
        return "Date inconnue"

    try:
        lang = _extract_language(locale)

        day_num = dt.day
        month = dt.month
        year = dt.year
        weekday = dt.weekday()

        day_str = f"{day_num:02d}"
        month_name = get_month_name(month, locale)
        day_name = get_day_name(weekday, locale) if include_day_name else ""

        # Build date string based on language
        if lang == "zh-CN":
            # Chinese: "2025年12月2日 星期一"
            date_str = f"{year}年{month}月{day_num}日"
            if include_day_name:
                date_str += f" {day_name}"
        else:
            # Western: "lundi 02 décembre 2025"
            if include_day_name:
                date_str = f"{day_name} {day_str} {month_name} {year}"
            else:
                date_str = f"{day_str} {month_name} {year}"

        if include_time:
            time_str = dt.strftime("%H:%M")
            if lang == "zh-CN":
                return f"{date_str} {time_str}"
            else:
                connector = get_time_connector(locale)
                return f"{date_str} {connector} {time_str}"

        return date_str

    except Exception as e:
        logger.warning(
            "datetime_format_failed",
            input=str(dt_input)[:50],
            error=str(e),
        )
        return "Date inconnue"


def is_iso_datetime_string(value: str) -> bool:
    """
    Check if a string matches ISO 8601 datetime format with timezone.

    Only matches complete datetime strings with timezone info:
    - 2026-02-06T08:30:00+01:00 ✓
    - 2026-02-06T08:30:00Z ✓
    - 2026-02-06T08:30:00.123456+01:00 ✓
    - 2026-02-06 ✗ (date only, no time/timezone)
    - 2026-02-06T08:30:00 ✗ (no timezone)

    Args:
        value: String to check

    Returns:
        True if string is a valid ISO 8601 datetime with timezone
    """
    return bool(ISO_DATETIME_PATTERN.match(value))


def format_value_if_iso_datetime(
    value: str,
    user_timezone: str = "UTC",
    locale: str = "fr",
    include_time: bool = True,
    include_day_name: bool = False,
) -> str:
    """
    Format a string value if it's an ISO datetime, otherwise return as-is.

    Useful for displaying data that may contain ISO datetime strings mixed
    with other text values (e.g., HITL item previews).

    Args:
        value: String value to potentially format
        user_timezone: User's IANA timezone
        locale: User's locale for formatting
        include_time: Whether to include time in output
        include_day_name: Whether to include day name in output

    Returns:
        Formatted datetime string if input is ISO datetime, original value otherwise

    Examples:
        >>> format_value_if_iso_datetime("2026-02-06T08:30:00+01:00", "Europe/Paris", "fr")
        "06 février 2026 à 08:30"

        >>> format_value_if_iso_datetime("Meeting notes", "Europe/Paris", "fr")
        "Meeting notes"
    """
    if is_iso_datetime_string(value):
        return format_datetime_for_display(
            value,
            user_timezone=user_timezone,
            locale=locale,
            include_time=include_time,
            include_day_name=include_day_name,
        )
    return value


def format_datetime_iso(
    dt_input: str | int | datetime | None,
    user_timezone: str = "UTC",
) -> str | None:
    """
    Convert datetime to ISO 8601 string in user's timezone.

    Useful for storing user-timezone-aware dates while maintaining
    machine-readable format.

    Args:
        dt_input: Datetime in various formats
        user_timezone: User's IANA timezone

    Returns:
        ISO 8601 string in user's timezone, or None if parsing fails

    Examples:
        >>> format_datetime_iso("2025-12-02T13:30:00Z", "Europe/Paris")
        "2025-12-02T14:30:00+01:00"
    """
    dt = convert_to_user_timezone(dt_input, user_timezone)
    if dt is None:
        return None
    return dt.isoformat()


def format_time_only(
    dt_input: str | int | datetime | None,
    user_timezone: str = "UTC",
) -> str:
    """
    Format datetime as time only (HH:MM) in user's timezone.

    Args:
        dt_input: Datetime in various formats
        user_timezone: User's IANA timezone

    Returns:
        Time string (e.g., "14:30"), or "--:--" if parsing fails
    """
    dt = convert_to_user_timezone(dt_input, user_timezone)
    if dt is None:
        return "--:--"
    return dt.strftime("%H:%M")


def format_date_only(
    dt_input: str | int | datetime | None,
    user_timezone: str = "UTC",
    locale: str = "fr",
) -> str:
    """
    Format datetime as date only in user's timezone and locale.

    Args:
        dt_input: Datetime in various formats
        user_timezone: User's IANA timezone
        locale: User's locale

    Returns:
        Formatted date string (e.g., "02 décembre 2025")
    """
    return format_datetime_for_display(
        dt_input,
        user_timezone,
        locale,
        include_time=False,
        include_day_name=False,
    )


def format_time_with_date_context(
    target_dt: datetime,
    reference_dt: datetime | None = None,
    locale: str = "fr",
) -> str:
    """
    Format a datetime as time with contextual date prefix.

    Returns time in HH:MM format with optional date context:
    - Same day as reference: "14:30"
    - Tomorrow relative to reference: "demain 14:30" / "tomorrow 14:30"
    - Other dates: "20/01 14:30" (locale-aware: dd/mm for EU, mm/dd for US)

    This helper centralizes the "today/tomorrow/date" formatting pattern
    used in routes, calendar, and other time-sensitive displays.

    Args:
        target_dt: The datetime to format (must be timezone-aware)
        reference_dt: Reference datetime for "today/tomorrow" comparison.
                     If None, uses current time in target_dt's timezone.
        locale: Language code for "tomorrow" translation (fr, en, es, de, it, zh-CN)

    Returns:
        Formatted time string with optional date context

    Examples:
        >>> from datetime import datetime
        >>> from zoneinfo import ZoneInfo
        >>> tz = ZoneInfo("Europe/Paris")
        >>> now = datetime(2026, 1, 20, 10, 0, tzinfo=tz)
        >>> target = datetime(2026, 1, 20, 14, 30, tzinfo=tz)
        >>> format_time_with_date_context(target, now, "fr")
        "14:30"
        >>> target = datetime(2026, 1, 21, 14, 30, tzinfo=tz)
        >>> format_time_with_date_context(target, now, "fr")
        "demain 14:30"
        >>> target = datetime(2026, 1, 25, 14, 30, tzinfo=tz)
        >>> format_time_with_date_context(target, now, "fr")
        "25/01 14:30"
    """
    from src.core.i18n_v3 import V3Messages

    # Get time string (always 24h format)
    time_str = target_dt.strftime("%H:%M")

    # Determine reference datetime
    if reference_dt is None:
        reference_dt = datetime.now(target_dt.tzinfo)

    # Compare dates
    target_date = target_dt.date()
    ref_date = reference_dt.date()
    tomorrow_date = ref_date + dt.timedelta(days=1)

    # Format based on date context
    if target_date == ref_date:
        # Same day - just time
        return time_str
    elif target_date == tomorrow_date:
        # Tomorrow - add "tomorrow" prefix
        tomorrow_word = V3Messages.get_tomorrow(locale)
        return f"{tomorrow_word} {time_str}"
    else:
        # Other date - add date prefix (locale-aware format)
        lang = _extract_language(locale)
        if lang == "en":
            # US format: mm/dd
            date_str = target_dt.strftime("%m/%d")
        else:
            # EU format: dd/mm (default for fr, es, de, it, zh-CN)
            date_str = target_dt.strftime("%d/%m")
        return f"{date_str} {time_str}"


# =============================================================================
# SAFE DATETIME UTILITIES (USE THESE!)
# =============================================================================


def now_utc() -> datetime:
    """
    Get current datetime in UTC (timezone-aware).

    USE THIS instead of datetime.now() to ensure timezone awareness.

    Returns:
        Timezone-aware datetime in UTC

    Example:
        >>> now = now_utc()
        >>> now.tzinfo
        datetime.timezone.utc
    """
    return datetime.now(UTC)


def now_in_timezone(user_timezone: str | None = None) -> datetime:
    """
    Get current datetime in a specific timezone (always aware).

    USE THIS instead of datetime.now(ZoneInfo(...)) for consistent error handling.
    Respects the datetime doctrine by centralizing timezone handling.

    Args:
        user_timezone: IANA timezone string (e.g., "Europe/Paris").
                      If None or invalid, falls back to DEFAULT_USER_DISPLAY_TIMEZONE.

    Returns:
        Timezone-aware datetime in the specified timezone

    Example:
        >>> now = now_in_timezone("Europe/Paris")
        >>> now.tzinfo
        ZoneInfo('Europe/Paris')

        >>> now = now_in_timezone(None)  # Uses default
        >>> now.tzinfo
        ZoneInfo('Europe/Paris')

        >>> now = now_in_timezone("Invalid/TZ")  # Falls back with warning
        >>> now.tzinfo
        ZoneInfo('Europe/Paris')
    """
    from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE

    if not user_timezone:
        user_timezone = DEFAULT_USER_DISPLAY_TIMEZONE

    try:
        tz = ZoneInfo(user_timezone)
    except (KeyError, ValueError):
        logger.warning(
            "invalid_timezone_fallback",
            timezone=user_timezone,
            default=DEFAULT_USER_DISPLAY_TIMEZONE,
        )
        tz = ZoneInfo(DEFAULT_USER_DISPLAY_TIMEZONE)

    return datetime.now(tz)


def is_past(
    dt_input: str | int | datetime | None,
    reference: datetime | None = None,
) -> bool:
    """
    Check if a datetime is in the past (safe comparison).

    Handles all input formats and ensures timezone-aware comparison.

    Args:
        dt_input: Datetime to check (any format accepted by parse_datetime)
        reference: Reference datetime for comparison (default: now UTC)

    Returns:
        True if dt_input is before reference, False otherwise or if parsing fails

    Example:
        >>> is_past("2020-01-01T00:00:00Z")
        True
        >>> is_past("2099-01-01T00:00:00Z")
        False
    """
    dt = parse_datetime(dt_input)
    if dt is None:
        return False

    ref = reference if reference is not None else now_utc()
    # Ensure both are aware
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=UTC)

    return dt < ref


def is_future(
    dt_input: str | int | datetime | None,
    reference: datetime | None = None,
) -> bool:
    """
    Check if a datetime is in the future (safe comparison).

    Handles all input formats and ensures timezone-aware comparison.

    Args:
        dt_input: Datetime to check (any format accepted by parse_datetime)
        reference: Reference datetime for comparison (default: now UTC)

    Returns:
        True if dt_input is after reference, False otherwise or if parsing fails

    Example:
        >>> is_future("2099-01-01T00:00:00Z")
        True
        >>> is_future("2020-01-01T00:00:00Z")
        False
    """
    dt = parse_datetime(dt_input)
    if dt is None:
        return False

    ref = reference if reference is not None else now_utc()
    # Ensure both are aware
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=UTC)

    return dt > ref


# =============================================================================
# PAYLOAD CONVERSION UTILITIES
# =============================================================================


def convert_event_dates_in_payload(
    event: dict[str, Any],
    user_timezone: str = "UTC",
    locale: str = "fr",
) -> dict[str, Any]:
    """
    Convert all date fields in a Google Calendar event payload to user's timezone.

    Modifies the event in-place and adds formatted display fields.

    Converted fields:
    - start.dateTime → start.dateTime (ISO in user TZ) + start.formatted
    - end.dateTime → end.dateTime (ISO in user TZ) + end.formatted
    - created, updated (if present)

    Args:
        event: Google Calendar event dict
        user_timezone: User's IANA timezone
        locale: User's locale for formatted strings

    Returns:
        The modified event dict

    Note:
        All-day events (start.date instead of start.dateTime) are left unchanged
        as they represent calendar dates, not moments in time.
    """
    # Convert start datetime
    start = event.get("start", {})
    if start.get("dateTime"):
        original_dt = start["dateTime"]
        iso_converted = format_datetime_iso(start["dateTime"], user_timezone)
        if iso_converted:
            start["dateTime"] = iso_converted
        start["formatted"] = format_datetime_for_display(
            original_dt,  # Use ORIGINAL datetime, not the converted one
            user_timezone,
            locale,
            include_time=True,
        )
        logger.debug(
            "convert_event_start_date",
            original=original_dt,
            iso_converted=iso_converted,
            formatted=start["formatted"],
            user_timezone=user_timezone,
            locale=locale,
        )
    elif start.get("date"):
        # All-day event: format date only
        start["formatted"] = format_date_only(start["date"], user_timezone, locale)

    # Convert end datetime
    end = event.get("end", {})
    if end.get("dateTime"):
        original_end_dt = end["dateTime"]  # Keep original before modification
        iso_converted = format_datetime_iso(end["dateTime"], user_timezone)
        if iso_converted:
            end["dateTime"] = iso_converted
        end["formatted"] = format_datetime_for_display(
            original_end_dt,  # Use ORIGINAL datetime, not the converted one
            user_timezone,
            locale,
            include_time=True,
        )
        logger.debug(
            "convert_event_end_date",
            original=original_end_dt,
            iso_converted=iso_converted,
            formatted=end["formatted"],
            user_timezone=user_timezone,
            locale=locale,
        )
    elif end.get("date"):
        end["formatted"] = format_date_only(end["date"], user_timezone, locale)

    # Convert metadata dates if present
    for field in ("created", "updated"):
        if event.get(field):
            iso_converted = format_datetime_iso(event[field], user_timezone)
            if iso_converted:
                event[field] = iso_converted

    return event


def convert_email_dates_in_payload(
    email: dict[str, Any],
    user_timezone: str = "UTC",
    locale: str = "fr",
) -> dict[str, Any]:
    """
    Convert date fields in a Gmail message payload to user's timezone.

    Converts internalDate (milliseconds) to formatted display string.

    Args:
        email: Gmail message dict
        user_timezone: User's IANA timezone
        locale: User's locale

    Returns:
        The modified email dict with added 'date_formatted' field
    """
    internal_date = email.get("internalDate")
    if internal_date:
        # Parse and validate the date
        parsed_dt = parse_datetime(internal_date)
        email_id = email.get("id", "unknown")

        # Validate date range and log if suspicious
        _validate_date_range(
            parsed_dt,
            original_input=internal_date,
            context=f"email_internalDate:{email_id}",
        )

        email["date_formatted"] = format_datetime_for_display(
            internal_date,
            user_timezone,
            locale,
            include_time=True,
        )
        # Also add ISO version for consistent handling
        iso_converted = format_datetime_iso(internal_date, user_timezone)
        if iso_converted:
            email["date_iso"] = iso_converted

    # =========================================================================
    # HEADER EXTRACTION: Extract Gmail headers to top-level for display/LLM
    # =========================================================================
    # Gmail API returns headers nested in payload.headers as list of {name, value}
    # Extract to top-level fields for email_card.py and llm_serializer.py
    payload = email.get("payload", {})
    headers_list = payload.get("headers", [])
    if headers_list:
        headers_dict = {
            h.get("name", "").lower(): h.get("value", "") for h in headers_list if h.get("name")
        }
        # Extract common headers to top-level (only if not already present)
        if "subject" not in email and headers_dict.get("subject"):
            email["subject"] = headers_dict["subject"]
        if "from" not in email and headers_dict.get("from"):
            email["from"] = headers_dict["from"]
        if "to" not in email and headers_dict.get("to"):
            email["to"] = headers_dict["to"]
        if "cc" not in email and headers_dict.get("cc"):
            email["cc"] = headers_dict["cc"]
        if "date" not in email and headers_dict.get("date"):
            email["date"] = headers_dict["date"]

    return email


def convert_task_dates_in_payload(
    task: dict[str, Any],
    user_timezone: str = "UTC",
    locale: str = "fr",
) -> dict[str, Any]:
    """
    Convert date fields in a Google Tasks payload to user's timezone.

    Note: Google Tasks API returns dates in RFC 3339 format.
    Due dates are often date-only (no time component).

    Args:
        task: Google Tasks dict
        user_timezone: User's IANA timezone
        locale: User's locale

    Returns:
        The modified task dict with formatted date fields
    """
    # Due date
    if task.get("due"):
        task["due_formatted"] = format_datetime_for_display(
            task["due"],
            user_timezone,
            locale,
            include_time=False,  # Task due dates typically don't have time
            include_day_name=True,
        )

    # Completion date
    if task.get("completed"):
        task["completed_formatted"] = format_datetime_for_display(
            task["completed"],
            user_timezone,
            locale,
            include_time=True,
        )

    # Created date (for task details display)
    if task.get("created"):
        task["created_formatted"] = format_datetime_for_display(
            task["created"],
            user_timezone,
            locale,
            include_time=False,  # Date only for creation
            include_day_name=False,
        )
        iso_converted = format_datetime_iso(task["created"], user_timezone)
        if iso_converted:
            task["created"] = iso_converted

    # Updated date (for task details display)
    if task.get("updated"):
        task["updated_formatted"] = format_datetime_for_display(
            task["updated"],
            user_timezone,
            locale,
            include_time=False,  # Date only for modification
            include_day_name=False,
        )
        iso_converted = format_datetime_iso(task["updated"], user_timezone)
        if iso_converted:
            task["updated"] = iso_converted

    return task


def convert_file_dates_in_payload(
    file: dict[str, Any],
    user_timezone: str = "UTC",
    locale: str = "fr",
) -> dict[str, Any]:
    """
    Convert date fields in a Google Drive file payload to user's timezone.

    Args:
        file: Google Drive file dict
        user_timezone: User's IANA timezone
        locale: User's locale

    Returns:
        The modified file dict with formatted date fields
    """
    # Modified time
    if file.get("modifiedTime"):
        file["modifiedTime_formatted"] = format_datetime_for_display(
            file["modifiedTime"],
            user_timezone,
            locale,
            include_time=True,
        )
        iso_converted = format_datetime_iso(file["modifiedTime"], user_timezone)
        if iso_converted:
            file["modifiedTime"] = iso_converted

    # Created time
    if file.get("createdTime"):
        file["createdTime_formatted"] = format_datetime_for_display(
            file["createdTime"],
            user_timezone,
            locale,
            include_time=True,
        )
        iso_converted = format_datetime_iso(file["createdTime"], user_timezone)
        if iso_converted:
            file["createdTime"] = iso_converted

    # Viewed by me time
    if file.get("viewedByMeTime"):
        iso_converted = format_datetime_iso(file["viewedByMeTime"], user_timezone)
        if iso_converted:
            file["viewedByMeTime"] = iso_converted

    return file


def convert_weather_dates_in_payload(
    weather: dict[str, Any],
    user_timezone: str = "UTC",
    locale: str = "fr",
) -> dict[str, Any]:
    """
    Convert date fields in weather API payload to user's timezone.

    OpenWeatherMap uses Unix timestamps (seconds).

    Args:
        weather: Weather data dict
        user_timezone: User's IANA timezone
        locale: User's locale

    Returns:
        The modified weather dict with formatted date fields
    """
    # Main timestamp
    if weather.get("dt"):
        weather["dt_formatted"] = format_datetime_for_display(
            weather["dt"],
            user_timezone,
            locale,
            include_time=True,
        )

    # Sunrise/sunset in sys object
    sys = weather.get("sys", {})
    if sys.get("sunrise"):
        sys["sunrise_formatted"] = format_time_only(sys["sunrise"], user_timezone)
    if sys.get("sunset"):
        sys["sunset_formatted"] = format_time_only(sys["sunset"], user_timezone)

    return weather
