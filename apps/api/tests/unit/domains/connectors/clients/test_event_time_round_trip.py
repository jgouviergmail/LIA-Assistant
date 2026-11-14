"""A time written to a calendar is read back the instant it was meant (ADR-380).

A person says a time on THEIR wall. It crosses the Tools' service or a confirmed
draft, becomes typed bounds, leaves through a provider client, is stored by the
provider, comes back through the client's normaliser and reaches the screen as an
instant. Every hour LIA lost was lost between two of those steps, each of them
right on its own — so this file checks none of them: it checks the JOURNEY, on
providers simulated from their own reference (``tests/helpers/calendar_providers``).

The oracle is spelled in UTC by hand, case by case, never computed by the code
under test. And no case stands in UTC alone: the defect of 2026-11-12 — a wall
time stamped ``Z`` on its way to Google — is invisible there.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator, Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest

from src.domains.agents.calendar.event_times import timed_bounds, updated_bounds
from src.domains.agents.tools.calendar_draft_execution import (
    execute_event_draft,
    execute_event_update_draft,
)
from src.domains.connectors.active_client import ActiveClient
from src.domains.connectors.clients.event_bounds import EventBounds, bounds_of, change_of
from src.domains.connectors.models import ConnectorType
from src.domains.workbench import calendar_service
from src.domains.workbench.calendar_times import provider_time
from src.domains.workbench.schemas.calendar import EventChange, NewEvent
from tests.helpers.calendar_providers import (
    PROVIDERS,
    CalDavCollection,
    CalendarProvider,
    GoogleCalendar,
    Refused,
    connected,
    google_moment,
    graph_moment,
    ical_moment,
)

pytestmark = pytest.mark.unit

USER = UUID("00000000-0000-4000-8000-000000000003")
KEY = "22222222-2222-4222-8222-222222222222"


def _utc(year: int, month: int, day: int, hour: int, minute: int) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


@dataclass(frozen=True)
class _Meant:
    """What a person writes on their wall, and the instants it means — spelled by hand."""

    zone: str
    start: str
    end: str
    starts: datetime
    ends: datetime


def _an_hour(zone: str, start: str, starts: datetime) -> _Meant:
    """An hour on an ordinary day: it ends an hour later, on the wall as in fact."""
    end = (datetime.fromisoformat(start) + timedelta(hours=1)).isoformat(timespec="minutes")
    return _Meant(zone, start, end, starts, starts + timedelta(hours=1))


#: Half past nine, where the clocks are an hour, five and a half, or half a day from UTC.
ORDINARY = [
    _an_hour("Europe/Paris", "2026-11-27T09:30", _utc(2026, 11, 27, 8, 30)),  # winter, +1
    _an_hour("Europe/Paris", "2026-07-14T09:30", _utc(2026, 7, 14, 7, 30)),  # summer, +2
    _an_hour("America/New_York", "2026-11-27T09:30", _utc(2026, 11, 27, 14, 30)),  # EST, -5
    _an_hour("America/New_York", "2026-07-14T09:30", _utc(2026, 7, 14, 13, 30)),  # EDT, -4
    _an_hour("Asia/Kolkata", "2026-11-27T09:30", _utc(2026, 11, 27, 4, 0)),  # +5:30
    _an_hour("Pacific/Auckland", "2026-11-27T09:30", _utc(2026, 11, 26, 20, 30)),  # +13
    _an_hour("Pacific/Auckland", "2026-07-14T09:30", _utc(2026, 7, 13, 21, 30)),  # +12
    _an_hour("UTC", "2026-11-27T09:30", _utc(2026, 11, 27, 9, 30)),
]

#: The two nights a year a zone alone does not place a time, north and south.
NIGHTS = [
    # Paris, 29 March 2026, 02:00 -> 03:00: half past two is skipped, read at +1.
    _Meant(
        "Europe/Paris",
        "2026-03-29T02:30",
        "2026-03-29T05:30",
        _utc(2026, 3, 29, 1, 30),
        _utc(2026, 3, 29, 3, 30),
    ),
    # Paris, 25 October 2026, 03:00 -> 02:00: half past two shows twice, the first at +2.
    _Meant(
        "Europe/Paris",
        "2026-10-25T02:30",
        "2026-10-25T05:30",
        _utc(2026, 10, 25, 0, 30),
        _utc(2026, 10, 25, 4, 30),
    ),
    # ... and its SECOND passage, which only an offset can say.
    _Meant(
        "Europe/Paris",
        "2026-10-25T02:30:00+01:00",
        "2026-10-25T05:30:00+01:00",
        _utc(2026, 10, 25, 1, 30),
        _utc(2026, 10, 25, 4, 30),
    ),
    # New York, 8 March 2026, 02:00 -> 03:00: skipped, read at -5.
    _Meant(
        "America/New_York",
        "2026-03-08T02:30",
        "2026-03-08T05:30",
        _utc(2026, 3, 8, 7, 30),
        _utc(2026, 3, 8, 9, 30),
    ),
    # New York, 1 November 2026, 02:00 -> 01:00: half past one shows twice, the first at -4.
    _Meant(
        "America/New_York",
        "2026-11-01T01:30",
        "2026-11-01T04:30",
        _utc(2026, 11, 1, 5, 30),
        _utc(2026, 11, 1, 9, 30),
    ),
    # Auckland, 5 April 2026, 03:00 -> 02:00: shown twice, the first at +13.
    _Meant(
        "Pacific/Auckland",
        "2026-04-05T02:30",
        "2026-04-05T05:30",
        _utc(2026, 4, 4, 13, 30),
        _utc(2026, 4, 4, 17, 30),
    ),
    # Auckland, 27 September 2026, 02:00 -> 03:00: skipped, read at +12.
    _Meant(
        "Pacific/Auckland",
        "2026-09-27T02:30",
        "2026-09-27T05:30",
        _utc(2026, 9, 26, 14, 30),
        _utc(2026, 9, 26, 16, 30),
    ),
]


def _named(meant: _Meant) -> str:
    return f"{meant.zone} {meant.start}"


def _bounds(meant: _Meant) -> EventBounds:
    return bounds_of(meant.start, meant.end, ZoneInfo(meant.zone), all_day=False)


def _door(client: Any, kind: ConnectorType) -> Any:
    """The Tools' service opening ``client`` as the account's calendar."""

    @contextlib.asynccontextmanager
    async def opened(tool: Any, user_id: Any, container: Any = None) -> AsyncIterator[ActiveClient]:
        yield ActiveClient(client=client, connector_type=kind, preferred_name=None)

    return patch.object(calendar_service, "open_tool_client", opened)


@contextlib.contextmanager
def _resolved(client: Any, kind: ConnectorType) -> Iterator[None]:
    """A confirmed draft finding ``client`` as the account's calendar."""
    with (
        patch(
            "src.domains.connectors.provider_resolver.resolve_client_for_category",
            AsyncMock(return_value=(client, kind)),
        ),
        patch(
            "src.domains.agents.tools.calendar_draft_execution._resolve_calendar_id",
            AsyncMock(return_value="primary"),
        ),
    ):
        yield


