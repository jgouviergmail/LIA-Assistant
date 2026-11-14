"""Housekeeping of the routines, run at the start of every executor tick.

Three steps sit before the batch (ADR-265, ADR-281, ADR-386): the retention of
the run history and of the calls already served, and the closing of the routines
with no future left. Inside the tick rather than jobs of their own — no new
interval to jitter, no new lock — each in its OWN session so a failed statement
cannot poison the batch that follows, and BEFORE the empty-batch early return,
which is the common tick.

Housekeeping never costs the tick: every failure is swallowed, logged by its
facts and counted as zero.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import structlog

from src.core.config import settings
from src.core.constants import ROUTINE_WEBHOOK_SERVED_RETENTION_DAYS

logger = structlog.get_logger(__name__)


async def purge_run_history(now: datetime) -> int:
    """Drop run rows older than the retention; best effort, never raises.

    Args:
        now: The tick's instant (UTC); the cutoff is counted back from it.

    Returns:
        How many rows went (0 when nothing was old enough or the purge failed).
    """
    # Imported HERE, not at module level: a module-level import binds the name
    # at import time, and the tick's tests patch the SOURCE.
    from src.domains.scheduled_actions.run_repository import ScheduledActionRunRepository
    from src.infrastructure.database.errors import database_error_fields
    from src.infrastructure.database.session import get_db_context

    cutoff = now - timedelta(days=settings.scheduled_actions_runs_retention_days)
    try:
        async with get_db_context() as db:
            purged = await ScheduledActionRunRepository(db).purge_older_than(cutoff)
            await db.commit()
            return purged
    except Exception as exc:
        # A database failure is logged by its facts, never by its text (ADR-317).
        logger.warning(
            "scheduled_action_runs_purge_failed",
            error_type=type(exc).__name__,
            **database_error_fields(exc),
        )
        return 0


async def purge_served_calls(now: datetime) -> int:
    """Drop the calls served longer ago than their retention; best effort, never raises.

    A served call keeps no body; its row only lets the same delivery, sent
    again, be recognised for ``ROUTINE_WEBHOOK_SERVED_RETENTION_DAYS`` (ADR-386).

    Args:
        now: The tick's instant (UTC); the cutoff is counted back from it.

    Returns:
        How many rows went (0 when nothing was old enough or the purge failed).
    """
    # Imported HERE for the same reason as the run history's purge.
    from src.domains.scheduled_actions.webhook_repository import RoutineWebhookRepository
    from src.infrastructure.database.errors import database_error_fields
    from src.infrastructure.database.session import get_db_context

    cutoff = now - timedelta(days=ROUTINE_WEBHOOK_SERVED_RETENTION_DAYS)
    try:
        async with get_db_context() as db:
            purged = await RoutineWebhookRepository(db).purge_served_before(cutoff)
            await db.commit()
            return purged
    except Exception as exc:
        # A database failure is logged by its facts, never by its text (ADR-317).
        logger.warning(
            "routine_webhook_calls_purge_failed",
            error_type=type(exc).__name__,
            **database_error_fields(exc),
        )
        return 0


async def close_finished_routines() -> int:
    """Close the routines with no future left; best effort, never raises.

    A series ends three ways — its ``SeriesEnd`` date reached, its
    ``after_count`` exhausted, its single occurrence consumed — and all three
    leave the same state: a NULL trigger. Nothing closed those rows, so they
    stayed enabled and « active » for good, indistinguishable from a pause.

    Disabled, never deleted: the person must be able to see what they had
    posted.

    Returns:
        How many were closed (0 when none were due or the sweep failed).
    """
    from src.domains.scheduled_actions.repository import ScheduledActionRepository
    from src.infrastructure.database.session import get_db_context

    try:
        async with get_db_context() as db:
            closed = await ScheduledActionRepository(db).close_finished()
            await db.commit()
            return closed
    except Exception as exc:  # noqa: BLE001 — housekeeping never costs the tick
        logger.warning(
            "scheduled_action_close_finished_failed",
            error_type=type(exc).__name__,
        )
        return 0
