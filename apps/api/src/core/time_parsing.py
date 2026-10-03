"""Central aware datetime parsers, re-exported by the time utility facade."""

import email.utils
import re
from collections.abc import Mapping
from contextlib import suppress
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import structlog

logger = structlog.get_logger(__name__)


def parse_provider_datetime(value: object) -> datetime | None:
    """Read an ISO provider wall time in its stated IANA zone, never guess an unknown zone."""
    if not isinstance(value, Mapping):
        return None
    text = value.get("dateTime")
    if not isinstance(text, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|[+-]\d{2}:\d{2})?", text
    ):
        return None
    try:
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is not None:
            return parsed
        zone = value.get("timeZone")
        if zone is None or zone == "":
            zone = "UTC"
        if not isinstance(zone, str):
            return None
        return _provider_wall_time(parsed, ZoneInfo(zone))
    except ValueError, ZoneInfoNotFoundError, OverflowError:
        return None


def _provider_wall_time(parsed: datetime, zone: ZoneInfo) -> datetime | None:
    aware = parsed.replace(tzinfo=zone)
    # The provider supplied no offset/fold: both a gap and a repeated hour are uncertain.
    if aware.utcoffset() != aware.replace(fold=1).utcoffset():
        return None
    return aware if aware.astimezone(UTC).astimezone(zone).replace(tzinfo=None) == parsed else None


def parse_rfc3339(value: object) -> datetime | None:
    """Parse a provider instant only when its calendar and explicit offset are valid."""
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|[+-]\d{2}:\d{2})", value
    ):
        return None
    return parse_datetime(value)


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
            with suppress(ValueError):
                dt = datetime.fromisoformat(normalized)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=UTC)
                return dt

            # Try RFC 2822 format (Gmail date header): "Sat, 03 Jan 2026 10:45:00 +0100"
            # Also handles: "03 Jan 2026 10:45:00 +0100" (without day name)
            with suppress(TypeError, ValueError, OverflowError):
                parsed_tuple = email.utils.parsedate_tz(dt_input)
                if parsed_tuple:
                    # parsedate_tz returns (y, m, d, H, M, S, weekday, yearday, dst, tz_offset_seconds)
                    # tz_offset_seconds is the offset from UTC in seconds (can be None)
                    timestamp = email.utils.mktime_tz(parsed_tuple)
                    return datetime.fromtimestamp(timestamp, tz=UTC)

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
            input_length=len(str(dt_input)),
            error=str(e),
        )

    return None
