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

The calendar read is the OWNER's configured default, never ``primary``.
``connectors/preferences`` exists because that shortcut once answered that a
peer was free at 10:00 while his agenda — in a named calendar — held a meeting.

Apple's events carry no organizer at all. Rather than report "organized
nothing" (a negative nobody verified — ADR-184), the payload states that the
split is UNKNOWN, and the reader is shown one list instead of two.

No count is reported. A window is not the whole calendar, so any total would
be a claim the data cannot back — ADR-185. What the reader is told instead is
the window itself.

All three clients answer ``{"items": [...]}`` with Google-shaped events
(``attendees[].email``, ``start.dateTime`` or ``start.date``), so one parser
serves them all.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import structlog

from src.domains.connectors.preferences.owner_defaults import resolve_owner_calendar_id
from src.domains.relations.providers.client import open_category_client
from src.domains.relations.providers.schemas import SharedEvent
from src.domains.shared.text_normalization import fold_email

if TYPE_CHECKING:
    from uuid import UUID

logger = structlog.get_logger(__name__)

#: Shown when the provider gave no title — never an empty line.
_NO_TITLE = "(no title)"

#: How many events the window may return before the local filter runs. Wide on
#: purpose: the filter keeps a handful, so a narrow page would silently hide
#: meetings simply because the calendar is busy.
_WINDOW_PAGE_SIZE = 250


def _instant(event: dict[str, Any], edge: str) -> datetime | None:
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


def _organizes(event: dict[str, Any], folded_addresses: set[str]) -> bool:
    """Whether this person is the event's organizer."""
    organizer = event.get("organizer")
    if not isinstance(organizer, dict):
        return False
    return fold_email(str(organizer.get("email") or "")) in folded_addresses


def _attends(event: dict[str, Any], folded_addresses: set[str]) -> bool:
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
    event_id = str(event.get("id") or "").strip()
    if not event_id:
        return None  # nothing stable to key a row on
    starts_at = _instant(event, "start")
    return SharedEvent(
        id=event_id,
        summary=str(event.get("summary") or "").strip() or _NO_TITLE,
        starts_at=starts_at,
        ends_at=_instant(event, "end"),
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


async def _read_window(user_id: UUID, *, window_days: int, now: datetime) -> list[dict[str, Any]]:
    """Fetch the event window from the OWNER's configured calendar.

    Split from the matching so each half stays readable — and so the calendar
    resolution, the costliest thing to get wrong here, sits alone.
    """
    window = timedelta(days=window_days)
    async with open_category_client("calendar", user_id) as opened:
        calendar_id = await resolve_owner_calendar_id(
            db=opened.session,
            client=opened.client,
            owner_id=user_id,
            connector_type=opened.connector_type,
        )
        response = await opened.client.list_events(
            time_min=(now - window).isoformat(),
            time_max=(now + window).isoformat(),
            max_results=_WINDOW_PAGE_SIZE,
            calendar_id=calendar_id,
        )
    return [event for event in (response.get("items") or []) if isinstance(event, dict)]


def _shared_with(
    items: list[dict[str, Any]], folded_addresses: set[str], now: datetime
) -> list[SharedEvent]:
    """Keep the events this person is part of, each with its role."""
    # Detected from the DATA, not from the provider name: if nothing in this
    # window carried an organizer, we cannot tell who organized what — and an
    # empty calendar makes no claim either way.
    organizer_known = any("organizer" in event for event in items)
    shared: list[SharedEvent] = []
    for event in items:
        organizes = _organizes(event, folded_addresses)
        if not organizes and not _attends(event, folded_addresses):
            continue
        mapped = _to_event(
            event,
            now,
            role="organizer" if organizes else "attendee",
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
) -> list[SharedEvent]:
    """Events around today this person is part of, attending OR organizing.

    Args:
        user_id: Owner of the calendar.
        addresses: The person's addresses, already capped by the caller.
        limit: Cap on returned items.
        window_days: Half-window scanned around ``now``, in days.
        now: Timezone-aware UTC reference instant.

    Returns:
        Upcoming meetings first, then the most recent past ones, each carrying
        its role; empty when no address was given.

    Raises:
        ProviderNotConfigured: When no calendar connector is usable.
        Exception: Provider failures propagate — unlike the mail section, one
            call carries the WHOLE answer here, so swallowing it would report
            "no shared meetings" without having looked.
    """
    if not addresses:
        return []
    folded = {fold_email(address) for address in addresses if address.strip()}
    if not folded:
        return []
    items = await _read_window(user_id, window_days=window_days, now=now)
    shared = _shared_with(items, folded, now)
    shared.sort(key=lambda event: _sort_key(event, now))
    return shared[:limit]
