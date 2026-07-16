"""Reindex dimension-change is atomic with the durable requeue (audit F001, V8).

The V8 counter-audit proved a reproducible failure window in the reindex
setup: the chunk destruction + vector DDL were committed in one transaction,
and the READY/ERROR → PENDING requeue (the durable "work to do" state) in a
SECOND one. A crash between the two commits left documents READY with zero
chunks — invisible to the reaper (which only scans PROCESSING/REINDEXING/
PENDING), hence unrecoverable data loss until a manual re-run.

These real-PostgreSQL tests pin the closed window. The savepoint fixture
(F049) makes transaction boundaries faithfully observable: a ``commit()``
inside the code under test releases a savepoint (survives a subsequent
rollback), while the teardown rolls back everything including test DDL.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.rag_spaces import reindex
from src.domains.rag_spaces.jobs_repository import RAGJobsRepository
from src.domains.rag_spaces.models import (
    RAGChunk,
    RAGDocument,
    RAGDocumentStatus,
    RAGSpace,
)

pytestmark = pytest.mark.integration


async def _current_dims(db: AsyncSession) -> int:
    res = await db.execute(
        text(
            "SELECT atttypmod FROM pg_attribute "
            "WHERE attrelid = 'rag_chunks'::regclass AND attname = 'embedding'"
        )
    )
    return int(res.scalar_one())


async def _make_ready_document_with_chunk(db: AsyncSession, dims: int) -> uuid.UUID:
    """One READY document owning one real chunk (the pre-reindex state)."""
    space = RAGSpace(name="reindex-tx-space")
    db.add(space)
    await db.flush()
    doc = RAGDocument(
        space_id=space.id,
        filename="f.txt",
        original_filename="f.txt",
        file_size=10,
        content_type="text/plain",
        status=RAGDocumentStatus.READY,
        chunk_count=1,
    )
    db.add(doc)
    await db.flush()
    db.add(
        RAGChunk(
            document_id=doc.id,
            space_id=space.id,
            chunk_index=0,
            content="hello world",
            embedding=[0.0] * dims,
            embedding_model="test-model",
        )
    )
    await db.commit()
    return doc.id


async def _chunk_count(db: AsyncSession) -> int:
    res = await db.execute(text("SELECT count(*) FROM rag_chunks"))
    return int(res.scalar_one())


class TestReindexSetupAtomicity:
    """The destructive DDL and the durable requeue live in ONE transaction."""

    async def test_crash_between_destruction_and_requeue_loses_nothing(
        self, async_session: AsyncSession
    ) -> None:
        """A crash after the DDL but before the requeue must leave a
        recoverable-or-intact state — never READY documents without chunks.

        The crash is simulated by rolling back the open transaction right
        after the destructive step, exactly what a process death does to an
        uncommitted transaction. Red on the pre-fix code (the destruction was
        already committed on its own), green once destruction + requeue share
        a single commit.
        """
        dims = await _current_dims(async_session)
        new_dims = 768 if dims != 768 else 1024
        doc_id = await _make_ready_document_with_chunk(async_session, dims)

        # --- the destructive first step of the reindex setup ---
        await reindex._alter_vector_dimensions_if_needed(async_session, new_dims)

        # --- CRASH before the requeue: the open transaction dies with the
        # process; anything already committed stays. ---
        await async_session.rollback()

        chunks_left = await _chunk_count(async_session)
        res = await async_session.execute(
            text("SELECT status FROM rag_documents WHERE id = :id"), {"id": str(doc_id)}
        )
        doc_status = res.scalar_one()
        recoverable = await RAGJobsRepository(async_session).fetch_recoverable_documents(
            grace_s=0, limit=100
        )

        state_is_intact = chunks_left == 1 and doc_status == RAGDocumentStatus.READY
        state_is_recoverable = doc_id in set(recoverable)
        assert state_is_intact or state_is_recoverable, (
            "crash window (audit F001/V8): chunks destroyed "
            f"(count={chunks_left}) while the document stayed {doc_status!r} "
            "and the reaper cannot see it — unrecoverable data loss"
        )

    async def test_successful_setup_commits_destruction_and_requeue_together(
        self, async_session: AsyncSession
    ) -> None:
        """The nominal path lands both effects atomically: chunks purged,
        column altered, and every target document durably PENDING."""
        dims = await _current_dims(async_session)
        new_dims = 768 if dims != 768 else 1024
        doc_id = await _make_ready_document_with_chunk(async_session, dims)

        await reindex._persist_reindex_intent(async_session, [doc_id], new_dims)

        # A rollback right after must be a no-op: everything was committed.
        await async_session.rollback()

        assert await _chunk_count(async_session) == 0
        assert await _current_dims(async_session) == new_dims
        res = await async_session.execute(
            text("SELECT status FROM rag_documents WHERE id = :id"), {"id": str(doc_id)}
        )
        assert res.scalar_one() == RAGDocumentStatus.PENDING
        # And the reaper CAN see it once past the grace window (heartbeat is
        # stamped by the requeue, so backdate it as a crashed drain would age).
        await async_session.execute(
            text(
                "UPDATE rag_documents SET heartbeat_at = now() - interval '10 minutes' "
                "WHERE id = :id"
            ),
            {"id": str(doc_id)},
        )
        await async_session.commit()
        recoverable = await RAGJobsRepository(async_session).fetch_recoverable_documents(
            grace_s=60, limit=100
        )
        assert doc_id in set(recoverable)

    async def test_requeue_failure_rolls_back_the_destruction(
        self, async_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If the requeue step itself fails mid-setup, the destructive DDL is
        rolled back with it — the index stays fully servable."""
        dims = await _current_dims(async_session)
        new_dims = 768 if dims != 768 else 1024
        doc_id = await _make_ready_document_with_chunk(async_session, dims)

        async def _boom(self, ids):  # noqa: ANN001, ANN202 - test stub
            raise RuntimeError("requeue blew up mid-setup")

        monkeypatch.setattr(RAGJobsRepository, "requeue_documents_for_reindex", _boom)

        with pytest.raises(RuntimeError, match="requeue blew up"):
            await reindex._persist_reindex_intent(async_session, [doc_id], new_dims)
        await async_session.rollback()

        assert await _chunk_count(async_session) == 1
        assert await _current_dims(async_session) == dims
        res = await async_session.execute(
            text("SELECT status FROM rag_documents WHERE id = :id"), {"id": str(doc_id)}
        )
        assert res.scalar_one() == RAGDocumentStatus.READY
