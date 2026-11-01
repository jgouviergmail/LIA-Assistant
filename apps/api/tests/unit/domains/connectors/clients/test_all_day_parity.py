"""All-day events written on the three calendar providers, and windows drained (ADR-369, D2).

All three READ an all-day event (Google's ``start.date`` / exclusive ``end.date``);
none could WRITE one — Google's update only kept an existing shape. ``all_day``
now writes it the way each provider stores it, in the convention the clients
read, so an event read and written back keeps its days. A calendar window is
read whole up to a published bound, and a cut says so.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import httpx
import pytest
import vobject

from src.domains.connectors.clients.apple_calendar_client import AppleCalendarClient
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
                "2026-11-03",
                "2026-11-06",
                timezone="UTC",
                all_day=True,
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
                "e1", start_datetime="2026-11-03", end_datetime="2026-11-04", all_day=True
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
                start_datetime="2026-11-03T14:00:00",
                end_datetime="2026-11-03T15:00:00",
                timezone="UTC",
                all_day=False,
            ),
        )
        patched = recorder.calls[-1][2]
        assert patched["start"]["date"] is None
        assert patched["start"]["dateTime"].startswith("2026-11-03T14:00:00")

    async def test_switching_shape_without_both_bounds_is_refused(self) -> None:
        client = GoogleCalendarClient(USER, _credentials(), MagicMock())
        recorder = _Recorder(lambda request: httpx.Response(200, json={"id": "e1", "start": {}}))
        with pytest.raises(ValueError):
            await _drive(
                client,
                recorder,
                lambda: client.update_event("e1", start_datetime="2026-11-03", all_day=True),
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
                "2026-03-29",
                "2026-03-30",
                timezone="Europe/Berlin",
                all_day=True,
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
                start_datetime="2026-11-03T09:00:00",
                end_datetime="2026-11-03T10:00:00",
                timezone="UTC",
                all_day=False,
            ),
        )

        body = recorder.calls[0][2]
        assert body["isAllDay"] is False
        assert body["start"] == {"dateTime": "2026-11-03T09:00:00", "timeZone": "UTC"}


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
            await client.create_event("Congress", "2026-11-03", "2026-11-04", all_day=True)
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
                "apple-1", start_datetime="2026-11-03", end_datetime="2026-11-04", all_day=True
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
                "apple-1", start_datetime="2026-11-03", end_datetime="2026-11-04", all_day=True
            )
        ics = calendar.saves[-1]["ics"]
        assert "DTEND;VALUE=DATE:20261104" in ics
        assert "DURATION" not in ics, "DTEND and DURATION together are invalid (RFC 5545)"
