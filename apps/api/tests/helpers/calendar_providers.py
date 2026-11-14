"""Three calendar providers, simulated from their own reference (ADR-380).

A test that checks what a client SENDS freezes a form, right or wrong: the frozen
reference of 2026-11 held a wall time stamped ``Z`` and stayed green. These
simulators answer the other question — what does the provider UNDERSTAND? — by
reading a request the way its reference says, and nothing else:

- **Google Calendar**, ``events`` resource: « start.dateTime … a time zone offset
  is required unless a time zone is explicitly specified in ``timeZone`` ». An
  offset, when there is one, IS the instant; without one the time is read on the
  wall of ``timeZone``. A PATCH merges ``start`` and ``end`` field by field, a
  null clearing one, and a ``date`` left beside a ``dateTime`` is refused — the
  behaviour the client is written for (ADR-369). Times are answered in the
  CALENDAR's zone, whatever the event's own.
- **Microsoft Graph**, ``dateTimeTimeZone``: ``dateTime`` is « {date}T{time} »,
  with NO offset, read in the zone ``timeZone`` names; an all-day event is bound
  by midnights; an event is answered in UTC unless ``Prefer: outlook.timezone``
  asks otherwise.
- **CalDAV**, RFC 5545 §3.3.5: a DATE-TIME is UTC (``…Z``, never under a TZID) or
  local to the zone its ``TZID`` names. The simulator reads a name it KNOWS by
  that name, as a server that takes time zones by reference does (RFC 7809) —
  and as LIA's own creates need, which carry no definition — and only an unknown
  one by the VTIMEZONE beside it. So an abbreviation that is another zone's name
  (« EST ») is that other zone.

None of them reads an hour its zone's clocks skip or show twice: how a provider
places one is written nowhere, so a client must say the instant instead
(``WallTime.zone_suffices``). A request a reference does not define is REFUSED
and written down in ``refused``.
"""

from __future__ import annotations

import contextlib
import json
from collections.abc import AsyncIterator, Mapping
from datetime import UTC, date, datetime, time, tzinfo
from typing import Any, Final, Protocol
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import unquote
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
import icalendar
import vobject
from caldav.lib import vcal

from src.domains.connectors.clients.apple_calendar_client import AppleCalendarClient
from src.domains.connectors.clients.google_calendar_client import GoogleCalendarClient
from src.domains.connectors.clients.microsoft_calendar_client import MicrosoftCalendarClient
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.schemas import ConnectorCredentials

#: What a provider holds for one bound: an instant, or a day.
Moment = datetime | date

#: The simulated providers, by the name a test asks them under.
PROVIDERS: Final = ("google", "graph", "caldav")


class Refused(ValueError):
    """A request the provider's reference does not let it read."""


class CalendarProvider(Protocol):
    """What a test asks of a simulated provider."""

    kind: ConnectorType
    refused: list[str]

    def held(self, event_id: str) -> tuple[Moment, Moment]:
        """The start and end the provider holds for an event, as it read them."""


def the_instant(wall: datetime, zone: tzinfo) -> datetime:
    """The one instant a wall time is in a zone.

    Raises:
        Refused: The zone's clocks skip that time or show it twice.
    """
    first, second = (wall.replace(tzinfo=zone, fold=fold) for fold in (0, 1))
    if first.utcoffset() != second.utcoffset():
        raise Refused(
            f"{wall.isoformat()} is skipped or repeated in {zone}: no reference says how it is read"
        )
    return first.astimezone(UTC)


def _zone(name: object) -> ZoneInfo:
    try:
        return ZoneInfo(str(name))
    except (ZoneInfoNotFoundError, ValueError) as unknown:
        raise Refused(f"an unknown time zone: {name!r}") from unknown


def _in_order(start: Moment, end: Moment) -> None:
    """Refuse bounds of two shapes, or an event that does not end after it starts."""
    if isinstance(start, datetime) != isinstance(end, datetime):
        raise Refused("a day beside a time")
    if not end > start:
        raise Refused("the event does not end after it starts")


