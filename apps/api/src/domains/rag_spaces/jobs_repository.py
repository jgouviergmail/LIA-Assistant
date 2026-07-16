"""Atomic durable-job operations for RAG documents (audit F001, Phase 1).

Turns ``RAGDocument`` into a leased job. A worker CLAIMs a ``PENDING`` document
(atomic ``PENDING → PROCESSING``), renews a lease HEARTBEAT while working, then
COMPLETEs (``→ READY``, attempts reset) or FAILs (``→ ERROR`` once attempts reach
the bound, else ``→ PENDING`` for a bounded retry). ``fetch_recoverable_documents``
surfaces the jobs the reaper must requeue: ``PROCESSING`` with an expired/absent
lease, plus orphaned ``PENDING`` (created but never claimed — a crash right after
upload).

Every mutation is a single atomic ``UPDATE ... WHERE`` (imitates
``scheduled_actions/repository.py`` and ``drive_sync.try_acquire_sync_lock``), so
concurrent workers cannot double-claim: only one transaction can flip a given row
out of ``PENDING``.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.rag_spaces.models import RAGDocumentStatus, RAGDriveSyncStatus


class RAGJobsRepository:
    """Atomic claim/heartbeat/complete/fail + recovery scan for document jobs."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def claim_document(self, document_id: UUID, worker_id: str, lease_ttl_s: int) -> bool:
        """Atomically claim a PENDING document (→ PROCESSING). True iff claimed."""
        res = await self.db.execute(
            text(
                "UPDATE rag_documents SET status = :proc, "
                "lease_expires_at = now() + (:ttl * interval '1 second'), "
                "heartbeat_at = now(), attempts = attempts + 1, worker_id = :wid "
                "WHERE id = :id AND status = :pending"
            ),
            {
                "proc": RAGDocumentStatus.PROCESSING,
                "ttl": lease_ttl_s,
                "wid": worker_id,
                "id": str(document_id),
                "pending": RAGDocumentStatus.PENDING,
            },
        )
        await self.db.commit()
        return (getattr(res, "rowcount", 0) or 0) > 0

    async def heartbeat_document(self, document_id: UUID, worker_id: str, lease_ttl_s: int) -> bool:
        """Renew the lease if this worker still holds it. True iff renewed."""
        res = await self.db.execute(
            text(
                "UPDATE rag_documents SET "
                "lease_expires_at = now() + (:ttl * interval '1 second'), "
                "heartbeat_at = now() "
                "WHERE id = :id AND worker_id = :wid AND status = :proc"
            ),
            {
                "ttl": lease_ttl_s,
                "id": str(document_id),
                "wid": worker_id,
                "proc": RAGDocumentStatus.PROCESSING,
            },
        )
        await self.db.commit()
        return (getattr(res, "rowcount", 0) or 0) > 0

    async def complete_document(self, document_id: UUID) -> None:
        """Mark the document READY, clear the lease and reset the retry budget."""
        await self.db.execute(
            text(
                "UPDATE rag_documents SET status = :ready, attempts = 0, "
                "lease_expires_at = NULL, worker_id = NULL, heartbeat_at = NULL "
                "WHERE id = :id"
            ),
            {"ready": RAGDocumentStatus.READY, "id": str(document_id)},
        )
        await self.db.commit()

    async def fail_or_retry_document(self, document_id: UUID, error: str, max_attempts: int) -> str:
        """ERROR once attempts reach ``max_attempts``, else back to PENDING.

        Returns the resulting status. ``attempts`` was already incremented by the
        claim, so a document that has been claimed ``max_attempts`` times is
        dead-lettered to ERROR; otherwise it returns to PENDING for another try.
        """
        res = await self.db.execute(
            text(
                "UPDATE rag_documents SET "
                "status = CASE WHEN attempts >= :max THEN :error ELSE :pending END, "
                "error_message = :msg, lease_expires_at = NULL, worker_id = NULL "
                "WHERE id = :id "
                "RETURNING status"
            ),
            {
                "max": max_attempts,
                "error": RAGDocumentStatus.ERROR,
                "pending": RAGDocumentStatus.PENDING,
                "msg": error,
                "id": str(document_id),
            },
        )
        row = res.first()
        await self.db.commit()
        return str(row[0]) if row else RAGDocumentStatus.ERROR

    async def fetch_recoverable_documents(self, grace_s: int, limit: int) -> list[UUID]:
        """IDs the reaper must requeue: stuck PROCESSING/REINDEXING + stale PENDING.

        Three recoverable shapes:

        * ``PROCESSING`` with an expired/absent lease — the worker died.
        * ``PENDING`` untouched for longer than the grace window
          (``COALESCE(heartbeat_at, created_at)``: a fresh upload has no
          heartbeat, while a claimed-then-requeued or reindex-requeued document
          carries the last owner's timestamp — keying on ``created_at`` alone
          left requeued documents unrecoverable, and keying on
          ``heartbeat_at IS NULL`` alone made old requeued rows invisible).
        * Legacy ``REINDEXING`` with no live lease — the pre-durable reindex
          flow stranded documents in that transient status on crash; the
          rewritten flow never writes it, so any such row is recoverable debt.

        A PENDING document whose Drive source is actively SYNCING under a live
        lease is a *live* job — its sync created it and will claim it once the
        remaining downloads finish (which can take longer than the grace window
        on large folders). Requeuing it here would race the live sync (audit
        F001 residual: double owner). It is excluded until the source lease
        expires; a crash kills the source heartbeat, so both the source and its
        stranded PENDING documents become recoverable within one lease TTL.
        Upload documents (``drive_source_id IS NULL``) are unaffected.

        Uses ``FOR UPDATE SKIP LOCKED`` so multiple reaper instances never contend
        for the same rows.
        """
        res = await self.db.execute(
            text(
                "SELECT id FROM rag_documents WHERE "
                "(status = :proc AND (lease_expires_at IS NULL OR lease_expires_at < now())) "
                "OR (status = :reindexing "
                "AND (lease_expires_at IS NULL OR lease_expires_at < now())) "
                "OR (status = :pending "
                "AND COALESCE(heartbeat_at, created_at) < now() - (:grace * interval '1 second') "
                "AND NOT EXISTS ("
                "    SELECT 1 FROM rag_drive_sources s "
                "    WHERE s.id = rag_documents.drive_source_id "
                "    AND s.sync_status = :syncing "
                "    AND s.lease_expires_at IS NOT NULL AND s.lease_expires_at > now()"
                ")) "
                "ORDER BY created_at LIMIT :limit FOR UPDATE SKIP LOCKED"
            ),
            {
                "proc": RAGDocumentStatus.PROCESSING,
                "reindexing": RAGDocumentStatus.REINDEXING,
                "pending": RAGDocumentStatus.PENDING,
                "syncing": RAGDriveSyncStatus.SYNCING,
                "grace": grace_s,
                "limit": limit,
            },
        )
        return [row[0] for row in res.fetchall()]

    async def requeue_documents_for_reindex(self, document_ids: list[UUID]) -> int:
        """Durably mark documents as reindex work: ``READY``/``ERROR`` → ``PENDING``.

        This UPDATE **is** the persistent reindex job state (audit F001): once
        committed, every marked document is drained either by the in-process
        reindex loop or — after any crash/restart — by the regular document
        reaper, both through the same atomic claim. Stamps ``heartbeat_at`` so
        a healthy reindex has one grace window to reach each document before
        the reaper may take over (claim exclusivity keeps that takeover safe).
        Only READY/ERROR rows are flipped: a document currently
        PENDING/PROCESSING already has an owner. Returns the requeued count.

        Runs in the CALLER's transaction and never commits (audit F001, V8):
        the requeue must land in the same commit as the destructive
        dimension-change DDL — see ``reindex._persist_reindex_intent``.
        """
        if not document_ids:
            return 0
        res = await self.db.execute(
            text(
                "UPDATE rag_documents SET status = :pending, heartbeat_at = now(), "
                "lease_expires_at = NULL, worker_id = NULL, attempts = 0, "
                "error_message = NULL "
                "WHERE id = ANY(:ids) AND status IN (:ready, :error)"
            ),
            {
                "pending": RAGDocumentStatus.PENDING,
                "ready": RAGDocumentStatus.READY,
                "error": RAGDocumentStatus.ERROR,
                # UUID objects, not strings: asyncpg encodes the list as a
                # uuid[] array for the ANY() comparison against the uuid column.
                "ids": list(document_ids),
            },
        )
        return int(getattr(res, "rowcount", 0) or 0)

    # ------------------------------------------------------------------ #
    # Drive-source sync jobs (audit F001, T6): sync_status IDLE/SYNCING   #
    # ------------------------------------------------------------------ #

    async def heartbeat_source(self, source_id: UUID, lease_ttl_s: int) -> bool:
        """Renew a syncing source's lease (the SYNCING status is the single-sync guard)."""
        res = await self.db.execute(
            text(
                "UPDATE rag_drive_sources SET "
                "lease_expires_at = now() + (:ttl * interval '1 second'), "
                "heartbeat_at = now() "
                "WHERE id = :id AND sync_status = :syncing"
            ),
            {
                "ttl": lease_ttl_s,
                "id": str(source_id),
                "syncing": RAGDriveSyncStatus.SYNCING,
            },
        )
        await self.db.commit()
        return (getattr(res, "rowcount", 0) or 0) > 0

    async def reclaim_or_fail_source(
        self, source_id: UUID, lease_ttl_s: int, max_attempts: int
    ) -> str:
        """Re-lease a stuck sync for another attempt, or ERROR once exhausted.

        Keeps the source ``SYNCING`` with a fresh lease while attempts remain (so a
        re-sync that crashes again stays recoverable), incrementing ``attempts``;
        dead-letters to ``ERROR`` once ``attempts`` reach the bound. All SET
        expressions read the pre-update ``attempts``, so the decision and the
        increment are consistent. Returns the resulting status.
        """
        res = await self.db.execute(
            text(
                "UPDATE rag_drive_sources SET "
                "sync_status = CASE WHEN attempts >= :max THEN :error ELSE :syncing END, "
                "lease_expires_at = CASE WHEN attempts >= :max THEN NULL "
                "  ELSE now() + (:ttl * interval '1 second') END, "
                "worker_id = CASE WHEN attempts >= :max THEN NULL ELSE worker_id END, "
                "heartbeat_at = now(), attempts = attempts + 1, "
                "error_message = :msg "
                "WHERE id = :id "
                "RETURNING sync_status"
            ),
            {
                "max": max_attempts,
                "error": RAGDriveSyncStatus.ERROR,
                "syncing": RAGDriveSyncStatus.SYNCING,
                "ttl": lease_ttl_s,
                "msg": "recovered from stuck sync lease (worker crash)",
                "id": str(source_id),
            },
        )
        row = res.first()
        await self.db.commit()
        return str(row[0]) if row else RAGDriveSyncStatus.ERROR

    async def fetch_recoverable_sources(self, limit: int) -> list[UUID]:
        """IDs of sources stuck in SYNCING with an expired/absent lease."""
        res = await self.db.execute(
            text(
                "SELECT id FROM rag_drive_sources WHERE sync_status = :syncing "
                "AND (lease_expires_at IS NULL OR lease_expires_at < now()) "
                "ORDER BY last_sync_at NULLS FIRST LIMIT :limit FOR UPDATE SKIP LOCKED"
            ),
            {"syncing": RAGDriveSyncStatus.SYNCING, "limit": limit},
        )
        return [row[0] for row in res.fetchall()]
