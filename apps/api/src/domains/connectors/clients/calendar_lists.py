"""Which calendars hold the person's meetings: every one the account owns (owner rule 2026-11-15).

The default calendar a person configures says where LIA CREATES an event; it never
bounds where their meetings are. An invitation lands in the provider's main
calendar, a meeting someone booked in a named one: a reader of « the meetings I
share with this person » that asked one calendar missed the others (measured
2026-11-15: the relationship cards read a named calendar, the main one holding 34
events was never read). Same rule as the task lists of 2026-11-10: every READER
reads them all.

« Owned » is the provider's own word, read the same way everywhere: Google says
``accessRole: owner``, Graph says it through ``canShare`` (only a calendar's
creator may share it, normalised to ``owner``). A calendar shared by someone else
— a colleague's, a holiday feed — is theirs, never read as the person's meetings.
CalDAV's listing publishes no role: every calendar of the account's calendar home
is read as its own, a calendar another iCloud account shares with it included
(a limit stated, not a guess: no live proof on a consumer mailbox, 2026-11-11).

The whole listing is asked before the owned ones are kept: its order is the
provider's, so asking « the first N » would drop an owned calendar listed after N
shared ones, silently. A listing the provider cut, or more owned calendars than
the reader's bound, is said (``cut``), never read as complete (ADR-185).

The windows of those calendars are then read a few at a time on the ONE client
(``read_calendar_windows``): a failed read cancels its siblings before the client
closes, and is raised as itself, never as the group around it, so a caller's
handler sees the provider's failure it knows how to say.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from src.core.constants import (
    CALENDAR_LIST_PAGE_MAX,
    CALENDAR_READ_CONCURRENCY,
    CALENDARS_READ_MAX,
)

if TYPE_CHECKING:
    from src.domains.connectors.clients.protocols import CalendarClientProtocol

#: One window to read: the calendar, then the window's ISO bounds.
WindowRead = tuple[str, str, str]
#: A window's ISO bounds, asked of every calendar read.
Span = tuple[str, str]

#: The alias a client resolves to the account's main calendar.
_MAIN_ALIAS = "primary"


def is_owned(calendar: Mapping[str, Any]) -> bool:
    """Whether the account owns this calendar, as its provider says it.

    Args:
        calendar: A calendar as a client's listing normalises it.

    Returns:
        True for ``accessRole: owner``, and for a calendar with no role (CalDAV).
    """
    role = calendar.get("accessRole")
    return role is None or role == "owner"


@dataclass(frozen=True)
class CalendarsRead:
    """The calendars a reader of the person's meetings reads, and whether more exist.

    Attributes:
        ids: The configured default first, then every other calendar the account owns.
        cut: The listing was cut, or the account owns more calendars than the
            reader's bound: some were not read.
    """

    ids: list[str] = field(default_factory=list)
    cut: bool = False


def _default_of(entries: list[Mapping[str, Any]], default_id: str) -> str:
    """The configured default as the listing names it: the main calendar under its own id.

    Read by alias AND by id, the main calendar would be read twice.
    """
    if default_id != _MAIN_ALIAS:
        return default_id
    return next((str(entry["id"]) for entry in entries if entry.get("primary") is True), default_id)


async def calendars_to_read(
    client: CalendarClientProtocol, default_id: str, *, bound: int
) -> CalendarsRead:
    """The configured default, then every other calendar the account owns, at most ``bound``.

    Args:
        client: The account's calendar client.
        default_id: The configured default calendar (``primary`` when none is): read
            whatever its role, since it is where the person's events are created.
        bound: The calendars read at most, the default always among them.

    Returns:
        The ids to read, and whether some were left unread.
    """
    listed = await client.list_calendars(max_results=CALENDAR_LIST_PAGE_MAX)
    entries = [
        entry
        for entry in listed.get("items") or []
        if isinstance(entry, Mapping) and entry.get("id")
    ]
    owned = (str(entry["id"]) for entry in entries if is_owned(entry))
    ids = list(dict.fromkeys([_default_of(entries, default_id), *owned]))
    cut = bool(listed.get("truncated")) or len(ids) > bound
    return CalendarsRead(ids=ids[:bound], cut=cut)


async def read_calendar_windows(
    client: CalendarClientProtocol,
    reads: Sequence[WindowRead],
    *,
    bound: int,
    fields: list[str] | None = None,
) -> list[tuple[str, dict[str, Any]]]:
    """Every window asked, ``CALENDAR_READ_CONCURRENCY`` at a time, each read whole.

    Args:
        client: The account's calendar client, shared by every read.
        reads: The windows, each naming its calendar.
        bound: The most events one window read returns (its cut said by ``truncated``).
        fields: The event fields asked for, where the provider projects them.

    Returns:
        Each answer (``{"events", "truncated"}``) beside the calendar it read, in
        the order asked.

    Raises:
        Exception: The first read's own failure, its siblings cancelled.
    """
    gate = asyncio.Semaphore(CALENDAR_READ_CONCURRENCY)
    projection: dict[str, Any] = {} if fields is None else {"fields": fields}

    async def one(calendar_id: str, time_min: str, time_max: str) -> dict[str, Any]:
        async with gate:
            answer: dict[str, Any] = await client.list_events_window(
                calendar_id, time_min, time_max, bound=bound, **projection
            )
            return answer

    try:
        async with asyncio.TaskGroup() as group:
            tasks = [(read[0], group.create_task(one(*read))) for read in reads]
    except ExceptionGroup as failures:
        raise failures.exceptions[0] from None
    return [(calendar_id, task.result()) for calendar_id, task in tasks]


def event_key(event: Mapping[str, Any]) -> str:
    """The id an event is known by across calendars ("" when it carries none).

    Args:
        event: An event as a client normalises it.

    Returns:
        Its provider id, stripped.
    """
    return str(event.get("id") or "").strip()


def merge_calendar_events(
    answers: Sequence[tuple[str, Mapping[str, Any]]],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Every event the calendars gave, each kept once with the calendar it was first read in.

    A meeting two calendars hold is one meeting; an event under way belongs to two
    windows. An event with no id is kept, never matched with another by guesswork.

    Args:
        answers: Each window read, beside the calendar it read, in the order asked.

    Returns:
        The events, and the calendar of each event id.
    """
    events: list[dict[str, Any]] = []
    calendar_of: dict[str, str] = {}
    for calendar_id, answer in answers:
        for event in answer.get("events") or []:
            if not isinstance(event, dict):
                continue
            key = event_key(event)
            if key in calendar_of:
                continue
            if key:
                calendar_of[key] = calendar_id
            events.append(event)
    return events, calendar_of


