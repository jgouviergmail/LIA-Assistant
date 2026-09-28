"""The calendar for the journal: what took place today, what the week ahead holds."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from src.domains.radio.facts import FactKind, Sensitivity
from src.domains.radio.personal import JournalPart
from src.domains.radio.readers.agenda import (
    AHEAD_DAYS,
    EventLine,
    agenda_ahead_drafts,
    agenda_done_drafts,
    event_line,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 26, 13, 0, tzinfo=UTC)  # Saturday, 13:00 UTC
PLUS_TWO = timezone(timedelta(hours=2))


def event(
    n: int,
    start: datetime,
    *,
    end: datetime | None = None,
    all_day: bool = False,
    location: str | None = None,
    with_id: bool = True,
) -> EventLine:
    return EventLine(
        id=f"e{n}" if with_id else None,
        title=f"Event {n}",
        start=start,
        end=end,
        all_day=all_day,
        location=location,
    )


class TestDone:
    def test_an_appointment_over_by_now_took_place_today(self) -> None:
        [draft] = agenda_done_drafts(
            [event(1, NOW - timedelta(hours=4), end=NOW - timedelta(hours=3), location="Clinic")],
            now=NOW,
            tz=UTC,
        )
        assert draft.text == 'Appointment "Event 1" took place today from 09:00 to 10:00, at Clinic'
        assert (draft.kind, draft.sensitivity, draft.part) == (
            FactKind.EVENT,
            Sensitivity.PERSONAL,
            JournalPart.DONE,
        )
        assert draft.key == "done:event:e1"  # never the day's key: a new fact about the record

    def test_an_appointment_still_running_or_still_ahead_is_not_done(self) -> None:
        running = event(2, NOW - timedelta(minutes=30), end=NOW + timedelta(minutes=30))
        ahead = event(3, NOW + timedelta(hours=1))
        no_end_yet = event(4, NOW + timedelta(minutes=1))
        assert agenda_done_drafts([running, ahead, no_end_yet], now=NOW, tz=UTC) == []

    def test_an_all_day_event_is_never_done_before_its_day_is(self) -> None:
        fair = event(5, NOW.replace(hour=0), all_day=True)
        assert agenda_done_drafts([fair], now=NOW, tz=UTC) == []

    def test_yesterday_s_appointment_is_not_today_s_and_the_day_is_the_listener_s(self) -> None:
        # 23:30 UTC yesterday is 01:30 today two hours east.
        late = event(
            6,
            datetime(2026, 9, 25, 23, 30, tzinfo=UTC),
            end=datetime(2026, 9, 26, 0, 30, tzinfo=UTC),
        )
        assert agenda_done_drafts([late], now=NOW, tz=UTC) == []
        [east] = agenda_done_drafts([late], now=NOW, tz=PLUS_TWO)
        assert "from 01:30 to 02:30" in east.text

    def test_without_an_id_the_key_is_a_digest_of_the_record(self) -> None:
        [draft] = agenda_done_drafts(
            [event(7, NOW - timedelta(hours=2), end=NOW - timedelta(hours=1), with_id=False)],
            now=NOW,
            tz=UTC,
        )
        assert draft.key.startswith("done:event:") and len(draft.key) > len("done:event:")


class TestAhead:
    def test_the_week_ahead_starts_tomorrow_and_ends_seven_days_on(self) -> None:
        tomorrow = event(1, NOW + timedelta(days=1), end=NOW + timedelta(days=1, hours=1))
        last_day = event(2, NOW + timedelta(days=AHEAD_DAYS))
        too_far = event(3, NOW + timedelta(days=AHEAD_DAYS + 1))
        later_today = event(4, NOW + timedelta(hours=2))
        drafts = agenda_ahead_drafts([later_today, tomorrow, too_far, last_day], now=NOW, tz=UTC)
        assert [d.key for d in drafts] == ["event:e1", "event:e2"]  # the DAY's own key
        assert drafts[0].text == 'Appointment "Event 1" on Sunday 2026-09-27, 13:00 until 14:00'
        assert {d.part for d in drafts} == {JournalPart.AHEAD}

    def test_an_all_day_event_names_its_day_alone(self) -> None:
        [draft] = agenda_ahead_drafts(
            [event(5, (NOW + timedelta(days=2)).replace(hour=0), all_day=True, location="Lyon")],
            now=NOW,
            tz=UTC,
        )
        assert draft.text == 'Appointment "Event 5" on Monday 2026-09-28 (all day), at Lyon'

    def test_the_day_is_the_listener_s(self) -> None:
        # 23:30 UTC today is 01:30 TOMORROW two hours east: in the week ahead there, not here.
        tonight = event(6, datetime(2026, 9, 26, 23, 30, tzinfo=UTC))
        assert agenda_ahead_drafts([tonight], now=NOW, tz=UTC) == []
        [east] = agenda_ahead_drafts([tonight], now=NOW, tz=PLUS_TWO)
        assert "Sunday 2026-09-27, 01:30" in east.text


class TestEventLine:
    def test_the_three_providers_shapes_are_read_by_the_briefing_s_one_reading(self) -> None:
        paris = ZoneInfo("Europe/Paris")
        google = {
            "id": "g1",
            "summary": "Dentist",
            "start": {"dateTime": "2026-09-26T09:30:00+02:00"},
            "end": {"dateTime": "2026-09-26T10:00:00+02:00"},
            "location": "  Clinic ",
        }
        line = event_line(google, paris)
        assert line is not None
        assert (line.id, line.title, line.all_day, line.location) == (
            "g1",
            "Dentist",
            False,
            "Clinic",
        )
        assert line.start == datetime(2026, 9, 26, 7, 30, tzinfo=UTC)
        assert line.end == datetime(2026, 9, 26, 8, 0, tzinfo=UTC)
        all_day = event_line(
            {"id": "a1", "summary": "Fair", "start": {"date": "2026-09-27"}}, paris
        )
        assert all_day is not None and all_day.all_day and all_day.end is None
        assert all_day.start == datetime(2026, 9, 27, 0, 0, tzinfo=paris)

    def test_an_event_without_a_start_or_a_title_is_read_as_far_as_it_goes(self) -> None:
        assert event_line({"id": "x", "summary": "No start"}, UTC) is None
        untitled = event_line({"start": {"dateTime": "2026-09-26T09:30:00Z"}}, UTC)
        assert untitled is not None and (untitled.id, untitled.title) == (None, "Untitled")
