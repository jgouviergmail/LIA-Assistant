"""
Calendar normalizer: CalDAV VEVENT → dict format Google Calendar API.

Converts caldav Event objects to the dict structure
expected by calendar_tools.py (same format as GoogleCalendarClient).
"""

from datetime import date, datetime
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


def normalize_vevent(event: Any) -> dict[str, Any]:
    """
    Normalize a caldav Event to Google Calendar API dict format.

    Args:
        event: caldav Event object (with vobject_instance).

    Returns:
        Dict matching Google Calendar API event format.
    """
    vevent = event.vobject_instance.vevent

    result: dict[str, Any] = {}

    # ID — use UID from VEVENT
    result["id"] = _get_prop(vevent, "uid", str(event.url) if hasattr(event, "url") else "unknown")

    # Summary
    result["summary"] = _get_prop(vevent, "summary", "")

    # Start
    dtstart = _get_prop_value(vevent, "dtstart")
    if dtstart is not None:
        result["start"] = _format_datetime_field(dtstart)
    else:
        result["start"] = {}

    # End
    dtend = _get_prop_value(vevent, "dtend")
    if dtend is not None:
        result["end"] = _format_datetime_field(dtend)
    else:
        result["end"] = {}

    # Location
    location = _get_prop(vevent, "location")
    if location:
        result["location"] = location

    # Description
    description = _get_prop(vevent, "description")
    if description:
        result["description"] = description

    # Status
    status = _get_prop(vevent, "status")
    if status:
        result["status"] = status.lower()

    # Attendees
    attendees = _extract_attendees(vevent)
    if attendees:
        result["attendees"] = attendees

    # Created / Updated
    created = _get_prop_value(vevent, "created")
    if created and isinstance(created, datetime):
        result["created"] = created.isoformat()

    updated = _get_prop_value(vevent, "last_modified")
    if updated and isinstance(updated, datetime):
        result["updated"] = updated.isoformat()

    # No web link for iCloud
    result["htmlLink"] = None

    return result


def normalize_calendar(cal: Any) -> dict[str, Any]:
    """
    Normalize a caldav Calendar to Google Calendar API dict format.

    Args:
        cal: caldav Calendar object.

    Returns:
        Dict matching Google Calendar API calendar list item.
    """
    cal_id = str(cal.url) if hasattr(cal, "url") else "unknown"
    display_name = getattr(cal, "name", None) or cal_id

    result: dict[str, Any] = {
        "id": cal_id,
        "summary": display_name,
        "primary": False,
    }

    # Try to extract timezone from calendar properties
    tz = getattr(cal, "get_supported_components", None)
    if tz:
        result["timeZone"] = "UTC"  # Default, CalDAV doesn't always expose TZ

    return result


def _format_datetime_field(value: Any) -> dict[str, Any]:
    """
    Format a dtstart/dtend value to Google Calendar API start/end format.

    Handles both date (all-day) and datetime (timed) events.
    """
    if isinstance(value, datetime):
        field: dict[str, Any] = {"dateTime": value.isoformat()}
        if value.tzinfo:
            field["timeZone"] = (
                getattr(value.tzinfo, "zone", None)
                or getattr(value.tzinfo, "key", None)
                or getattr(value.tzinfo, "_name", None)
                or str(value.tzinfo)
            )
        return field
    elif isinstance(value, date):
        return {"date": value.isoformat()}
    else:
        return {"dateTime": str(value)}


def _extract_attendees(vevent: Any) -> list[dict[str, str]]:
    """Extract attendees from VEVENT."""
    attendees = []
    attendee_list = getattr(vevent, "attendee_list", [])

    for attendee in attendee_list:
        att_value = str(attendee.value) if hasattr(attendee, "value") else str(attendee)
        email = att_value.replace("mailto:", "").replace("MAILTO:", "")

        attendee_dict: dict[str, str] = {"email": email}

        # Display name from CN parameter
        cn = getattr(attendee, "cn_paramval", None) or getattr(attendee, "CN_paramval", None)
        if cn:
            attendee_dict["displayName"] = str(cn)

        # Response status from PARTSTAT parameter
        partstat = getattr(attendee, "partstat_paramval", None) or getattr(
            attendee, "PARTSTAT_paramval", None
        )
        if partstat:
            status_map = {
                "ACCEPTED": "accepted",
                "DECLINED": "declined",
                "TENTATIVE": "tentative",
                "NEEDS-ACTION": "needsAction",
            }
            attendee_dict["responseStatus"] = status_map.get(str(partstat).upper(), "needsAction")

        attendees.append(attendee_dict)

    return attendees


def _get_prop(vevent: Any, prop_name: str, default: str = "") -> str:
    """Safely get a string property from a VEVENT."""
    try:
        prop = getattr(vevent, prop_name, None)
        if prop is not None:
            return str(prop.value) if hasattr(prop, "value") else str(prop)
    except Exception:
        pass
    return default


def _get_prop_value(vevent: Any, prop_name: str) -> Any:
    """Safely get the raw value of a VEVENT property."""
    try:
        prop = getattr(vevent, prop_name, None)
        if prop is not None:
            return prop.value
    except Exception:
        pass
    return None
