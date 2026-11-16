"""Unit tests for the telephony availability pre-fetch (P3.2).

The load-bearing test is the leak assertion: a calendar event carrying a title
and a location must project to a busy time range that contains NEITHER — the
minimization is by capability (the projection reads only start/end), so the
guarantee is verifiable in isolation on the pure projector.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest

from src.domains.connectors.active_client import ClientUnavailable
from src.domains.connectors.calendar_access import CalendarAccess
from src.domains.telephony import availability as availability_module
from src.domains.telephony.availability import build_availability, summarize_busy_periods

# A timed event and an all-day event, each carrying detail fields that MUST NOT
# leak into the projected summary.
_SECRET_TITLE = "Chemo appointment"
_SECRET_LOCATION = "Oncology ward, room 12"
_EVENTS: list[dict] = [
    {
        "summary": _SECRET_TITLE,
        "location": _SECRET_LOCATION,
        "attendees": [{"email": "doctor@example.com"}],
        "start": {"dateTime": "2026-07-14T09:00:00+02:00"},
        "end": {"dateTime": "2026-07-14T10:30:00+02:00"},
    },
    {
        "summary": "Family holiday",
        "start": {"date": "2026-07-20"},
        "end": {"date": "2026-07-21"},
    },
]


@pytest.mark.unit
def test_summary_emits_busy_ranges_and_leaks_nothing() -> None:
    """Busy ranges are present; titles/locations/attendees never appear."""
    out = summarize_busy_periods(_EVENTS, "Europe/Paris", "fr")

    # Busy time ranges are present (French localized time components).
    assert "09:00" in out and "10:30" in out
    assert "→" in out
    # Leak assertion: no meeting detail whatsoever.
    assert _SECRET_TITLE not in out
    assert _SECRET_LOCATION not in out
    assert "Family holiday" not in out
    assert "doctor@example.com" not in out


@pytest.mark.unit
def test_all_day_event_renders_without_spurious_time() -> None:
    """An all-day (date-only) block renders as a date, not a shifted time."""
    out = summarize_busy_periods([_EVENTS[1]], "Europe/Paris", "en")
    # Date-only events use include_time=False → no "at HH:MM" tail.
    assert " at " not in out
    assert "July" in out


@pytest.mark.unit
def test_empty_events_returns_all_free_phrase() -> None:
    """No events → the localized 'fully available' line, per language."""
    assert summarize_busy_periods([], "Europe/Paris", "fr").startswith("Aucun créneau")
    assert summarize_busy_periods([], "Europe/Paris", "en").startswith("No busy periods")
    assert summarize_busy_periods([], "Europe/Paris", "zh-CN").startswith("该时间段内无占用")


@pytest.mark.unit
def test_event_without_start_is_skipped() -> None:
    """A malformed event with no start yields no busy line (treated as free)."""
    out = summarize_busy_periods([{"summary": "x", "end": {"date": "2026-07-21"}}], "UTC", "en")
    assert out.startswith("No busy periods")


class _FakeCalendarClient:
    """A client without freeBusy (CalDAV: its listing names no role).

    Each calendar answers its own events; every window read is recorded.
    """

    def __init__(
        self,
        calendars: dict[str, list[dict]] | None = None,
        *,
        truncated: bool = False,
    ) -> None:
        self.calendars = {"home": _EVENTS} if calendars is None else calendars
        self.windows: list[tuple[str, str, str]] = []
        self.last_bound: int | None = None
        self.last_fields: list[str] | None = None
        self.truncated = truncated

    async def list_calendars(self, max_results: int = 100, show_hidden: bool = False) -> dict:
        listed = [{"id": key, "primary": index == 0} for index, key in enumerate(self.calendars)]
        return {"items": listed, "truncated": False}

    async def list_events_window(
        self,
        calendar_id: str,
        time_min: str,
        time_max: str,
        *,
        bound: int,
        fields: list[str] | None = None,
    ) -> dict:
        self.windows.append((calendar_id, time_min, time_max))
        self.last_bound = bound
        self.last_fields = fields
        return {"events": self.calendars.get(calendar_id, []), "truncated": self.truncated}


#: The account's main calendar, under the id Google lists it by.
_MAIN = "moi@x.com"
_NINE_TO_HALF_TEN = {"start": "2026-07-15T09:00:00+02:00", "end": "2026-07-15T10:30:00+02:00"}


class _FakeFreeBusyClient:
    """Calendar client exposing freeBusy: the fast-path must be preferred.

    It lists its calendars and echoes every calendar freeBusy is asked about,
    as Google does — an unreadable one with ``errors`` and no busy block.
    """

    def __init__(
        self,
        busy: dict[str, list[dict]] | None = None,
        *,
        listing: list[dict] | None = None,
        errors: tuple[str, ...] = (),
    ) -> None:
        self.busy = {_MAIN: [_NINE_TO_HALF_TEN]} if busy is None else busy
        self.listing = (
            [{"id": key, "accessRole": "owner", "primary": key == _MAIN} for key in self.busy]
            if listing is None
            else listing
        )
        self.errors = errors
        self.asked: list[str] = []
        self.list_events_called = False

    async def list_calendars(self, max_results: int = 100, show_hidden: bool = False) -> dict:
        return {"items": self.listing, "truncated": False}

    async def query_freebusy(
        self, *, time_min: str, time_max: str, calendar_ids: list[str]
    ) -> dict:
        self.asked = list(calendar_ids)
        return {
            "calendars": {
                calendar_id: (
                    {"errors": [{"reason": "notFound"}], "busy": []}
                    if calendar_id in self.errors
                    else {"busy": self.busy.get(calendar_id, [])}
                )
                for calendar_id in calendar_ids
            }
        }

    async def list_events(self, **kwargs: object) -> dict:
        self.list_events_called = True
        return {"items": []}


def _door(opened: object) -> object:
    """The calendar door, answering ``opened`` (an access, a refusal, or an error)."""

    @asynccontextmanager
    async def _open(_user_id: object) -> AsyncIterator[object]:
        if isinstance(opened, Exception):
            raise opened
        yield opened

    return _open


def _access(client: object, default: str = "primary") -> CalendarAccess:
    return CalendarAccess(client=client, calendar_id=default, connector_type="google_calendar")


async def _read(monkeypatch: pytest.MonkeyPatch, opened: object, language: str = "fr"):
    monkeypatch.setattr(
        "src.domains.connectors.calendar_access.open_active_calendar", _door(opened)
    )
    return await build_availability(
        uuid4(),
        datetime(2026, 7, 14, tzinfo=UTC),
        datetime(2026, 7, 21, tzinfo=UTC),
        "Europe/Paris",
        language,
    )


@pytest.mark.unit
async def test_build_reads_the_whole_window_and_projects_busy_blocks_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without freeBusy, every event of the window is read; only busy ranges are said."""
    fake_client = _FakeCalendarClient()
    read = await _read(monkeypatch, _access(fake_client))

    # ``primary`` names the main calendar the listing has: read under its own id.
    ((calendar_id, time_min, time_max),) = fake_client.windows
    assert calendar_id == "home"
    assert time_min.startswith("2026-07-14")
    assert time_max.startswith("2026-07-21")
    assert fake_client.last_bound == availability_module._MAX_EVENTS
    # Minimization by capability: start and end alone are asked for.
    assert fake_client.last_fields == ["start", "end"]
    assert "09:00" in read.summary and _SECRET_TITLE not in read.summary
    assert (read.opened, read.failed) == (True, False)


