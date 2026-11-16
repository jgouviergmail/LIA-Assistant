"""Meetings shared with one person (Bloc C, B3).

The provider is asked for a WINDOW, and the participant matching — attendee
OR organizer — happens here.
That split is forced by the evidence: ``list_events(query=)`` has no
cross-provider parity — Google full-text searches the event, Apple filters
locally on its own field set, Microsoft runs KQL — and none of them promises
"this person is an ATTENDEE" rather than "this string appears somewhere". One
call plus a local filter is both portable and exact about what it means.

Matching is by ADDRESS, folded like every other mailbox in this codebase
(``fold_email``): case is not a difference, accents are. Both roles count — a
meeting this person ORGANIZED is shared with you as surely as one they merely
attend, and the two are told apart rather than merged.

Every calendar the account OWNS is read, the configured default first
(``calendar_lists``): the default says where an event is created, never where a
meeting is. Reading it alone missed every invitation the main calendar held
while the default was a named one (measured 2026-11-15), as reading ``primary``
alone once answered that a peer was free at 10:00 while his named calendar held
a meeting. A calendar someone else shares is theirs, never read.

An event that names no organizer (most of Apple's) is never reported as
"organized nothing", a negative nobody verified (ADR-184): the payload states
that the split is UNKNOWN, and the reader is shown one list instead of two.

No count is reported. A window is not the whole calendar, so any total would
be a claim the data cannot back — ADR-185. What the reader is told instead is
the window itself.

The window is read WHOLE, page after page (``list_events_window``), the coming
half then the past one. The agents' one-request listing answers the oldest
events of a window first and stops at their per-request ceiling: read from 90
days back, it never reached today, and every meeting to come was missing from
every card (measured 2026-11-15: 25 events read, 18 August to 4 October, of 88).
A half that holds more than ``CALENDAR_WINDOW_READ_MAX`` events is cut, as is a
calendar left unread past ``CALENDARS_READ_MAX``, and the cut is said (ADR-185
amendment 2026-11-15).

All three clients answer Google-shaped events (``attendees[].email``,
``start.dateTime`` or ``start.date``), so one parser serves them all.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import structlog

from src.core.classification_projection import event_classification
from src.core.constants import CALENDAR_WINDOW_READ_MAX
from src.domains.connectors.calendar_access import CalendarAccess, open_active_calendar
from src.domains.connectors.clients.calendar_lists import event_key, read_owned_events
from src.domains.relations.providers.classification import (
    ClassificationSource,
    capture_source,
    qualify_rows,
)
from src.domains.relations.providers.client import ProviderNotConfigured
from src.domains.relations.providers.schemas import SharedEvent
from src.domains.shared.text_normalization import fold_email

if TYPE_CHECKING:
    from uuid import UUID

    from src.core.content_classification import EventClassification

logger = structlog.get_logger(__name__)

#: Shown when the provider gave no title — never an empty line.
_NO_TITLE = "(no title)"


def event_instant(event: dict[str, Any], edge: str) -> datetime | None:
    """Parse one edge of an event, ``dateTime`` or all-day ``date``.

    Args:
        event: Normalized event record.
        edge: ``start`` or ``end``.

    Returns:
        The instant, or None when absent or unparseable — never a guess: a
        meeting with an invented duration is a claim the calendar never made.
    """
    side = event.get(edge)
    if not isinstance(side, dict):
        return None
    raw = side.get("dateTime") or side.get("date")
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    # An all-day date carries no zone; anchoring it to UTC keeps every
    # comparison in one frame (the display timezone is the frontend's job).
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def is_cancelled(event: dict[str, Any]) -> bool:
    """Whether the provider marks the event cancelled: a meeting nobody will hold.

    One reading for every surface that tells what two people share, the
    relationship card and the Tools' contact history alike.

    Args:
        event: Normalized event record.

    Returns:
        True when its ``status`` says it was cancelled.
    """
    return event.get("status") == "cancelled"


def organizes(event: dict[str, Any], folded_addresses: set[str]) -> bool:
    """Whether this person is the event's organizer."""
    organizer = event.get("organizer")
    if not isinstance(organizer, dict):
        return False
    return fold_email(str(organizer.get("email") or "")) in folded_addresses


def attends(event: dict[str, Any], folded_addresses: set[str]) -> bool:
    """Whether one of the person's addresses is on the attendee list."""
    for attendee in event.get("attendees") or []:
        if not isinstance(attendee, dict):
            continue
        if fold_email(str(attendee.get("email") or "")) in folded_addresses:
            return True
    return False


def _to_event(
    event: dict[str, Any], now: datetime, *, role: str, organizer_known: bool
) -> SharedEvent | None:
    """Map one normalized event onto the contract (None when unusable)."""
    # The read, the match and the qualification key a row on ONE reading of its id.
    event_id = event_key(event)
    if not event_id:
        return None  # nothing stable to key a row on
    starts_at = event_instant(event, "start")
    return SharedEvent(
        id=event_id,
        summary=str(event.get("summary") or "").strip() or _NO_TITLE,
        starts_at=starts_at,
        ends_at=event_instant(event, "end"),
        is_past=starts_at is not None and starts_at < now,
        role=role,
        organizer_known=organizer_known,
    )


def _sort_key(event: SharedEvent, now: datetime) -> tuple[int, float]:
    """Upcoming first (soonest first), then the past (most recent first).

    A relationship card answers "what is coming with this person?" before "what
    happened?" — and an undated event sorts last rather than disappearing.
    """
    if event.starts_at is None:
        return (2, 0.0)
    delta = (event.starts_at - now).total_seconds()
    return (0, delta) if not event.is_past else (1, -delta)


