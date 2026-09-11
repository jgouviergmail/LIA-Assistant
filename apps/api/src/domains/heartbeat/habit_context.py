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
- the deterministic TICK SCORING moved to ``habits.tick_scoring`` on
  2026-09-11 (A11): the interest sweep reads it too, and ``heartbeat``
  imports ``interests``, so the rule now lives with the rhythm it reads.

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
from src.core.time_utils import resolve_user_timezone
from src.domains.habits import recurrence_locks
from src.domains.habits.capability import habits_capability_enabled
from src.domains.habits.consumption import load_consumable_profile
from src.domains.habits.models import HabitKind, HabitStatus, UserHabit
from src.domains.habits.offer_bookkeeping import ignored_offer_count as ignored_offer_count
from src.domains.habits.repository import HabitsRepository
from src.domains.habits.rhythm import RhythmProfile
from src.infrastructure.cache import recurrence_store

logger = structlog.get_logger(__name__)


#: Shapes that promise a calendar slot the heartbeat can find MISSED — one
#: declaration, in the habits domain (heartbeat already imports habits; the
#: literal that used to live here existed only to avoid a heartbeat→agents
#: edge, and the vocabulary has moved out of agents since).
SLOTTED_SHAPES = recurrence_locks.SLOTTED_SHAPES


def rhythm_summary(profile: RhythmProfile | None) -> dict[str, list[str]] | None:
    """Compact per-class window labels of a (consumable) rhythm profile.

    Args:
        profile: The profile as narrowed by ``load_consumable_profile`` —
            the caller never hands the raw stored payload here, or a window
            the person paused or blocked would be served again.

    Returns:
        ``{"weekday": ["08:00-10:00", ...], "weekend": [...]}`` with only the
        classes that actually claim windows; None when nothing is claimed.
    """
    if profile is None:
        return None
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
    if shape not in SLOTTED_SHAPES or trigger_hour is None:
        return None

    today = now_local.date()
    if not _slot_missed(
        shape, days_of_week, float(trigger_hour), occurrence_days, now_local, settings
    ):
        return None
    if not _offer_allowed(payload, occurrence_days, today, settings):
        return None

    usual_intent = payload.get("usual_intent")
    return {
        "habit_id": str(habit.id),
        "signature": habit.key,
        "shape": shape,
        "trigger_label": format_half_hour_label(float(trigger_hour)),
        "weekday": days_of_week[0] if shape == "weekly" else None,
        # The request descriptor the sync copied from the ledger (Q4): what
        # the person usually asks for on this domain, or None when the row
        # was rebuilt from history that stores no intent.
        "usual_intent": str(usual_intent) if isinstance(usual_intent, str) else None,
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
    if not await habits_capability_enabled():
        return None

    repo = HabitsRepository(db)
    rhythm = rhythm_summary(await load_consumable_profile(repo, user_id))

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
