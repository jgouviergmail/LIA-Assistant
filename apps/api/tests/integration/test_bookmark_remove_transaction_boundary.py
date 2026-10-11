"""Bookmark removal never commits or destroys an unrelated projection in native transactions."""

import pytest
from sqlalchemy import select

from src.core.config import settings
from src.core.constants import RAG_SPACES_EMBEDDING_DIMENSIONS_DEFAULT
from src.core.exceptions import ResourceConflictError
from src.domains.bookmarks.models import MessageBookmark
from src.domains.bookmarks.service import BookmarkService
from src.domains.rag_spaces.models import (
    RAGChunk,
    RAGDocument,
    RAGDocumentSourceType,
    RAGDocumentStatus,
)
from tests.integration.domains.bookmarks.test_bookmarks_db import (
    _bookmark,
    _document,
    _space,
    _user,
)

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "reason",
    [
        "deferred",
        "foreign_projection",
        "unrelated_kind",
        "foreign_chunk",
        "system_chunk",
        "wrong_chunk_space",
        "foreign_parent",
        "shared_projection",
        "shared_file",
    ],
)
async def test_saved_answer_removal_preserves_files_until_commit_and_refuses_wrong_projection(
    async_session, test_user, monkeypatch, tmp_path, reason
):
    monkeypatch.setattr(settings, "rag_spaces_storage_path", str(tmp_path))
    actor = test_user.id
    owner = await _user(async_session) if reason == "foreign_projection" else test_user
    space = await _space(async_session, owner)
    document = await _document(async_session, owner, space, RAGDocumentStatus.READY)
    if reason == "unrelated_kind":
        document.source_type = RAGDocumentSourceType.UPLOAD
    if reason == "foreign_parent":
        document.space_id = (await _space(async_session, await _user(async_session))).id
    row = await _bookmark(async_session, test_user, None)
    row.rag_document_id = document.id
    if reason == "shared_projection":
        shared = await _bookmark(async_session, test_user, None)
        shared.rag_document_id = document.id
    if reason == "shared_file":
        other_document = await _document(async_session, test_user, space, RAGDocumentStatus.READY)
        other_document.filename = document.filename
    if reason in {"foreign_chunk", "system_chunk", "wrong_chunk_space"}:
        chunk_owner = None if reason == "system_chunk" else actor
        if reason == "foreign_chunk":
            chunk_owner = (await _user(async_session)).id
        chunk_space = space.id
        if reason == "wrong_chunk_space":
            chunk_space = (await _space(async_session, await _user(async_session))).id
        async_session.add(
            RAGChunk(
                document_id=document.id,
                space_id=chunk_space,
                user_id=chunk_owner,
                chunk_index=0,
                content="Unapproved chunk",
                embedding=[0.0] * RAG_SPACES_EMBEDDING_DIMENSIONS_DEFAULT,
                embedding_model="fixture",
            )
        )
    identity, document_id = row.id, document.id
    path = tmp_path / str(owner.id) / str(space.id) / document.filename
    path.parent.mkdir(parents=True)
    path.write_bytes(b"owned projection bytes")
    await async_session.commit()
    service = BookmarkService(async_session)
    if reason == "deferred":
        deferred = await service.remove(actor, identity, commit=False)
        assert deferred == path and path.exists()
        assert (
            await async_session.scalar(
                select(MessageBookmark.id).where(MessageBookmark.id == identity)
            )
            is None
        )
        assert (
            await async_session.scalar(select(RAGDocument.id).where(RAGDocument.id == document_id))
            is None
        )
        await async_session.rollback()
    else:
        with pytest.raises(ResourceConflictError):
            await service.remove(actor, identity)
        await async_session.rollback()
    assert path.read_bytes() == b"owned projection bytes"
    assert (
        await async_session.scalar(select(MessageBookmark.id).where(MessageBookmark.id == identity))
        == identity
    )
    assert (
        await async_session.scalar(select(RAGDocument.id).where(RAGDocument.id == document_id))
        == document_id
    )
