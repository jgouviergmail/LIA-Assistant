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


async def _write_shielded(decision: TurnDecision) -> None:
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
        lambda: _write_logged(decision),
        attempts=CANCELLATION_GRACE_ATTEMPTS,
        label="decision_write",
    )
    if cancelled:
        raise asyncio.CancelledError


async def _write_logged(decision: TurnDecision) -> None:
    """Write, and turn a failure into a log rather than a raised task.

    The register is best-effort: losing a row must never take the turn down
    with it, and an unretrieved task exception would only surface as an
    asyncio warning nobody reads.

    Args:
        decision: The record to persist.
    """
    try:
        await _write(decision)
    except Exception:
        logger.exception("decision_write_failed", run_id=decision.run_id)


async def _write(decision: TurnDecision) -> None:
    """Upsert the turn's row.

    Args:
        decision: The record to persist.
    """
    if decision.user_id is None:
        # No account named the turn — a probe, a boot check, a test harness.
        # Nothing to record and nobody to record it for.
        return

    from src.domains.agents.effects.decision_repository import DecisionRepository
    from src.infrastructure.database.session import get_db_context

    ended_at = datetime.now(UTC)
    async with get_db_context() as db:
        await DecisionRepository(db).record(decision, ended_at=ended_at)
        await db.commit()

    from src.infrastructure.observability.metrics_effects import decisions_total

    decisions_total.labels(
        outcome=decision.outcome.value,
        execution_mode=decision.execution_mode,
        source=decision.source,
    ).inc()


__all__ = ["CANCELLATION_GRACE_ATTEMPTS", "decision_recorder"]
