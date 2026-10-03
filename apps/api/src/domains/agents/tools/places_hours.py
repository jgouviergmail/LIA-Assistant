"""Bounded semantic hour facts and complete display-only provider schedules."""

from collections.abc import Mapping
from contextlib import suppress
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.core.field_names import FIELD_DISPLAY_ONLY
from src.core.time_utils import parse_rfc3339

_HOUR_FIELDS = (
    "periods",
    "weekdayDescriptions",
    "specialDays",
    "nextOpenTime",
    "nextCloseTime",
    "openNow",
)


def normalized_hours(place: Mapping[str, object]) -> dict[str, object]:
    fields: dict[str, object] = {}
    display: dict[str, object] = {}
    for key in ("currentOpeningHours", "regularOpeningHours"):
        source = place.get(key)
        if isinstance(source, dict):
            display[key] = {field: source[field] for field in _HOUR_FIELDS if field in source}
    current = place.get("currentOpeningHours")
    if isinstance(current, dict):
        for source_key, target in (
            ("nextOpenTime", "next_open_time"),
            ("nextCloseTime", "next_close_time"),
        ):
            value = current.get(source_key)
            if parse_rfc3339(value) is not None:
                fields[target] = value
    fields.update(_timezone_fields(place))
    if display:
        fields[FIELD_DISPLAY_ONLY] = display
    return fields


def _timezone_fields(place: Mapping[str, object]) -> dict[str, object]:
    fields: dict[str, object] = {}
    zone = place.get("timeZone")
    if isinstance(zone, dict) and isinstance(zone.get("id"), str):
        with suppress(ZoneInfoNotFoundError, ValueError):
            ZoneInfo(zone["id"])
            fields["place_timezone"] = zone["id"]
    offset = place.get("utcOffsetMinutes")
    if isinstance(offset, int) and not isinstance(offset, bool) and -840 <= offset <= 840:
        fields["utc_offset_minutes"] = offset
    return fields