def _last_segment(request: httpx.Request) -> str:
    """The id a request names: the last segment of its path, as it was written."""
    return unquote(request.url.raw_path.decode().partition("?")[0].rsplit("/", 1)[-1])


def _body(request: httpx.Request) -> dict[str, Any]:
    sent: dict[str, Any] = json.loads(request.content) if request.content else {}
    return sent


# --- Google Calendar ----------------------------------------------------------------------


def google_moment(edge: Mapping[str, Any]) -> Moment:
    """One bound of an event, as Google's reference reads it."""
    if "date" in edge:
        if "dateTime" in edge:
            raise Refused("a date beside a dateTime")
        return date.fromisoformat(str(edge["date"]))
    if "dateTime" not in edge:
        raise Refused("a bound with neither a date nor a dateTime")
    stamp = datetime.fromisoformat(str(edge["dateTime"]))
    if stamp.tzinfo is not None:
        # An offset IS the instant: the zone beside it only says how the event is shown.
        return stamp.astimezone(UTC)
    if "timeZone" not in edge:
        raise Refused("a dateTime with no offset and no timeZone")
    return the_instant(stamp, _zone(edge["timeZone"]))


class GoogleCalendar:
    """Google Calendar's ``events`` resource, as far as an event's bounds go."""

    kind = ConnectorType.GOOGLE_CALENDAR

    def __init__(self, calendar_zone: str = "America/Los_Angeles") -> None:
        self.events: dict[str, dict[str, Any]] = {}
        self.refused: list[str] = []
        # Google answers every time in the CALENDAR's zone, whatever the event's own.
        self._calendar_zone = ZoneInfo(calendar_zone)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        try:
            return httpx.Response(200, json=self._serve(request))
        except KeyError:
            return httpx.Response(404, json={"error": {"message": "Not Found"}})
        except Refused as refusal:
            self.refused.append(str(refusal))
            return httpx.Response(400, json={"error": {"message": str(refusal)}})

    def held(self, event_id: str) -> tuple[Moment, Moment]:
        """The start and end Google holds for an event."""
        event = self.events[event_id]
        return google_moment(event["start"]), google_moment(event["end"])

    def _serve(self, request: httpx.Request) -> dict[str, Any]:
        sent = _body(request)
        event_id = str(sent["id"]) if request.method == "POST" else _last_segment(request)
        if request.method in {"POST", "PATCH"}:
            stored = {} if request.method == "POST" else self.events[event_id]
            event = _google_patched(stored, sent)
            _in_order(google_moment(event["start"]), google_moment(event["end"]))
            self.events[event_id] = event
        return self._answer(event_id)

    def _answer(self, event_id: str) -> dict[str, Any]:
        event = self.events[event_id]
        return {
            **event,
            "id": event_id,
            "status": "confirmed",
            "start": self._shown(event["start"]),
            "end": self._shown(event["end"]),
        }

    def _shown(self, edge: Mapping[str, Any]) -> dict[str, str]:
        moment = google_moment(edge)
        if not isinstance(moment, datetime):
            return {"date": moment.isoformat()}
        shown = {"dateTime": moment.astimezone(self._calendar_zone).isoformat()}
        return shown | ({"timeZone": str(edge["timeZone"])} if "timeZone" in edge else {})


def _google_patched(stored: Mapping[str, Any], sent: Mapping[str, Any]) -> dict[str, Any]:
    """A resource after a POST or a PATCH: ``start``/``end`` merge field by field, a null clears."""
    event = {**stored, **sent}
    for side in ("start", "end"):
        merged = {**stored.get(side, {}), **sent.get(side, {})}
        event[side] = {name: value for name, value in merged.items() if value is not None}
    return event


# --- Microsoft Graph ------------------------------------------------------------------------


