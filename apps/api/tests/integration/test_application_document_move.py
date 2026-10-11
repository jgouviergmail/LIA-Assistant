"""Exact native movement preserves source bytes on rollback and uncertain SQL ACK."""

import asyncio
from pathlib import Path

import pytest
from sqlalchemy import select

from src.core.config import settings
from src.core.constants import RAG_SPACES_EMBEDDING_DIMENSIONS_DEFAULT
from src.core.exceptions import ResourceConflictError
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.document_move import (
    execute_document_move,
    prepare_document_move,
)
from src.domains.agents.application.document_move_schemas import DocumentMoveInput
from src.domains.rag_spaces.models import RAGChunk, RAGDocument, RAGSpace
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "obstacle",
    [
        "none",
        "changed",
        "chunk_changed",
        "lost_ack",
        "cancelled_ack",
        "copy_failed",
        "copy_cancelled",
        "cleanup_failed",
    ],
)
async def test_native_document_move_is_exact_and_keeps_files_on_unknown_commit(
    async_session, test_user, monkeypatch, tmp_path: Path, obstacle
):
    monkeypatch.setattr(settings, "rag_spaces_enabled", True)
    monkeypatch.setattr(settings, "rag_spaces_storage_path", str(tmp_path))
    monkeypatch.setattr(
        "src.domains.agents.application.document_move_scope.get_reindex_status", _idle
    )
    owner = test_user.id
    source, target = RAGSpace(user_id=owner, name="Source"), RAGSpace(user_id=owner, name="Target")
    async_session.add_all([source, target])
    await async_session.flush()
    document = RAGDocument(
        user_id=owner,
        space_id=source.id,
        filename="moved.txt",
        original_filename="Moved.txt",
        file_size=4,
        content_type="text/plain",
        status="ready",
    )
    async_session.add(document)
    await async_session.flush()
    chunk = RAGChunk(
        document_id=document.id,
        space_id=source.id,
        user_id=owner,
        chunk_index=0,
        content="Controlled private content",
        embedding=[0.0] * RAG_SPACES_EMBEDDING_DIMENSIONS_DEFAULT,
        embedding_model="move-fixture",
    )
    async_session.add(chunk)
    await async_session.commit()
    source_id, target_id, identity = source.id, target.id, document.id
    chunk_id = chunk.id
    original = tmp_path / str(owner) / str(source_id) / "moved.txt"
    destination = tmp_path / str(owner) / str(target_id) / "moved.txt"
    original.parent.mkdir(parents=True)
    original.write_bytes(b"data")
    draft = await prepare_document_move(
        async_session,
        owner,
        DocumentMoveInput(space_id=source_id, document_ids=[identity], target_space_id=target_id),
    )
    assert original.read_bytes() == b"data" and not destination.exists()
    if obstacle == "changed":
        document.original_filename = "Changed since consent"
        await async_session.commit()
    if obstacle == "chunk_changed":
        chunk.content = "Changed chunk after consent"
        await async_session.commit()
    if obstacle in {"copy_failed", "copy_cancelled", "cleanup_failed"}:
        from unittest.mock import AsyncMock

        if obstacle == "cleanup_failed":
            monkeypatch.setattr(
                "src.domains.agents.application.document_move.cleanup_deleted_document_file",
                AsyncMock(return_value=False),
            )
        else:
            failure = (
                asyncio.CancelledError()
                if obstacle == "copy_cancelled"
                else OSError("Controlled staging failure")
            )
            monkeypatch.setattr(
                "src.domains.agents.application.document_move.stage_document_file",
                AsyncMock(side_effect=failure),
            )
    if obstacle in {"lost_ack", "cancelled_ack"}:
        commit = async_session.commit

        async def lost():
            await commit()
            if obstacle == "cancelled_ack":
                raise asyncio.CancelledError()
            raise OSError("Controlled lost commit acknowledgement")

        monkeypatch.setattr(async_session, "commit", lost)
    receipt = PreferenceWriteReceipt()
    if obstacle not in {"none", "cleanup_failed"}:
        with pytest.raises(
            (ResourceConflictError, CommandRejected, OSError, asyncio.CancelledError)
        ) as rejected:
            await execute_document_move(async_session, owner, draft, receipt)
        assert not receipt.committed and original.read_bytes() == b"data"
        await async_session.rollback()
        moved = obstacle in {"lost_ack", "cancelled_ack"}
        if moved:
            assert (
                isinstance(rejected.value, CommandRejected)
                and rejected.value.code == "COMPLETION_UNKNOWN"
            )
            assert destination.read_bytes() == b"data"
        else:
            assert not destination.exists()
        assert await async_session.scalar(
            select(RAGDocument.space_id).where(RAGDocument.id == identity)
        ) == (target_id if moved else source_id)
        assert await async_session.scalar(
            select(RAGChunk.space_id).where(RAGChunk.id == chunk_id)
        ) == (target_id if moved else source_id)
    else:
        await execute_document_move(async_session, owner, draft, receipt)
        assert receipt.committed and destination.read_bytes() == b"data"
        assert original.exists() is (obstacle == "cleanup_failed")
        assert receipt.values["documents_to_move"]["file_cleanup_pending"] is (
            obstacle == "cleanup_failed"
        )
        assert (
            await async_session.scalar(
                select(RAGDocument.space_id).where(RAGDocument.id == identity)
            )
            == target_id
        )
        assert (
            await async_session.scalar(select(RAGChunk.space_id).where(RAGChunk.id == chunk_id))
            == target_id
        )


async def _idle():
    return {"in_progress": False}
