"""RAG durable-job recovery reaper (audit F001, Phase 1 T5).

Requeues document-processing jobs a crash stranded: documents stuck in
``PROCESSING`` with an expired/absent lease, plus orphaned ``PENDING`` (created
but never claimed — a crash right after upload). Under the scheduler leader
election + ``max_instances=1`` exactly one instance sweeps. Each recoverable job
is reset via the same bounded-retry decision as an in-band failure
(``fail_or_retry_document``: ``ERROR`` once attempts reach the bound, else
``PENDING``), then re-driven through ``process_document`` (which re-claims the
now-PENDING row). Bounded per tick (batch size) with bounded concurrency so a
large backlog cannot saturate the process; the remainder drains next tick.
"""

from __future__ import annotations

import asyncio
from uuid import UUID

import structlog

from src.core.config import settings
from src.domains.rag_spaces.jobs_repository import MAIL_SOURCE_TABLE, RAGJobsRepository
from src.domains.rag_spaces.models import (
    RAGDocument,
    RAGDocumentStatus,
    RAGDriveSource,
    RAGDriveSyncStatus,
    RAGMailSource,
)
from src.infrastructure.database.session import get_db_context
from src.infrastructure.observability.metrics_rag_spaces import rag_jobs_recovered_total

logger = structlog.get_logger(__name__)


async def rag_job_reaper() -> None:
    """One recovery sweep over stuck/orphaned document AND drive-sync jobs."""
    semaphore = asyncio.Semaphore(settings.rag_job_reaper_concurrency)
    await _recover_documents(semaphore)
    await _recover_sources(semaphore)
    await _recover_mail_sources(semaphore)

    # AC-001 crash-resume: after rebuilding the requeued documents, activate any
    # generational reindex whose interrupted drain never reached the flip. The
    # space stayed pinned on (and serving) the stable OLD generation throughout;
    # this flips it once every document is on the current model. Best-effort — a
    # flip hiccup must never abort the reaper's core recovery.
    try:
        from src.domains.rag_spaces.reindex import flip_pinned_spaces_if_ready

        await flip_pinned_spaces_if_ready()
    except Exception as exc:  # noqa: BLE001 - flip is a best-effort resume step
        logger.warning("rag_reaper_generational_flip_failed", error=str(exc))


async def _recover_documents(semaphore: asyncio.Semaphore) -> None:
    async with get_db_context() as db:
        doc_ids = await RAGJobsRepository(db).fetch_recoverable_documents(
            grace_s=settings.rag_job_reaper_grace_seconds,
            limit=settings.rag_job_reaper_batch_size,
        )
    if not doc_ids:
        return
    if len(doc_ids) >= settings.rag_job_reaper_batch_size:
        # Backlog exceeded one tick's bound — the rest drains next tick. Never a
        # silent truncation.
        logger.info("rag_reaper_batch_capped", job_type="document", batch=len(doc_ids))

    outcomes = await asyncio.gather(*(_recover_one(doc_id, semaphore) for doc_id in doc_ids))
    requeued = sum(1 for o in outcomes if o == "requeued")
    failed = sum(1 for o in outcomes if o == "failed")
    if requeued:
        rag_jobs_recovered_total.labels(job_type="document", outcome="requeued").inc(requeued)
    if failed:
        rag_jobs_recovered_total.labels(job_type="document", outcome="failed").inc(failed)
    logger.info("rag_jobs_recovered", requeued=requeued, failed=failed)


async def _recover_sources(semaphore: asyncio.Semaphore) -> None:
    async with get_db_context() as db:
        source_ids = await RAGJobsRepository(db).fetch_recoverable_sources(
            limit=settings.rag_job_reaper_batch_size,
        )
    if not source_ids:
        return
    if len(source_ids) >= settings.rag_job_reaper_batch_size:
        logger.info("rag_reaper_batch_capped", job_type="sync", batch=len(source_ids))

    outcomes = await asyncio.gather(
        *(_recover_source(source_id, semaphore) for source_id in source_ids)
    )
    requeued = sum(1 for o in outcomes if o == "requeued")
    failed = sum(1 for o in outcomes if o == "failed")
    if requeued:
        rag_jobs_recovered_total.labels(job_type="sync", outcome="requeued").inc(requeued)
    if failed:
        rag_jobs_recovered_total.labels(job_type="sync", outcome="failed").inc(failed)
    logger.info("rag_sync_jobs_recovered", requeued=requeued, failed=failed)