def graph_moment(event: Mapping[str, Any], side: str) -> Moment:
    """One bound of an event, as Graph's ``dateTimeTimeZone`` is documented."""
    edge = event[side]
    stamp = datetime.fromisoformat(str(edge["dateTime"]))
    if stamp.tzinfo is not None:
        raise Refused("dateTimeTimeZone.dateTime carries an offset: its reference names none")
    zone = _zone(edge["timeZone"])
    if event.get("isAllDay"):
        if stamp.time() != time.min:
            raise Refused("an all-day event is bound by midnights")
        return stamp.date()
    return the_instant(stamp, zone)


class Graph:
    """Microsoft Graph's ``event`` resource, as far as an event's bounds go."""

    kind = ConnectorType.MICROSOFT_CALENDAR

    def __init__(self) -> None:
        self.events: dict[str, dict[str, Any]] = {}
        self.refused: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        try:
            return httpx.Response(
                201 if request.method == "POST" else 200, json=self._serve(request)
            )
        except KeyError:
            return httpx.Response(404, json={"error": {"code": "ErrorItemNotFound"}})
        except Refused as refusal:
            self.refused.append(str(refusal))
            return httpx.Response(400, json={"error": {"message": str(refusal)}})

    def held(self, event_id: str) -> tuple[Moment, Moment]:
        """The start and end Graph holds for an event."""
        event = self.events[event_id]
        return graph_moment(event, "start"), graph_moment(event, "end")

    def _serve(self, request: httpx.Request) -> dict[str, Any]:
        if "outlook.timezone" in request.headers.get("Prefer", ""):
            raise Refused("this simulator answers in UTC, as Graph does when nothing is asked")
        posted = request.method == "POST"
        event_id = f"graph-{len(self.events) + 1}" if posted else _last_segment(request)
        if request.method in {"POST", "PATCH"}:
            event = {**({} if posted else self.events[event_id]), **_body(request)}
            _in_order(graph_moment(event, "start"), graph_moment(event, "end"))
            self.events[event_id] = event
        return self._answer(event_id)

    def _answer(self, event_id: str) -> dict[str, Any]:
        event = self.events[event_id]
        return {
            "id": event_id,
            "subject": event.get("subject", ""),
            "isAllDay": bool(event.get("isAllDay")),
            "start": _in_utc(graph_moment(event, "start")),
            "end": _in_utc(graph_moment(event, "end")),
        }


def _in_utc(moment: Moment) -> dict[str, str]:
    """Graph's answer for a bound: seven fractional digits, no offset, the zone named beside."""
    wall = (
        moment.replace(tzinfo=None)
        if isinstance(moment, datetime)
        else datetime.combine(moment, time.min)
    )
    return {"dateTime": f"{wall.isoformat(timespec='seconds')}.0000000", "timeZone": "UTC"}


# --- CalDAV ---------------------------------------------------------------------------------


def ical_moment(text: str, name: str) -> Moment:
    """One bound of the event in ``text``, as a server reads RFC 5545 §3.3.5."""
    head, _, value = _event_line(text, name).partition(":")
    parameters = {
        key.upper(): said for key, _, said in (p.partition("=") for p in head.split(";")[1:])
    }
    if value.endswith("Z") and "TZID" in parameters:
        raise Refused(f"{name}: a TZID on a time written in UTC")
    if parameters.get("VALUE") != "DATE" and not value.endswith("Z") and "TZID" not in parameters:
        raise Refused(f"{name}: a floating time, which no zone places")
    read = _read_by_name(text, name)
    if not isinstance(read, datetime):
        return read
    if read.tzinfo is None:
        raise Refused(f"{name}: a time no zone places")
    return the_instant(read.replace(tzinfo=None), read.tzinfo)


def _read_by_name(text: str, name: str) -> date:
    """One bound as icalendar reads it: a TZID it knows by its NAME, and only an
    unknown one by the VTIMEZONE beside it — the reading this simulator stands for."""
    calendar = icalendar.Calendar.from_ical(text)
    assert isinstance(calendar, icalendar.Calendar)
    event = calendar.events[0]
    read = event.DTSTART if name == "DTSTART" else event.DTEND
    if not isinstance(read, date):
        raise Refused(f"{name}: the event has none")
    return read


