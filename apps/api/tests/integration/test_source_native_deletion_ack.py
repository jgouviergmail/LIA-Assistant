"""Native synced-file deletion never removes bytes before a known SQL acknowledgement."""

import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import select, text

from src.core.config import settings
from src.domains.rag_spaces.drive_ingest import discard_document
from src.domains.rag_spaces.models import RAGDocument, RAGDriveSource, RAGSpace
from src.domains.rag_spaces.source_worker_lease import (
    SourceLeaseLost,
    SourceWorkerLease,
    source_worker_scope,
)
from src.domains.rag_spaces.storage_paths import stored_file_path

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("ack", ["known", "failed", "lost", "cancelled", "active_job"])
async def test_native_document_deletion_waits_for_ack_before_file_cleanup(
    async_session, test_user, monkeypatch, tmp_path, ack
):
    for flag in (
        "application_tools_enabled",
        "rag_spaces_enabled",
        "rag_spaces_mail_sync_enabled",
        "rag_spaces_drive_sync_enabled",
    ):
        monkeypatch.setattr(settings, flag, True)
    owner = test_user.id
    space = RAGSpace(user_id=owner, name="Destination")
    async_session.add(space)
    await async_session.flush()
    space_id = space.id
    token = f"native-{uuid4()}"
    source = RAGDriveSource(
        user_id=owner,
        space_id=space_id,
        folder_id="root",
        folder_name="Root",
        worker_id=token,
        sync_status="syncing",
    )
    async_session.add(source)
    await async_session.flush()
    source_id = source.id
    await async_session.execute(
        text(
            "UPDATE rag_drive_sources SET lease_expires_at = clock_timestamp() + interval '1 minute' WHERE id = :id"
        ),
        {"id": str(source_id)},
    )
    document = RAGDocument(
        user_id=owner,
        space_id=space_id,
        drive_source_id=source_id,
        filename="old.txt",
        original_filename="old.txt",
        file_size=3,
        content_type="text/plain",
        status="ready",
    )
    async_session.add(document)
    await async_session.flush()
    document_id = document.id
    await async_session.commit()
    monkeypatch.setattr(settings, "rag_spaces_storage_path", str(tmp_path))
    file = stored_file_path(owner, space_id, "old.txt")
    file.parent.mkdir(parents=True)
    file.write_bytes(b"old")
    original = async_session.commit

    async def acknowledgement():
        assert file.read_bytes() == b"old", "Old bytes must exist before SQL acknowledgement"
        if ack == "failed":
            raise OSError("controlled SQL failure")
        await original()
        if ack == "lost":
            raise OSError("controlled acknowledgement loss")
        if ack == "cancelled":
            raise asyncio.CancelledError()

    monkeypatch.setattr(async_session, "commit", acknowledgement)
    if ack == "active_job":
        await async_session.execute(
            text("UPDATE rag_documents SET status = 'processing' WHERE id = :id"),
            {"id": str(document_id)},
        )
    scope = SourceWorkerLease(
        kind="drive", source_id=source_id, space_id=space_id, actor_id=owner, worker_id=token
    )
    with source_worker_scope(scope):
        if ack == "known":
            await discard_document(async_session, document, user_id=owner, space_id=space_id)
        else:
            with pytest.raises((OSError, asyncio.CancelledError, SourceLeaseLost)):
                await discard_document(async_session, document, user_id=owner, space_id=space_id)
            await async_session.rollback()
    assert file.exists() is (ack != "known")
    present = await async_session.scalar(
        select(RAGDocument.id).where(RAGDocument.id == document_id)
    )
    assert (present is not None) is (ack in {"failed", "active_job"})
