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

from datetime import UTC, date, datetime, timedelta
from typing import Any

import structlog

from src.core.i18n_automation import get_recurrence_schedule_suggestion_text

# The lock SEMANTICS live in the habits domain since 2026-09-11 (the nightly
# sync evaluates every signature there); this module keeps the chat-side
# behaviour and re-exports every historical name.
from src.domains.habits.recurrence_locks import (
    RECURRENCE_SHAPES,
    SHAPE_DAILY,
    SHAPE_INTERMITTENT,
    SHAPE_WEEKLY,
    SHAPE_WORKDAYS,
    SLOTTED_SHAPES,
    RecurrenceLock,
    circular_hour_dist,
    circular_r,
    evaluate_locks,
)
from src.infrastructure.cache import recurrence_store
from src.infrastructure.observability.metrics_agents import recurrence_ledger_writes_total

logger = structlog.get_logger(__name__)

#: Historical surface of this module: the lock vocabulary and evaluation now
#: owned by ``habits.recurrence_locks`` stay importable from here.
__all__ = [
    "RECURRENCE_SHAPES",
    "SHAPE_DAILY",
    "SHAPE_INTERMITTENT",
    "SHAPE_WEEKLY",
    "SHAPE_WORKDAYS",
    "SLOTTED_SHAPES",
    "RecurrenceLock",
    "build_signature",
    "circular_hour_dist",
    "circular_r",
    "evaluate_locks",
    "evaluate_suggestion",
    "record_occurrence",
    "record_occurrence_if_allowed",
]

#: Ledger write outcomes (``recurrence_ledger_writes_total``).
WRITE_WRITTEN = "written"
WRITE_REDIS_UNAVAILABLE = "redis_unavailable"
WRITE_FAILED = "failed"
#: The person switched « Apprendre mes habitudes » off: a refusal of THEIRS,
#: which the ``RecurrenceLedgerSilent`` alert must read as such.
WRITE_USER_DISABLED = "user_disabled"
#: The operator switched the habits capability off after boot (the
#: deployment ceiling is read by the extraction gate itself).
WRITE_FEATURE_DISABLED = "feature_disabled"


# Storage format extracted to infrastructure (three domains share the keys);
# thin aliases keep this module the semantic API and the existing contract
# tests meaningful. ``build_signature`` lives there too: the seed (habits)
# needs it and habits importing agents would close the cycle the coupling
# ratchet forbids.
build_signature = recurrence_store.build_signature
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
    intent: str | None = None,
) -> None:
    """Append one occurrence for (user, signature) — per-day, capped.

    Best-effort: the ledger is advisory, so a failure never reaches the turn
    — but it is COUNTED (``recurrence_ledger_writes_total``) and logged at
    warning, because production ships INFO and above and a debug line was a
    trace nobody could read (2026-09-11).

    Args:
        user_id: Owner user id (string form).
        signature: Output of :func:`build_signature`.
        local_date: The user's LOCAL calendar date of the occurrence.
        local_hour: Local hour (fractional) of the occurrence.
        settings: Settings view (window, caps).
        intent: The analyzer's ``immediate_intent`` for this turn — recorded
            as DATA in the payload's histogram (Q4), never in the key.
    """
    try:
        from src.infrastructure.cache.redis import get_redis_cache

        redis = await get_redis_cache()
        if not redis:
            recurrence_ledger_writes_total.labels(outcome=WRITE_REDIS_UNAVAILABLE).inc()
            return
        key = _redis_key(user_id, signature)
        data = await _load(redis, key)
        hours = data["days"].setdefault(local_date.isoformat(), [])
        if len(hours) < settings.recurrence_day_hours_cap:
            hours.append(round(float(local_hour), 2))
        recurrence_store.record_intent(data, intent)
        # A live turn is direct evidence: the payload's provenance becomes
        # ``live`` even when the seed first rebuilt it (ADR-214 amendment).
        data["origin"] = recurrence_store.ORIGIN_LIVE
        _trim(data, settings.recurrence_ledger_max_entries)
        await _store(redis, key, data, settings.recurrence_window_days)
        recurrence_ledger_writes_total.labels(outcome=WRITE_WRITTEN).inc()
    except Exception as exc:  # noqa: BLE001 — advisory ledger, never blocks
        recurrence_ledger_writes_total.labels(outcome=WRITE_FAILED).inc()
        logger.warning("recurrence_record_failed", error=str(exc), error_type=type(exc).__name__)


async def record_occurrence_if_allowed(
    user_id: str,
    signature: str,
    *,
    local_date: date,
    local_hour: float,
    settings: Any,
    intent: str | None = None,
) -> None:
    """Record one occurrence unless the person switched learning off.

    The gate (``habits/learning_gate.py``) is the account preference the
    settings panel edits; it used to stop the promotion only, so the ledger
    kept recording the requests of someone who had asked LIA not to learn
    them (measured 2026-09-11, sim C5). Read here, in the background task,
    so the turn's own path pays nothing.

    Args:
        user_id: Owner user id (string form).
        signature: Output of :func:`build_signature`.
        local_date: The user's LOCAL calendar date of the occurrence.
        local_hour: Local hour (fractional) of the occurrence.
        settings: Settings view (window, caps).
        intent: The analyzer's ``immediate_intent`` for this turn.
    """
    from src.domains.habits.capability import habits_capability_enabled
    from src.domains.habits.learning_gate import read_learning_gate

    if not await habits_capability_enabled():
        recurrence_ledger_writes_total.labels(outcome=WRITE_FEATURE_DISABLED).inc()
        return
    gate = await read_learning_gate(user_id)
    if not gate.allowed:
        recurrence_ledger_writes_total.labels(outcome=WRITE_USER_DISABLED).inc()
        return
    await record_occurrence(
        user_id,
        signature,
        local_date=local_date,
        local_hour=local_hour,
        settings=settings,
        intent=intent,
    )


async def _promote_recurring_habit(
    user_id: str,
    signature: str,
    lock: RecurrenceLock,
    *,
    usual_intent: str | None = None,
) -> None:
    """Persist the locked recurrence as a user-controllable habit row.

    Own session, best-effort: promotion failing must never affect the turn.
    Respects the user's habits preference and BLOCKED tombstones (repository
    contract).

    Args:
        user_id: Owner (string form).
        signature: The locked signature.
        lock: The proven lock.
        usual_intent: The ledger's dominant intent, carried into the row so
            the panel and the heartbeat name the request (Q4); None when
            nothing usable was recorded.
    """
    try:
        from uuid import UUID

        from src.core.config import settings as app_settings
        from src.domains.habits.capability import habits_capability_enabled
        from src.infrastructure.database import get_db_context

        if not await habits_capability_enabled():
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
            from src.domains.habits.recurrence_sync import lock_payload

            # The same payload the nightly sync writes (one builder), and a
            # live turn IS a fresh occurrence: the stop-rule mute may lift.
            outcome = await repo.upsert_habit(
                user_id=uid,
                kind=HabitKind.RECURRING_REQUEST.value,
                key=signature,
                payload=lock_payload(lock, usual_intent=usual_intent),
                last_observed_at=datetime.now(UTC),
                reset_mute=True,
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
            _promote_recurring_habit(
                user_id,
                signature,
                lock,
                usual_intent=recurrence_store.dominant_intent(data),
            ),
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
