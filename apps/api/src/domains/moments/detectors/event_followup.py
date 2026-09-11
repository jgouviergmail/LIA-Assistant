"""« Your meeting just ended » — detecting it, and re-checking it before speaking.

The heartbeat reads a calendar window that starts at ``now`` and looks FORWARD,
so a finished meeting is invisible to it by construction. This detector reads
BACKWARD instead, over a bounded window, and files a moment for each finished
event that earned one.

Three rules that are not conventions:

- **the block, not the slot.** Three meetings back to back are one afternoon,
  not three debriefs: an event followed by another within
  ``moments_event_chain_gap_minutes`` files nothing, and the last of the run
  carries the block. Doing this in the detector rather than in the anti-repeat
  window is what stops two decisions and two quota slots being spent to say one
  thing.
- **a meeting LIA recorded is already answered.** Its minutes reached the person
  the moment they were ready, and asking « how did it go » on top of that reads
  as not having noticed.
- **the fact is re-read before it is said.** A moment is detected minutes or
  hours ahead, and the world moves: the event is cancelled, moved, or declined.
  The revalidation re-reads it, which is also why the stored payload carries no
  names — they would be a stale copy of something re-read anyway.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import structlog

from src.core.config import get_settings
from src.core.time_utils import resolve_user_timezone
from src.domains.connectors.calendar_access import CalendarAccess, open_active_calendar
from src.domains.moments.calendar_reading import (
    event_instant,
    is_cancelled,
    is_declined_by_self,
)
from src.domains.moments.importance import EventScore, score_event
from src.domains.moments.models import MomentKind
from src.domains.moments.repository import MomentCandidate
from src.domains.moments.schemas import MomentFacts
from src.domains.shared.text_normalization import fold_email, fold_name
from src.infrastructure.database import get_db_context

logger = structlog.get_logger(__name__)

#: What the detector asks the provider for. ``attendees`` and ``organizer`` are
#: what the score is made of; ``status`` is how a cancelled event says so.
_EVENT_FIELDS: list[str] = [
    "id",
    "summary",
    "start",
    "end",
    "location",
    "attendees",
    "organizer",
    "status",
    "hangoutLink",
]


def _has_other_people(event: Mapping[str, Any]) -> bool:
    """Whether anyone but the account holder is on it — the chain rule's unit.

    Deliberately coarser than the score: a block is broken by any real meeting
    that follows, whether or not that one would itself earn a debrief.
    """
    attendees = event.get("attendees")
    return isinstance(attendees, list) and len(attendees) > 1


def is_chained(
    event: Mapping[str, Any],
    others: Sequence[Mapping[str, Any]],
    *,
    user_tz: ZoneInfo,
    gap_minutes: int,
) -> bool:
    """Whether another meeting starts too soon after this one ends.

    Args:
        event: The finished event under consideration.
        others: Every event of the read window, this one included.
        user_tz: Fallback zone for a naive local time.
        gap_minutes: How close counts as « the same block ».

    Returns:
        True when this event is not the last of its block.
    """
    end = event_instant(event.get("end"), user_tz)
    if end is None:
        return False
    horizon = end + timedelta(minutes=gap_minutes)
    for other in others:
        if other.get("id") == event.get("id") or not _has_other_people(other):
            continue
        start = event_instant(other.get("start"), user_tz)
        if start is not None and end <= start <= horizon:
            return True
    return False


@dataclass(frozen=True, slots=True)
class _LocalContext:
    """What the score needs from this deployment's own tables.

    Read in ONE session rather than three: the sweep runs every five minutes
    per account, and a session opened per lookup is churn for nothing when the
    three queries are indexed and sequential.

    Attributes:
        recorded: Calendar events LIA already recorded a meeting for.
        favorites: Folded names of the people the account marked as favourites.
        linked: Folded names cited by an open commitment.
    """

    recorded: frozenset[str]
    favorites: frozenset[str]
    linked: frozenset[str]


async def _local_context(user_id: UUID, *, since: datetime) -> _LocalContext:
    """Read the three local sets the score needs.

    Best-effort IN FULL: this only ever raises a score or excludes an already
    answered meeting, so an unreadable table costs a duplicate question at
    worst — never a lost detection, and never the pass.

    Args:
        user_id: Whose tables.
        since: Meetings older than this are irrelevant — the detector only
            looks at events that ended inside its read window, so scanning an
            account's whole meeting history would grow without bound.

    Returns:
        The three sets, each possibly empty.
    """
    try:
        from sqlalchemy import select

        from src.domains.meetings.models import Meeting
        from src.domains.open_loops.models import OpenLoop, OpenLoopStatus
        from src.domains.relations.models import RelationFavorite

        async with get_db_context() as db:
            recorded_rows = await db.execute(
                select(Meeting.calendar_event_id).where(
                    Meeting.user_id == user_id,
                    Meeting.calendar_event_id.is_not(None),
                    Meeting.started_at >= since,
                )
            )
            favorite_rows = await db.execute(
                select(RelationFavorite.name_key).where(RelationFavorite.user_id == user_id)
            )
            loop_rows = await db.execute(
                select(OpenLoop.counterparty).where(
                    OpenLoop.user_id == user_id,
                    OpenLoop.status == OpenLoopStatus.OPEN.value,
                    OpenLoop.counterparty.is_not(None),
                )
            )
            return _LocalContext(
                recorded=frozenset(str(value) for value in recorded_rows.scalars().all() if value),
                favorites=frozenset(str(key) for key in favorite_rows.scalars().all() if key),
                linked=frozenset(
                    fold_name(str(name)) for name in loop_rows.scalars().all() if str(name).strip()
                ),
            )
    except Exception as exc:  # noqa: BLE001 — best effort by contract
        logger.warning(
            "moment_local_context_unreadable",
            user_id=str(user_id),
            error_type=type(exc).__name__,
        )
        return _LocalContext(frozenset(), frozenset(), frozenset())


def _payload(event: Mapping[str, Any], verdict: EventScore, end: datetime) -> dict[str, Any]:
    """What deduplication and scoring need — and nothing else.

    No attendee names: the revalidation re-reads the event anyway, so storing
    the people would be personal data kept for nothing.
    """
    attendees = event.get("attendees")
    return {
        "title": str(event.get("summary") or "")[:200],
        "end": end.isoformat(),
        "score": verdict.score,
        "reasons": [reason.value for reason in verdict.reasons],
        "attendee_count": len(attendees) if isinstance(attendees, list) else 0,
    }


def _candidate_for(
    event: Mapping[str, Any],
    events: Sequence[Mapping[str, Any]],
    *,
    user_id: UUID,
    user_tz: ZoneInfo,
    user_email: str | None,
    favorite_keys: frozenset[str],
    linked_keys: frozenset[str],
    recorded: frozenset[str],
    now: datetime,
) -> MomentCandidate | None:
    """Whether this finished event earns a moment, and what that moment is.

    Args:
        event: The event under consideration.
        events: Every event of the read window, for the chain rule.
        user_id: Whose moment.
        user_tz: Fallback zone for a naive local time.
        user_email: The account holder's address, or None.
        favorite_keys: Folded names of their favourites.
        linked_keys: Folded names cited by an open commitment.
        recorded: Calendar events LIA already recorded a meeting for.
        now: The instant the pass runs at.

    Returns:
        The candidate, or None when this event earns nothing.
    """
    settings = get_settings()
    event_id = str(event.get("id") or "")
    if not event_id or event_id in recorded:
        return None
    end = event_instant(event.get("end"), user_tz)
    if end is None or end > now:
        return None
    if is_chained(
        event,
        events,
        user_tz=user_tz,
        gap_minutes=settings.moments_event_chain_gap_minutes,
    ):
        return None
    verdict = score_event(
        event,
        user_email=user_email,
        favorite_keys=favorite_keys,
        linked_keys=linked_keys,
        user_tz=user_tz,
    )
    if not verdict.worthy:
        return None
    due_at = end + timedelta(minutes=settings.moments_event_followup_delay_minutes)
    return MomentCandidate(
        user_id=user_id,
        kind=MomentKind.EVENT_FOLLOWUP.value,
        source_ref=event_id,
        due_at=due_at,
        not_after=due_at + timedelta(minutes=settings.moments_event_followup_window_minutes),
        payload=_payload(event, verdict, end),
    )


async def detect(user: Any, now: datetime) -> list[MomentCandidate]:
    """Find the finished meetings this account should be asked about.

    Args:
        user: The account row (id, timezone, email).
        now: The instant the pass runs at.

    Returns:
        Candidates for the repository to file, possibly empty. Never raises: a
        provider failure costs one pass, never the sweep.
    """
    settings = get_settings()
    user_id = UUID(str(user.id))
    user_tz = resolve_user_timezone(user)

    try:
        async with get_db_context() as db, open_active_calendar(db, user_id) as access:
            if not isinstance(access, CalendarAccess):
                return []
            result = await access.client.list_events(
                time_min=(
                    now - timedelta(minutes=settings.moments_detect_lookback_minutes)
                ).isoformat(),
                # Past ``now`` by exactly the chain gap, and no further. The
                # block rule asks whether another meeting starts within that
                # gap AFTER this one ends; a window stopping at ``now`` cannot
                # see a meeting that has not started, so the rule answered
                # « nothing follows » about a block whose end it could not see —
                # and a filed moment is never un-filed. What comes back from the
                # future half is a chain BREAKER only: `_candidate_for` refuses
                # anything that has not ended.
                time_max=(
                    now + timedelta(minutes=settings.moments_event_chain_gap_minutes)
                ).isoformat(),
                max_results=25,
                calendar_id=access.calendar_id,
                fields=_EVENT_FIELDS,
            )
    except Exception as exc:  # noqa: BLE001 — one pass, never the sweep
        logger.warning(
            "moment_calendar_read_failed",
            user_id=str(user_id),
            error_type=type(exc).__name__,
        )
        return []

    events = [item for item in (result.get("items") or []) if isinstance(item, Mapping)]
    if not events:
        return []

    local = await _local_context(
        user_id, since=now - timedelta(minutes=settings.moments_detect_lookback_minutes)
    )
    user_email = getattr(user, "email", None)

    candidates = [
        candidate
        for event in events
        if (
            candidate := _candidate_for(
                event,
                events,
                user_id=user_id,
                user_tz=user_tz,
                user_email=user_email,
                favorite_keys=local.favorites,
                linked_keys=local.linked,
                recorded=local.recorded,
                now=now,
            )
        )
        is not None
    ]
    return candidates


def _people_line(event: Mapping[str, Any], user_email: str | None) -> str | None:
    """Who else was there, named when the provider gave names.

    First names only: the prompt needs enough to write « with Marc and Julie »,
    and a full address in a prompt is personal data the sentence never uses.
    """
    attendees = event.get("attendees")
    if not isinstance(attendees, list):
        return None
    folded_me = (user_email or "").strip().lower()
    names: list[str] = []
    for entry in attendees:
        if not isinstance(entry, Mapping):
            continue
        email = str(entry.get("email") or "").strip().lower()
        if entry.get("self") is True or (folded_me and email == folded_me):
            continue
        display = str(entry.get("displayName") or "").strip()
        names.append(display.split(" ")[0] if display else "someone")
    if not names:
        return None
    shown = ", ".join(names[:3])
    extra = len(names) - 3
    return f"With: {shown}" + (f" and {extra} more" if extra > 0 else "")


def _fact_lines(
    event: Mapping[str, Any],
    end: datetime,
    *,
    user_tz: ZoneInfo,
    user_email: str | None,
    title: str,
) -> tuple[str, ...]:
    """The bounded, factual lines the decision reads.

    What happened, when, and with whom — never an opinion about it. The prompt
    turns these into a question; anything evaluative here would come back as a
    judgement on the person's afternoon.
    """
    lines = [f'Meeting: "{str(event.get("summary") or title)[:120]}"']
    lines.append(f"Ended at: {end.astimezone(user_tz).strftime('%H:%M')} (their local time)")
    people = _people_line(event, user_email)
    if people:
        lines.append(people)
    location = str(event.get("location") or "").strip()
    if location:
        lines.append(f"Where: {location[:120]}")
    return tuple(lines)


async def revalidate(user: Any, source_ref: str, payload: Mapping[str, Any]) -> MomentFacts:
    """Re-read the event, and say whether there is still something to ask about.

    Args:
        user: The account row.
        source_ref: The provider event id.
        payload: What the detector filed, used as the fallback description.

    Returns:
        The facts to put in front of the decision, or ``still_valid=False`` when
        the event was cancelled or the person declined it in the meantime.
    """
    user_id = UUID(str(user.id))
    user_tz = resolve_user_timezone(user)
    title = str(payload.get("title") or "a meeting")

    try:
        async with get_db_context() as db, open_active_calendar(db, user_id) as access:
            if not isinstance(access, CalendarAccess):
                return MomentFacts(still_valid=False)
            event = await access.client.get_event(
                event_id=source_ref,
                calendar_id=access.calendar_id,
                fields=_EVENT_FIELDS,
            )
    except Exception as exc:  # noqa: BLE001 — a re-read that fails says nothing
        logger.info(
            "moment_revalidation_unreadable",
            user_id=str(user_id),
            error_type=type(exc).__name__,
        )
        return MomentFacts(still_valid=False)

    if not isinstance(event, Mapping) or not event:
        return MomentFacts(still_valid=False)
    if is_cancelled(event):
        return MomentFacts(still_valid=False)
    # Declining is an answer that can change AFTER the moment was filed, and
    # the gap between filing and serving is minutes to hours by design. A
    # meeting one declined is not a meeting one had.
    if is_declined_by_self(event, fold_email(str(getattr(user, "email", "") or "")) or None):
        return MomentFacts(still_valid=False)

    end = event_instant(event.get("end"), user_tz)
    if end is None or end > datetime.now(UTC):
        # Moved into the future while the moment waited: there is nothing to
        # debrief yet, and the detector will file it again once it really ends.
        return MomentFacts(still_valid=False)

    return MomentFacts(
        still_valid=True,
        lines=_fact_lines(event, end, user_tz=user_tz, user_email=user.email, title=title),
    )