async def _recover_one(doc_id: UUID, semaphore: asyncio.Semaphore) -> str:
    """Requeue-or-dead-letter one document, then re-drive it if requeued.

    Returns ``"requeued"``, ``"failed"`` (dead-lettered to ERROR) or ``"skipped"``.
    """
    async with semaphore:
        async with get_db_context() as db:
            doc = await db.get(RAGDocument, doc_id)
            if doc is None or doc.user_id is None:
                # user_id is None only for system-space documents, which are owned
                # by the system indexer, not this reaper.
                return "skipped"
            # Snapshot the processing args (typed) before the session closes.
            space_id = doc.space_id
            user_id = doc.user_id
            filename = doc.filename
            original_filename = doc.original_filename
            content_type = doc.content_type
            new_status = await RAGJobsRepository(db).fail_or_retry_document(
                doc_id,
                "recovered from stuck lease (worker crash)",
                settings.rag_job_max_attempts,
            )

        if new_status == RAGDocumentStatus.ERROR:
            logger.warning("rag_job_dead_lettered", document_id=str(doc_id))
            return "failed"

        # Re-drive: process_document opens its own session and re-claims the now
        # PENDING document (PENDING -> PROCESSING + lease), then reprocesses.
        from src.domains.rag_spaces.processing import process_document

        await process_document(
            document_id=doc_id,
            space_id=space_id,
            user_id=user_id,
            filename=filename,
            original_filename=original_filename,
            content_type=content_type,
        )
        return "requeued"


async def _recover_source(source_id: UUID, semaphore: asyncio.Semaphore) -> str:
    """Requeue-or-dead-letter one stuck sync source, then re-drive it if requeued.

    Returns ``"requeued"``, ``"failed"`` (dead-lettered to ERROR) or ``"skipped"``.
    The re-sync is idempotent (re-lists the Drive folder and skips already-synced
    files by drive_file_id + modified time), so a partial sync completes.
    """
    async with semaphore:
        async with get_db_context() as db:
            source = await db.get(RAGDriveSource, source_id)
            if source is None or source.user_id is None:
                return "skipped"
            space_id = source.space_id
            user_id = source.user_id
            new_status = await RAGJobsRepository(db).reclaim_or_fail_source(
                source_id,
                settings.rag_job_lease_ttl_seconds,
                settings.rag_job_max_attempts,
            )

        if new_status == RAGDriveSyncStatus.ERROR:
            logger.warning("rag_sync_dead_lettered", source_id=str(source_id))
            return "failed"

        # Re-drive: the source is re-leased and still SYNCING, so a crash during the
        # re-sync stays recoverable. sync_folder_background re-lists the folder,
        # skipping already-synced files, and sets COMPLETED (clearing the lease).
        from src.domains.rag_spaces.drive_sync import sync_folder_background

        await sync_folder_background(space_id=space_id, source_id=source_id, user_id=user_id)
        return "requeued"


async def _recover_mail_sources(semaphore: asyncio.Semaphore) -> None:
    """Same sweep over the Gmail label sources (ADR-262): stuck SYNCING + dead lease."""
    async with get_db_context() as db:
        source_ids = await RAGJobsRepository(db).fetch_recoverable_sources(
            limit=settings.rag_job_reaper_batch_size, table=MAIL_SOURCE_TABLE
        )
    if not source_ids:
        return
    if len(source_ids) >= settings.rag_job_reaper_batch_size:
        logger.info("rag_reaper_batch_capped", job_type="mail_sync", batch=len(source_ids))

    outcomes = await asyncio.gather(
        *(_recover_mail_source(source_id, semaphore) for source_id in source_ids)
    )
    requeued = sum(1 for o in outcomes if o == "requeued")
    failed = sum(1 for o in outcomes if o == "failed")
    if requeued:
        rag_jobs_recovered_total.labels(job_type="mail_sync", outcome="requeued").inc(requeued)
    if failed:
        rag_jobs_recovered_total.labels(job_type="mail_sync", outcome="failed").inc(failed)
    logger.info("rag_mail_sync_jobs_recovered", requeued=requeued, failed=failed)


async def _recover_mail_source(source_id: UUID, semaphore: asyncio.Semaphore) -> str:
    """Requeue-or-dead-letter one stuck label sync, then re-drive it if requeued.

    The re-sync is idempotent (unchanged threads are skipped by their newest
    message stamp), so a partial sync completes.
    """
    async with semaphore:
        async with get_db_context() as db:
            source = await db.get(RAGMailSource, source_id)
            if source is None or source.user_id is None:
                return "skipped"
            user_id = source.user_id
            new_status = await RAGJobsRepository(db).reclaim_or_fail_source(
                source_id,
                settings.rag_job_lease_ttl_seconds,
                settings.rag_job_max_attempts,
                table=MAIL_SOURCE_TABLE,
            )

        if new_status == RAGDriveSyncStatus.ERROR:
            logger.warning("rag_mail_sync_dead_lettered", source_id=str(source_id))
            return "failed"

        from src.domains.rag_spaces.mail_sync import sync_label_background

        await sync_label_background(source_id=source_id, user_id=user_id)
        return "requeued"
