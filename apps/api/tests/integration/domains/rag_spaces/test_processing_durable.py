"""process_document durable integration: claim + atomic chunk swap (F001 T4).

Runs the real ``process_document`` pipeline against real PostgreSQL, with the
embedding model mocked (no external API) and ``get_db_context`` redirected to the
test session. Proves the PENDING claim, the READY completion with attempts reset,
and that a reprocess replaces chunks atomically (no duplicates, never zero).
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.rag_spaces import processing
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

    monkeypatch.setattr(processing, "get_db_context", _fake_ctx)
    monkeypatch.setattr(processing, "get_rag_embeddings", lambda: _FakeEmbeddings())
    monkeypatch.setattr(settings, "rag_spaces_storage_path", str(tmp_path))
    return tmp_path


async def _make_pending_doc_with_file(
    db: AsyncSession, storage: object, content: str = "Hello world. This is a test document."
) -> RAGDocument:
    from pathlib import Path

    user = UserFactory.create()
    db.add(user)
    await db.flush()
    user_id = user.id
    space = RAGSpace(name="proc-test", user_id=user_id)
    db.add(space)
    await db.flush()
    filename = "doc.txt"
    doc = RAGDocument(
        space_id=space.id,
        user_id=user_id,
        filename=filename,
        original_filename=filename,
        file_size=len(content),
        content_type="text/plain",
        status=RAGDocumentStatus.PENDING,
    )
    db.add(doc)
    await db.commit()
    file_dir = Path(str(storage)) / str(user_id) / str(space.id)
    file_dir.mkdir(parents=True, exist_ok=True)
    (file_dir / filename).write_text(content, encoding="utf-8")
    return doc


async def _chunk_rows(db: AsyncSession, doc_id: uuid.UUID) -> list[int]:
    res = await db.execute(
        text("SELECT chunk_index FROM rag_chunks WHERE document_id = :id ORDER BY chunk_index"),
        {"id": str(doc_id)},
    )
    return [r[0] for r in res.fetchall()]


async def test_pending_document_processed_to_ready(_patched, async_session: AsyncSession) -> None:
    doc = await _make_pending_doc_with_file(async_session, _patched)
    ok = await processing.process_document(
        document_id=doc.id,
        space_id=doc.space_id,
        user_id=doc.user_id,
        filename=doc.filename,
        original_filename=doc.original_filename,
        content_type=doc.content_type,
    )
    assert ok is True
    res = await async_session.execute(
        text(
            "SELECT status, attempts, chunk_count, lease_expires_at FROM rag_documents WHERE id = :id"
        ),
        {"id": str(doc.id)},
    )
    status, attempts, chunk_count, lease = res.one()
    assert status == RAGDocumentStatus.READY
    assert attempts == 0  # reset on completion
    assert lease is None
    assert chunk_count >= 1
    assert len(await _chunk_rows(async_session, doc.id)) == chunk_count


async def test_reprocess_replaces_chunks_without_duplicates(
    _patched, async_session: AsyncSession
) -> None:
    doc = await _make_pending_doc_with_file(async_session, _patched)
    args = {
        "document_id": doc.id,
        "space_id": doc.space_id,
        "user_id": doc.user_id,
        "filename": doc.filename,
        "original_filename": doc.original_filename,
        "content_type": doc.content_type,
    }
    assert await processing.process_document(**args) is True
    first = await _chunk_rows(async_session, doc.id)
    assert first  # chunks present after first pass

    # Reset to PENDING and reprocess (simulates recovery re-drive).
    await async_session.execute(
        text("UPDATE rag_documents SET status = :p WHERE id = :id"),
        {"p": RAGDocumentStatus.PENDING, "id": str(doc.id)},
    )
    await async_session.commit()
    assert await processing.process_document(**args) is True

    second = await _chunk_rows(async_session, doc.id)
    assert second  # never left at zero chunks
    # No duplicate chunk_index (atomic swap replaced, didn't append).
    assert len(second) == len(set(second))
    assert second == first  # same deterministic chunking
