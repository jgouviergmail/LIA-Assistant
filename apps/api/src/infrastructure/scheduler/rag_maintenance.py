"""One tick for the RAG durable-job recovery and the kept-answers backfill.

The reconciliation of bookmark projections (2026-09-16 design, part A) rides
the reaper's tick — one leader-elected, jittered job, one lock — rather than
a second interval job. ``bookmarks`` imports ``rag_spaces``, so ``rag_spaces``
calling the reconciliation back would close a cycle the coupling ratchet
refuses; the composition therefore sits here, where this codebase already
orchestrates across domains for exactly this reason (``timezone_propagation``).

Order matters: the reaper re-drives what a crash stranded BEFORE the backfill
adds new PENDING documents, so a stuck lease is never starved by fresh work.
Each half is independently best-effort — a failure in one is logged and never
costs the other.
"""

from __future__ import annotations

import structlog

from src.core.config import settings
from src.domains.bookmarks.indexing import reconcile_bookmark_index
from src.domains.rag_spaces.reapers import rag_job_reaper

logger = structlog.get_logger(__name__)


async def rag_maintenance_tick() -> None:
    """The reaper, then the bookmark backfill under the reaper's own bounds."""
    try:
        await rag_job_reaper()
    except Exception:  # noqa: BLE001 — the backfill must still run
        logger.exception("rag_job_reaper_failed")
    try:
        await reconcile_bookmark_index(
            limit=settings.rag_job_reaper_batch_size,
            concurrency=settings.rag_job_reaper_concurrency,
            grace_seconds=settings.rag_job_reaper_grace_seconds,
        )
    except Exception:  # noqa: BLE001 — a failed backfill is a log line, not an outage
        logger.exception("bookmark_reconcile_failed")


__all__ = ["rag_maintenance_tick"]
