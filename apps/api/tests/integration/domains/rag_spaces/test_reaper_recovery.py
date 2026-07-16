"""rag_job_reaper recovery on real PostgreSQL (audit F001, Phase 1 T5).

Proves the reaper requeues + re-drives a stuck document (expired lease) and an
orphaned PENDING back to READY, and dead-letters a document that has exhausted
its retry budget. Embedding is mocked and ``get_db_context`` is redirected to the
test session (same harness as the T4 processing test).
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.rag_spaces import processing, reapers
from src.domains.rag_spaces.models import RAGDocument, RAGDocumentStatus, RAGSpace
from tests.fixtures.factories import UserFactory

pytestmark = pytest.mark.integration

_DIM = settings.rag_spaces_embedding_dimensions


class _FakeEmbeddings:
    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.001] * _DIM for _ in texts]


@pytest.fixture
def _patched(monkeypatch, async_session: AsyncSession, tmp_path):
    @asynccontextmanager
    async def _fake_ctx():
        yield async_session

    # Both the reaper and process_document open get_db_context; redirect both.
    monkeypatch.setattr(reapers, "get_db_context", _fake_ctx)
    monkeypatch.setattr(processing, "get_db_context", _fake_ctx)
    monkeypatch.setattr(processing, "get_rag_embeddings", lambda: _FakeEmbeddings())
    monkeypatch.setattr(settings, "rag_spaces_storage_path", str(tmp_path))
    return tmp_path


async def _make_doc(
    db: AsyncSession, storage: object, *, status: str, with_file: bool = True
) -> RAGDocument:
    from pathlib import Path

    user = UserFactory.create()
    db.add(user)
    await db.flush()
    space = RAGSpace(name="reaper-test", user_id=user.id)
    db.add(space)
    await db.flush()
    filename = "doc.txt"
    doc = RAGDocument(
        space_id=space.id,
        user_id=user.id,
        filename=filename,
        original_filename=filename,
        file_size=20,
        content_type="text/plain",
        status=status,
    )
    db.add(doc)
    await db.commit()
    if with_file:
        d = Path(str(storage)) / str(user.id) / str(space.id)
        d.mkdir(parents=True, exist_ok=True)
        (d / filename).write_text("Hello world. Reaper recovery test.", encoding="utf-8")
    return doc


async def _status(db: AsyncSession, doc_id: uuid.UUID) -> str:
    res = await db.execute(
        text("SELECT status FROM rag_documents WHERE id = :id"), {"id": str(doc_id)}
    )
    return str(res.scalar_one())


async def test_reaper_requeues_and_redrives_stuck_document(
    _patched, async_session: AsyncSession
) -> None:
    doc = await _make_doc(async_session, _patched, status=RAGDocumentStatus.PROCESSING)
    # Stuck: expired lease, one attempt already spent (< max).
    await async_session.execute(
        text(
            "UPDATE rag_documents SET lease_expires_at = now() - interval '1 hour', "
            "attempts = 1 WHERE id = :id"
        ),
        {"id": str(doc.id)},
    )
    await async_session.commit()

    await reapers.rag_job_reaper()

    # Requeued (PENDING) then re-driven through process_document to READY.
    assert await _status(async_session, doc.id) == RAGDocumentStatus.READY
    res = await async_session.execute(
        text("SELECT count(*) FROM rag_chunks WHERE document_id = :id"), {"id": str(doc.id)}
    )
    assert res.scalar_one() >= 1


async def test_reaper_recovers_orphaned_pending(_patched, async_session: AsyncSession) -> None:
    doc = await _make_doc(async_session, _patched, status=RAGDocumentStatus.PENDING)
    # Orphaned: created long ago, never claimed (heartbeat_at NULL).
    await async_session.execute(
        text("UPDATE rag_documents SET created_at = now() - interval '1 hour' WHERE id = :id"),
        {"id": str(doc.id)},
    )
    await async_session.commit()

    await reapers.rag_job_reaper()

    assert await _status(async_session, doc.id) == RAGDocumentStatus.READY


async def test_reaper_dead_letters_at_max_attempts(_patched, async_session: AsyncSession) -> None:
    doc = await _make_doc(
        async_session, _patched, status=RAGDocumentStatus.PROCESSING, with_file=False
    )
    # Exhausted retry budget: attempts == max, expired lease → ERROR, not re-driven.
    await async_session.execute(
        text(
            "UPDATE rag_documents SET lease_expires_at = now() - interval '1 hour', "
            "attempts = :max WHERE id = :id"
        ),
        {"max": settings.rag_job_max_attempts, "id": str(doc.id)},
    )
    await async_session.commit()

    await reapers.rag_job_reaper()

    assert await _status(async_session, doc.id) == RAGDocumentStatus.ERROR
