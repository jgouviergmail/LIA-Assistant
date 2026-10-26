"""Calendar comparison facts computed by code, never inferred by a decision model.

Every civil day is the PERSON's: the timezone is their own setting, handed in by the
caller, and without it no day is stated. A request names relative days (« tomorrow »,
« this week »); the collection question reads where the item's own date sits from
today and never computes it (docs/superpowers/qualification/jev-audit-2026-10-25).
"""

from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import JsonValue

_WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


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


def _monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _day_facts(day: date, today: date) -> dict[str, JsonValue]:
    """Where one civil day sits from today: no model does this arithmetic."""
    return {
        "local_date": day.isoformat(),
        "local_weekday": _WEEKDAYS[day.weekday()],
        "day_offset": (day - today).days,
        "week_offset": (_monday(day) - _monday(today)).days // 7,
    }


def _local_day(instant: datetime, timezone: ZoneInfo) -> date | None:
    try:
        return instant.astimezone(timezone).date()
    except OverflowError:
        return None


def _reference_facts(
    reference: datetime | None, zone: ZoneInfo | None, local_date: date | None
) -> dict[str, JsonValue]:
    return {
        "reference_datetime": reference.isoformat() if reference else None,
        "reference_timezone": zone.key if zone else None,
        "reference_local_date": local_date.isoformat() if local_date else None,
        "reference_local_weekday": _WEEKDAYS[local_date.weekday()] if local_date else None,
    }


def calendar_time_facts(
    payload: Mapping[str, object], reference_datetime: datetime, timezone: str | None
) -> dict[str, JsonValue]:
    """Compare a canonical event start with one operation's captured reference.

    All-day dates are compared as civil dates in the user's known timezone;
    their granularity is explicit and cannot establish a time within that day.
    Naive date-times need their source timezone, never an assumed user offset.
    Unresolved, ambiguous or nonexistent instants remain unknown, and so does the
    start's day (`start`) whenever the person's timezone is unknown.
    """
    zone = _zone(timezone)
    reference = _as_utc(reference_datetime)
    local_date = _local_date(reference, zone)
    facts: dict[str, JsonValue] = {
        **_reference_facts(reference, zone, local_date),
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
            facts["start"] = {**_day_facts(start_date, local_date), "all_day": True}
        return facts
    instant = _start_instant(start)
    if instant is not None:
        facts["comparison_granularity"] = "instant"
        facts["start_at_or_after_reference"] = instant >= reference
        if zone is not None and local_date is not None:
            if (start_day := _local_day(instant, zone)) is not None:
                facts["start"] = {**_day_facts(start_day, local_date), "all_day": False}
    return facts


def _received_instant(stamp: object) -> datetime | None:
    """The unified mail vocabulary's `internalDate`: epoch milliseconds, int or digits."""
    if isinstance(stamp, bool) or not isinstance(stamp, int | str):
        return None
    if isinstance(stamp, str) and not stamp.isdigit():
        return None
    try:
        return datetime.fromtimestamp(int(stamp) / 1000, UTC)
    except OverflowError, OSError, ValueError:
        return None


def email_time_facts(
    payload: Mapping[str, object], reference_datetime: datetime, timezone: str | None
) -> dict[str, JsonValue]:
    """The day a message was received, in the person's timezone, from today.

    Every provider's normaliser publishes the received instant as `internalDate`
    (ADR-287). An unreadable stamp or an unknown timezone states nothing at all: a
    reference with no day of its own to compare would only enlarge the shared state.
    """
    zone = _zone(timezone)
    reference = _as_utc(reference_datetime)
    local_date = _local_date(reference, zone)
    received = _received_instant(payload.get("internalDate"))
    if received is None or zone is None or local_date is None:
        return {}
    received_day = _local_day(received, zone)
    if received_day is None:
        return {}
    return {
        **_reference_facts(reference, zone, local_date),
        "received": _day_facts(received_day, local_date),
    }
