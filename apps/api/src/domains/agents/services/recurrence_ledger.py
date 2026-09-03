"""Recurrence ledger — detect repeated same-shape requests (P12, ADR-140; v2 ADR-214).

A user asking the same kind of actionable thing with a stable temporal shape
is a candidate for a recurring automation. v2 changes (habits program):

- :func:`build_signature` — the shape is the DOMAINS ONLY; the hour is now a
  MEASURE, no longer part of the key (the fixed 4h bucket split habits
  straddling a boundary and could never see weekly rhythms).
- Storage is PER LOCAL DAY (``{"days": {iso_date: [hours]}, ...}``), capped
  in day entries: the historical 20-occurrence cap kept only ~7 days for a
  multi-daily domain, making the spread lock unreachable (counter-review
  finding of the habits plan).
- :func:`evaluate_suggestion` fires ONLY when a shape LOCK holds (daily /
  workdays / weekly with a learned hour) — measured 0% false suggestions on
  spread/sporadic usage. On lock it promotes a persisted ``UserHabit``
  (fire-and-forget) and returns a localized suggestion carrying the learned
  schedule.

No new table for the ledger itself: it is advisory, losing it on Redis flush
is harmless — the PROMOTED habits live in PostgreSQL, and an empty ledger is
reseeded from durable ``product_outcomes`` by the habits recompute
(``domains.habits.ledger_seed``, storage format shared through
``infrastructure.cache.recurrence_store``).
"""

from __future__ import annotations

import cmath
import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

import structlog

from src.core.i18n_automation import get_recurrence_schedule_suggestion_text
from src.infrastructure.cache import recurrence_store

logger = structlog.get_logger(__name__)

SHAPE_DAILY = "daily"
SHAPE_WORKDAYS = "workdays"
SHAPE_WEEKLY = "weekly"


def build_signature(primary_domain: str, secondary_domains: list[str]) -> str:
    """Stable shape signature of an actionable request — domains only.

    Args:
        primary_domain: Detected primary domain (query intelligence).
        secondary_domains: Detected secondary domains (order-insensitive).

    Returns:
        Signature like ``"email+contact"``.
    """
    return "+".join([primary_domain, *sorted(secondary_domains)])


@dataclass(frozen=True, slots=True)
class RecurrenceLock:
    """A proven temporal shape for a recurring request.

    Attributes:
        shape: ``daily`` | ``workdays`` | ``weekly``.
        trigger_hour: Learned circular-mean hour (None when the weekly lock
            held without hour concentration).
        modal_weekday: 0=Monday..6=Sunday for weekly locks, else None.
        distinct_days: Distinct days observed inside the window.
        occurrences: Total occurrences inside the window.
    """

    shape: str
    trigger_hour: float | None
    modal_weekday: int | None
    distinct_days: int
    occurrences: int

    def days_of_week(self) -> list[int]:
        """Schedule days implied by the shape (0=Monday..6=Sunday)."""
        if self.shape == SHAPE_WEEKLY and self.modal_weekday is not None:
            return [self.modal_weekday]
        if self.shape == SHAPE_WORKDAYS:
            return [0, 1, 2, 3, 4]
        return [0, 1, 2, 3, 4, 5, 6]


# Storage format extracted to infrastructure (three domains share the keys);
# thin aliases keep this module the semantic API and the existing contract
# tests meaningful.
_redis_key = recurrence_store.redis_key
_convert_legacy = recurrence_store.convert_legacy
_load = recurrence_store.load
_store = recurrence_store.store
_trim = recurrence_store.trim
_parse_days = recurrence_store.parse_days


async def record_occurrence(
    user_id: str,
    signature: str,
    *,
    local_date: date,
    local_hour: float,
    settings: Any,
) -> None:
    """Append one occurrence for (user, signature) — per-day, capped.

    Best-effort: any Redis failure is logged at debug and swallowed — the
    ledger is advisory.

    Args:
        user_id: Owner user id (string form).
        signature: Output of :func:`build_signature`.
        local_date: The user's LOCAL calendar date of the occurrence.
        local_hour: Local hour (fractional) of the occurrence.
        settings: Settings view (window, caps).
    """
    try:
        from src.infrastructure.cache.redis import get_redis_cache

        redis = await get_redis_cache()
        if not redis:
            return
        key = _redis_key(user_id, signature)
        data = await _load(redis, key)
        hours = data["days"].setdefault(local_date.isoformat(), [])
        if len(hours) < settings.recurrence_day_hours_cap:
            hours.append(round(float(local_hour), 2))
        # A live turn is direct evidence: the payload's provenance becomes
        # ``live`` even when the seed first rebuilt it (ADR-214 amendment).
        data["origin"] = recurrence_store.ORIGIN_LIVE
        _trim(data, settings.recurrence_ledger_max_entries)
        await _store(redis, key, data, settings.recurrence_window_days)
    except Exception as exc:  # noqa: BLE001 — advisory ledger, never blocks
        logger.debug("recurrence_record_failed", error=str(exc))