def _screen(edge: Mapping[str, Any]) -> datetime | date:
    """What the calendar screen is given for one bound of an event read from its provider."""
    read = provider_time(edge)
    assert read is not None
    all_day, value = read
    return date.fromisoformat(value) if all_day else datetime.fromisoformat(value)


async def _is_when_it_was_meant(
    client: Any, provider: CalendarProvider, event_id: str, meant: _Meant
) -> None:
    """The event is the hour that was meant: at its provider, and read back for the screen."""
    assert provider.refused == []
    assert provider.held(event_id) == (meant.starts, meant.ends)
    read = await client.get_event(event_id, "primary")
    assert (_screen(read["start"]), _screen(read["end"])) == (meant.starts, meant.ends)


async def _an_event(client: Any, zone: str) -> str:
    """An event of another year and hour, there to be moved."""
    made = await client.create_event(
        "Visit", bounds_of("2027-06-01T15:00", "2027-06-01T16:00", ZoneInfo(zone), all_day=False)
    )
    return str(made["id"])


@pytest.mark.parametrize("provider", PROVIDERS)
@pytest.mark.parametrize("meant", ORDINARY, ids=_named)
class TestFromTheTools:
    """The calendar screen sends a wall time and a zone id; it is answered an instant."""

    async def test_a_new_event_starts_when_it_was_meant(self, provider: str, meant: _Meant) -> None:
        request = NewEvent.model_validate(
            {
                "calendar_id": "primary",
                "summary": "Visit",
                "start": meant.start,
                "end": meant.end,
                "all_day": False,
                "timezone": meant.zone,
                "idempotency_key": KEY,
            }
        )

        async with connected(provider, USER) as (client, held):
            with _door(client, held.kind):
                made = await calendar_service.create_event(USER, request)

            assert datetime.fromisoformat(made.start) == meant.starts
            await _is_when_it_was_meant(client, held, made.id, meant)

    async def test_an_event_moved_starts_when_it_was_meant(
        self, provider: str, meant: _Meant
    ) -> None:
        async with connected(provider, USER) as (client, held):
            event_id = await _an_event(client, meant.zone)
            request = EventChange.model_validate(
                {
                    "calendar_id": "primary",
                    "event_id": event_id,
                    "start": meant.start,
                    "end": meant.end,
                    "all_day": False,
                    "timezone": meant.zone,
                }
            )

            with _door(client, held.kind):
                moved = await calendar_service.update_event(USER, request)

            assert datetime.fromisoformat(moved.start) == meant.starts
            await _is_when_it_was_meant(client, held, event_id, meant)


