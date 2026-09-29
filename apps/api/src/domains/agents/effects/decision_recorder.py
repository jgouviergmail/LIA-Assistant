"""Writing one row per turn, exactly once (ADR-263, lot 6).

The companion of ``treatment_recorder``, and deliberately built the same way,
because the two failures it must survive are the same:

- ``__aexit__`` runs on the normal path, on an exception AND on a cancellation,
  so a turn stopped mid-flight still closes its books;
- the write is ``asyncio.shield``ed with a bounded grace, because a
  re-delivered cancellation during cleanup would otherwise lose it — measured
  in lot 4, where an unshielded flush dropped every consultation of a
  cancelled turn.

One difference, and it is the whole point of the lot: the write is an **upsert
on ``run_id``**. A HITL resumption reuses the identifier, so the same turn comes
back — with an answer this time. Inserting would fail on the unique constraint;
overwriting in silence would make an interrupted turn indistinguishable from a
straight one. So the row keeps the EARLIEST start, takes the LATEST end,
accumulates the duration, and counts its ``segments``.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import structlog

from src.domains.agents.effects.decisions import (
    TurnDecision,
    publish_turn,
    reset_turn,
)
from src.domains.agents.effects.models import DecisionOutcome
from src.infrastructure.async_utils import write_through_cancellation

logger = structlog.get_logger(__name__)

#: How many times the write may be re-attempted while the task is being
#: cancelled. Same bound and same reason as the consultation recorder: a
#: re-delivered cancellation must not cost the row, and an unbounded retry must
#: not hold a shutdown open.
CANCELLATION_GRACE_ATTEMPTS = 3


@asynccontextmanager
async def decision_recorder(decision: TurnDecision) -> AsyncIterator[TurnDecision]:
    """Publish the turn, then write it once whatever happens.

    Args:
        decision: The live record, already carrying what the parent knows.

    The outcome is DERIVED here, from what actually happened, rather than
    asked of a caller who would eventually forget:

    - the body raised → ``failed``;
    - the body was cancelled, or simply ended without an answer (a HITL
      interrupt is exactly that) → ``interrupted``, the starting value;
    - something called ``note_answered`` → ``answered``.

    And an explicit success is never downgraded: a stream that breaks during
    teardown after the answer was delivered leaves a turn the user DID get an
    answer from, and recording it as a failure would be the register lying in
    the other direction.

    Yields:
        The same record, so the caller can enrich it directly as well as
        through the ``note_*`` helpers.
    """
    token = publish_turn(decision)
    try:
        yield decision
    except asyncio.CancelledError:
        # The turn was cut short. ``interrupted`` is already the value.
        raise
    except Exception:
        if decision.outcome is DecisionOutcome.INTERRUPTED:
            decision.outcome = DecisionOutcome.FAILED
        raise
    finally:
        reset_turn(token)
        await _write_shielded(decision)


async def record_decision(decision: TurnDecision) -> None:
    """Write one turn's row directly, for a caller that owns no context.

    The context manager above suits a turn whose START and END bracket real
    work. A proactive run is reported the other way round: the work is over and
    its cost is known when ``track_proactive_tokens`` is called, so there is
    nothing to wrap — only a row to file, under the very ``run_id`` the cost
    was filed under.

    Best-effort like every register write: the money is already spent, and a
    ledger that can take a briefing down is worse than the gap it closes.

    Args:
        decision: The completed record.
    """
    await _write_logged(decision)


async def record_decision_once(decision: TurnDecision) -> None:
    """Write the row of an act that cannot be resumed; a second filing changes nothing.

    For a run out of any conversation whose end more than one party may see —
    a radio session is closed by its loop, or by the service when no loop holds
    it (ADR-263 amendment 2026-09-27). Merged, two closers racing would read as a turn
    run twice. Best-effort like :func:`record_decision`.

    Args:
        decision: The completed record.
    """
    await _write_shielded(decision, once=True)


async def _write_shielded(decision: TurnDecision, *, once: bool = False) -> None:
    """Write the turn, surviving a cancellation delivered during cleanup.

    One implementation, shared with the consultation register: shielding a
    FRESH coroutine per attempt runs the write twice (simulated), and here that
    would upsert the turn a second time — ``segments`` reading 2 for a turn
    nobody interrupted.

    Args:
        decision: The record to persist.

    Raises:
        asyncio.CancelledError: Re-raised once the write is done, so a
            cancelled turn stays cancelled.
    """
    cancelled = await write_through_cancellation(
        lambda: _write_logged(decision, once=once),
        attempts=CANCELLATION_GRACE_ATTEMPTS,
        label="decision_write",
    )
    if cancelled:
        raise asyncio.CancelledError


async def _write_logged(decision: TurnDecision, *, once: bool = False) -> None:
    """Write, and turn a failure into a log rather than a raised task.

    The register is best-effort: losing a row must never take the turn down
    with it, and an unretrieved task exception would only surface as an
    asyncio warning nobody reads.

    Args:
        decision: The record to persist.
        once: Whether a second filing of the run is a duplicate rather than a
            new segment.
    """
    try:
        await _write(decision, once=once)
    except Exception:
        logger.exception("decision_write_failed", run_id=decision.run_id)


async def _write(decision: TurnDecision, *, once: bool = False) -> None:
    """Upsert the turn's row — or, for an act filed once, insert it unless it exists.

    Args:
        decision: The record to persist.
        once: Whether a second filing of the run is a duplicate rather than a
            new segment.
    """
    if decision.user_id is None:
        # No account named the turn — a probe, a boot check, a test harness.
        # Nothing to record and nobody to record it for.
        return

    from src.domains.agents.effects.decision_repository import DecisionRepository
    from src.infrastructure.database.session import get_db_context

    ended_at = datetime.now(UTC)
    async with get_db_context() as db:
        repository = DecisionRepository(db)
        if once:
            await repository.record_once(decision, ended_at=ended_at)
        else:
            await repository.record(decision, ended_at=ended_at)
        await db.commit()

    from src.infrastructure.observability.metrics_effects import decisions_total

    decisions_total.labels(
        outcome=decision.outcome.value,
        execution_mode=decision.execution_mode,
        source=decision.source,
    ).inc()


__all__ = [
    "CANCELLATION_GRACE_ATTEMPTS",
    "decision_recorder",
    "record_decision",
    "record_decision_once",
]
