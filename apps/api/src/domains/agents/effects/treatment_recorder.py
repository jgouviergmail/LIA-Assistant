"""Publishing the collector for a turn, and flushing it whatever happens.

One ``async with`` around the turn, placed next to the token tracker it
resembles. The exhaustiveness is acquired **by construction** rather than by
vigilance: ``__aexit__`` runs on the normal path, on an exception and on a
cancellation, so no node has to remember to close the register.

Why the flush is shielded, measured on this loop rather than assumed:

    ONE cancellation (a client disconnects)      naive: writes   shielded: writes
    cancellation RE-DELIVERED during cleanup     naive: NOTHING  shielded: writes
    (a container stopping, an enclosing timeout)

The second row is the ordinary case on a Raspberry Pi that reboots — which is
where this assistant runs. The shield is bounded (three attempts): a register
must not be able to keep a shutting-down process alive.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from typing import Final

import structlog

from src.domains.agents.effects.treatment_repository import TreatmentRepository
from src.domains.agents.effects.treatments import Treatment, treatment_collector
from src.infrastructure.async_utils import write_through_cancellation

logger = structlog.get_logger(__name__)

#: How many times the flush may survive a re-delivered cancellation. Bounded so
#: a register can never keep a stopping container alive.
CANCELLATION_GRACE_ATTEMPTS: Final[int] = 3


@asynccontextmanager
async def treatment_recorder(*, run_id: str) -> AsyncIterator[list[Treatment]]:
    """Collect a turn's consultations and write them once, at the end.

    Args:
        run_id: The turn's run id, which every collected row is filed under.
            Passed explicitly rather than rebuilt from a config: rebuilding it
            one layer above is precisely how lot 3 filed a turn's effects under
            the thread id and made the surface look empty.

    Yields:
        The live list the gate appends to.
    """
    with treatment_collector(run_id=run_id) as rows:
        try:
            yield rows
        finally:
            await _flush_shielded(rows)


async def _flush_shielded(rows: list[Treatment]) -> None:
    """Write the batch, surviving a cancellation delivered during cleanup.

    Args:
        rows: What the turn consulted.

    Raises:
        asyncio.CancelledError: Re-raised once the write is done, so a
            cancelled turn stays cancelled — writing the register must never
            resurrect it.
    """
    if not rows:
        return

    # The dance itself lives in ``async_utils``: it is subtle enough that a
    # second copy regressed it once (the decision recorder shielded a fresh
    # coroutine per attempt and wrote twice), so there is now one
    # implementation and two callers.
    batch = list(rows)
    cancelled = await write_through_cancellation(
        lambda: _flush(batch),
        attempts=CANCELLATION_GRACE_ATTEMPTS,
        label="treatment_flush",
    )
    if cancelled:
        raise asyncio.CancelledError


def count_persisted_treatments(rows: list[Treatment]) -> None:
    """Count what the register actually KEPT, by readable domain.

    Called only after a successful write: a counter that moved on a failed
    flush would claim rows the database refused, and an operator reading it
    would conclude the register is complete when it has a hole.

    The label set is bounded by construction — the domain comes from our own
    taxonomy, never from a tool name, whose value set belongs to third-party
    servers.

    Args:
        rows: The consultations that were written.
    """
    from src.domains.agents.effects.treatment_labels import treatment_domain
    from src.infrastructure.observability.metrics_effects import treatments_total

    for row in rows:
        treatments_total.labels(
            domain=treatment_domain(row.tool_name),
            outcome=row.outcome,
            execution_mode=row.execution_mode,
        ).inc()


async def _flush(rows: list[Treatment]) -> None:
    """Write one turn's consultations, best-effort.

    Args:
        rows: What the turn consulted.
    """
    from src.infrastructure.database.session import get_db_context
    from src.infrastructure.observability.metrics_effects import effect_ledger_failures_total

    try:
        async with get_db_context() as db:
            written = await TreatmentRepository(db).record_batch(rows)
            await db.commit()
        logger.debug("treatments_recorded", rows=written)
    except Exception as exc:  # noqa: BLE001 - the turn already answered the user
        effect_ledger_failures_total.labels(operation="treatments_flush").inc()
        logger.error(
            "treatment_flush_failed",
            rows=len(rows),
            error_type=type(exc).__name__,
            exc_info=True,
        )
        return

    # Emitted AFTER the write, and shielded from it: a broken counter must not
    # cost the register the rows it just kept.
    with suppress(Exception):
        count_persisted_treatments(rows)
