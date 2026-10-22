"""Provider recurrence identity must survive normalization before any pattern inference."""

from types import SimpleNamespace

import pytest
import vobject

from src.domains.connectors.clients.microsoft_calendar_client import _EVENT_SELECT_FIELDS
from src.domains.connectors.clients.normalizers.calendar_normalizer import normalize_vevent
from src.domains.connectors.clients.normalizers.microsoft_calendar_normalizer import (
    normalize_graph_event,
)

pytestmark = pytest.mark.unit


def test_graph_occurrence_keeps_its_series_original_instant_and_type() -> None:
    row = normalize_graph_event(
        {
            "id": "moved-instance",
            "subject": "Fictional appointment",
            "seriesMasterId": "series-1",
            "type": "exception",
            "originalStart": "2026-10-20T09:00:00Z",
            "originalStartTimeZone": "Romance Standard Time",
            "start": {"dateTime": "2026-10-21T09:00:00", "timeZone": "UTC"},
            "end": {"dateTime": "2026-10-21T10:00:00", "timeZone": "UTC"},
        }
    )
    assert row["recurringEventId"] == "series-1"
    assert row["originalStartTime"] == {"dateTime": "2026-10-20T09:00:00Z"}
    assert row["_provider_event_type"] == "exception"
    for field in ("seriesMasterId", "type", "originalStart", "originalStartTimeZone"):
        assert field in _EVENT_SELECT_FIELDS.split(",")


def test_apple_exception_retains_recurrence_id_instead_of_the_moved_date() -> None:
    calendar = vobject.readOne(
        "\r\n".join(
            [
                "BEGIN:VCALENDAR",
                "VERSION:2.0",
                "PRODID:-//LIA test//EN",
                "BEGIN:VEVENT",
                "UID:series-1",
                "DTSTART:20261021T090000Z",
                "DTEND:20261021T100000Z",
                "RECURRENCE-ID:20261020T090000Z",
                "RRULE:FREQ=MONTHLY;BYMONTHDAY=20",
                "SUMMARY:Fictional appointment",
                "END:VEVENT",
                "END:VCALENDAR",
                "",
            ]
        )
    )
    row = normalize_vevent(
        SimpleNamespace(vobject_instance=calendar, url="https://calendar.example.test/event")
    )
    assert row["recurringEventId"] == "series-1"
    assert row["originalStartTime"]["dateTime"].startswith("2026-10-20T09:00:00")
    assert row["recurrence"] == ["RRULE:FREQ=MONTHLY;BYMONTHDAY=20"]
