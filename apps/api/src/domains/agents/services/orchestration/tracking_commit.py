"""Persist a turn's tracked spend at the end of its stream, whatever ends it.

The stream's ``finally`` commits what the turn's tracker holds: model calls that
happened and were billed (ADR-117), so the commit must run to its end even while
the turn is being cancelled. It used to be shielded with the cancellation caught
and logged as « completed » — it was not, ``shield`` does not wait — so a turn
cancelled while its spend was written ran on past its stream (2026-10-25). The
commit now runs as one task the stream owns, then the cancellation propagates.
"""

from __future__ import annotations

import asyncio
from typing import Protocol

import structlog

from src.core.constants import TRACKER_COMMIT_CANCELLATION_GRACE_ATTEMPTS
from src.infrastructure.async_utils import write_through_cancellation

logger = structlog.get_logger(__name__)


class SpendTracker(Protocol):
    """What the stream's ``finally`` needs of the turn's ``TrackingContext``."""

    async def commit(self) -> None:
        """Persist the spend records still pending."""


async def commit_tracked_spend(tracker: SpendTracker, run_id: str) -> None:
    """Commit ``tracker`` to its end, then let a cancellation reach the stream's task.

    A failure of the commit itself never breaks the stream: it is logged, as
    the ``finally`` always did.

    Args:
        tracker: The turn's ``TrackingContext``.
        run_id: The turn's run id, named in the failure log.

    Raises:
        asyncio.CancelledError: A cancellation delivered while committing,
            once the commit is done or left to finish on its own.
    """
    try:
        cancelled = await write_through_cancellation(
            tracker.commit,
            attempts=TRACKER_COMMIT_CANCELLATION_GRACE_ATTEMPTS,
            label="tracker_commit",
        )
    except (RuntimeError, ValueError, ConnectionError, AttributeError, OSError) as commit_error:
        logger.error(
            "tracker_commit_failed_in_finally",
            run_id=run_id,
            error=str(commit_error),
            error_type=type(commit_error).__name__,
            exc_info=True,
        )
        return
    if cancelled:
        raise asyncio.CancelledError
