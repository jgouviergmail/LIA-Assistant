"""What this turn actually did, for the message that reports it (ADR-263).

The source of truth is the REGISTER, read back by ``run_id`` — not the graph
state, and not a counter kept along the way. That is the whole point of the
programme: the answer states what was recorded, so a reader does not have to
trust the executor that produced it.

Two rules the shape follows:

- **only what was performed.** A refusal changed nothing and the answer already
  says so in prose; a claim still open at archive time is an effect nobody can
  describe yet, and guessing would be exactly the invented diagnosis this
  register exists to remove.
- **keys and values, never a sentence.** The frontend resolves the wording in
  the reader's current language (``apps/web`` conventions), so a message
  archived in French still reads in German after the user switches.
"""

from __future__ import annotations

from typing import Any

import structlog

from src.domains.agents.effects.models import EffectStatus

logger = structlog.get_logger(__name__)

#: Statuses that describe something that HAPPENED. ``refused`` and ``claimed``
#: are deliberately absent — see the module docstring.
REPORTED_STATUSES: frozenset[EffectStatus] = frozenset(
    {EffectStatus.SUCCEEDED, EffectStatus.FAILED}
)


async def performed_effects(run_id: str) -> list[dict[str, Any]]:
    """The effects of one run, shaped for the message metadata.

    Best-effort by contract: the answer is already written by the time this
    runs, and failing to describe what happened must never cost the user their
    answer. A failure is logged and the message simply carries no effect list.

    Args:
        run_id: The run whose effects to report.

    Returns:
        One entry per performed effect, oldest first, each carrying
        ``label_key``, ``values``, ``status`` and ``tool_name``. Empty for a
        turn that performed nothing — the common case.
    """
    if not run_id:
        return []

    from src.domains.agents.effects.repository import EffectLedgerRepository
    from src.infrastructure.database.session import get_db_context

    try:
        async with get_db_context() as db:
            repository = EffectLedgerRepository(db)
            rows = await repository.list_for_run(run_id)
            return [_entry(row) for row in rows if row.status in REPORTED_STATUSES]
    except Exception as exc:  # noqa: BLE001 - the answer must survive this
        logger.warning(
            "performed_effects_unavailable",
            run_id=run_id,
            error_type=type(exc).__name__,
        )
        return []


def _entry(row: Any) -> dict[str, Any]:
    """One display entry from one row.

    Args:
        row: The ledger row.

    Returns:
        The entry the frontend renders.
    """
    from src.domains.agents.effects.labels import readable_label

    label_key, values = readable_label(row)
    return {
        "label_key": label_key,
        "values": values,
        "status": row.status.value if hasattr(row.status, "value") else str(row.status),
        "tool_name": row.tool_name,
    }
