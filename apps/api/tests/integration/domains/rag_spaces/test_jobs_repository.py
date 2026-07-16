"""RAGJobsRepository: atomic claim/heartbeat/complete/fail + recovery scan.

Audit F001, Phase 1 T3. Real PostgreSQL (``async_session`` fixture). ``now()`` is
frozen within the fixture's outer transaction, so time-based cases set the
relevant timestamp explicitly in the past rather than waiting.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.rag_spaces.jobs_repository import RAGJobsRepository
from src.domains.rag_spaces.models import (
    RAGDocument,
    RAGDocumentSourceType,
    RAGDocumentStatus,
    RAGDriveSource,
    RAGDriveSyncStatus,
    RAGSpace,
)
from tests.fixtures.factories import UserFactory

pytestmark = pytest.mark.integration


async def _make_pending_document(db: AsyncSession) -> uuid.UUID:
    space = RAGSpace(name="jobs-test-space")
    db.add(space)
    await db.flush()
    doc = RAGDocument(
        space_id=space.id,
        filename="f.txt",
        original_filename="f.txt",
        file_size=10,
        content_type="text/plain",
        status=RAGDocumentStatus.PENDING,
    )
    db.add(doc)
    await db.commit()
    return doc.id


async def _make_drive_pending_document(
    db: AsyncSession, *, source_sync_status: str, source_lease_live: bool
) -> tuple[uuid.UUID, uuid.UUID]:
    """A PENDING Drive document past the grace window, under a configurable source.

    Returns ``(document_id, source_id)``. ``created_at`` is pushed one hour back
    so only the live-source exclusion can keep it out of a recovery scan.
    """
    user = UserFactory.create()
    db.add(user)
    await db.flush()
    space = RAGSpace(name="drive-interleave-space", user_id=user.id)
    db.add(space)
    await db.flush()
    source = RAGDriveSource(
        space_id=space.id,
        user_id=user.id,
        folder_id="folder-x",
        folder_name="Folder X",
        sync_status=source_sync_status,
    )
    db.add(source)
    await db.flush()
    doc = RAGDocument(
        space_id=space.id,
        user_id=user.id,
        filename="d.txt",
        original_filename="d.txt",
        file_size=10,
        content_type="text/plain",
        status=RAGDocumentStatus.PENDING,
        source_type=RAGDocumentSourceType.DRIVE,
        drive_source_id=source.id,
        drive_file_id=f"file-{uuid.uuid4().hex[:8]}",
    )
    db.add(doc)
    await db.commit()
    lease_sql = (
        "lease_expires_at = now() + interval '5 minutes'"
        if source_lease_live
        else "lease_expires_at = now() - interval '5 minutes'"
    )
    await db.execute(
        text(f"UPDATE rag_drive_sources SET {lease_sql} WHERE id = :id"),
        {"id": str(source.id)},
    )
    await db.execute(
        text("UPDATE rag_documents SET created_at = now() - interval '1 hour' WHERE id = :id"),
        {"id": str(doc.id)},
    )
    await db.commit()
    return doc.id, source.id


async def _row(db: AsyncSession, doc_id: uuid.UUID) -> dict:
    res = await db.execute(
        text(
            "SELECT status, attempts, worker_id, lease_expires_at "
            "FROM rag_documents WHERE id = :id"
        ),
        {"id": str(doc_id)},
    )
    status, attempts, worker_id, lease = res.one()
    return {
        "status": status,
        "attempts": attempts,
        "worker_id": worker_id,
        "lease": lease,
    }


async def test_claim_is_exclusive_and_increments_attempts(
    async_session: AsyncSession,
) -> None:
    doc_id = await _make_pending_document(async_session)
    repo = RAGJobsRepository(async_session)
    assert await repo.claim_document(doc_id, "w1", 300) is True
    # Re-claim fails: the row is no longer PENDING (atomic WHERE guard = the
    # double-launch protection; DB row locking handles true concurrency).
    assert await repo.claim_document(doc_id, "w2", 300) is False
    row = await _row(async_session, doc_id)
    assert row["status"] == RAGDocumentStatus.PROCESSING
    assert row["attempts"] == 1
    assert row["worker_id"] == "w1"
    assert row["lease"] is not None


async def test_heartbeat_only_by_holder(async_session: AsyncSession) -> None:
    doc_id = await _make_pending_document(async_session)
    repo = RAGJobsRepository(async_session)
    await repo.claim_document(doc_id, "w1", 300)
    assert await repo.heartbeat_document(doc_id, "w1", 300) is True
    assert await repo.heartbeat_document(doc_id, "someone-else", 300) is False


async def test_complete_resets_attempts_and_clears_lease(
    async_session: AsyncSession,
) -> None:
    doc_id = await _make_pending_document(async_session)
    repo = RAGJobsRepository(async_session)
    await repo.claim_document(doc_id, "w1", 300)
    await repo.complete_document(doc_id)
    row = await _row(async_session, doc_id)
    assert row["status"] == RAGDocumentStatus.READY
    assert row["attempts"] == 0
    assert row["lease"] is None and row["worker_id"] is None


async def test_fail_retries_then_errors_at_max(async_session: AsyncSession) -> None:
    doc_id = await _make_pending_document(async_session)
    repo = RAGJobsRepository(async_session)
    statuses = []
    for _ in range(3):  # max_attempts = 3
        assert await repo.claim_document(doc_id, "w1", 300) is True
        statuses.append(await repo.fail_or_retry_document(doc_id, "boom", max_attempts=3))
    assert statuses[0] == RAGDocumentStatus.PENDING  # attempt 1 < 3
    assert statuses[1] == RAGDocumentStatus.PENDING  # attempt 2 < 3
    assert statuses[2] == RAGDocumentStatus.ERROR  # attempt 3 == 3 → dead-letter


async def test_fetch_recoverable_finds_stuck_and_orphaned_but_not_fresh(
    async_session: AsyncSession,
) -> None:
    repo = RAGJobsRepository(async_session)
    # (a) PROCESSING with an expired lease.
    stuck_id = await _make_pending_document(async_session)
    await repo.claim_document(stuck_id, "w1", 300)
    await async_session.execute(
        text(
            "UPDATE rag_documents SET lease_expires_at = now() - interval '1 hour' "
            "WHERE id = :id"
        ),
        {"id": str(stuck_id)},
    )
    # (b) Orphaned PENDING older than the grace window.
    orphan_id = await _make_pending_document(async_session)
    await async_session.execute(
        text("UPDATE rag_documents SET created_at = now() - interval '1 hour' " "WHERE id = :id"),
        {"id": str(orphan_id)},
    )
    # (c) A fresh PENDING must NOT be recovered.
    fresh_id = await _make_pending_document(async_session)
    await async_session.commit()

    recoverable = set(await repo.fetch_recoverable_documents(grace_s=60, limit=100))
    assert stuck_id in recoverable
    assert orphan_id in recoverable
    assert fresh_id not in recoverable


class TestDriveSyncReaperInterleaving:
    """Audit F001 residual: a live Drive sync's documents are never reaped.

    Drive documents are born PENDING and claimed atomically by the same
    PENDING → PROCESSING + lease transition as uploads. While the parent source
    holds a live SYNCING lease (renewed before every download), its PENDING
    documents are *live* jobs: a recovery scan running mid-sync must not requeue
    them — that interleaving previously produced two owners and a duplicated
    chunk set. Once the source lease expires (crash), recovery must resume.
    """

    async def test_live_sync_documents_are_invisible_to_the_reaper(
        self, async_session: AsyncSession
    ) -> None:
        doc_id, source_id = await _make_drive_pending_document(
            async_session,
            source_sync_status=RAGDriveSyncStatus.SYNCING,
            source_lease_live=True,
        )
        repo = RAGJobsRepository(async_session)

        # Mid-sync recovery scan: the document is past the grace window but its
        # source lease is live → NOT recoverable (single owner stays the sync).
        recoverable = set(await repo.fetch_recoverable_documents(grace_s=60, limit=100))
        assert doc_id not in recoverable

        # The sync crashes: its lease expires → the document becomes
        # recoverable (durability preserved, not traded away).
        await async_session.execute(
            text(
                "UPDATE rag_drive_sources SET lease_expires_at = now() - interval '1 minute' "
                "WHERE id = :id"
            ),
            {"id": str(source_id)},
        )
        await async_session.commit()
        recoverable = set(await repo.fetch_recoverable_documents(grace_s=60, limit=100))
        assert doc_id in recoverable

    async def test_interleaved_claim_yields_a_single_owner(
        self, async_session: AsyncSession
    ) -> None:
        # Sync still live; it reaches the document and claims it.
        doc_id, _source_id = await _make_drive_pending_document(
            async_session,
            source_sync_status=RAGDriveSyncStatus.SYNCING,
            source_lease_live=True,
        )
        repo = RAGJobsRepository(async_session)
        assert await repo.claim_document(doc_id, "sync-worker", 300) is True

        # Simultaneous reaper scan: PROCESSING with a live lease → invisible.
        recoverable = set(await repo.fetch_recoverable_documents(grace_s=60, limit=100))
        assert doc_id not in recoverable

        # A concurrent claim attempt (reaper re-drive, double launch…) loses:
        # exactly one owner, hence exactly one chunk set is ever written.
        assert await repo.claim_document(doc_id, "reaper-worker", 300) is False
        row = await _row(async_session, doc_id)
        assert row["worker_id"] == "sync-worker"

    async def test_documents_of_a_finished_source_stay_recoverable(
        self, async_session: AsyncSession
    ) -> None:
        # A PENDING document left behind by a COMPLETED source (e.g. its claim
        # was never reached because the process died right after the source
        # flipped) is orphaned — the live-source exclusion must not shield it.
        doc_id, _source_id = await _make_drive_pending_document(
            async_session,
            source_sync_status=RAGDriveSyncStatus.COMPLETED,
            source_lease_live=True,
        )
        repo = RAGJobsRepository(async_session)
        recoverable = set(await repo.fetch_recoverable_documents(grace_s=60, limit=100))
        assert doc_id in recoverable


class TestReindexDurableRequeue:
    """Audit F001: the reindex job state is the committed PENDING flip.

    ``requeue_documents_for_reindex`` durably marks the target documents; the
    reindex loop and — after any crash — the regular reaper drain them through
    the same claim. The heartbeat stamp gives the live loop one grace window
    per document before the reaper may take over.
    """

    async def test_requeue_flips_ready_and_error_but_not_active_rows(
        self, async_session: AsyncSession
    ) -> None:
        repo = RAGJobsRepository(async_session)
        ready_id = await _make_pending_document(async_session)
        error_id = await _make_pending_document(async_session)
        active_id = await _make_pending_document(async_session)
        await async_session.execute(
            text("UPDATE rag_documents SET status = :s, error_message = 'old' WHERE id = :id"),
            {"s": RAGDocumentStatus.READY, "id": str(ready_id)},
        )
        await async_session.execute(
            text("UPDATE rag_documents SET status = :s, attempts = 2 WHERE id = :id"),
            {"s": RAGDocumentStatus.ERROR, "id": str(error_id)},
        )
        # active_id: claim it so it is PROCESSING (owned by a live worker).
        await repo.claim_document(active_id, "w-live", 300)
        await async_session.commit()

        count = await repo.requeue_documents_for_reindex([ready_id, error_id, active_id])
        assert count == 2  # the PROCESSING row is never touched

        for doc_id in (ready_id, error_id):
            row = await _row(async_session, doc_id)
            assert row["status"] == RAGDocumentStatus.PENDING
            assert row["attempts"] == 0
            assert row["lease"] is None and row["worker_id"] is None
        active = await _row(async_session, active_id)
        assert active["status"] == RAGDocumentStatus.PROCESSING
        assert active["worker_id"] == "w-live"

    async def test_requeued_documents_get_one_grace_window_then_recover(
        self, async_session: AsyncSession
    ) -> None:
        repo = RAGJobsRepository(async_session)
        doc_id = await _make_pending_document(async_session)
        await async_session.execute(
            # An OLD document (created long ago) — exactly the reindex shape.
            text(
                "UPDATE rag_documents SET status = :s, "
                "created_at = now() - interval '30 days' WHERE id = :id"
            ),
            {"s": RAGDocumentStatus.READY, "id": str(doc_id)},
        )
        await async_session.commit()
        assert await repo.requeue_documents_for_reindex([doc_id]) == 1

        # Freshly requeued: the heartbeat stamp shields it for one grace window
        # (created_at alone would make every old document instantly stealable).
        recoverable = set(await repo.fetch_recoverable_documents(grace_s=60, limit=100))
        assert doc_id not in recoverable

        # Crash: nothing touches it past the grace window → recoverable.
        await async_session.execute(
            text(
                "UPDATE rag_documents SET heartbeat_at = now() - interval '10 minutes' "
                "WHERE id = :id"
            ),
            {"id": str(doc_id)},
        )
        await async_session.commit()
        recoverable = set(await repo.fetch_recoverable_documents(grace_s=60, limit=100))
        assert doc_id in recoverable

    async def test_legacy_reindexing_rows_are_recoverable(
        self, async_session: AsyncSession
    ) -> None:
        # The pre-durable reindex flow stranded documents in REINDEXING on
        # crash; the rewritten flow never writes that status, so any such row
        # is recoverable debt the reaper must drain.
        doc_id = await _make_pending_document(async_session)
        await async_session.execute(
            text("UPDATE rag_documents SET status = :s WHERE id = :id"),
            {"s": RAGDocumentStatus.REINDEXING, "id": str(doc_id)},
        )
        await async_session.commit()

        recoverable = set(await repo_fetch(async_session))
        assert doc_id in recoverable


async def repo_fetch(db: AsyncSession) -> list[uuid.UUID]:
    return await RAGJobsRepository(db).fetch_recoverable_documents(grace_s=60, limit=100)
