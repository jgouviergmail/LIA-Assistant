"""Destructive source boundaries use actual owned SQL rows and vector chunks."""

from uuid import uuid4

import pytest
from sqlalchemy import func, select

from src.core.config import settings
from src.core.constants import RAG_SPACES_EMBEDDING_DIMENSIONS_DEFAULT
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.source_delete import (
    execute_source_deletion,
    prepare_source_deletion,
)
from src.domains.agents.application.source_delete_schemas import SourceDeleteInput
from src.domains.rag_spaces.models import RAGChunk, RAGDocument, RAGDriveSource, RAGSpace
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "boundary",
    ["empty", "chunk", "wrong_chunk_space", "system_chunk", "oversized", "multiple_batches"],
)
async def test_source_deletion_exact_chunk_scope_and_bounded_selection(
    async_session, test_user, monkeypatch, tmp_path, boundary
):
    for flag in ("application_tools_enabled", "rag_spaces_enabled"):
        monkeypatch.setattr(settings, flag, True)
    monkeypatch.setattr(settings, "rag_spaces_storage_path", str(tmp_path))
    actor = test_user.id
    space = RAGSpace(user_id=actor, name="Source destination")
    other = RAGSpace(user_id=actor, name="Other destination")
    async_session.add_all([space, other])
    await async_session.flush()
    space_id, other_id = space.id, other.id
    source = RAGDriveSource(user_id=actor, space_id=space_id, folder_id="root", folder_name="Root")
    async_session.add(source)
    await async_session.flush()
    source_id = source.id
    count = 0 if boundary == "empty" else 101 if boundary == "multiple_batches" else 1
    documents = [
        RAGDocument(
            user_id=actor,
            space_id=space_id,
            drive_source_id=source_id,
            filename=f"{uuid4()}.txt",
            original_filename="x",
            content_type="text/plain",
            file_size=1,
            status="ready",
        )
        for _ in range(count)
    ]
    async_session.add_all(documents)
    await async_session.flush()
    if boundary in {"chunk", "wrong_chunk_space", "system_chunk", "oversized"}:
        async_session.add(
            RAGChunk(
                document_id=documents[0].id,
                space_id=other_id if boundary == "wrong_chunk_space" else space_id,
                user_id=None if boundary == "system_chunk" else actor,
                chunk_index=0,
                content="x" * 64001 if boundary == "oversized" else "Literal content",
                embedding=[0.0] * RAG_SPACES_EMBEDDING_DIMENSIONS_DEFAULT,
                embedding_model="controlled",
            )
        )
    await async_session.commit()
    request = SourceDeleteInput(space_id=space_id, source_id=source_id, kind="drive")
    if boundary in {"wrong_chunk_space", "system_chunk", "oversized"}:
        with pytest.raises((CommandRejected, ValueError)):
            await prepare_source_deletion(async_session, actor, request)
        assert (
            await async_session.scalar(
                select(RAGDriveSource.id).where(RAGDriveSource.id == source_id)
            )
            == source_id
        )
        return
    draft = await prepare_source_deletion(async_session, actor, request)
    if boundary == "multiple_batches":
        assert len(draft.intent["source_to_delete"]["batches"]) == 2
    await async_session.commit()
    receipt = PreferenceWriteReceipt()
    await execute_source_deletion(async_session, actor, draft, receipt)
    assert receipt.committed and receipt.values["source_to_delete"]["documents_deleted"] == count
    assert (
        await async_session.scalar(
            select(func.count(RAGChunk.id)).where(RAGChunk.space_id == space_id)
        )
        == 0
    )
    assert (
        await async_session.scalar(select(RAGDriveSource.id).where(RAGDriveSource.id == source_id))
        is None
    )
