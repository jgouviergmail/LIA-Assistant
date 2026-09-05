"""Recording one tick of a routine at its result (ADR-265).

The executor has five exits — success, failure, condition skipped, proposed,
HITL skipped — and each one ends with a row here, in the SAME transaction as
the routine's own marking. One function for the five, so an exit added later
cannot forget the history the way it could not forget the re-arm.

Two rules that are structural, not stylistic:

- **The row is written inside a savepoint.** A failed INSERT poisons a
  PostgreSQL transaction, and the commit that follows carries the routine's
  ``mark_execution_success``: losing THAT to a history write would re-run the
  routine after stale recovery. ``begin_nested`` confines the failure to the
  savepoint (pinned by ``tests/integration/test_begin_nested_contract.py``),
  and the failure is logged, never raised.
- **The served slot is derived, never passed.** :func:`served_slot` reads the
  due instant captured BEFORE the re-arm mutated it, so a due run serves its
  due instant and a manual run serves the day's slot only once that slot has
  passed.
"""

from __future__ import annotations

from datetime import datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.time_utils import now_utc
from src.domains.scheduled_actions.models import (
    ScheduledAction,
    ScheduledActionRun,
    ScheduledRunOutcome,
)
from src.domains.scheduled_actions.run_repository import ScheduledActionRunRepository
from src.domains.scheduled_actions.schedule_helpers import served_slot

logger = structlog.get_logger(__name__)


async def record_run(
    db: AsyncSession,
    action: ScheduledAction,
    *,
    due_at: datetime,
    started_at: datetime,
    outcome: ScheduledRunOutcome,
    attempts: int,
    error: str | None = None,
) -> ScheduledActionRun | None:
    """Write the run row for the tick that just ended.

    Args:
        db: The executor's session — the row joins ITS transaction.
        action: The routine, as loaded at the start of the tick.
        due_at: ``action.next_trigger_at`` captured BEFORE any re-arm.
        started_at: When the tick started (UTC).
        outcome: How it ended.
        attempts: Pipeline attempts made; 0 when the pipeline never ran.
        error: The failure message, if any.

    Returns:
        The row, or ``None`` when the write failed — logged, the routine's own
        marking untouched.
    """
    try:
        # Inside the guard too: the success branch of the executor calls this
        # from within its retry loop, where an unexpected raise would be read
        # as an execution failure and mark the routine failed.
        slot_at = served_slot(
            action.days_of_week,
            action.trigger_hour,
            action.trigger_minute,
            action.user_timezone,
            due_at=due_at,
            now=started_at,
        )
        async with db.begin_nested():
            return await ScheduledActionRunRepository(db).record(
                scheduled_action_id=action.id,
                user_id=action.user_id,
                slot_at=slot_at,
                started_at=started_at,
                ended_at=now_utc(),
                outcome=outcome,
                attempts=attempts,
                manual=due_at > started_at,
                error=error,
            )
    except Exception as exc:
        # The history is a record of the routine, never a gate on it: the
        # marking that follows must still commit.
        logger.warning(
            "scheduled_action_run_record_failed",
            action_id=str(action.id),
            outcome=outcome.value,
            error=str(exc)[:200],
        )
        return None