@pytest.mark.parametrize("provider", PROVIDERS)
@pytest.mark.parametrize("meant", ORDINARY, ids=_named)
class TestFromAConfirmedDraft:
    """The assistant's tool re-localises what the model gave; the draft's executor writes it."""

    async def test_a_new_event_starts_when_it_was_meant(self, provider: str, meant: _Meant) -> None:
        start, end = timed_bounds(f"{meant.start}:00", f"{meant.end}:00", meant.zone)
        draft = {
            "summary": "Visit",
            "start_datetime": start,
            "end_datetime": end,
            "timezone": meant.zone,
        }

        async with connected(provider, USER) as (client, held):
            with _resolved(client, held.kind):
                done = await execute_event_draft(draft, USER, MagicMock())

            await _is_when_it_was_meant(client, held, str(done["event_id"]), meant)

    async def test_an_event_moved_starts_when_it_was_meant(
        self, provider: str, meant: _Meant
    ) -> None:
        async with connected(provider, USER) as (client, held):
            event_id = await _an_event(client, meant.zone)
            current = await client.get_event(event_id, "primary")
            start, end, all_day = updated_bounds(
                f"{meant.start}:00", f"{meant.end}:00", meant.zone, None, current
            )
            draft = {
                "event_id": event_id,
                "start_datetime": start,
                "end_datetime": end,
                "timezone": meant.zone,
                "all_day": all_day,
            }

            with _resolved(client, held.kind):
                await execute_event_update_draft(draft, USER, MagicMock())

            await _is_when_it_was_meant(client, held, event_id, meant)


@pytest.mark.parametrize("provider", PROVIDERS)
@pytest.mark.parametrize("meant", ORDINARY, ids=_named)
class TestOneSideAlone:
    """A change may name one side only: the other stays the instant it was."""

    async def test_a_start_moved_alone_leaves_the_end_where_it_was(
        self, provider: str, meant: _Meant
    ) -> None:
        async with connected(provider, USER) as (client, held):
            event_id = await _an_event(client, meant.zone)
            _, was_ending = held.held(event_id)

            await client.update_event(
                event_id,
                bounds=change_of(f"{meant.start}:00", None, ZoneInfo(meant.zone), all_day=None),
            )

            assert held.refused == []
            assert held.held(event_id) == (meant.starts, was_ending)


async def test_an_offset_the_model_got_wrong_is_still_the_persons_own_hour() -> None:
    """The model wrote « Z » for a Paris morning: the hour it names is the person's."""
    meant = _an_hour("Europe/Paris", "2026-11-27T09:30", _utc(2026, 11, 27, 8, 30))
    start, end = timed_bounds("2026-11-27T09:30:00Z", "2026-11-27T10:30:00Z", meant.zone)
    draft = {
        "summary": "Visit",
        "start_datetime": start,
        "end_datetime": end,
        "timezone": meant.zone,
    }

    async with connected("google", USER) as (client, held):
        with _resolved(client, held.kind):
            done = await execute_event_draft(draft, USER, MagicMock())

        await _is_when_it_was_meant(client, held, str(done["event_id"]), meant)


