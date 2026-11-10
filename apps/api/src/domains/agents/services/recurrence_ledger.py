"""Recurrence ledger — record what a person asks, day by day (ADR-140, ADR-214, ADR-375).

The chat side of the ledger is a WRITER only: each actionable human turn
appends its local hour to the day of its domain (``record_occurrence``). What
the ledger means — the recurring needs and the proposals they open — is read
by the habits domain's nightly recompute (``habits.needs``,
``habits.proposal_rules``). The lock this module used to evaluate on every
turn, the suggestion text it injected into the answer and the promotion it ran
from the chat are gone (ADR-375): the hour is a descriptor, never a condition,
and a proposal is shown by the code, never left for a model to repeat.

No new table for the ledger itself: it is advisory, losing it on Redis flush
is harmless — an empty ledger is reseeded from durable ``product_outcomes`` by
the habits recompute (``domains.habits.ledger_seed``, storage format shared
through ``infrastructure.cache.recurrence_store``).
"""

from __future__ import annotations

from datetime import date
from typing import Any

import structlog

from src.infrastructure.cache import recurrence_store
from src.infrastructure.observability.metrics_agents import recurrence_ledger_writes_total

logger = structlog.get_logger(__name__)

__all__ = [
    "build_signature",
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


# The key's tail has ONE producer, shared with the nightly seed (habits): the
# storage module owns it, this module re-exports it as its historical name.
build_signature = recurrence_store.build_signature


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
        key = recurrence_store.redis_key(user_id, signature)
        data = await recurrence_store.load(redis, key)
        recurrence_store.add_day_hour(
            data,
            local_date.isoformat(),
            local_hour,
            cap=int(settings.recurrence_day_hours_cap),
        )
        recurrence_store.record_intent(data, intent)
        # A live turn is direct evidence: the payload's provenance becomes
        # ``live`` even when the seed first rebuilt it (ADR-214 amendment).
        data["origin"] = recurrence_store.ORIGIN_LIVE
        recurrence_store.trim(data, settings.recurrence_ledger_max_entries)
        await recurrence_store.store(redis, key, data, settings.recurrence_window_days)
        recurrence_ledger_writes_total.labels(outcome=WRITE_WRITTEN).inc()
    except Exception as exc:  # noqa: BLE001 — advisory ledger, never blocks
        recurrence_ledger_writes_total.labels(outcome=WRITE_FAILED).inc()
        # Facts only (ADR-317): the exception text may quote the payload.
        logger.warning("recurrence_record_failed", error_type=type(exc).__name__)


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
