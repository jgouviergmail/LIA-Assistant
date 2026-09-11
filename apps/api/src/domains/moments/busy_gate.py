"""Do not interrupt someone who is in a meeting.

The heartbeat's nearest guard is the activity cooldown, which asks « did they
just type? ». Someone in a meeting precisely does not type, so that guard reads
their silence as availability — it is the moment it believes them MOST
available.

This runs BEFORE the decision spends a model call, which is why it reads the
calendar itself rather than waiting for the aggregator. Three rules follow:

- **it fails open, everywhere.** Not knowing is not a reason to stay silent,
  and never a reason to take a tick down.
- **the read is cached briefly.** A tick per account every thirty minutes must
  not become a calendar call every thirty minutes for a verdict that barely
  moves.
- **a cache hit is not a consultation.** Redis answered; the calendar was never
  opened. Recording one would be a false claim in a register whose whole promise
  is « exact or absent » — and a LIVE read is recorded even when the tick then
  says nothing, because the person's calendar was opened on LIA's own
  initiative.

A moment never reaches this gate: ``check_eligibility`` answers on the account
flag alone when it serves one, because a debrief speaks exactly when a meeting
has just ended (ADR-281).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from time import perf_counter
from typing import Any
from uuid import UUID

import structlog

from src.core.config import settings
from src.core.constants import REDIS_KEY_MOMENTS_AGENDA_PREFIX
from src.core.time_utils import resolve_user_timezone
from src.domains.connectors.calendar_access import CalendarAccess, open_active_calendar
from src.domains.moments.busy import is_in_meeting, next_event_start
from src.domains.shared.consultation_surfaces import record_surface_consultations
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.database import get_db_context

logger = structlog.get_logger(__name__)

#: The surface this read belongs to by default: it IS part of the heartbeat
#: tick, taken before the aggregator gets a chance to record anything. The
#: interest sweep asks the same question about the same calendar and files
#: its live read under its OWN surface (A11) — one cached verdict, two
#: readers, and a cache hit still records nothing for either.
_SURFACE = "heartbeat"
_SECTION = "calendar"

#: What the guard asks the provider for — the minimum the predicate reads.
_FIELDS: list[str] = ["id", "summary", "start", "end", "attendees", "status"]


def _cache_key(user_id: UUID) -> str:
    return f"{REDIS_KEY_MOMENTS_AGENDA_PREFIX}{user_id}"


@dataclass(frozen=True, slots=True)
class AgendaVerdict:
    """What one calendar read said about the next couple of hours.

    Attributes:
        busy: A meeting this person attends is in progress (ADR-281).
        next_start: The earliest future start of an event of theirs inside
            the guard's window, or None — read by the learned-rhythm tick
            scoring, which must not defer a tick past an imminent appointment
            (2026-09-11).
    """

    busy: bool
    next_start: datetime | None = None


def _decode_verdict(raw: Any) -> AgendaVerdict:
    """Read a cached verdict — the JSON shape, or the ``"0"``/``"1"`` flag the
    cache held before the next start travelled with it."""
    value = raw.decode() if isinstance(raw, bytes) else str(raw)
    if value in ("0", "1"):
        return AgendaVerdict(busy=value == "1")
    data = json.loads(value)
    next_start = data.get("next_start")
    return AgendaVerdict(
        busy=bool(data.get("busy")),
        next_start=datetime.fromisoformat(next_start) if next_start else None,
    )


async def _cached_verdict(user_id: UUID) -> AgendaVerdict | None:
    """A recent verdict for this account, or None when there is none."""
    try:
        redis = await get_redis_cache()
        raw = await redis.get(_cache_key(user_id))
        return None if raw is None else _decode_verdict(raw)
    except Exception as exc:  # noqa: BLE001 — a cache is never the answer
        logger.debug("moment_busy_cache_unavailable", error_type=type(exc).__name__)
        return None


async def _remember(user_id: UUID, verdict: AgendaVerdict) -> None:
    """Store the verdict for the configured window, best-effort."""
    try:
        redis = await get_redis_cache()
        await redis.set(
            _cache_key(user_id),
            json.dumps(
                {
                    "busy": verdict.busy,
                    "next_start": verdict.next_start.isoformat() if verdict.next_start else None,
                }
            ),
            ex=settings.moments_busy_guard_cache_seconds,
        )
    except Exception as exc:  # noqa: BLE001 — a cache is never the answer
        logger.debug("moment_busy_cache_write_failed", error_type=type(exc).__name__)


@dataclass(frozen=True, slots=True)
class _CalendarRead:
    """What one attempt to read the calendar produced.

    Three readings of one fact, kept apart because the register tells them
    apart: the provider answered (``events``), the provider was asked and
    could not answer (``asked`` and no events — filed ``failed``), nobody
    was asked at all (no account, no connector — nothing to file).
    """

    events: list[Any] | None
    user: Any
    duration_ms: int
    asked: bool


async def _read_calendar(user_id: UUID, now: datetime) -> _CalendarRead:
    """Read the window around ``now``, or say the calendar could not be read.

    The account row is loaded in the SAME session the calendar lookup already
    opens — the predicate needs their zone and their address, and the alternative
    was widening the ``ProactiveTask`` protocol for one caller.

    Returns:
        The read. ``events`` is None when nothing could be read — which is NOT
        an empty calendar, and is recorded as such when a provider was asked.
    """
    started = perf_counter()
    window = timedelta(hours=settings.moments_busy_guard_window_hours)
    asked = False
    try:
        from src.domains.users.models import User

        async with get_db_context() as db:
            user = await db.get(User, user_id)
            if user is None:
                return _CalendarRead(None, None, int((perf_counter() - started) * 1000), False)
            async with open_active_calendar(db, user_id) as access:
                if not isinstance(access, CalendarAccess):
                    return _CalendarRead(None, user, int((perf_counter() - started) * 1000), False)
                asked = True
                result = await access.client.list_events(
                    time_min=(now - window).isoformat(),
                    time_max=(now + window).isoformat(),
                    max_results=20,
                    calendar_id=access.calendar_id,
                    fields=_FIELDS,
                )
    except Exception as exc:  # noqa: BLE001 — fail open
        logger.info(
            "moment_busy_calendar_unreadable",
            user_id=str(user_id),
            error_type=type(exc).__name__,
        )
        return _CalendarRead(None, None, int((perf_counter() - started) * 1000), asked)
    return _CalendarRead(
        list(result.get("items") or []), user, int((perf_counter() - started) * 1000), True
    )


async def agenda_verdict(
    user_id: UUID, now: datetime, *, surface: str = _SURFACE
) -> AgendaVerdict | None:
    """What the calendar says about now and the next couple of hours.

    ONE read per tick per account (cached ``moments_busy_guard_cache_seconds``),
    consumed twice by a sweep's ``check_eligibility``: the busy half stands
    the tick aside, the next start lets the learned rhythm's deferral step
    aside.

    Args:
        user_id: Whose calendar.
        now: The instant the tick runs at.
        surface: The consultation surface a LIVE read is filed under — the
            sweep's ``task_type`` (its surface key, ADR-263).

    Returns:
        The verdict, or None when the guard is switched off or nothing could
        be read — every failure is « no verdict », never a deferral.
    """
    if not settings.moments_busy_guard_enabled:
        return None

    cached = await _cached_verdict(user_id)
    if cached is not None:
        # Redis answered: the calendar was never opened, so nothing is recorded.
        return cached

    read = await _read_calendar(user_id, now)
    if read.asked:
        # The calendar was OPENED on LIA's own initiative: filed whether it
        # answered or not — a blind source is NAMED, never read as « nothing
        # there » (an ``opened`` that omits the section files nothing at all,
        # which is how the failed branch used to vanish). A calendar nobody
        # could ask — no account, no connector — is not a consultation.
        record_surface_consultations(
            surface=surface,
            user_id=user_id,
            opened=[_SECTION],
            failed=[_SECTION] if read.events is None else [],
            duration_ms=read.duration_ms,
        )
    events, user = read.events, read.user
    if events is None or user is None:
        return None

    user_tz = resolve_user_timezone(user)
    user_email = getattr(user, "email", None)
    verdict = AgendaVerdict(
        busy=is_in_meeting(events, now=now, user_tz=user_tz, user_email=user_email),
        next_start=next_event_start(events, now=now, user_tz=user_tz, user_email=user_email),
    )
    await _remember(user_id, verdict)
    return verdict


async def should_defer_for_meeting(user_id: UUID, now: datetime) -> bool:
    """Whether this tick should stand aside because a meeting is in progress.

    Args:
        user_id: Whose calendar.
        now: The instant the tick runs at.

    Returns:
        True only when a meeting this person attends is demonstrably in
        progress. Every other answer, including every failure, is False.
    """
    verdict = await agenda_verdict(user_id, now)
    return verdict is not None and verdict.busy