@pytest.mark.parametrize("provider", PROVIDERS)
@pytest.mark.parametrize("meant", NIGHTS, ids=_named)
class TestTheNightsTheClocksChange:
    """Where a zone alone does not place a time, the provider is told the instant."""

    async def test_a_new_event_is_the_instant_our_rule_names(
        self, provider: str, meant: _Meant
    ) -> None:
        async with connected(provider, USER) as (client, held):
            made = await client.create_event("Night", _bounds(meant))

            await _is_when_it_was_meant(client, held, str(made["id"]), meant)

    async def test_an_event_moved_there_is_that_instant(self, provider: str, meant: _Meant) -> None:
        async with connected(provider, USER) as (client, held):
            event_id = await _an_event(client, meant.zone)

            await client.update_event(event_id, bounds=_bounds(meant))

            await _is_when_it_was_meant(client, held, event_id, meant)

    async def test_its_sides_moved_there_are_those_instants(
        self, provider: str, meant: _Meant
    ) -> None:
        async with connected(provider, USER) as (client, held):
            event_id = await _an_event(client, meant.zone)

            await client.update_event(
                event_id,
                bounds=change_of(meant.start, meant.end, ZoneInfo(meant.zone), all_day=None),
            )

            await _is_when_it_was_meant(client, held, event_id, meant)


#: Half past nine on 27 November 2026, on each of these walls.
_THAT_MORNING = {
    "Europe/Paris": _utc(2026, 11, 27, 8, 30),
    "America/New_York": _utc(2026, 11, 27, 14, 30),
    "Pacific/Auckland": _utc(2026, 11, 26, 20, 30),
    "UTC": _utc(2026, 11, 27, 9, 30),
}


@pytest.mark.parametrize("provider", PROVIDERS)
@pytest.mark.parametrize("zone", sorted(_THAT_MORNING))
class TestDays:
    """A day is no instant: no zone moves it, however far from UTC the person lives."""

    async def test_an_all_day_event_keeps_its_days(self, provider: str, zone: str) -> None:
        request = NewEvent.model_validate(
            {
                "calendar_id": "primary",
                "summary": "Congress",
                "start": "2026-11-03",
                "end": "2026-11-06",
                "all_day": True,
                "timezone": zone,
                "idempotency_key": KEY,
            }
        )

        async with connected(provider, USER) as (client, held):
            with _door(client, held.kind):
                made = await calendar_service.create_event(USER, request)

            assert held.refused == []
            assert held.held(made.id) == (date(2026, 11, 3), date(2026, 11, 6))
            assert (made.all_day, made.start, made.end) == (True, "2026-11-03", "2026-11-06")
            read = await client.get_event(made.id, "primary")
            assert (_screen(read["start"]), _screen(read["end"])) == (
                date(2026, 11, 3),
                date(2026, 11, 6),
            )

    async def test_a_timed_event_becomes_days_and_times_again(
        self, provider: str, zone: str
    ) -> None:
        there = ZoneInfo(zone)
        async with connected(provider, USER) as (client, held):
            event_id = await _an_event(client, zone)

            await client.update_event(
                event_id, bounds=bounds_of("2026-11-03", "2026-11-06", there, all_day=True)
            )
            assert held.held(event_id) == (date(2026, 11, 3), date(2026, 11, 6))

            await client.update_event(
                event_id,
                bounds=bounds_of("2026-11-27T09:30", "2026-11-27T10:30", there, all_day=False),
            )
            starts = _THAT_MORNING[zone]
            assert held.refused == []
            assert held.held(event_id) == (starts, starts + timedelta(hours=1))