def circular_r(hours: list[float]) -> tuple[float, float]:
    """Resultant length R and circular mean hour of a set of hours (period 24)."""
    if not hours:
        return 0.0, 0.0
    z = sum(cmath.exp(2j * math.pi * h / 24.0) for h in hours) / len(hours)
    return abs(z), (cmath.phase(z) * 24.0 / (2 * math.pi)) % 24


def circular_hour_dist(a: float, b: float) -> float:
    """Shortest circular distance between two hours (period 24)."""
    return min((a - b) % 24, (b - a) % 24)


def evaluate_locks(
    days: dict[date, list[float]],
    today: date,
    settings: Any,
) -> RecurrenceLock | None:
    """Pure shape-lock evaluation over per-day occurrence hours.

    Rules (all deterministic, calibrated — habits plan §4.2):
    - existence: ≥ ``recurrence_min_distinct_days`` distinct days in window;
    - weekly lock: ≥ ``recurrence_weekly_min_same_dow`` distinct days on the
      modal weekday AND that weekday holds ≥ ``recurrence_weekly_dow_fraction``
      of distinct days;
    - time lock: ≥ ``recurrence_lock_min_occurrences`` occurrences spread over
      ≥ ``recurrence_lock_min_spread_days`` days with circular R ≥
      ``recurrence_lock_r_min`` AND split-half consistency (both interleaved
      halves R ≥ half_r_min, means within half_agree_hours) — the split-half
      test is what keeps sporadic usage at 0% false locks;
    - daily/workdays labeling deferred to ≥ ``recurrence_shape_min_days``
      distinct days, 'workdays' when ≤ ``recurrence_weekend_tolerance``
      weekend days (early labeling mislabeled daily as workdays — measured).

    Args:
        days: Per-local-date occurrence hours inside (or beyond) the window.
        today: The user's local date (window anchor).
        settings: Settings view (thresholds).

    Returns:
        The proven lock, or None (not recurrent enough / no stable shape yet).
    """
    window_start = today - timedelta(days=settings.recurrence_window_days)
    recent = {d: h for d, h in days.items() if d > window_start and h}
    distinct = sorted(recent.keys())
    if len(distinct) < settings.recurrence_min_distinct_days:
        return None

    occurrences = [h for d in distinct for h in recent[d]]
    r_all, mean_hour = circular_r(occurrences)

    weekly = _weekly_lock(distinct, occurrences, r_all, mean_hour, settings)
    if weekly is not None:
        return weekly
    return _time_lock(recent, distinct, occurrences, r_all, mean_hour, settings)


def _weekly_lock(
    distinct: list[date],
    occurrences: list[float],
    r_all: float,
    mean_hour: float,
    settings: Any,
) -> RecurrenceLock | None:
    """Weekly lock — distinct DAYS per weekday (same-day repeats count once)."""
    dow_days: dict[int, int] = {}
    for d in distinct:
        dow_days[d.weekday()] = dow_days.get(d.weekday(), 0) + 1
    modal_dow, modal_n = max(dow_days.items(), key=lambda kv: kv[1])
    if (
        modal_n < settings.recurrence_weekly_min_same_dow
        or modal_n / len(distinct) < settings.recurrence_weekly_dow_fraction
    ):
        return None
    return RecurrenceLock(
        shape=SHAPE_WEEKLY,
        trigger_hour=mean_hour if r_all >= settings.recurrence_lock_r_min else None,
        modal_weekday=modal_dow,
        distinct_days=len(distinct),
        occurrences=len(occurrences),
    )


def _split_halves_agree(
    recent: dict[date, list[float]], distinct: list[date], settings: Any
) -> bool:
    """Split-half consistency — what keeps sporadic usage at 0% false locks."""
    ordered = [h for d in distinct for h in sorted(recent[d])]
    r1, m1 = circular_r(ordered[0::2])
    r2, m2 = circular_r(ordered[1::2])
    return bool(
        r1 >= settings.recurrence_lock_half_r_min
        and r2 >= settings.recurrence_lock_half_r_min
        and circular_hour_dist(m1, m2) <= settings.recurrence_lock_half_agree_hours
    )


def _time_lock(
    recent: dict[date, list[float]],
    distinct: list[date],
    occurrences: list[float],
    r_all: float,
    mean_hour: float,
    settings: Any,
) -> RecurrenceLock | None:
    """Time lock (daily/workdays) with split-half consistency and deferred labeling."""
    if len(occurrences) < settings.recurrence_lock_min_occurrences:
        return None
    if (distinct[-1] - distinct[0]).days < settings.recurrence_lock_min_spread_days:
        return None
    if r_all < settings.recurrence_lock_r_min:
        return None
    if not _split_halves_agree(recent, distinct, settings):
        return None
    # Shape labeling deferred until enough distinct days are seen (early
    # labeling mislabeled daily habits as workdays — measured).
    if len(distinct) < settings.recurrence_shape_min_days:
        return None
    weekend_days = sum(1 for d in distinct if d.weekday() >= 5)
    shape = SHAPE_WORKDAYS if weekend_days <= settings.recurrence_weekend_tolerance else SHAPE_DAILY
    return RecurrenceLock(
        shape=shape,
        trigger_hour=mean_hour,
        modal_weekday=None,
        distinct_days=len(distinct),
        occurrences=len(occurrences),
    )


