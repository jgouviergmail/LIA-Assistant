"""Deterministic tick scoring — a periodic sweep waits for the learned rhythm.

ADR-214 §11.2, behind its own OFF-by-default flag. A proactive tick outside
the learned windows defers ONLY when a later same-day tick can land inside
one within the person's configured bounds — anti-starvation first, fail-open
everywhere: the sweep must never be blocked by its own optimisation.

Lived in ``heartbeat.habit_context`` while the heartbeat was its only reader.
The interest sweep is a second periodic surface interrupting the same person
(A11, 2026-09-11), and ``heartbeat`` imports ``interests`` for its interest
source, so the rule moved to the domain that OWNS the rhythm rather than let
``interests`` import ``heartbeat`` back — a local import there would only
have hidden the cycle from the coupling ratchet.

What differs between the two sweeps is data, declared once per sweep as a
:class:`TickSurface` beside its ``task_type``: which user fields carry its
hour bounds, which setting carries its period, and which label its
deferrals count under.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

import structlog

from src.core.time_utils import now_in_timezone
from src.domains.habits.capability import habits_capability_enabled
from src.domains.habits.consumption import load_consumable_profile
from src.domains.habits.models import ProfileVerdict
from src.domains.habits.repository import HabitsRepository
from src.domains.habits.rhythm import ClaimedWindow, RhythmProfile, hour_in_windows
from src.infrastructure.observability.metrics_habits import (
    heartbeat_rhythm_escapes_total,
    heartbeat_ticks_deferred_total,
)

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class TickSurface:
    """How one periodic sweep names its bounds and its period.

    Declared by the sweep's task module, beside the ``task_type`` its runner
    metrics already carry, and pinned by a test against the sweep's own
    ``EligibilityChecker`` so the two cannot read different fields.
    """

    #: The ``ProactiveTask.task_type`` — the label the deferral counts under.
    task_type: str
    #: The user-settings keys the runner extracted for the sweep's window.
    start_hour_field: str
    end_hour_field: str
    #: The fallbacks the sweep's checker applies when a field is missing.
    default_start_hour: int
    default_end_hour: int
    #: The settings attribute carrying the sweep's period, in minutes.
    interval_setting: str


def should_defer_tick(
    now_local: datetime,
    windows: tuple[ClaimedWindow, ...],
    *,
    notify_start_hour: int,
    notify_end_hour: int,
    tick_interval_minutes: int,
) -> bool:
    """Whether this proactive tick should wait for a learned window (pure).

    The learned rhythm PRIORITIZES, it never widens (ADR-214 decision 4):
    a tick is deferred ONLY when a later same-day tick can land both inside
    a learned window and inside the user's configured bounds. Otherwise —
    inside a window already, last window passed, window out of bounds, or
    no room left for even one tick — the tick flows normally
    (anti-starvation; the runner's guaranteed-minimum pressure stays intact
    because in-window and post-window ticks are never deferred).

    Args:
        now_local: Current time in the user's timezone.
        windows: Claimed windows of the CURRENT day class.
        notify_start_hour: User's configured window start (bounds are never
            widened; used only to detect a midnight-wrapping bounds pair).
        notify_end_hour: User's configured window end.
        tick_interval_minutes: Runner tick period — the margin one more
            tick needs before the bounds close.

    Returns:
        True when the tick should wait for a learned window later today.
    """
    if not windows:
        return False
    hour = now_local.hour + now_local.minute / 60.0
    if hour_in_windows(hour, windows):
        return False
    # Same-day ceiling: with midnight-wrapping user bounds the conservative
    # ceiling is midnight — deferring toward tomorrow would starve today.
    end_bound = float(notify_end_hour) if notify_end_hour > notify_start_hour else 24.0
    entries = [float(w.start_hour) for w in windows if w.start_hour > hour]
    if not entries:
        return False
    return min(entries) + tick_interval_minutes / 60.0 <= end_bound


def _bound(user_settings: dict[str, Any], field: str, default: int) -> int:
    """A configured hour bound — ``is None`` on purpose: hour 0 is a VALID bound."""
    value = user_settings.get(field)
    return default if value is None else int(value)


def _claimed_windows(
    profile: RhythmProfile | None, day_class: str
) -> tuple[ClaimedWindow, ...] | None:
    """The windows a tick may wait for today, or None when there is no claim.

    Claim-quality only: windows without the WINDOWS verdict (corrupt or stale
    payload) must never steer timing.

    Args:
        profile: The consumable profile, or None when nothing is learned.
        day_class: ``weekday`` | ``weekend``.

    Returns:
        The class's claimed windows, or None.
    """
    if profile is None:
        return None
    rhythm = profile.weekday if day_class == "weekday" else profile.weekend
    if rhythm.verdict != ProfileVerdict.WINDOWS.value or not rhythm.windows:
        return None
    return rhythm.windows


async def should_defer_tick_for_rhythm(
    user_id: UUID,
    user_settings: dict[str, Any],
    settings: Any,
    *,
    surface: TickSurface,
    imminent_event_at: datetime | None = None,
) -> bool:
    """Async gate around :func:`should_defer_tick` — flags, profile, class.

    Fail-open at every step: scoring disabled, feature off, user preference
    off, capability off, no profile, non-window verdict, or any storage
    error → False (the sweep must never be blocked by its own optimisation).

    The rhythm PRIORITISES, it never hides an appointment (2026-09-11): when
    the busy guard's calendar read saw an event of theirs starting inside its
    window, this tick is not deferred — a departure advice or a meeting
    reminder is what the tick exists for, and an evening window is no place
    for a 15:00 meeting.

    Args:
        user_id: Owner.
        user_settings: The runner's extracted user settings (timezone,
            bounds, ``habits_enabled`` preference).
        settings: Application settings view.
        surface: The sweep asking — its bounds fields, period and label.
        imminent_event_at: The next event start the agenda verdict carried,
            or None when the guard is off or the calendar was quiet.

    Returns:
        True when this tick should wait for a learned window later today.
    """
    if not getattr(settings, "habits_tick_scoring_enabled", False):
        return False
    if not getattr(settings, "habits_enabled", False):
        return False
    if not user_settings.get("habits_enabled", True):
        return False
    if not await habits_capability_enabled():
        return False
    if imminent_event_at is not None:
        now_utc = now_in_timezone(user_settings.get("timezone"))
        horizon = timedelta(hours=float(settings.moments_busy_guard_window_hours))
        if now_utc <= imminent_event_at <= now_utc + horizon:
            heartbeat_rhythm_escapes_total.labels(
                task_type=surface.task_type, reason="imminent_event"
            ).inc()
            return False
    try:
        from src.infrastructure.database import get_db_context

        async with get_db_context() as db:
            # Consumable windows only: a window the person paused or blocked
            # must never steer the timing (ADR-214 decision 3, measured
            # violated 2026-09-11).
            profile = await load_consumable_profile(HabitsRepository(db), user_id)
        now_local = now_in_timezone(user_settings.get("timezone"))
        day_class = "weekday" if now_local.weekday() < 5 else "weekend"
        windows = _claimed_windows(profile, day_class)
        if windows is None:
            return False
        deferred = should_defer_tick(
            now_local,
            windows,
            notify_start_hour=_bound(
                user_settings, surface.start_hour_field, surface.default_start_hour
            ),
            notify_end_hour=_bound(user_settings, surface.end_hour_field, surface.default_end_hour),
            tick_interval_minutes=int(getattr(settings, surface.interval_setting)),
        )
        if deferred:
            heartbeat_ticks_deferred_total.labels(
                task_type=surface.task_type, day_class=day_class, reason="rhythm"
            ).inc()
            logger.debug(
                "proactive_tick_deferred_rhythm",
                user_id=str(user_id),
                task_type=surface.task_type,
                day_class=day_class,
            )
        return deferred
    except Exception as exc:  # noqa: BLE001 — optimisation must never block ticks
        logger.debug("habit_tick_scoring_failed", error=str(exc))
        return False