class TestAWholeSeries:
    """A series moved takes the new hour from its own first day, on the person's wall."""

    #: A Monday series at eight in Paris — still Sunday evening on the calendar's own wall.
    _MASTER: dict[str, Any] = {
        "summary": "Standup",
        "start": {"dateTime": "2027-01-04T08:00:00", "timeZone": "Europe/Paris"},
        "end": {"dateTime": "2027-01-04T08:30:00", "timeZone": "Europe/Paris"},
        "recurrence": ["RRULE:FREQ=WEEKLY;BYDAY=MO"],
    }
    _OCCURRENCE: dict[str, Any] = {
        "summary": "Standup",
        "start": {"dateTime": "2027-01-11T08:00:00", "timeZone": "Europe/Paris"},
        "end": {"dateTime": "2027-01-11T08:30:00", "timeZone": "Europe/Paris"},
        "recurringEventId": "series",
    }
    #: A quarter past ten to eleven, Paris, on the series' first Monday.
    _MOVED = (_utc(2027, 1, 4, 9, 15), _utc(2027, 1, 4, 10, 0))

    def _held(self, provider: CalendarProvider) -> GoogleCalendar:
        assert isinstance(provider, GoogleCalendar)
        provider.events.update(series=dict(self._MASTER), occurrence=dict(self._OCCURRENCE))
        return provider

    async def test_from_the_tools(self) -> None:
        request = EventChange.model_validate(
            {
                "calendar_id": "primary",
                "event_id": "occurrence",
                "scope": "series",
                "start": "2027-01-11T10:15",
                "end": "2027-01-11T11:00",
                "all_day": False,
                "timezone": "Europe/Paris",
            }
        )

        async with connected("google", USER) as (client, provider):
            google = self._held(provider)
            with _door(client, google.kind):
                await calendar_service.update_event(USER, request)

            assert google.refused == []
            assert google.held("series") == self._MOVED

    async def test_from_a_confirmed_draft(self) -> None:
        start, end = timed_bounds("2027-01-11T10:15:00", "2027-01-11T11:00:00", "Europe/Paris")
        draft = {
            "event_id": "occurrence",
            "scope": "series",
            "moves_series": True,
            "start_datetime": start,
            "end_datetime": end,
            "timezone": "Europe/Paris",
        }

        async with connected("google", USER) as (client, provider):
            google = self._held(provider)
            with _resolved(client, google.kind):
                await execute_event_update_draft(draft, USER, MagicMock())

            assert google.refused == []
            assert google.held("series") == self._MOVED


class TestTheSimulatorsReadAsTheirReferenceSays:
    """A simulator that accepts anything proves nothing: each one is shown to refuse."""

    def test_google_reads_an_offset_before_the_zone(self) -> None:
        # The defect of 2026-11-12: half past nine on a Paris wall, stamped « Z » on its
        # way, is half past nine in UTC — half past ten in Paris.
        stamped = {"dateTime": "2026-11-27T09:30:00Z", "timeZone": "Europe/Paris"}

        assert google_moment(stamped) == _utc(2026, 11, 27, 9, 30)

    @pytest.mark.parametrize(
        "edge",
        [
            {"dateTime": "2026-11-27T09:30:00"},
            {"dateTime": "2026-11-27T09:30:00", "timeZone": "Mars/Olympus"},
            {"dateTime": "2026-10-25T02:30:00", "timeZone": "Europe/Paris"},
            {"date": "2026-11-27", "dateTime": "2026-11-27T09:30:00Z"},
        ],
    )
    def test_google_refuses_what_its_reference_does_not_define(self, edge: dict[str, str]) -> None:
        with pytest.raises(Refused):
            google_moment(edge)

    @pytest.mark.parametrize(
        "edge",
        [
            {"dateTime": "2026-11-27T09:30:00Z", "timeZone": "Europe/Paris"},
            {"dateTime": "2026-11-27T09:30:00+01:00", "timeZone": "Europe/Paris"},
            {"dateTime": "2026-03-29T02:30:00", "timeZone": "Europe/Paris"},
        ],
    )
    def test_graph_refuses_an_offset_and_an_hour_no_zone_places(self, edge: dict[str, str]) -> None:
        with pytest.raises(Refused):
            graph_moment({"start": edge}, "start")

    def test_caldav_reads_an_abbreviation_as_the_zone_of_that_name(self) -> None:
        # « EST » is a zone of its own, five hours behind all year: a New York summer
        # morning named by it lands an hour late.
        text = _ics("DTSTART;TZID=EST:20260714T093000", "DTEND;TZID=EST:20260714T103000")

        assert ical_moment(text, "DTSTART") == _utc(2026, 7, 14, 14, 30)

    @pytest.mark.parametrize(
        ("start", "end"),
        [
            ("DTSTART:20261127T093000", "DTEND:20261127T103000"),
            ("DTSTART;TZID=Europe/Paris:20261127T083000Z", "DTEND:20261127T093000Z"),
            ("DTSTART;TZID=Europe/Paris:20261025T023000", "DTEND:20261025T043000Z"),
        ],
    )
    def test_caldav_refuses_a_time_no_zone_places(self, start: str, end: str) -> None:
        collection = CalDavCollection()

        with pytest.raises(Refused):
            collection.put(_ics(start, end))

        assert len(collection.refused) == 1


def _ics(start: str, end: str) -> str:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//lia//test//EN",
        "BEGIN:VEVENT",
        "UID:probe-1",
        "SUMMARY:x",
        start,
        end,
        "END:VEVENT",
        "END:VCALENDAR",
        "",
    ]
    return "\r\n".join(lines)
