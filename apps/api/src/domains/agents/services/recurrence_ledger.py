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

import json
from datetime import date
from typing import Protocol
from uuid import UUID

import structlog
from sqlalchemy import select

from src.core.conversation_execution import ExecutionRevoked
from src.core.conversation_source import current_conversation_source
from src.core.run_authority import require_runtime_authority
from src.domains.agents.context.extraction_revision import capture_run_extraction_revision
from src.domains.users.models import User
from src.infrastructure.cache import recurrence_store
from src.infrastructure.database.session import get_db_context
from src.infrastructure.observability.metrics_agents import recurrence_ledger_writes_total
from src.infrastructure.streaming.runtime_redis import run_runtime_mutation

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
WRITE_SOURCE_RETIRED = "source_retired"


class RecurrenceSettings(Protocol):
    """Only the storage bounds the writer consumes."""

    recurrence_day_hours_cap: int
    recurrence_ledger_max_entries: int
    recurrence_window_days: int


# The key's tail has ONE producer, shared with the nightly seed (habits): the
# storage module owns it, this module re-exports it as its historical name.
build_signature = recurrence_store.build_signature


async def record_occurrence(
    user_id: str,
    signature: str,
    *,
    local_date: date,
    local_hour: float,
    settings: RecurrenceSettings,
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
        source = current_conversation_source()
        write_token = await recurrence_store.acquire_write_token(redis, user_id) if source else None
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
        if source is None:
            await recurrence_store.store(redis, key, data, settings.recurrence_window_days)
        else:
            owner = UUID(user_id)
            require_runtime_authority(owner, source.runtime_id)
            async with get_db_context() as db:
                if await capture_run_extraction_revision(db, owner) is None:
                    raise ExecutionRevoked()
                if not await db.scalar(select(User.habits_enabled).where(User.id == owner)):
                    raise ExecutionRevoked()
            # Account learning is not runtime garbage: do not inventory this
            # key. The atomic invocation grant still rejects a command that
            # arrives after closure/reset, without holding SQL across Redis.
            written = await run_runtime_mutation(
                redis,
                owner_id=owner,
                runtime_id=source.runtime_id,
                script=recurrence_store.FENCED_STORE
                + "return store_current(KEYS[4], KEYS[3], ARGV[5], ARGV[3], ARGV[4], false)",
                keys=(key, recurrence_store.writer_key(user_id)),
                args=(
                    json.dumps(data),
                    str(settings.recurrence_window_days * 86400),
                    str(write_token),
                ),
            )
            if written != 1:
                raise ExecutionRevoked()
        recurrence_ledger_writes_total.labels(outcome=WRITE_WRITTEN).inc()
    except ExecutionRevoked:
        recurrence_ledger_writes_total.labels(outcome=WRITE_SOURCE_RETIRED).inc()
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
    settings: RecurrenceSettings,
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
