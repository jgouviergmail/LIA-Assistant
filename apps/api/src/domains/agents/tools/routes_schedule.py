"""Route clocks computed from explicit instants and elapsed travel seconds."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.core.time_parsing import parse_rfc3339
from src.core.time_utils import format_time_with_date_context


def route_schedule(
    duration_seconds: int,
    now: datetime,
    language: str,
    user_timezone: str,
    *,
    departure_time: object,
    arrival_time_target: object,
    is_arrival_based: bool,
) -> dict[str, str | bool | None]:
    """Retain both route clocks without replacing an invalid request with now.

    Args:
        duration_seconds: Validated nonnegative elapsed travel seconds, including zero.
        now: Aware instant sampled by the formatter, also its immediate departure.
        language: Declared display language.
        user_timezone: Account display zone; invalid zones use the declared default.
        departure_time: Explicit RFC3339 departure, or None for an immediate route.
        arrival_time_target: Explicit RFC3339 arrival target for reverse calculation.
        is_arrival_based: Whether the request specifies an arrival target.

    Returns:
        Optional clock fields, including the existing arrival-based aliases.
        Unreadable instants and overflowing calculations remain absent.
    """
    try:
        zone = ZoneInfo(user_timezone)
    except ZoneInfoNotFoundError, ValueError:
        zone = ZoneInfo(DEFAULT_USER_DISPLAY_TIMEZONE)
    reference = now.astimezone(zone)

    if is_arrival_based:
        arrival = parse_rfc3339(arrival_time_target)
        departure = _shift(arrival, -duration_seconds)
    else:
        departure = now if departure_time is None else parse_rfc3339(departure_time)
        arrival = _shift(departure, duration_seconds)

    departure_iso, departure_text = _clock(departure, reference, language)
    arrival_iso, arrival_text = _clock(arrival, reference, language)
    return {
        "departure_time": departure_iso,
        "departure_formatted": departure_text,
        "eta": arrival_iso,
        "eta_formatted": arrival_text,
        "is_arrival_based": is_arrival_based,
        "target_arrival_time": arrival_iso if is_arrival_based else None,
        "target_arrival_formatted": arrival_text if is_arrival_based else None,
        "suggested_departure_time": departure_iso if is_arrival_based else None,
        "suggested_departure_formatted": departure_text if is_arrival_based else None,
    }


def _shift(instant: datetime | None, seconds: int) -> datetime | None:
    """Apply elapsed time on UTC, never the wall clock across a DST transition."""
    if instant is None:
        return None
    try:
        return instant.astimezone(UTC) + timedelta(seconds=seconds)
    except OverflowError:
        return None


def _clock(
    instant: datetime | None, reference: datetime, language: str
) -> tuple[str | None, str | None]:
    """Project a known instant into the account zone with its date context."""
    if instant is None:
        return None, None
    try:
        local = instant.astimezone(reference.tzinfo)
    except OverflowError:
        return None, None
    return local.isoformat(), format_time_with_date_context(local, reference, language)