@dataclass(frozen=True)
class OwnedEvents:
    """The events of every calendar the account owns over the windows asked, each once.

    Attributes:
        events: In the order read, the configured default's first.
        calendar_of: The calendar each event id was read in.
        cut: A calendar was left unread, or a window held more than its bound.
        calendars: The calendars read, the default first, under the id it was READ
            by (``primary`` names the main calendar the listing gives).
    """

    events: list[dict[str, Any]] = field(default_factory=list)
    calendar_of: dict[str, str] = field(default_factory=dict)
    cut: bool = False
    calendars: list[str] = field(default_factory=list)


async def read_owned_events(
    client: CalendarClientProtocol,
    default_id: str,
    spans: Sequence[Span],
    *,
    bound: int,
    fields: list[str] | None = None,
) -> OwnedEvents:
    """Every event of the account's own calendars over ``spans``, each window read whole.

    Args:
        client: The account's calendar client.
        default_id: The configured default calendar (``primary`` when none is).
        spans: The windows, each asked of every calendar.
        bound: The most events one window read returns.
        fields: The event fields asked for, where the provider projects them.

    Returns:
        The events, the calendar of each, and whether anything was left unread.

    Raises:
        Exception: The listing's or the first window's own failure.
    """
    calendars = await calendars_to_read(client, default_id, bound=CALENDARS_READ_MAX)
    answers = await read_calendar_windows(
        client,
        [(calendar_id, *span) for calendar_id in calendars.ids for span in spans],
        bound=bound,
        fields=fields,
    )
    events, calendar_of = merge_calendar_events(answers)
    cut = calendars.cut or any(bool(answer.get("truncated")) for _, answer in answers)
    return OwnedEvents(
        events=events, calendar_of=calendar_of, cut=cut, calendars=list(calendars.ids)
    )


def calendar_ref(calendar_id: str) -> str:
    """What a stored record keeps of a calendar: a digest of its id, never the id.

    Google names a main calendar by its owner's address, and a calendar shared with
    owner rights by its owner's: a record that must find the calendar again keeps
    this instead (``owned_calendar_by_ref``).

    Args:
        calendar_id: The calendar.

    Returns:
        Sixteen hexadecimal characters.
    """
    return hashlib.sha256(calendar_id.encode("utf-8")).hexdigest()[:16]


async def owned_calendar_by_ref(
    client: CalendarClientProtocol, default_id: str, ref: str
) -> str | None:
    """The calendar the account still owns under ``ref``, or None when it is gone.

    Args:
        client: The account's calendar client.
        default_id: The configured default calendar.
        ref: What a record kept (``calendar_ref``).

    Returns:
        The calendar's id, or None.
    """
    calendars = await calendars_to_read(client, default_id, bound=CALENDARS_READ_MAX)
    return next((each for each in calendars.ids if calendar_ref(each) == ref), None)


def unread_in_freebusy(response: Mapping[str, Any], calendar_ids: Sequence[str]) -> bool:
    """Whether a calendar asked of Google's freeBusy came back unread.

    Google answers a calendar it could not read with ``errors`` and an EMPTY busy
    list, which a reader of busy blocks would take for a free day: a failure read
    as success (ADR-303).

    Args:
        response: The freeBusy answer.
        calendar_ids: The calendars it was asked about.

    Returns:
        True when one of them is missing from the answer or carries errors.
    """
    answered = response.get("calendars") or {}
    return any(
        not isinstance(answered.get(calendar_id), Mapping) or answered[calendar_id].get("errors")
        for calendar_id in calendar_ids
    )