@dataclass(frozen=True)
class _Window:
    """Every event the window gave, the calendar each came from, and whether it was cut."""

    items: list[dict[str, Any]]
    cut: bool
    source: ClassificationSource
    calendar_of: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SharedEventsRead:
    """The meetings shared with one person, and whether the window was read in part.

    Attributes:
        events: Upcoming first, then the most recent past ones.
        cut: A half of a calendar's window held more than
            ``CALENDAR_WINDOW_READ_MAX`` events, or some owned calendars were left
            unread (``CalendarsRead.cut``): what was found was found in part.
    """

    events: list[SharedEvent] = field(default_factory=list)
    cut: bool = False


async def _read_window(user_id: UUID, *, window_days: int, now: datetime) -> _Window:
    """Read the whole window of EVERY calendar the account owns, the coming half first.

    Split from the matching so each half stays readable — and so the calendar
    resolution, the costliest thing to get wrong here, sits alone. The default
    calendar only says where an event is created (``calendar_lists``): an
    invitation sits in the main calendar, a booking in a named one. An event
    under way belongs to both halves (one bounds the end, the other the start),
    and an event two calendars hold is one meeting: each is kept once, with the
    calendar it was first read in. The past half reaches one second past
    ``now``, or an event with no length starting exactly then would fall between.
    """
    window = timedelta(days=window_days)
    halves = ((now, now + window), (now - window, now + timedelta(seconds=1)))
    # The shared calendar door: no session held while the provider answers (ADR-304).
    async with open_active_calendar(user_id) as access:
        if not isinstance(access, CalendarAccess):
            raise ProviderNotConfigured("calendar")
        owned = await read_owned_events(
            access.client,
            access.calendar_id,
            [(start.isoformat(), end.isoformat()) for start, end in halves],
            bound=CALENDAR_WINDOW_READ_MAX,
        )
        source = capture_source(access.client, access.connector_type, access.calendar_id)
    return _Window(items=owned.events, cut=owned.cut, source=source, calendar_of=owned.calendar_of)


def _shared_with(
    items: list[dict[str, Any]], folded_addresses: set[str], now: datetime
) -> list[SharedEvent]:
    """Keep the events this person is part of, each with its role, a cancelled one never."""
    # Detected from the DATA, not from the provider name: if nothing in this
    # window carried an organizer, we cannot tell who organized what — and an
    # empty calendar makes no claim either way.
    organizer_known = any("organizer" in event for event in items)
    shared: list[SharedEvent] = []
    for event in items:
        if is_cancelled(event):
            continue
        organizer = organizes(event, folded_addresses)
        if not organizer and not attends(event, folded_addresses):
            continue
        mapped = _to_event(
            event,
            now,
            role="organizer" if organizer else "attendee",
            organizer_known=organizer_known,
        )
        if mapped is not None:
            shared.append(mapped)
    return shared


async def fetch_shared_events(
    user_id: UUID,
    *,
    addresses: list[str],
    limit: int,
    window_days: int,
    now: datetime,
) -> SharedEventsRead:
    """Events around today this person is part of, attending OR organizing.

    Args:
        user_id: Owner of the calendar.
        addresses: The person's addresses, already capped by the caller.
        limit: Cap on returned items.
        window_days: Half-window scanned around ``now``, in days.
        now: Timezone-aware UTC reference instant.

    Returns:
        Upcoming meetings first, then the most recent past ones, each carrying
        its role, and whether the window was cut; empty when no address was given.

    Raises:
        ProviderNotConfigured: When no calendar connector is usable.
        Exception: Provider failures propagate — unlike the mail section, one
            call carries the WHOLE answer here, so swallowing it would report
            "no shared meetings" without having looked.
    """
    if not addresses:
        return SharedEventsRead()
    folded = {fold_email(address) for address in addresses if address.strip()}
    if not folded:
        return SharedEventsRead()
    window = await _read_window(user_id, window_days=window_days, now=now)
    shared = _shared_with(window.items, folded, now)
    shared.sort(key=lambda event: _sort_key(event, now))
    selected = shared[:limit]
    qualified = await _qualified(selected, window, user_id)
    return SharedEventsRead(
        events=[
            event.model_copy(update={"classification": qualified.get(event.id)})
            for event in selected
        ],
        cut=window.cut,
    )


async def _qualified(
    selected: list[SharedEvent], window: _Window, user_id: UUID
) -> dict[str, EventClassification | None]:
    """Each selected meeting's qualification, in ONE request whatever the calendars.

    Every record carries the calendar it was read in under ``calendar_id``, the
    key the qualification reads as an observation's container: one request for
    the section, never one per calendar.

    Args:
        selected: The meetings the section shows.
        window: The read they came from, with the calendar each was read in.
        user_id: Owner of the calendars.

    Returns:
        Event id to its qualification (None when the evidence gave none).
    """
    raw_by_id = {event_key(item): item for item in window.items}
    # Every selected id was kept with its calendar (``_to_event`` drops an id-less event).
    records = [
        {**raw_by_id[event.id], "calendar_id": window.calendar_of[event.id]} for event in selected
    ]
    annotations = await qualify_rows(records, source=window.source, user_id=user_id, kind="event")
    return {
        event.id: event_classification(annotations.get(str(index)))
        for index, event in enumerate(selected)
    }
