"""When the record itself is incomplete (ADR-263, lot 8).

Four situations mean « the registers are not telling the whole truth », and
none of them can be written into the register that is failing:

- an effect was performed with **no ledger row** — the gate ran without a
  claim, so an action happened that the action register does not hold;
- a turn consulted capabilities with **no register open** — some path runs the
  graph without publishing the collector;
- a **chain break** — a register row or a sealing entry was altered outside the
  application;
- a **notary pass failed** for an account, so its chain fell behind.

They already have metrics and alerts. What a counter cannot say is **which**
accounts and **which** turns are affected, and that is precisely what a user and
a regulator ask. Hence a row, not a fifth counter.

Three rules the shape enforces:

- **Bounded kinds.** A free-text event log would become a second logging
  system; four declared kinds stay a register.
- **No content, ever.** The detail is a short, bounded classification — never
  what was asked, never what a tool returned.
- **Observing never breaks the observed.** Every write is best-effort and
  swallows its own failure: an integrity note that could fail a turn would be a
  worse defect than the one it records.
"""

from __future__ import annotations

import uuid
from enum import Enum

import structlog

logger = structlog.get_logger(__name__)


class IntegrityKind(str, Enum):
    """What kind of gap was observed.

    Bounded on purpose: each value has one detection point, and a fifth would
    be a decision someone takes here rather than a string someone passes.

    Attributes:
        EFFECT_UNRECORDED: An effect ran with no ledger row.
        TREATMENTS_UNCOLLECTED: A turn consulted capabilities with no register.
        CHAIN_BROKEN: A sealed row or entry no longer verifies.
        NOTARY_FAILED: One account's sealing pass was rolled back.
    """

    EFFECT_UNRECORDED = "effect_unrecorded"
    TREATMENTS_UNCOLLECTED = "treatments_uncollected"
    CHAIN_BROKEN = "chain_broken"
    NOTARY_FAILED = "notary_failed"


async def record_integrity_event(
    kind: IntegrityKind,
    *,
    user_id: uuid.UUID | None = None,
    run_id: str | None = None,
    detail: str | None = None,
) -> None:
    """Persist one integrity gap, beside the metric that already counts it.

    One detection, two destinations — never a second detector. The caller is
    the place that already knows, so this adds no new opinion about when a gap
    happened.

    Args:
        kind: Which gap.
        user_id: Whose account, when the detection knew; a gap detected with no
            run context has none, and that is itself the interesting part.
        run_id: Which turn, when the detection knew.
        detail: A SHORT bounded classification (a reason code, a position) —
            never content.

    Returns:
        None. Failures are logged and swallowed: an integrity note that could
        break a turn would be a worse defect than the one it records.
    """
    try:
        from src.domains.agents.effects.integrity_repository import IntegrityRepository
        from src.infrastructure.database.session import get_db_context

        async with get_db_context() as db:
            await IntegrityRepository(db).record(
                kind=kind, user_id=user_id, run_id=run_id, detail=detail
            )
            await db.commit()
    except Exception:  # noqa: BLE001 - observing must never break the observed
        logger.warning("integrity_event_not_recorded", kind=kind.value, exc_info=True)


__all__ = ["IntegrityKind", "record_integrity_event"]