def _event_line(text: str, name: str) -> str:
    """The unfolded line ``name`` of the VEVENT (a VTIMEZONE has a DTSTART of its own)."""
    lines = text.replace("\r\n", "\n").replace("\n ", "").split("\n")
    inside = lines[lines.index("BEGIN:VEVENT") : lines.index("END:VEVENT")]
    return next(line for line in inside if line.partition(":")[0].partition(";")[0] == name)


class CalDavObject:
    """An event as caldav hands it over: read by vobject, saved back through it."""

    def __init__(self, collection: CalDavCollection, text: str) -> None:
        self._collection = collection
        self.vobject_instance = vobject.readOne(text)

    async def save(self) -> None:
        """Send the object back as vobject writes it: what an update puts on the wire."""
        self._collection.put(self.vobject_instance.serialize())


class CalDavCollection:
    """A CalDAV calendar collection: it keeps the iCalendar text it is sent."""

    kind = ConnectorType.APPLE_CALENDAR

    def __init__(self) -> None:
        self.texts: dict[str, str] = {}
        self.refused: list[str] = []

    async def save_event(self, **properties: Any) -> CalDavObject:
        """A create, written by caldav's own writer as on a real collection."""
        made = vcal.create_ical(objtype="VEVENT", **properties)
        return self.put(made if isinstance(made, str) else made.decode("utf-8"))

    async def search(self, **_asked: Any) -> list[CalDavObject]:
        """Every event of the collection, each read afresh from its text."""
        return [CalDavObject(self, text) for text in self.texts.values()]

    def put(self, text: str) -> CalDavObject:
        """Keep a text the server can read; refuse and write down one it cannot."""
        try:
            _in_order(ical_moment(text, "DTSTART"), ical_moment(text, "DTEND"))
        except Refused as refusal:
            self.refused.append(str(refusal))
            raise
        self.texts[_event_line(text, "UID").partition(":")[2]] = text
        return CalDavObject(self, text)

    def held(self, event_id: str) -> tuple[Moment, Moment]:
        """The start and end the collection holds for an event."""
        text = self.texts[event_id]
        return ical_moment(text, "DTSTART"), ical_moment(text, "DTEND")


# --- A real client on a simulated provider ----------------------------------------------------


def _credentials() -> ConnectorCredentials:
    return ConnectorCredentials(
        access_token="token",
        refresh_token="refresh",
        expires_at=datetime(2099, 1, 1, tzinfo=UTC),
    )


@contextlib.asynccontextmanager
async def connected(name: str, user_id: UUID) -> AsyncIterator[tuple[Any, CalendarProvider]]:
    """A REAL calendar client of provider ``name``, talking to its simulator only.

    Args:
        name: One of :data:`PROVIDERS`.
        user_id: The account the client acts for.

    Yields:
        The client and the provider it talks to.
    """
    if name == "caldav":
        collection = CalDavCollection()
        apple = AppleCalendarClient(user_id, MagicMock(), MagicMock())
        breaker = MagicMock(
            check=AsyncMock(), record_success=AsyncMock(), record_failure=AsyncMock()
        )
        with (
            patch.object(apple, "_rate_limit", AsyncMock()),
            patch.object(apple, "_get_circuit_breaker", return_value=breaker),
            patch.object(apple, "_get_calendar", AsyncMock(return_value=collection)),
            patch("asyncio.sleep", AsyncMock()),
        ):
            yield apple, collection
        return
    provider: GoogleCalendar | Graph
    client: GoogleCalendarClient | MicrosoftCalendarClient
    if name == "google":
        provider = GoogleCalendar()
        client = GoogleCalendarClient(user_id, _credentials(), MagicMock())
    else:
        provider = Graph()
        client = MicrosoftCalendarClient(user_id, _credentials(), MagicMock())
    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as http:
        client._http_client = http
        with (
            patch.object(client, "_rate_limit", AsyncMock()),
            patch.object(client, "_is_circuit_breaker_enabled", return_value=False),
            patch("asyncio.sleep", AsyncMock()),
        ):
            yield client, provider
