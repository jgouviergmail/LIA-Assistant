"""Calendar comparison facts computed by code, never inferred by a decision model."""

from collections.abc import Mapping
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import JsonValue


def _zone(value: object) -> ZoneInfo | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return ZoneInfo(value)
    except ValueError, ZoneInfoNotFoundError:
        return None


def _local_instant(value: datetime, timezone: ZoneInfo) -> datetime | None:
    """A naive wall time needs exactly one valid instant, including at DST changes."""
    try:
        instants = {
            candidate.astimezone(UTC)
            for fold in (0, 1)
            if (candidate := value.replace(tzinfo=timezone, fold=fold))
            .astimezone(UTC)
            .astimezone(timezone)
            .replace(tzinfo=None)
            == value
        }
    except OverflowError:
        return None
    return next(iter(instants)) if len(instants) == 1 else None


def _as_utc(value: datetime) -> datetime | None:
    try:
        return value.astimezone(UTC) if value.utcoffset() is not None else None
    except OverflowError:
        return None


def _local_date(reference: datetime | None, timezone: ZoneInfo | None) -> date | None:
    if reference is None or timezone is None:
        return None
    try:
        return reference.astimezone(timezone).date()
    except OverflowError:
        return None


def _start_instant(start: Mapping[str, object]) -> datetime | None:
    value = start.get("dateTime")
    if not isinstance(value, str) or ("T" not in value and " " not in value):
        return None
    try:
        instant = datetime.fromisoformat(value)
    except ValueError:
        return None
    if instant.utcoffset() is not None:
        return _as_utc(instant)
    timezone = _zone(start.get("timeZone"))
    return _local_instant(instant, timezone) if timezone is not None else None


def calendar_time_facts(
    payload: Mapping[str, object], reference_datetime: datetime, timezone: str | None
) -> dict[str, JsonValue]:
    """Compare a canonical event start with one operation's captured reference.

    All-day dates are compared as civil dates in the user's known timezone;
    their granularity is explicit and cannot establish a time within that day.
    Naive date-times need their source timezone, never an assumed user offset.
    Unresolved, ambiguous or nonexistent instants remain unknown.
    """
    zone = _zone(timezone)
    reference = _as_utc(reference_datetime)
    local_date = _local_date(reference, zone)
    facts: dict[str, JsonValue] = {
        "reference_datetime": reference.isoformat() if reference else None,
        "reference_timezone": zone.key if zone else None,
        "reference_local_date": local_date.isoformat() if local_date else None,
        "comparison_granularity": None,
        "start_at_or_after_reference": None,
    }
    start = payload.get("start")
    if reference is None or not isinstance(start, Mapping):
        return facts
    all_day = start.get("date")
    if isinstance(all_day, str):
        try:
            start_date = date.fromisoformat(all_day)
        except ValueError:
            return facts
        facts["comparison_granularity"] = "civil_date"
        if local_date is not None:
            facts["start_at_or_after_reference"] = start_date >= local_date
        return facts
    instant = _start_instant(start)
    if instant is not None:
        facts["comparison_granularity"] = "instant"
        facts["start_at_or_after_reference"] = instant >= reference
    return facts
