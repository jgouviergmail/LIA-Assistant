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

from datetime import datetime, timedelta
from time import perf_counter
from typing import Any
from uuid import UUID

import structlog

from src.core.config import settings
from src.core.constants import REDIS_KEY_MOMENTS_AGENDA_PREFIX
from src.core.time_utils import resolve_user_timezone
from src.domains.connectors.calendar_access import CalendarAccess, open_active_calendar
from src.domains.moments.busy import is_in_meeting
from src.domains.shared.consultation_surfaces import record_surface_consultations
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.database import get_db_context

logger = structlog.get_logger(__name__)

#: The surface this read belongs to: it IS part of the heartbeat tick, taken
#: before the aggregator gets a chance to record anything.
_SURFACE = "heartbeat"
_SECTION = "calendar"

#: What the guard asks the provider for — the minimum the predicate reads.
_FIELDS: list[str] = ["id", "summary", "start", "end", "attendees", "status"]


def _cache_key(user_id: UUID) -> str:
    return f"{REDIS_KEY_MOMENTS_AGENDA_PREFIX}{user_id}"


async def _cached_verdict(user_id: UUID) -> bool | None:
    """A recent verdict for this account, or None when there is none."""
    try:
        redis = await get_redis_cache()
        raw = await redis.get(_cache_key(user_id))
    except Exception as exc:  # noqa: BLE001 — a cache is never the answer
        logger.debug("moment_busy_cache_unavailable", error_type=type(exc).__name__)
        return None
    if raw is None:
        return None
    value = raw.decode() if isinstance(raw, bytes) else str(raw)
    return value == "1"


async def _remember(user_id: UUID, busy: bool) -> None:
    """Store the verdict for the configured window, best-effort."""
    try:
        redis = await get_redis_cache()
        await redis.set(
            _cache_key(user_id),
            "1" if busy else "0",
            ex=settings.moments_busy_guard_cache_seconds,
        )
    except Exception as exc:  # noqa: BLE001 — a cache is never the answer
        logger.debug("moment_busy_cache_write_failed", error_type=type(exc).__name__)


async def _read_calendar(user_id: UUID, now: datetime) -> tuple[list[Any] | None, Any, int]:
    """Read the window around ``now``, or say the calendar could not be read.

    The account row is loaded in the SAME session the calendar lookup already
    opens — the predicate needs their zone and their address, and the alternative
    was widening the ``ProactiveTask`` protocol for one caller.

    Returns:
        (events, user, duration_ms). ``events`` is None when nothing could be
        read — which is NOT an empty calendar, and is recorded as such.
    """
    started = perf_counter()
    window = timedelta(hours=settings.moments_busy_guard_window_hours)
    try:
        from src.domains.users.models import User

        async with get_db_context() as db:
            user = await db.get(User, user_id)
            if user is None:
                return None, None, int((perf_counter() - started) * 1000)
            async with open_active_calendar(db, user_id) as access:
                if not isinstance(access, CalendarAccess):
                    return None, user, int((perf_counter() - started) * 1000)
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
        return None, None, int((perf_counter() - started) * 1000)
    return list(result.get("items") or []), user, int((perf_counter() - started) * 1000)


async def should_defer_for_meeting(user_id: UUID, now: datetime) -> bool:
    """Whether this tick should stand aside because a meeting is in progress.

    Args:
        user_id: Whose calendar.
        now: The instant the tick runs at.

    Returns:
        True only when a meeting this person attends is demonstrably in
        progress. Every other answer, including every failure, is False.
    """
    if not settings.moments_busy_guard_enabled:
        return False

    cached = await _cached_verdict(user_id)
    if cached is not None:
        # Redis answered: the calendar was never opened, so nothing is recorded.
        return cached

    events, user, duration_ms = await _read_calendar(user_id, now)
    record_surface_consultations(
        surface=_SURFACE,
        user_id=user_id,
        opened=[] if events is None else [_SECTION],
        # A blind source is NAMED, never read as « nothing there ».
        failed=[_SECTION] if events is None else [],
        duration_ms=duration_ms,
    )
    if events is None or user is None:
        return False

    busy = is_in_meeting(
        events,
        now=now,
        user_tz=resolve_user_timezone(user),
        user_email=getattr(user, "email", None),
    )
    await _remember(user_id, busy)
    return busy
