"""
Calendar normalizer: Microsoft Graph event → dict format Google Calendar API.

Converts Microsoft Graph API calendar event objects to the dict structure
expected by calendar_tools.py (same format as GoogleCalendarClient).
"""

from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Microsoft Graph attendee responseStatus → Google Calendar responseStatus mapping
_RESPONSE_STATUS_MAP: dict[str, str] = {
    "accepted": "accepted",
    "tentativelyAccepted": "tentative",
    "declined": "declined",
    "notResponded": "needsAction",
    "none": "needsAction",
    "organizer": "accepted",
}


def normalize_graph_event(event: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize a Microsoft Graph event to Google Calendar API dict format.

    Args:
        event: Microsoft Graph event dict from /me/events or /me/calendarView.

    Returns:
        Dict in Google Calendar API event format with _provider marker.
    """
    event_id = event.get("id", "")
    summary = event.get("subject", "")
    description = event.get("bodyPreview", "")

    # Full body if available
    body_data = event.get("body", {})
    if body_data.get("content"):
        description = body_data["content"]

    # Location
    location_data = event.get("location", {})
    location = location_data.get("displayName", "")

    # Start/End datetime handling
    start = _normalize_datetime(event.get("start"))
    end = _normalize_datetime(event.get("end"))

    # Determine if all-day event
    is_all_day = event.get("isAllDay", False)
    if is_all_day and start and end:
        # For all-day events, use date format (not dateTime)
        start = {"date": start.get("dateTime", "")[:10]}
        end = {"date": end.get("dateTime", "")[:10]}

    # Attendees
    attendees = []
    for att in event.get("attendees", []):
        email_addr = att.get("emailAddress", {})
        response = att.get("status", {}).get("response", "none")
        attendees.append(
            {
                "email": email_addr.get("address", ""),
                "displayName": email_addr.get("name", ""),
                "responseStatus": _RESPONSE_STATUS_MAP.get(response, "needsAction"),
            }
        )

    # Organizer
    organizer_data = event.get("organizer", {}).get("emailAddress", {})
    organizer = {}
    if organizer_data:
        organizer = {
            "email": organizer_data.get("address", ""),
            "displayName": organizer_data.get("name", ""),
        }

    # Recurrence
    recurrence = []
    if event.get("recurrence"):
        pattern = event["recurrence"].get("pattern", {})
        recurrence_type = pattern.get("type", "")
        if recurrence_type:
            recurrence.append(f"RRULE:FREQ={recurrence_type.upper()}")

    # Status mapping (Microsoft → Google)
    show_as = event.get("showAs", "busy")
    transparency = "transparent" if show_as == "free" else "opaque"

    return {
        "id": event_id,
        "summary": summary,
        "description": description,
        "location": location,
        "start": start or {},
        "end": end or {},
        "attendees": attendees,
        "organizer": organizer,
        "recurrence": recurrence,
        "status": "confirmed" if not event.get("isCancelled", False) else "cancelled",
        "transparency": transparency,
        "htmlLink": event.get("webLink", ""),
        "created": event.get("createdDateTime", ""),
        "updated": event.get("lastModifiedDateTime", ""),
        "iCalUID": event.get("iCalUId", ""),
        "_provider": "microsoft",
    }


def _normalize_datetime(dt_data: dict[str, Any] | None) -> dict[str, str] | None:
    """
    Normalize Microsoft Graph dateTime to Google Calendar format.

    Microsoft: {"dateTime": "2025-01-15T10:00:00.0000000", "timeZone": "Europe/Paris"}
    Google:    {"dateTime": "2025-01-15T10:00:00", "timeZone": "Europe/Paris"}

    Args:
        dt_data: Microsoft Graph dateTimeTimeZone object.

    Returns:
        Dict with dateTime and timeZone in Google Calendar format.
    """
    if not dt_data:
        return None

    dt_str = dt_data.get("dateTime", "")
    timezone = dt_data.get("timeZone", "")

    # Microsoft sometimes returns fractional seconds — strip them for consistency
    if "." in dt_str:
        dt_str = dt_str.split(".")[0]

    return {
        "dateTime": dt_str,
        "timeZone": timezone,
    }


def normalize_graph_calendar(cal: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize a Microsoft Graph calendar to Google Calendar list format.

    Args:
        cal: Microsoft Graph calendar dict from /me/calendars.

    Returns:
        Dict in Google Calendar calendarList format.
    """
    return {
        "id": cal.get("id", ""),
        "summary": cal.get("name", ""),
        "description": "",
        "primary": cal.get("isDefaultCalendar", False),
        "accessRole": "owner" if cal.get("canEdit", False) else "reader",
        "backgroundColor": _color_name_to_hex(cal.get("color", "")),
        "selected": True,
        "_provider": "microsoft",
    }


def _color_name_to_hex(color_name: str) -> str:
    """Map Microsoft Graph calendar color name to hex code."""
    color_map: dict[str, str] = {
        "auto": "#4285F4",
        "lightBlue": "#039BE5",
        "lightGreen": "#33B679",
        "lightOrange": "#F4511E",
        "lightGray": "#616161",
        "lightYellow": "#F6BF26",
        "lightTeal": "#009688",
        "lightPink": "#D81B60",
        "lightBrown": "#795548",
        "lightRed": "#D50000",
        "maxColor": "#4285F4",
    }
    return color_map.get(color_name, "#4285F4")