@pytest.mark.unit
async def test_a_window_read_in_part_is_said_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A cut busy list would tell the voice a booked hour is free: never a guess."""
    read = await _read(monkeypatch, _access(_FakeCalendarClient(truncated=True)))

    assert read.summary.startswith("Disponibilités indisponibles")
    assert (read.opened, read.failed) == (True, True)


@pytest.mark.unit
async def test_build_unavailable_when_no_connector(monkeypatch: pytest.MonkeyPatch) -> None:
    """No active calendar connector → the 'unavailable' line; nothing was opened."""
    read = await _read(monkeypatch, ClientUnavailable.NO_CONNECTOR)
    assert read.summary.startswith("Disponibilités indisponibles")
    assert (read.opened, read.failed) == (False, False)


@pytest.mark.unit
async def test_build_swallows_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A provider HTTP error is swallowed → 'unavailable', the call is not blocked."""
    read = await _read(monkeypatch, httpx.HTTPError("boom"), language="en")
    assert read.summary.startswith("Availability unavailable")
    assert (read.opened, read.failed) == (True, True)


@pytest.mark.unit
async def test_build_prefers_freebusy_when_available(monkeypatch: pytest.MonkeyPatch) -> None:
    """Google-path (lot B): freeBusy returns busy ranges only — even less data
    than the start/end projection, so it wins when the client offers it."""
    fake_client = _FakeFreeBusyClient()
    read = await _read(monkeypatch, _access(fake_client))

    assert fake_client.asked == [_MAIN]
    assert fake_client.list_events_called is False
    assert "09:00" in read.summary


@pytest.mark.unit
async def test_a_meeting_in_the_main_calendar_is_busy_for_the_voice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The default says where events are created: an invitation sits in the main one."""
    fake_client = _FakeFreeBusyClient(
        {_MAIN: [_NINE_TO_HALF_TEN], "famille": []},
        listing=[
            {"id": _MAIN, "accessRole": "owner", "primary": True},
            {"id": "famille", "accessRole": "owner"},
            {"id": "collegue@x.com", "accessRole": "reader"},
        ],
    )
    read = await _read(monkeypatch, _access(fake_client, "famille"))

    assert fake_client.asked == ["famille", _MAIN]
    assert "09:00" in read.summary
    assert (read.opened, read.failed) == (True, False)


@pytest.mark.unit
async def test_a_calendar_google_could_not_read_is_said_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unreadable calendar comes back with no busy block: never a free hour."""
    fake_client = _FakeFreeBusyClient({_MAIN: [], "famille": []}, errors=(_MAIN,))
    read = await _read(monkeypatch, _access(fake_client, "famille"))

    assert read.summary.startswith("Disponibilités indisponibles")
    assert (read.opened, read.failed) == (True, True)


@pytest.mark.unit
async def test_two_calendars_holding_one_meeting_say_it_once_and_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    later = {
        "start": {"dateTime": "2026-07-16T15:00:00+02:00"},
        "end": {"dateTime": "2026-07-16T16:00:00+02:00"},
    }
    fake_client = _FakeCalendarClient({"home": [later, _EVENTS[0]], "work": [_EVENTS[0]]})
    read = await _read(monkeypatch, _access(fake_client), language="en")

    lines = read.summary.splitlines()[1:]
    assert len(lines) == 2
    assert "09:00" in lines[0] and "15:00" in lines[1]
