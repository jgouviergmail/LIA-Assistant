"""Heartbeat habits source — learned rhythm + missed-routine offers (ADR-214).

Its own module (``context_aggregator`` is frozen at its audited size and must
only shrink — the ``context_sources`` precedent). One-way dependency: this
module never imports the aggregator.

Three things live here:

- the learned RHYTHM (claimed active windows per day class) — informational:
  the decision LLM prefers notifying inside these windows but the user's
  configured hour bounds always prevail (the block says so explicitly);
- at most ONE missed-routine candidate (a locked recurring request whose
  usual slot passed with no ask) — an OFFER framed as service, bounded by
  the shape-aware k rule, a per-habit cooldown and the stop rule (2
  consecutive ignored offers → mute until the routine re-occurs);
- the deterministic TICK SCORING (plan §11.2, own OFF-by-default flag): a
  proactive tick outside the learned windows defers only when a later
  same-day tick can land inside one within the user's bounds —
  anti-starvation first, fail-open everywhere.

Everything here is READ-ONLY: the offer bookkeeping (dates, mute) is stamped
by ``proactive_task.on_notification_sent`` only when a notification actually
used the HABITS source — exposing a candidate the LLM chose not to surface
must not burn its cooldown.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.i18n_dates import format_half_hour_label
from src.core.time_utils import now_in_timezone, resolve_user_timezone
from src.domains.habits.models import HabitKind, HabitStatus, ProfileVerdict, UserHabit
from src.domains.habits.repository import HabitsRepository
from src.domains.habits.rhythm import ClaimedWindow, RhythmProfile, hour_in_windows
from src.infrastructure.cache import recurrence_store

logger = structlog.get_logger(__name__)


def rhythm_summary(profile_payload: dict[str, Any] | None) -> dict[str, list[str]] | None:
    """Compact per-class window labels from a stored profile payload.

    Args:
        profile_payload: The stored ``UserHabitProfile.payload``, or None.

    Returns:
        ``{"weekday": ["08:00-10:00", ...], "weekend": [...]}`` with only the
        classes that actually claim windows; None when nothing is claimed.
    """
    if not profile_payload:
        return None
    profile = RhythmProfile.from_payload(profile_payload)
    summary = {
        name: [w.label() for w in rhythm.windows]
        for name, rhythm in (("weekday", profile.weekday), ("weekend", profile.weekend))
        if rhythm.windows
    }
    return summary or None


def _scheduled_days_between(days_of_week: list[int], start: date, end: date) -> list[date]:
    """Scheduled dates in (start, end], oldest first."""
    out = []
    d = start + timedelta(days=1)
    while d <= end:
        if d.weekday() in days_of_week:
            out.append(d)
        d += timedelta(days=1)
    return out


def ignored_offer_count(offer_dates: list[str], occurrence_days: set[str]) -> int:
    """Consecutive trailing offers with no occurrence on a later day.

    Read-only stop-rule input: an offer counts as ignored while no occurrence
    happened strictly AFTER it. A single later occurrence resets the run —
    the routine re-proved itself.
    """
    ignored = 0
    for offer_iso in sorted(offer_dates, reverse=True):
        if any(day > offer_iso for day in occurrence_days):
            break
        ignored += 1
    return ignored


def detect_missed_routine(
    habit: UserHabit,
    occurrence_days: set[str],
    now_local: datetime,
    settings: Any,
) -> dict[str, Any] | None:
    """Pure per-habit missed-slot evaluation (plan §5.4, calibrated k rule).

    Args:
        habit: An ACTIVE ``recurring_request`` habit row.
        occurrence_days: ISO dates with ledger occurrences for the signature.
        now_local: The user's local clock.
        settings: Settings view (grace, cooldown, stop rule).

    Returns:
        The offer candidate payload, or None (not missed / muted / cooldown).
    """
    payload = habit.payload or {}
    shape = payload.get("shape")
    trigger_hour = payload.get("trigger_hour")
    days_of_week = payload.get("days_of_week") or []
    if shape not in ("daily", "workdays", "weekly") or trigger_hour is None:
        return None

    today = now_local.date()
    if not _slot_missed(
        shape, days_of_week, float(trigger_hour), occurrence_days, now_local, settings
    ):
        return None
    if not _offer_allowed(payload, occurrence_days, today, settings):
        return None

    return {
        "habit_id": str(habit.id),
        "signature": habit.key,
        "shape": shape,
        "trigger_label": format_half_hour_label(float(trigger_hour)),
        "weekday": days_of_week[0] if shape == "weekly" else None,
    }


def _slot_missed(
    shape: str,
    days_of_week: list[int],
    trigger_hour: float,
    occurrence_days: set[str],
    now_local: datetime,
    settings: Any,
) -> bool:
    """Whether today's scheduled slot passed with no ask (shape-aware k rule).

    A daily/workdays habit needs the PREVIOUS scheduled day missed too
    (k=2 — k=1 at p̂≈0.85 produces ~one false remark a week); a weekly habit
    offers on the first miss (the slot has immediate value).
    """
    today = now_local.date()
    if today.weekday() not in days_of_week:
        return False
    grace = float(settings.habits_deviation_grace_hours)
    if now_local.hour + now_local.minute / 60.0 < trigger_hour + grace:
        return False
    if today.isoformat() in occurrence_days:
        return False
    if shape in ("daily", "workdays"):
        previous = _scheduled_days_between(
            days_of_week, today - timedelta(days=8), today - timedelta(days=1)
        )
        if not previous or previous[-1].isoformat() in occurrence_days:
            return False
    return True


def _offer_allowed(
    payload: dict[str, Any],
    occurrence_days: set[str],
    today: date,
    settings: Any,
) -> bool:
    """Per-habit cooldown + the stop rule (2 ignored offers → silence)."""
    offer_dates = [str(d) for d in payload.get("offer_dates") or []]
    if offer_dates:
        cooldown_floor = (
            today - timedelta(days=settings.habits_deviation_offer_cooldown_days)
        ).isoformat()
        if max(offer_dates) > cooldown_floor:
            return False
    return bool(
        ignored_offer_count(offer_dates, occurrence_days)
        < settings.habits_deviation_stop_after_ignored
    )


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


async def should_defer_tick_for_rhythm(
    user_id: UUID,
    user_settings: dict[str, Any],
    settings: Any,
) -> bool:
    """Async gate around :func:`should_defer_tick` — flags, profile, class.

    Fail-open at every step: scoring disabled, feature off, user preference
    off, no profile, non-window verdict, or any storage error → False (the
    tick pipeline must never be blocked by its own optimization).

    Args:
        user_id: Owner.
        user_settings: The runner's extracted user settings (timezone,
            bounds, ``habits_enabled`` preference).
        settings: Application settings view.

    Returns:
        True when this tick should wait for a learned window later today.
    """
    if not getattr(settings, "habits_tick_scoring_enabled", False):
        return False
    if not getattr(settings, "habits_enabled", False):
        return False
    if not user_settings.get("habits_enabled", True):
        return False
    try:
        from src.infrastructure.database import get_db_context

        async with get_db_context() as db:
            profile_row = await HabitsRepository(db).get_profile(user_id)
        if profile_row is None:
            return False
        profile = RhythmProfile.from_payload(profile_row.payload)
        now_local = now_in_timezone(user_settings.get("timezone"))
        day_class = "weekday" if now_local.weekday() < 5 else "weekend"
        rhythm = profile.weekday if day_class == "weekday" else profile.weekend
        # Claim-quality only: windows without the WINDOWS verdict (corrupt or
        # stale payload) must never steer timing.
        if rhythm.verdict != ProfileVerdict.WINDOWS.value or not rhythm.windows:
            return False
        # Defaults mirror the runner's own bound fallbacks (runner.py) —
        # `is None` checks, because hour 0 (midnight) is a VALID bound.
        start_bound = user_settings.get("heartbeat_notify_start_hour")
        end_bound = user_settings.get("heartbeat_notify_end_hour")
        deferred = should_defer_tick(
            now_local,
            rhythm.windows,
            notify_start_hour=9 if start_bound is None else int(start_bound),
            notify_end_hour=22 if end_bound is None else int(end_bound),
            tick_interval_minutes=int(settings.heartbeat_notification_interval_minutes),
        )
        if deferred:
            from src.infrastructure.observability.metrics_habits import (
                heartbeat_ticks_deferred_total,
            )

            heartbeat_ticks_deferred_total.labels(day_class=day_class).inc()
            logger.debug(
                "heartbeat_tick_deferred_rhythm",
                user_id=str(user_id),
                day_class=day_class,
            )
        return deferred
    except Exception as exc:  # noqa: BLE001 — optimization must never block ticks
        logger.debug("habit_tick_scoring_failed", error=str(exc))
        return False


async def _ledger_occurrence_days(user_id: UUID, signature: str) -> set[str]:
    """ISO dates with recorded occurrences for (user, signature) — best-effort."""
    try:
        from src.infrastructure.cache.redis import get_redis_cache

        redis = await get_redis_cache()
        if not redis:
            return set()
        data = await recurrence_store.load(
            redis, recurrence_store.redis_key(str(user_id), signature)
        )
        return set((data.get("days") or {}).keys())
    except Exception as exc:  # noqa: BLE001 — advisory source, never blocks
        logger.debug("habit_ledger_read_failed", error=str(exc))
        return set()


async def fetch_habits_context(
    db: AsyncSession,
    user_id: UUID,
    user: Any,
    settings: Any,
) -> dict[str, Any] | None:
    """Aggregate the habits block for the heartbeat decision context.

    Args:
        db: Fresh session provided by the aggregator (scoped fetcher).
        user_id: Owner.
        user: The User row (timezone + preference).
        settings: Application settings.

    Returns:
        ``{"rhythm": ..., "missed_routine": ...}`` or None when the feature
        is off for this user or nothing is learned yet.
    """
    if not getattr(settings, "habits_enabled", False) or not getattr(user, "habits_enabled", True):
        return None

    repo = HabitsRepository(db)
    profile_row = await repo.get_profile(user_id)
    rhythm = rhythm_summary(profile_row.payload if profile_row else None)

    now_local = datetime.now(resolve_user_timezone(user))
    candidates = [
        habit
        for habit in await repo.list_habits(user_id, HabitKind.RECURRING_REQUEST.value)
        if habit.status == HabitStatus.ACTIVE.value and not habit.muted_until_reproof
    ]
    missed: dict[str, Any] | None = None
    # Budget: at most ONE offer per cycle — the most confirmed habit first.
    for habit in sorted(candidates, key=lambda h: -h.positive_signals):
        occurrence_days = await _ledger_occurrence_days(user_id, habit.key)
        missed = detect_missed_routine(habit, occurrence_days, now_local, settings)
        if missed:
            break

    if not rhythm and not missed:
        return None
    return {"rhythm": rhythm, "missed_routine": missed}
