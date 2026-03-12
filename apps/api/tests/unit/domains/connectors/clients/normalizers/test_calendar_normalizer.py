"""Unit tests for CalDAV calendar normalizer."""

from datetime import UTC, date, datetime
from unittest.mock import MagicMock

import pytest

from src.domains.connectors.clients.normalizers.calendar_normalizer import (
    normalize_calendar,
    normalize_vevent,
)


def _make_vevent_prop(value: object) -> MagicMock:
    """Create a mock vobject property with a .value attribute."""
    prop = MagicMock()
    prop.value = value
    return prop


def _make_caldav_event(
    uid: str = "abc-123",
    summary: str = "Team Standup",
    dtstart: datetime | date | None = None,
    dtend: datetime | date | None = None,
    location: str | None = None,
    description: str | None = None,
    status: str | None = None,
    attendees: list | None = None,
    created: datetime | None = None,
    last_modified: datetime | None = None,
) -> MagicMock:
    """Build a mock caldav Event with a vobject_instance.vevent."""
    vevent = MagicMock()

    # Property access via getattr — return mock with .value, or None
    def _getattr(name: str, default: object = None) -> object:
        props = {
            "uid": _make_vevent_prop(uid),
            "summary": _make_vevent_prop(summary),
            "dtstart": _make_vevent_prop(dtstart or datetime(2024, 6, 15, 9, 0, tzinfo=UTC)),
            "dtend": _make_vevent_prop(dtend or datetime(2024, 6, 15, 10, 0, tzinfo=UTC)),
        }
        if location is not None:
            props["location"] = _make_vevent_prop(location)
        if description is not None:
            props["description"] = _make_vevent_prop(description)
        if status is not None:
            props["status"] = _make_vevent_prop(status)
        if created is not None:
            props["created"] = _make_vevent_prop(created)
        if last_modified is not None:
            props["last_modified"] = _make_vevent_prop(last_modified)

        return props.get(name, default)

    vevent.__class__ = type("MockVevent", (), {})
    # Use side_effect to simulate getattr on the mock
    type(vevent).__getattr__ = lambda self, name: _getattr(name)

    vevent.attendee_list = attendees or []

    event = MagicMock()
    event.vobject_instance.vevent = vevent
    event.url = f"https://caldav.example.com/event/{uid}"

    return event


@pytest.mark.unit
class TestNormalizeVevent:
    """Tests for normalize_vevent()."""

    def test_basic_event(self) -> None:
        """Normalize a simple timed event with summary, start, and end."""
        event = _make_caldav_event()
        result = normalize_vevent(event)

        assert result["id"] == "abc-123"
        assert result["summary"] == "Team Standup"
        assert "dateTime" in result["start"]
        assert "dateTime" in result["end"]
        assert result["htmlLink"] is None

    def test_all_day_event(self) -> None:
        """All-day events use 'date' key instead of 'dateTime'."""
        event = _make_caldav_event(
            dtstart=date(2024, 12, 25),
            dtend=date(2024, 12, 26),
        )
        result = normalize_vevent(event)

        assert "date" in result["start"]
        assert result["start"]["date"] == "2024-12-25"

    def test_optional_fields(self) -> None:
        """Location, description, and status are included when present."""
        event = _make_caldav_event(
            location="Conference Room B",
            description="Weekly sync meeting",
            status="CONFIRMED",
        )
        result = normalize_vevent(event)

        assert result["location"] == "Conference Room B"
        assert result["description"] == "Weekly sync meeting"
        assert result["status"] == "confirmed"

    def test_attendees(self) -> None:
        """Attendees are extracted with email and optional display name."""
        attendee = MagicMock()
        attendee.value = "mailto:bob@example.com"
        attendee.cn_paramval = "Bob Smith"
        attendee.CN_paramval = None
        attendee.partstat_paramval = "ACCEPTED"
        attendee.PARTSTAT_paramval = None

        event = _make_caldav_event(attendees=[attendee])
        result = normalize_vevent(event)

        assert len(result["attendees"]) == 1
        assert result["attendees"][0]["email"] == "bob@example.com"
        assert result["attendees"][0]["displayName"] == "Bob Smith"
        assert result["attendees"][0]["responseStatus"] == "accepted"


@pytest.mark.unit
class TestNormalizeCalendar:
    """Tests for normalize_calendar()."""

    def test_basic_calendar(self) -> None:
        """Normalize a calendar with name and URL."""
        cal = MagicMock()
        cal.url = "https://caldav.example.com/calendars/personal/"
        cal.name = "Personal"
        cal.get_supported_components = MagicMock()

        result = normalize_calendar(cal)

        assert result["id"] == "https://caldav.example.com/calendars/personal/"
        assert result["summary"] == "Personal"
        assert result["primary"] is False
        assert result["timeZone"] == "UTC"

    def test_calendar_without_name(self) -> None:
        """Calendar with no name falls back to URL as summary."""
        cal = MagicMock()
        cal.url = "https://caldav.example.com/cal/work/"
        cal.name = None
        cal.get_supported_components = None

        result = normalize_calendar(cal)

        assert result["summary"] == str(cal.url)
        assert "timeZone" not in result
