"""Additive native occurrence facts. A moved instance keeps its original identity."""

from collections.abc import Mapping
from datetime import date, datetime


def caldav_occurrence_fields(*, uid: str, rule: object, original: object) -> dict[str, object]:
    """Return the occurrence facts of a CalDAV event, in the normalised event shape.

    Args:
        uid: The event's UID, which names its series.
        rule: The event's RRULE, if any.
        original: The occurrence's RECURRENCE-ID, if any.

    Returns:
        The recurrence, series id and original start to merge into the event.
    """
    result: dict[str, object] = {}
    if isinstance(rule, str) and rule and len(rule) <= 1000:
        result["recurrence"] = [rule if rule.upper().startswith("RRULE:") else f"RRULE:{rule}"]
        result["recurringEventId"] = uid
    if isinstance(original, datetime):
        result["originalStartTime"] = {"dateTime": original.isoformat()}
        result["recurringEventId"] = uid
    elif isinstance(original, date):
        result["originalStartTime"] = {"date": original.isoformat()}
        result["recurringEventId"] = uid
    return result


def graph_occurrence_fields(event: Mapping[str, object]) -> dict[str, object]:
    """Return the occurrence facts of a Microsoft Graph event, in the normalised shape.

    Args:
        event: The Graph event.

    Returns:
        The series id, original start, event type and original time zone to merge.
    """
    result: dict[str, object] = {}
    series, original = event.get("seriesMasterId"), event.get("originalStart")
    if isinstance(series, str) and series:
        result["recurringEventId"] = series
    if isinstance(original, str) and original:
        result["originalStartTime"] = {"dateTime": original}
    kind = event.get("type")
    if kind in ("singleInstance", "occurrence", "exception", "seriesMaster"):
        result["_provider_event_type"] = kind
    zone = event.get("originalStartTimeZone")
    if isinstance(zone, str) and zone:
        result["_provider_original_start_timezone"] = zone
    return result
