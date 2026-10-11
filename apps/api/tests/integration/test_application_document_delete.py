"""Selected-document HITL deletes only the approved rows; changes require new consent."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from src.core.config import settings
from src.core.constants import RAG_SPACES_EMBEDDING_DIMENSIONS_DEFAULT
from src.core.exceptions import BaseAPIException, ResourceConflictError
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.document_delete import (
    execute_document_deletion,
    prepare_document_deletion,
)
from src.domains.agents.application.document_delete_schemas import DocumentDeleteInput
from src.domains.rag_spaces.models import RAGChunk, RAGDocument, RAGDriveSource, RAGSpace
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "obstacle",
    [
        "none",
        "renamed",
        "chunk_changed",
        "file_changed",
        "lost_ack",
        "cancelled_ack",
        "cleanup_failed",
        "cleanup_cancelled",
    ],
)
async def test_selected_document_delete_is_exact_and_rejects_changed_source(
    async_session, test_user, monkeypatch, tmp_path: Path, obstacle
):
    monkeypatch.setattr(settings, "rag_spaces_enabled", True)
    monkeypatch.setattr(settings, "rag_spaces_storage_path", str(tmp_path))
    owner = test_user.id
    space = RAGSpace(user_id=owner, name="Owned documents")
    async_session.add(space)
    await async_session.flush()
    documents = [
        RAGDocument(
            user_id=owner,
            space_id=space.id,
            filename=f"{index}.txt",
            original_filename=f"Document {index}.txt",
            file_size=4,
            content_type="text/plain",
            status="ready",
        )
        for index in range(3)
    ]
    async_session.add_all(documents)
    await async_session.flush()
    chunks = [
        RAGChunk(
            document_id=document.id,
            space_id=space.id,
            user_id=owner,
            chunk_index=0,
            content=f"Private body {index}",
            embedding=[0.0] * RAG_SPACES_EMBEDDING_DIMENSIONS_DEFAULT,
            embedding_model="controlled-deletion-fixture",
        )
        for index, document in enumerate(documents)
    ]
    async_session.add_all(chunks)
    await async_session.commit()
    space_id, selected_id, second_id, kept_id = (
        space.id,
        documents[0].id,
        documents[1].id,
        documents[2].id,
    )
    kept_chunk_id = chunks[2].id
    directory = tmp_path / str(owner) / str(space_id)
    directory.mkdir(parents=True)
    selected_path, second_path, kept_path = (
        directory / "0.txt",
        directory / "1.txt",
        directory / "2.txt",
    )
    selected_path.write_bytes(b"data")
    second_path.write_bytes(b"also")
    kept_path.write_bytes(b"kept")
    draft = await prepare_document_deletion(
        async_session,
        owner,
        DocumentDeleteInput(space_id=space_id, document_ids=[selected_id, second_id]),
    )
    assert selected_path.read_bytes() == b"data"
    assert str(tmp_path) not in str(draft.model_dump(mode="json"))
    assert "state_digest" not in str(draft.before) and "state_digest" not in str(draft.after)
    assert "Private body" not in str(draft.model_dump(mode="json"))
    assert draft.before["documents_to_delete"]["chunks"] == 2
    receipt = PreferenceWriteReceipt()
    if obstacle == "renamed":
        documents[0].original_filename = "Renamed since consent.txt"
        await async_session.commit()
    elif obstacle == "chunk_changed":
        chunks[0].content = "Changed since consent"
        await async_session.commit()
    elif obstacle == "file_changed":
        selected_path.write_bytes(b"more")
    elif obstacle in {"lost_ack", "cancelled_ack"}:
        original = async_session.commit

        async def lose_ack():
            await original()
            if obstacle == "cancelled_ack":
                raise asyncio.CancelledError()
            raise OSError("Controlled lost acknowledgement")

        monkeypatch.setattr(async_session, "commit", lose_ack)
    elif obstacle in {"cleanup_failed", "cleanup_cancelled"}:
        callback = (
            AsyncMock(return_value=False)
            if obstacle == "cleanup_failed"
            else AsyncMock(side_effect=asyncio.CancelledError())
        )
        monkeypatch.setattr(
            "src.domains.agents.application.document_delete.cleanup_deleted_document_file", callback
        )
    if obstacle in {"renamed", "chunk_changed", "file_changed"}:
        with pytest.raises(ResourceConflictError):
            await execute_document_deletion(async_session, owner, draft, receipt)
        await async_session.rollback()
        assert not receipt.committed and selected_path.exists()
        assert await async_session.get(RAGDocument, selected_id) is not None
    elif obstacle in {"lost_ack", "cancelled_ack"}:
        with pytest.raises(CommandRejected, match="COMPLETION_UNKNOWN"):
            await execute_document_deletion(async_session, owner, draft, receipt)
        assert not receipt.committed and selected_path.exists() and second_path.exists()
        await async_session.rollback()
        assert await async_session.get(RAGDocument, selected_id, populate_existing=True) is None
    else:
        await execute_document_deletion(async_session, owner, draft, receipt)
        assert receipt.committed
        assert (
            await async_session.scalar(select(RAGDocument.id).where(RAGDocument.id == selected_id))
            is None
        )
        pending = obstacle != "none"
        assert receipt.values["documents_to_delete"]["file_cleanup_pending"] is pending
        assert selected_path.exists() is pending and second_path.exists() is pending
        assert await async_session.get(RAGDocument, second_id, populate_existing=True) is None
    assert (
        await async_session.scalar(select(RAGDocument.id).where(RAGDocument.id == kept_id))
        == kept_id
    )
    assert kept_path.read_bytes() == b"kept"
    assert await async_session.get(RAGChunk, kept_chunk_id, populate_existing=True) is not None


@pytest.mark.parametrize(
    "obstacle",
    [
        "system",
        "foreign",
        "bookmark",
        "processing",
        "reindexing",
        "syncing",
        "wrong_source_space",
        "missing_file",
    ],
)
async def test_document_deletion_preserves_source_ownership_and_managed_rules(
    async_session, test_user, monkeypatch, tmp_path, obstacle
):
    from uuid import uuid4

    monkeypatch.setattr(settings, "rag_spaces_enabled", True)
    monkeypatch.setattr(settings, "rag_spaces_storage_path", str(tmp_path))
    owner = test_user.id
    space = RAGSpace(user_id=owner, name="Selected source", is_system=obstacle == "system")
    other = RAGSpace(user_id=owner, name="Other source")
    async_session.add_all([space, other])
    await async_session.flush()
    source = RAGDriveSource(
        user_id=owner,
        space_id=other.id if obstacle == "wrong_source_space" else space.id,
        folder_id="controlled-source",
        folder_name="Controlled source",
        sync_status="syncing" if obstacle == "syncing" else "idle",
    )
    async_session.add(source)
    await async_session.flush()
    document = RAGDocument(
        user_id=owner,
        space_id=space.id,
        filename="missing.txt",
        original_filename="Selected document",
        file_size=1,
        content_type="text/plain",
        source_type="bookmark" if obstacle == "bookmark" else "upload",
        status=obstacle if obstacle in {"processing", "reindexing"} else "ready",
        drive_source_id=source.id if obstacle in {"syncing", "wrong_source_space"} else None,
    )
    async_session.add(document)
    await async_session.commit()
    space_id, identity = space.id, document.id
    request = DocumentDeleteInput(
        space_id=space_id, document_ids=[uuid4() if obstacle == "foreign" else identity]
    )
    if obstacle == "missing_file":
        draft = await prepare_document_deletion(async_session, owner, request)
        receipt = PreferenceWriteReceipt()
        await execute_document_deletion(async_session, owner, draft, receipt)
        assert (
            receipt.committed
            and receipt.values["documents_to_delete"]["file_cleanup_pending"] is False
        )
    else:
        with pytest.raises((CommandRejected, BaseAPIException)):
            await prepare_document_deletion(async_session, owner, request)
        assert await async_session.get(RAGDocument, identity, populate_existing=True) is not None
