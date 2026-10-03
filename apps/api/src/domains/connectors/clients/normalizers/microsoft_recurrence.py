"""Closed, read-only Graph schedule facts; never invent an iCalendar rule."""

from collections.abc import Mapping

GRAPH_RECURRENCE_FIELDS: dict[str, tuple[str, ...]] = {
    "pattern": ("type", "interval", "daysOfWeek", "dayOfMonth", "month", "index", "firstDayOfWeek"),
    "range": ("type", "startDate", "endDate", "numberOfOccurrences", "recurrenceTimeZone"),
}


def graph_recurrence_snapshot(value: object) -> dict[str, object] | None:
    """Known provider schema only; bound malformed values before they enter model context."""
    if not isinstance(value, Mapping):
        return None
    result: dict[str, object] = {}
    for key, fields in GRAPH_RECURRENCE_FIELDS.items():
        section = value.get(key)
        if isinstance(section, Mapping):
            result[key] = {
                field: projected
                for field in fields
                if (projected := _graph_field(section.get(field))) is not None
            }
    return result or None


def _graph_field(value: object) -> object:
    if isinstance(value, str) and len(value) <= 256:
        return value
    if isinstance(value, int) and not isinstance(value, bool) and -(2**31) <= value < 2**31:
        return value
    if isinstance(value, list) and len(value) <= 7:
        return [item for item in value if isinstance(item, str) and len(item) <= 32]
    return None
