"""Source relocation can join exact approval without committing or touching local bytes."""

from pathlib import Path

import pytest
from sqlalchemy import select

from src.core.config import settings
from src.core.constants import RAG_SPACES_EMBEDDING_DIMENSIONS_DEFAULT
from src.domains.rag_spaces import document_ops
from src.domains.rag_spaces.models import RAGChunk, RAGDocument, RAGSpace
from src.domains.rag_spaces.service import RAGSpaceService

pytestmark = pytest.mark.integration


async def test_source_move_rows_are_deferred_and_rollbackable(
    async_session, test_user, monkeypatch, tmp_path: Path
):
    monkeypatch.setattr(settings, "rag_spaces_storage_path", str(tmp_path))
    owner = test_user.id
    source, target = RAGSpace(user_id=owner, name="Source"), RAGSpace(user_id=owner, name="Target")
    async_session.add_all([source, target])
    await async_session.flush()
    document = RAGDocument(
        user_id=owner,
        space_id=source.id,
        filename="original.txt",
        original_filename="Original.txt",
        file_size=4,
        content_type="text/plain",
        status="ready",
    )
    async_session.add(document)
    await async_session.flush()
    chunk = RAGChunk(
        user_id=owner,
        space_id=source.id,
        document_id=document.id,
        chunk_index=0,
        content="Controlled private text",
        embedding=[0.0] * RAG_SPACES_EMBEDDING_DIMENSIONS_DEFAULT,
        embedding_model="controlled-move-fixture",
    )
    async_session.add(chunk)
    await async_session.commit()
    source_id, target_id, identity, chunk_id = source.id, target.id, document.id, chunk.id
    original = tmp_path / str(owner) / str(source_id) / "original.txt"
    destination = tmp_path / str(owner) / str(target_id) / "original.txt"
    original.parent.mkdir(parents=True)
    original.write_bytes(b"data")
    await document_ops.relocate_document_rows(
        RAGSpaceService(async_session), document, target_id, commit=False
    )
    assert (
        await async_session.scalar(select(RAGDocument.space_id).where(RAGDocument.id == identity))
        == target_id
    )
    assert (
        await async_session.scalar(select(RAGChunk.space_id).where(RAGChunk.id == chunk_id))
        == target_id
    )
    assert original.read_bytes() == b"data" and not destination.exists()
    await async_session.rollback()
    assert (
        await async_session.scalar(select(RAGDocument.space_id).where(RAGDocument.id == identity))
        == source_id
    )
    assert (
        await async_session.scalar(select(RAGChunk.space_id).where(RAGChunk.id == chunk_id))
        == source_id
    )
    assert original.read_bytes() == b"data" and not destination.exists()
