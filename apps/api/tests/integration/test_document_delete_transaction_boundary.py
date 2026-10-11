"""Document deletion can join a caller-owned transaction without deleting bytes before ACK."""

from pathlib import Path

import pytest
from sqlalchemy import event, select

from src.core.config import settings
from src.core.constants import RAG_SPACES_EMBEDDING_DIMENSIONS_DEFAULT
from src.core.exceptions import BaseAPIException
from src.domains.rag_spaces.models import RAGChunk, RAGDocument, RAGSpace
from src.domains.rag_spaces.service import RAGSpaceService

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("obstacle", ["bookmark", "foreign", "system"])
async def test_selected_batch_source_refusal_precedes_every_delete(
    async_session, test_user, obstacle
):
    from uuid import uuid4

    owner = test_user.id
    space = RAGSpace(user_id=owner, name="Guarded source batch", is_system=obstacle == "system")
    async_session.add(space)
    await async_session.flush()
    document = RAGDocument(
        user_id=owner,
        space_id=space.id,
        filename="kept.txt",
        original_filename="Kept",
        file_size=4,
        content_type="text/plain",
        status="ready",
        source_type="bookmark" if obstacle == "bookmark" else "upload",
    )
    async_session.add(document)
    await async_session.commit()
    space_id, identity = space.id, document.id
    selected = (identity, uuid4()) if obstacle == "foreign" else (identity,)
    with pytest.raises(BaseAPIException):
        await RAGSpaceService(async_session).delete_selected_document_rows(
            space_id, selected, owner
        )
    assert await async_session.get(RAGDocument, identity, populate_existing=True) is not None


@pytest.mark.parametrize("count", [1, 10])
async def test_selected_document_batch_has_constant_sql_and_can_rollback(
    async_session, test_user, monkeypatch, tmp_path, count
):
    monkeypatch.setattr(settings, "rag_spaces_storage_path", str(tmp_path))
    owner = test_user.id
    space = RAGSpace(user_id=owner, name="Constant SQL batch")
    async_session.add(space)
    await async_session.flush()
    documents = [
        RAGDocument(
            user_id=owner,
            space_id=space.id,
            filename=f"{index}.txt",
            original_filename=f"Document {index}",
            file_size=4,
            content_type="text/plain",
            status="ready",
        )
        for index in range(count + 1)
    ]
    async_session.add_all(documents)
    await async_session.commit()
    space_id, identities, kept = (
        space.id,
        tuple(document.id for document in documents[:-1]),
        documents[-1].id,
    )
    calls = []
    engine = async_session.bind.sync_engine

    def record(_connection, _cursor, statement, _parameters, _context, _many):
        calls.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        await RAGSpaceService(async_session).delete_selected_document_rows(
            space_id, identities, owner
        )
    finally:
        event.remove(engine, "before_cursor_execute", record)
    # The hermetic fixture opens a SAVEPOINT for each transaction; count the
    # real data reads/writes rather than its test-isolation bookkeeping.
    data_calls = [statement for statement in calls if not statement.startswith("SAVEPOINT ")]
    assert len(data_calls) == 4, calls
    assert (
        await async_session.scalar(select(RAGDocument.id).where(RAGDocument.id.in_(identities)))
        is None
    )
    assert await async_session.get(RAGDocument, kept, populate_existing=True) is not None
    await async_session.rollback()
    restored = list(
        (
            await async_session.scalars(
                select(RAGDocument.id).where(RAGDocument.id.in_(identities))
            )
        ).all()
    )
    assert set(restored) == set(identities)


async def test_deferred_document_deletion_is_rollbackable_and_keeps_original_file(
    async_session, test_user, monkeypatch, tmp_path: Path
):
    monkeypatch.setattr(settings, "rag_spaces_storage_path", str(tmp_path))
    owner = test_user.id
    space = RAGSpace(user_id=owner, name="Document deletion")
    async_session.add(space)
    await async_session.flush()
    document = RAGDocument(
        user_id=owner,
        space_id=space.id,
        filename="original.txt",
        original_filename="Original.txt",
        content_type="text/plain",
        file_size=4,
        status="ready",
    )
    async_session.add(document)
    sibling = RAGDocument(
        user_id=owner,
        space_id=space.id,
        filename="kept.txt",
        original_filename="Kept.txt",
        content_type="text/plain",
        file_size=4,
        status="ready",
    )
    async_session.add(sibling)
    await async_session.flush()
    chunk = RAGChunk(
        document_id=document.id,
        space_id=space.id,
        user_id=owner,
        chunk_index=0,
        content="Controlled content",
        embedding=[0.0] * RAG_SPACES_EMBEDDING_DIMENSIONS_DEFAULT,
        embedding_model="transaction-fixture",
    )
    kept_chunk = RAGChunk(
        document_id=sibling.id,
        space_id=space.id,
        user_id=owner,
        chunk_index=0,
        content="Controlled sibling",
        embedding=[0.0] * RAG_SPACES_EMBEDDING_DIMENSIONS_DEFAULT,
        embedding_model="transaction-fixture",
    )
    async_session.add_all([chunk, kept_chunk])
    await async_session.commit()
    space_id, document_id, sibling_id, chunk_id, kept_chunk_id = (
        space.id,
        document.id,
        sibling.id,
        chunk.id,
        kept_chunk.id,
    )
    path = tmp_path / str(owner) / str(space_id) / "original.txt"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"data")
    await RAGSpaceService(async_session).delete_document(space_id, document_id, owner, commit=False)
    assert path.read_bytes() == b"data"
    assert await async_session.scalar(select(RAGChunk.id).where(RAGChunk.id == chunk_id)) is None
    assert (
        await async_session.scalar(select(RAGDocument.id).where(RAGDocument.id == sibling_id))
        == sibling_id
    )
    assert (
        await async_session.scalar(select(RAGChunk.id).where(RAGChunk.id == kept_chunk_id))
        == kept_chunk_id
    )
    assert (
        await async_session.scalar(select(RAGDocument.id).where(RAGDocument.id == document_id))
        is None
    )
    await async_session.rollback()
    assert (
        await async_session.scalar(select(RAGChunk.id).where(RAGChunk.id == chunk_id)) == chunk_id
    )
    assert (
        await async_session.scalar(select(RAGDocument.id).where(RAGDocument.id == document_id))
        == document_id
    )
    assert path.read_bytes() == b"data"