async def _promote_recurring_habit(user_id: str, signature: str, lock: RecurrenceLock) -> None:
    """Persist the locked recurrence as a user-controllable habit row.

    Own session, best-effort: promotion failing must never affect the turn.
    Respects the user's habits preference and BLOCKED tombstones (repository
    contract).
    """
    try:
        from uuid import UUID

        from src.core.config import settings as app_settings
        from src.infrastructure.database import get_db_context

        if not getattr(app_settings, "habits_enabled", False):
            return
        async with get_db_context() as db:
            from src.domains.habits.models import HabitKind
            from src.domains.habits.repository import HabitsRepository
            from src.domains.users.models import User

            uid = UUID(user_id)
            user = await db.get(User, uid)
            if user is None or not user.habits_enabled:
                return
            repo = HabitsRepository(db)
            # Per-kind cap (published setting — a declared bound must be
            # enforced): a NEW signature beyond the cap is dropped with a log;
            # an existing one keeps updating.
            existing = await repo.list_habits(uid, HabitKind.RECURRING_REQUEST.value)
            if signature not in {h.key for h in existing} and len(existing) >= int(
                app_settings.habits_max_habits_per_kind
            ):
                logger.info(
                    "recurring_habit_promotion_capped",
                    user_id=user_id,
                    signature=signature,
                    cap=app_settings.habits_max_habits_per_kind,
                )
                return
            outcome = await repo.upsert_habit(
                user_id=uid,
                kind=HabitKind.RECURRING_REQUEST.value,
                key=signature,
                payload={
                    "version": 1,
                    "shape": lock.shape,
                    "trigger_hour": lock.trigger_hour,
                    "days_of_week": lock.days_of_week(),
                    "distinct_days": lock.distinct_days,
                    "occurrences": lock.occurrences,
                },
                last_observed_at=datetime.now(UTC),
            )
            await db.commit()
            logger.info(
                "recurring_habit_promoted",
                user_id=user_id,
                signature=signature,
                shape=lock.shape,
                outcome=outcome,
            )
    except Exception as exc:  # noqa: BLE001 — best-effort persistence
        logger.warning("recurring_habit_promotion_failed", error=str(exc))


async def evaluate_suggestion(
    user_id: str,
    signature: str,
    *,
    language: str,
    local_today: date,
    settings: Any,
) -> str | None:
    """Return the localized automation suggestion when a shape lock is proven.

    Fires ONCE per cooldown; on fire, the locked habit is promoted to a
    persisted ``UserHabit`` (fire-and-forget) and the returned text carries
    the LEARNED schedule so the assistant can propose a prefilled automation.

    Args:
        user_id: Owner user id (string form).
        signature: Output of :func:`build_signature`.
        language: User language for the suggestion text.
        local_today: The user's local calendar date (window anchor).
        settings: Settings view (flag + thresholds).

    Returns:
        Localized suggestion text, or None (no lock / cooldown / off).
    """
    if not getattr(settings, "recurrence_suggestion_enabled", False):
        return None
    try:
        from src.infrastructure.cache.redis import get_redis_cache

        redis = await get_redis_cache()
        if not redis:
            return None
        key = _redis_key(user_id, signature)
        data = await _load(redis, key)

        now = datetime.now(UTC)
        suggested_at = data.get("suggested_at")
        if suggested_at is not None:
            cooldown_start = now - timedelta(days=settings.recurrence_suggestion_cooldown_days)
            if datetime.fromtimestamp(int(suggested_at), tz=UTC) > cooldown_start:
                return None

        lock = evaluate_locks(_parse_days(data), local_today, settings)
        if lock is None:
            return None

        data["suggested_at"] = int(now.timestamp())
        await _store(redis, key, data, settings.recurrence_window_days)

        from src.infrastructure.async_utils import safe_fire_and_forget

        safe_fire_and_forget(
            _promote_recurring_habit(user_id, signature, lock),
            name=f"recurring_habit_promotion_{user_id}",
        )

        logger.info(
            "recurrence_suggestion_fired",
            user_id=user_id,
            signature=signature,
            shape=lock.shape,
            distinct_days=lock.distinct_days,
        )
        return get_recurrence_schedule_suggestion_text(language, lock)
    except Exception as exc:  # noqa: BLE001 — advisory, never blocks the turn
        logger.debug("recurrence_evaluate_failed", error=str(exc))
        return None
