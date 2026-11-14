"""All-day events written on the three calendar providers, and windows drained (ADR-369, D2).

All three READ an all-day event (Google's ``start.date`` / exclusive ``end.date``);
none could WRITE one — Google's update only kept an existing shape. Day bounds
(``event_bounds.DayBounds``) now write it the way each provider stores it, in the
convention the clients read, so an event read and written back keeps its days. A
calendar window is read whole up to a published bound, and a cut says so.

The clients are handed BOUNDS, never text (ADR-380): a wall time travels with
its zone to the provider, and nothing on the way stamps another one on it.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID
from zoneinfo import ZoneInfo

import httpx
import pytest
import vobject

from src.domains.connectors.clients.apple_calendar_client import AppleCalendarClient
from src.domains.connectors.clients.event_bounds import bounds_of, change_of
from src.domains.connectors.clients.google_calendar_client import GoogleCalendarClient
from src.domains.connectors.clients.microsoft_calendar_client import MicrosoftCalendarClient
from src.domains.connectors.clients.normalizers.all_day import (
    all_day_dates,
    exclusive_end,
    inclusive_last_day,
    is_all_day,
)
from src.domains.connectors.schemas import ConnectorCredentials

pytestmark = pytest.mark.unit

USER = UUID("00000000-0000-4000-8000-000000000002")
_KEY = "draft:all-day"
_UTC = ZoneInfo("UTC")


def _credentials() -> ConnectorCredentials:
    return ConnectorCredentials(
        access_token="token",
        refresh_token="refresh",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )


class _Recorder:
    def __init__(self, answer: Callable[[httpx.Request], httpx.Response]) -> None:
        self.answer = answer
        self.calls: list[tuple[str, str, Any, dict[str, str]]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        self.calls.append(
            (request.method, request.url.path, body, dict(request.url.params.multi_items()))
        )
        return self.answer(request)


async def _drive(client: Any, recorder: _Recorder, call: Callable[[], Any]) -> Any:
    async with httpx.AsyncClient(transport=httpx.MockTransport(recorder)) as http:
        client._http_client = http
        with (
            patch.object(client, "_rate_limit", AsyncMock()),
            patch.object(client, "_is_circuit_breaker_enabled", return_value=False),
            patch("asyncio.sleep", AsyncMock()),
        ):
            return await call()


class TestTheConvention:
    def test_one_day_ends_the_next_day(self) -> None:
        assert all_day_dates("2026-11-03", "2026-11-04") == (date(2026, 11, 3), date(2026, 11, 4))
        assert exclusive_end(date(2026, 11, 3)) == date(2026, 11, 4)
        assert inclusive_last_day(date(2026, 11, 4)) == date(2026, 11, 3)

    @pytest.mark.parametrize(
        ("start", "end"),
        [
            ("2026-11-03", "2026-11-03"),
            ("2026-11-04", "2026-11-03"),
            ("tomorrow", "2026-11-04"),
            (None, "2026-11-04"),
        ],
    )
    def test_an_empty_or_backwards_range_is_refused(self, start: str | None, end: str) -> None:
        with pytest.raises(ValueError):
            all_day_dates(start, end)

    def test_a_datetime_names_its_day(self) -> None:
        assert all_day_dates("2026-11-03T00:00:00", "2026-11-04T00:00:00+01:00")[1] == date(
            2026, 11, 4
        )

    def test_the_read_shape_is_recognised(self) -> None:
        assert is_all_day({"start": {"date": "2026-11-03"}})
        assert not is_all_day({"start": {"dateTime": "2026-11-03T10:00:00Z"}})


class TestGoogle:
    async def test_a_three_day_event_is_written_with_dates_only(self) -> None:
        client = GoogleCalendarClient(USER, _credentials(), MagicMock())
        recorder = _Recorder(lambda request: httpx.Response(200, json={"id": "e1"}))

        await _drive(
            client,
            recorder,
            lambda: client.create_event(
                "Congress",
                bounds_of("2026-11-03", "2026-11-06", _UTC, all_day=True),
                idempotency_key=_KEY,
            ),
        )

        body = recorder.calls[0][2]
        assert body["start"] == {"date": "2026-11-03"}
        assert body["end"] == {"date": "2026-11-06"}

    async def test_a_timed_event_becomes_all_day_and_back(self) -> None:
        client = GoogleCalendarClient(USER, _credentials(), MagicMock())

        def answer(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "id": "e1",
                    "start": {"dateTime": "2026-11-03T09:00:00Z", "timeZone": "UTC"},
                    "end": {"dateTime": "2026-11-03T10:00:00Z", "timeZone": "UTC"},
                },
            )

        recorder = _Recorder(answer)
        await _drive(
            client,
            recorder,
            lambda: client.update_event(
                "e1", bounds=bounds_of("2026-11-03", "2026-11-04", _UTC, all_day=True)
            ),
        )
        patched = recorder.calls[-1][2]
        # The other half of the provider's start object is CLEARED, never left beside.
        assert patched["start"] == {"date": "2026-11-03", "dateTime": None, "timeZone": None}

        await _drive(
            client,
            recorder,
            lambda: client.update_event(
                "e1",
                bounds=bounds_of("2026-11-03T14:00:00", "2026-11-03T15:00:00", _UTC, all_day=False),
            ),
        )
        patched = recorder.calls[-1][2]
        assert patched["start"] == {
            "date": None,
            "dateTime": "2026-11-03T14:00:00",
            "timeZone": "UTC",
        }

    async def test_sides_given_to_an_all_day_event_name_their_days(self) -> None:
        # Sides keep the shape the event HAS: an all-day event's dates stay dates.
        client = GoogleCalendarClient(USER, _credentials(), MagicMock())
        recorder = _Recorder(
            lambda request: httpx.Response(
                200,
                json={"id": "e1", "start": {"date": "2026-11-03"}, "end": {"date": "2026-11-04"}},
            )
        )

        await _drive(
            client,
            recorder,
            lambda: client.update_event(
                "e1",
                bounds=change_of(
                    "2026-11-05T09:30:00", "2026-11-06T09:30:00", _PARIS_ZONE, all_day=None
                ),
            ),
        )

        patched = recorder.calls[-1][2]
        assert (patched["start"], patched["end"]) == (
            {"date": "2026-11-05"},
            {"date": "2026-11-06"},
        )


class TestGraph:
    async def test_all_day_is_midnight_bounds_in_the_events_zone(self) -> None:
        client = MicrosoftCalendarClient(USER, _credentials(), MagicMock())
        recorder = _Recorder(lambda request: httpx.Response(201, json={"id": "g1"}))

        await _drive(
            client,
            recorder,
            lambda: client.create_event(
                "Congress",
                bounds_of("2026-03-29", "2026-03-30", ZoneInfo("Europe/Berlin"), all_day=True),
                idempotency_key=_KEY,
            ),
        )

        body = recorder.calls[0][2]
        assert body["isAllDay"] is True
        # The DST weekend changes nothing: dates are not instants.
        assert body["start"] == {"dateTime": "2026-03-29T00:00:00", "timeZone": "Europe/Berlin"}
        assert body["end"] == {"dateTime": "2026-03-30T00:00:00", "timeZone": "Europe/Berlin"}

    async def test_update_switches_the_flag_with_the_bounds(self) -> None:
        client = MicrosoftCalendarClient(USER, _credentials(), MagicMock())
        recorder = _Recorder(lambda request: httpx.Response(200, json={"id": "g1"}))

        await _drive(
            client,
            recorder,
            lambda: client.update_event(
                "g1",
                bounds=bounds_of("2026-11-03T09:00:00", "2026-11-03T10:00:00", _UTC, all_day=False),
            ),
        )

        body = recorder.calls[0][2]
        assert body["isAllDay"] is False
        assert body["start"] == {"dateTime": "2026-11-03T09:00:00", "timeZone": "UTC"}


_PARIS = "Europe/Paris"
_PARIS_ZONE = ZoneInfo(_PARIS)
#: Nine thirty on a Paris wall in winter: 08:30 UTC, never 09:30 UTC.
_WALL_START, _WALL_END = "2026-11-27T09:30:00", "2026-11-27T10:30:00"


class TestWallTimesKeepTheirZone:
    """What the calendar screen sends is a wall time and its zone (ADR-369, spec §14).

    A provider reads an offset before it reads a zone: a wall time stamped ``Z``
    on the way is that hour in UTC, and the event lands an hour late in Paris
    (two in summer) — seen in production on every event moved or edited by hand.
    """

    @staticmethod
    def _timed(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "e1",
                "start": {"dateTime": "2026-11-27T14:00:00+01:00", "timeZone": _PARIS},
                "end": {"dateTime": "2026-11-27T15:00:00+01:00", "timeZone": _PARIS},
            },
        )

    async def test_google_creates_an_event_at_its_wall_time(self) -> None:
        client = GoogleCalendarClient(USER, _credentials(), MagicMock())
        recorder = _Recorder(lambda request: httpx.Response(200, json={"id": "e1"}))

        await _drive(
            client,
            recorder,
            lambda: client.create_event(
                "Visit",
                bounds_of(_WALL_START, _WALL_END, _PARIS_ZONE, all_day=False),
                idempotency_key=_KEY,
            ),
        )

        body = recorder.calls[0][2]
        assert body["start"] == {"dateTime": _WALL_START, "timeZone": _PARIS}
        assert body["end"] == {"dateTime": _WALL_END, "timeZone": _PARIS}

    async def test_google_moves_an_event_to_the_wall_time_it_is_given(self) -> None:
        client = GoogleCalendarClient(USER, _credentials(), MagicMock())
        recorder = _Recorder(self._timed)

        await _drive(
            client,
            recorder,
            lambda: client.update_event(
                "e1", bounds=change_of(_WALL_START, _WALL_END, _PARIS_ZONE, all_day=None)
            ),
        )

        method, _path, patched, _params = recorder.calls[-1]
        assert method == "PATCH"
        assert patched["start"] == {"dateTime": _WALL_START, "timeZone": _PARIS}
        assert patched["end"] == {"dateTime": _WALL_END, "timeZone": _PARIS}

    async def test_google_turns_a_day_into_the_wall_times_it_is_given(self) -> None:
        client = GoogleCalendarClient(USER, _credentials(), MagicMock())
        recorder = _Recorder(
            lambda request: httpx.Response(
                200,
                json={"id": "e1", "start": {"date": "2026-11-27"}, "end": {"date": "2026-11-28"}},
            )
        )

        await _drive(
            client,
            recorder,
            lambda: client.update_event(
                "e1", bounds=bounds_of(_WALL_START, _WALL_END, _PARIS_ZONE, all_day=False)
            ),
        )

        patched = recorder.calls[-1][2]
        assert patched["start"] == {"date": None, "dateTime": _WALL_START, "timeZone": _PARIS}
        assert patched["end"] == {"date": None, "dateTime": _WALL_END, "timeZone": _PARIS}

    @pytest.mark.parametrize(
        "written",
        ["2026-11-27T09:30:00+01:00", "2026-11-27T08:30:00Z", "2026-11-27T03:30:00-05:00"],
    )
    async def test_google_is_told_an_instant_as_the_wall_time_of_its_zone(
        self, written: str
    ) -> None:
        # The assistant's path may hand a time WITH an offset: it names an instant,
        # and whatever offset spelt it, the person's wall shows 09:30 at that instant.
        client = GoogleCalendarClient(USER, _credentials(), MagicMock())
        recorder = _Recorder(self._timed)

        await _drive(
            client,
            recorder,
            lambda: client.update_event(
                "e1", bounds=change_of(written, None, _PARIS_ZONE, all_day=None)
            ),
        )

        patched = recorder.calls[-1][2]
        assert patched["start"] == {"dateTime": _WALL_START, "timeZone": _PARIS}

    async def test_graph_moves_an_event_to_the_wall_time_it_is_given(self) -> None:
        client = MicrosoftCalendarClient(USER, _credentials(), MagicMock())
        recorder = _Recorder(lambda request: httpx.Response(200, json={"id": "g1"}))

        await _drive(
            client,
            recorder,
            lambda: client.update_event(
                "g1", bounds=change_of(_WALL_START, _WALL_END, _PARIS_ZONE, all_day=None)
            ),
        )

        body = recorder.calls[-1][2]
        assert body["start"] == {"dateTime": _WALL_START, "timeZone": _PARIS}
        assert body["end"] == {"dateTime": _WALL_END, "timeZone": _PARIS}

    async def test_caldav_moves_an_event_to_the_wall_time_it_is_given(self) -> None:
        calendar = _CalDav()
        client, patches = _apple(calendar)
        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patch(
                "src.domains.connectors.clients.apple_calendar_client.normalize_vevent",
                return_value={"id": "apple-1"},
            ),
        ):
            await client.update_event(
                "apple-1", bounds=change_of(_WALL_START, _WALL_END, _PARIS_ZONE, all_day=None)
            )

        ics = vobject.readOne(calendar.saves[-1]["ics"])
        start, end = ics.vevent.dtstart.value, ics.vevent.dtend.value
        # Read back as the instant it names: 09:30 on the Paris wall is 08:30 UTC.
        assert start.astimezone(UTC) == datetime(2026, 11, 27, 8, 30, tzinfo=UTC)
        assert end.astimezone(UTC) == datetime(2026, 11, 27, 9, 30, tzinfo=UTC)
        assert (start.hour, start.minute) == (9, 30)


#: The two nights of 2026 in Paris, as (written, its end, what names the instant).
_NIGHTS = [
    # 29 March, 02:00 -> 03:00: skipped, read with the offset before the change.
    ("2026-03-29T02:30:00", "2026-03-29T05:30:00", "2026-03-29T02:30:00+01:00"),
    # 25 October, 03:00 -> 02:00: shown twice, its first passage...
    ("2026-10-25T02:30:00", "2026-10-25T05:30:00", "2026-10-25T02:30:00+02:00"),
    # ... and its second, which only an instant can say.
    ("2026-10-25T02:30:00+01:00", "2026-10-25T05:30:00", "2026-10-25T02:30:00+01:00"),
]
#: An event as an iCloud calendar hands it over: its zone named, and defined beside it.
_FROM_THE_SERVER = "\r\n".join(
    [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//lia//test//EN",
        "BEGIN:VTIMEZONE",
        "TZID:America/New_York",
        "BEGIN:STANDARD",
        "DTSTART:20071104T020000",
        "RRULE:FREQ=YEARLY;BYDAY=1SU;BYMONTH=11",
        "TZOFFSETFROM:-0400",
        "TZOFFSETTO:-0500",
        "END:STANDARD",
        "BEGIN:DAYLIGHT",
        "DTSTART:20070311T020000",
        "RRULE:FREQ=YEARLY;BYDAY=2SU;BYMONTH=3",
        "TZOFFSETFROM:-0500",
        "TZOFFSETTO:-0400",
        "END:DAYLIGHT",
        "END:VTIMEZONE",
        "BEGIN:VEVENT",
        "UID:apple-1",
        "SUMMARY:Old",
        "DTSTART;TZID=America/New_York:20270601T150000",
        "DTEND;TZID=America/New_York:20270601T160000",
        "END:VEVENT",
        "END:VCALENDAR",
        "",
    ]
)


def _event_lines(ics: str, name: str) -> list[str]:
    """The lines ``name`` of the VEVENT (a VTIMEZONE has a DTSTART of its own)."""
    lines = ics.replace("\r\n", "\n").split("\n")
    return [line for line in lines[lines.index("BEGIN:VEVENT") :] if line.startswith(name)]


class TestWhereTheZoneAloneIsNotEnough:
    """An hour the clocks skip or show twice: each provider is told the INSTANT, in its words.

    How a provider places such a wall time is written in none of their references:
    told « 02:30, Europe/Paris », it would follow a rule of its own.
    """

    @pytest.mark.parametrize(("written", "ends", "told"), _NIGHTS)
    async def test_google_is_told_the_offset(self, written: str, ends: str, told: str) -> None:
        client = GoogleCalendarClient(USER, _credentials(), MagicMock())
        recorder = _Recorder(lambda request: httpx.Response(200, json={"id": "e1"}))

        await _drive(
            client,
            recorder,
            lambda: client.create_event(
                "Night", bounds_of(written, ends, _PARIS_ZONE, all_day=False), idempotency_key=_KEY
            ),
        )

        body = recorder.calls[0][2]
        # Google reads an offset before the zone: here that is the very point.
        assert body["start"] == {"dateTime": told, "timeZone": _PARIS}
        # An ordinary hour stays a wall time beside its zone.
        assert body["end"] == {"dateTime": ends, "timeZone": _PARIS}

    @pytest.mark.parametrize(("written", "ends", "told"), _NIGHTS)
    async def test_graph_is_told_the_time_on_the_wall_of_utc(
        self, written: str, ends: str, told: str
    ) -> None:
        client = MicrosoftCalendarClient(USER, _credentials(), MagicMock())
        recorder = _Recorder(lambda request: httpx.Response(201, json={"id": "g1"}))

        await _drive(
            client,
            recorder,
            lambda: client.create_event(
                "Night", bounds_of(written, ends, _PARIS_ZONE, all_day=False), idempotency_key=_KEY
            ),
        )

        body = recorder.calls[0][2]
        in_utc = datetime.fromisoformat(told).astimezone(UTC).replace(tzinfo=None)
        # ``dateTimeTimeZone`` has no offset to say it with.
        assert body["start"] == {"dateTime": in_utc.isoformat(), "timeZone": "UTC"}
        assert body["end"] == {"dateTime": ends, "timeZone": _PARIS}

    @pytest.mark.parametrize(("written", "ends", "told"), _NIGHTS)
    async def test_caldav_is_told_the_time_in_utc(self, written: str, ends: str, told: str) -> None:
        calendar = _CalDav()
        calendar.event.vobject_instance = vobject.readOne(_FROM_THE_SERVER)
        client, patches = _apple(calendar)
        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patch(
                "src.domains.connectors.clients.apple_calendar_client.normalize_vevent",
                return_value={"id": "apple-1"},
            ),
        ):
            await client.update_event(
                "apple-1", bounds=change_of(written, None, _PARIS_ZONE, all_day=None)
            )

        in_utc = datetime.fromisoformat(told).astimezone(UTC)
        # The zone the old start carried is gone with it: a TZID on a time in UTC is invalid.
        assert _event_lines(calendar.saves[-1]["ics"], "DTSTART") == [
            f"DTSTART:{in_utc:%Y%m%dT%H%M%S}Z"
        ]


class TestCalDavNamesAZoneByItsOwnName:
    """vobject writes every update, and names a zone by its winter abbreviation unless told.

    « EST » is the name of ANOTHER zone, five hours behind all year: a server that
    knows it places a New York summer morning an hour late.
    """

    async def test_an_update_names_the_zone_as_a_create_does(self) -> None:
        calendar = _CalDav()
        calendar.event.vobject_instance = vobject.readOne(_FROM_THE_SERVER)
        client, patches = _apple(calendar)
        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patch(
                "src.domains.connectors.clients.apple_calendar_client.normalize_vevent",
                return_value={"id": "apple-1"},
            ),
        ):
            await client.update_event(
                "apple-1",
                bounds=change_of(
                    "2026-07-14T09:30:00",
                    "2026-07-14T10:30:00",
                    ZoneInfo("America/New_York"),
                    all_day=None,
                ),
            )

        ics = calendar.saves[-1]["ics"]
        assert _event_lines(ics, "DTSTART") == ["DTSTART;TZID=America/New_York:20260714T093000"]
        assert _event_lines(ics, "DTEND") == ["DTEND;TZID=America/New_York:20260714T103000"]
        assert "TZID:EST" not in ics and "TZID=EST" not in ics

    async def test_a_create_hands_caldav_the_zone_under_its_name(self) -> None:
        calendar = _CalDav()
        client, patches = _apple(calendar)
        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patch(
                "src.domains.connectors.clients.apple_calendar_client.normalize_vevent",
                return_value={"id": "apple-1"},
            ),
        ):
            await client.create_event(
                "Visit",
                bounds_of(
                    "2026-07-14T09:30:00",
                    "2026-07-14T10:30:00",
                    ZoneInfo("America/New_York"),
                    all_day=False,
                ),
            )

        start = calendar.saves[0]["dtstart"]
        assert (str(start.tzinfo), start.tzinfo.tzid) == ("America/New_York", "America/New_York")
        assert start.astimezone(UTC) == datetime(2026, 7, 14, 13, 30, tzinfo=UTC)


class _CalDavEvent:
    def __init__(self, saves: list[dict[str, Any]]) -> None:
        cal = vobject.iCalendar()
        vevent = cal.add("vevent")
        vevent.add("uid").value = "apple-1"
        vevent.add("summary").value = "Old"
        vevent.add("dtstart").value = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)
        vevent.add("dtend").value = datetime(2026, 11, 3, 10, 0, tzinfo=UTC)
        self.vobject_instance = cal
        self._saves = saves

    async def save(self) -> None:
        self._saves.append({"ics": self.vobject_instance.serialize()})


class _CalDav:
    def __init__(self, found: list[Any] | None = None) -> None:
        self.saves: list[dict[str, Any]] = []
        self.event = _CalDavEvent(self.saves)
        self.found = found
        self.searches: list[dict[str, Any]] = []

    async def save_event(self, **kwargs: Any) -> Any:
        self.saves.append(kwargs)
        saved = MagicMock()
        saved.vobject_instance = None
        return saved

    async def search(self, **kwargs: Any) -> list[Any]:
        self.searches.append(kwargs)
        return self.found if self.found is not None else [self.event]


def _apple(calendar: _CalDav) -> Any:
    client = AppleCalendarClient(USER, MagicMock(), MagicMock())
    breaker = MagicMock(check=AsyncMock(), record_success=AsyncMock(), record_failure=AsyncMock())
    return client, (
        patch.object(client, "_rate_limit", AsyncMock()),
        patch.object(client, "_get_circuit_breaker", return_value=breaker),
        patch.object(client, "_get_calendar", AsyncMock(return_value=calendar)),
        patch("asyncio.sleep", AsyncMock()),
    )


class TestCalDav:
    async def test_all_day_is_a_date_start_and_an_exclusive_date_end(self) -> None:
        calendar = _CalDav()
        client, patches = _apple(calendar)
        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patch(
                "src.domains.connectors.clients.apple_calendar_client.normalize_vevent",
                return_value={"id": "apple-1"},
            ),
        ):
            await client.create_event(
                "Congress", bounds_of("2026-11-03", "2026-11-04", _UTC, all_day=True)
            )
        assert calendar.saves[0]["dtstart"] == date(2026, 11, 3)
        assert calendar.saves[0]["dtend"] == date(2026, 11, 4)
        assert not isinstance(calendar.saves[0]["dtstart"], datetime)

    async def test_an_update_writes_value_date(self) -> None:
        calendar = _CalDav()
        client, patches = _apple(calendar)
        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patch(
                "src.domains.connectors.clients.apple_calendar_client.normalize_vevent",
                return_value={"id": "apple-1"},
            ),
        ):
            await client.update_event(
                "apple-1", bounds=bounds_of("2026-11-03", "2026-11-04", _UTC, all_day=True)
            )
        assert "DTSTART;VALUE=DATE:20261103" in calendar.saves[-1]["ics"]
        assert "DTEND;VALUE=DATE:20261104" in calendar.saves[-1]["ics"]


class TestWindows:
    async def test_google_drains_pages_up_to_the_bound_and_says_it_cut(self) -> None:
        client = GoogleCalendarClient(USER, _credentials(), MagicMock())
        pages = iter(
            [
                {"items": [{"id": f"a{i}"} for i in range(3)], "nextPageToken": "p2"},
                {"items": [{"id": f"b{i}"} for i in range(3)], "nextPageToken": "p3"},
            ]
        )
        recorder = _Recorder(lambda request: httpx.Response(200, json=next(pages)))

        window = await _drive(
            client,
            recorder,
            lambda: client.list_events_window(
                "primary", "2026-11-02T00:00:00Z", "2026-11-09T00:00:00Z", bound=5
            ),
        )

        assert [e["id"] for e in window["events"]] == ["a0", "a1", "a2", "b0", "b1"]
        assert window["truncated"] is True
        assert recorder.calls[1][3]["pageToken"] == "p2"
        assert recorder.calls[0][3]["singleEvents"] == "true"

    async def test_google_reads_a_holiday_calendar_id_whole(self) -> None:
        client = GoogleCalendarClient(USER, _credentials(), MagicMock())
        recorder = _Recorder(lambda request: httpx.Response(200, json={"items": []}))
        window = await _drive(
            client,
            recorder,
            lambda: client.list_events_window(
                "fr.french#holiday@group.v.calendar.google.com",
                "2026-11-02T00:00:00Z",
                "2026-11-09T00:00:00Z",
                bound=5,
            ),
        )
        assert window == {"events": [], "truncated": False}
        assert "%23holiday" in recorder.calls[0][1] or "#holiday" in recorder.calls[0][1]

    async def test_graph_follows_its_own_links_up_to_the_bound(self) -> None:
        client = MicrosoftCalendarClient(USER, _credentials(), MagicMock())
        responses = iter(
            [
                {
                    "value": [{"id": "g1", "subject": "x", "start": {}, "end": {}}],
                    "@odata.nextLink": "https://graph.microsoft.com/v1.0/me/calendarView?$skip=1",
                },
                {"value": [{"id": "g2", "subject": "y", "start": {}, "end": {}}]},
            ]
        )
        recorder = _Recorder(lambda request: httpx.Response(200, json=next(responses)))

        window = await _drive(
            client,
            recorder,
            lambda: client.list_events_window(
                "primary", "2026-11-02T00:00:00Z", "2026-11-09T00:00:00Z", bound=10
            ),
        )

        assert [e["id"] for e in window["events"]] == ["g1", "g2"]
        assert window["truncated"] is False

    async def test_caldav_expands_occurrences_and_cuts_at_the_bound(self) -> None:
        events = []
        for day in range(4):
            event = MagicMock()
            event.vobject_instance = None
            events.append(
                (event, {"id": f"o{day}", "start": {"dateTime": f"2026-11-0{day + 2}T09:00:00Z"}})
            )
        calendar = _CalDav(found=[event for event, _ in events])
        client, patches = _apple(calendar)
        normalised = {id(event): payload for event, payload in events}
        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patch(
                "src.domains.connectors.clients.apple_calendar_client.normalize_vevent",
                side_effect=lambda event: normalised[id(event)],
            ),
        ):
            window = await client.list_events_window(
                "primary", "2026-11-02T00:00:00Z", "2026-11-09T00:00:00Z", bound=3
            )
        assert [e["id"] for e in window["events"]] == ["o0", "o1", "o2"]
        assert window["truncated"] is True
        assert calendar.searches[0]["expand"] is True


class TestWindowsAreBoundedAndOwnTheirRequests:
    """Cold review of L2: a window read never loops for ever, never follows a host
    it was handed, and cuts in TIME order whatever the offsets."""

    async def test_google_stops_at_its_page_ceiling_and_says_it_cut(self) -> None:
        from src.domains.connectors.clients.google_calendar_client import _WINDOW_MAX_PAGES

        client = GoogleCalendarClient(USER, _credentials(), MagicMock())
        recorder = _Recorder(
            lambda request: httpx.Response(200, json={"items": [], "nextPageToken": "again"})
        )

        window = await _drive(
            client,
            recorder,
            lambda: client.list_events_window(
                "primary", "2026-11-02T00:00:00Z", "2026-11-09T00:00:00Z", bound=5
            ),
        )

        assert len(recorder.calls) == _WINDOW_MAX_PAGES
        assert window == {"events": [], "truncated": True}

    async def test_graph_continues_on_its_own_host_whatever_the_link_names(self) -> None:
        client = MicrosoftCalendarClient(USER, _credentials(), MagicMock())
        hosts: list[str] = []
        responses = iter(
            [
                {
                    "value": [{"id": "g1", "subject": "x", "start": {}, "end": {}}],
                    "@odata.nextLink": "https://elsewhere.example/v1.0/me/calendarView?$skip=1",
                },
                {"value": [{"id": "g2", "subject": "y", "start": {}, "end": {}}]},
            ]
        )

        def answer(request: httpx.Request) -> httpx.Response:
            hosts.append(request.url.host)
            return httpx.Response(200, json=next(responses))

        recorder = _Recorder(answer)
        window = await _drive(
            client,
            recorder,
            lambda: client.list_events_window(
                "primary", "2026-11-02T00:00:00Z", "2026-11-09T00:00:00Z", bound=10
            ),
        )

        assert hosts == ["graph.microsoft.com", "graph.microsoft.com"]
        assert recorder.calls[1][3]["$skip"] == "1"
        assert recorder.calls[1][3]["startDateTime"] == "2026-11-02T00:00:00Z"
        assert [e["id"] for e in window["events"]] == ["g1", "g2"]

    async def test_graph_a_link_it_cannot_continue_is_a_cut(self) -> None:
        client = MicrosoftCalendarClient(USER, _credentials(), MagicMock())
        recorder = _Recorder(
            lambda request: httpx.Response(
                200,
                json={
                    "value": [{"id": "g1", "subject": "x", "start": {}, "end": {}}],
                    "@odata.nextLink": "https://graph.microsoft.com/v1.0/me/calendarView",
                },
            )
        )

        window = await _drive(
            client,
            recorder,
            lambda: client.list_events_window(
                "primary", "2026-11-02T00:00:00Z", "2026-11-09T00:00:00Z", bound=10
            ),
        )

        assert len(recorder.calls) == 1
        assert window["truncated"] is True

    async def test_caldav_cuts_in_time_order_across_offsets(self) -> None:
        late = MagicMock(vobject_instance=None)  # 23:00 at -05:00 = 04:00 UTC on the 4th
        early = MagicMock(vobject_instance=None)  # 01:00 at +01:00 = 00:00 UTC on the 4th
        payloads = {
            id(late): {"id": "late", "start": {"dateTime": "2026-11-03T23:00:00-05:00"}},
            id(early): {"id": "early", "start": {"dateTime": "2026-11-04T01:00:00+01:00"}},
        }
        calendar = _CalDav(found=[late, early])
        client, patches = _apple(calendar)
        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patch(
                "src.domains.connectors.clients.apple_calendar_client.normalize_vevent",
                side_effect=lambda event: payloads[id(event)],
            ),
        ):
            window = await client.list_events_window(
                "primary", "2026-11-02T00:00:00Z", "2026-11-09T00:00:00Z", bound=1
            )
        assert [e["id"] for e in window["events"]] == ["early"]

    async def test_caldav_a_new_shape_drops_a_duration(self) -> None:
        calendar = _CalDav()
        vevent = calendar.event.vobject_instance.vevent
        vevent.remove(vevent.dtend)
        vevent.add("duration").value = timedelta(hours=1)
        client, patches = _apple(calendar)
        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patch(
                "src.domains.connectors.clients.apple_calendar_client.normalize_vevent",
                return_value={"id": "apple-1"},
            ),
        ):
            await client.update_event(
                "apple-1", bounds=bounds_of("2026-11-03", "2026-11-04", _UTC, all_day=True)
            )
        ics = calendar.saves[-1]["ics"]
        assert "DTEND;VALUE=DATE:20261104" in ics
        assert "DURATION" not in ics, "DTEND and DURATION together are invalid (RFC 5545)"
