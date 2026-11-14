"""A source sync keeps its lease for as long as its documents embed (audit F001).

A source being synchronised is ``SYNCING`` under a lease. Two readers trust it:
the reaper re-drives a source whose lease expired, and the document reaper
leaves a syncing source's ``PENDING`` documents alone only while that lease is
alive. A sync renewed it before each thread or file it READ — and not once
while it embedded what it had queued, which is the long part: measured in
production on 2026-11-09, a label of 2,502 threads embedded for 13 minutes
under a 5-minute lease. The reaper started a second full sync beside the first
(221 threads done twice) and the document reaper requeued 32 documents under
it, in the very minutes the embedding provider's quota was exhausted.

The renewal runs on a timer, not once per document: one document may itself
last longer than the lease once a provider asks its callers to wait.

A native source worker is left alone: it renews around each external call
under its own unique claim (``source_worker_runtime.source_worker_external``),
and the repository refuses an anonymous heartbeat beside it.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from src.core.config import settings
from src.domains.rag_spaces.jobs_repository import RAGJobsRepository
from src.domains.rag_spaces.source_worker_lease import current_source_worker
from src.infrastructure.async_utils import cancel_and_join
from src.infrastructure.database.session import get_db_context
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

#: Name of the renewal task: what a census of the loop's tasks reads.
RENEWAL_TASK_NAME = "rag-source-lease-renewal"


@asynccontextmanager
async def source_lease_kept(source_id: UUID, *, table: str) -> AsyncIterator[None]:
    """Renew a syncing source's lease on the published cadence while the body runs.

    The renewal is owned by this scope: it is cancelled and JOINED before the
    scope returns, so no session of its own is still closing beside the caller
    that goes on to release the lease.

    Args:
        source_id: The source whose sync is running.
        table: Its table (``DRIVE_SOURCE_TABLE`` or ``MAIL_SOURCE_TABLE``).

    Yields:
        Nothing: the body is the work the lease must outlive.
    """
    if current_source_worker() is not None:
        yield
        return
    renewal = asyncio.create_task(_renew_on_cadence(source_id, table), name=RENEWAL_TASK_NAME)
    try:
        yield
    finally:
        await cancel_and_join(renewal)


async def _renew_on_cadence(source_id: UUID, table: str) -> None:
    """Renew until cancelled, or until the source is no longer there to renew.

    A renewal that FAILS (the database restarting, a pool exhausted) is logged
    and tried again at the next cadence: the lease outlives several of them
    (``rag_job_heartbeat_interval_seconds`` is held strictly under
    ``rag_job_lease_ttl_seconds`` by the settings). A renewal that is REFUSED
    means the source is no longer ``SYNCING`` — unlinked, or settled by someone
    else: there is nothing left to keep, and its documents went with it.
    """
    while True:
        await asyncio.sleep(settings.rag_job_heartbeat_interval_seconds)
        try:
            async with get_db_context() as db:
                renewed = await RAGJobsRepository(db).heartbeat_source(
                    source_id, settings.rag_job_lease_ttl_seconds, table=table
                )
        except Exception as exc:  # noqa: BLE001 — a missed renewal must never end the work
            logger.warning(
                "rag_source_lease_renewal_failed",
                source_id=str(source_id),
                source_table=table,
                error_type=type(exc).__name__,
            )
            continue
        if not renewed:
            logger.warning(
                "rag_source_lease_renewal_refused", source_id=str(source_id), source_table=table
            )
            return
