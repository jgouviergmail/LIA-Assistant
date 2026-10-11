"""Native replacement swaps rows atomically and retains old bytes through commit uncertainty."""

import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import select, text

from src.core.config import settings
from src.domains.rag_spaces.drive_ingest import create_pending_document
from src.domains.rag_spaces.models import RAGDocument, RAGDriveSource, RAGSpace
from src.domains.rag_spaces.repository import RAGDocumentRepository
from src.domains.rag_spaces.source_worker_lease import (
    SourceLeaseLost,
    SourceWorkerLease,
    source_worker_scope,
)
from src.domains.rag_spaces.storage_paths import stored_file_path

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "ack", ["known", "failed", "lost", "cancelled", "insert_failed", "active_job"]
)
async def test_native_replacement_keeps_old_version_until_atomic_sql_ack(
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
        sync_status="syncing",
        worker_id=token,
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
        drive_file_id="remote",
        filename="old.txt",
        original_filename="old.txt",
        file_size=3,
        content_type="text/plain",
        status="ready",
    )
    async_session.add(document)
    await async_session.flush()
    old_id = document.id
    await async_session.commit()
    monkeypatch.setattr(settings, "rag_spaces_storage_path", str(tmp_path))
    old_file = stored_file_path(owner, space_id, "old.txt")
    old_file.parent.mkdir(parents=True)
    old_file.write_bytes(b"old")
    original = async_session.commit

    async def acknowledgement():
        assert old_file.read_bytes() == b"old"
        if ack == "failed":
            raise OSError("controlled SQL failure")
        await original()
        if ack == "lost":
            raise OSError("controlled acknowledgement loss")
        if ack == "cancelled":
            raise asyncio.CancelledError()

    monkeypatch.setattr(async_session, "commit", acknowledgement)
    if ack == "insert_failed":

        async def failed_create(self, data):
            raise OSError("controlled insertion failure")

        monkeypatch.setattr(RAGDocumentRepository, "create", failed_create)
    elif ack == "active_job":
        await async_session.execute(
            text("UPDATE rag_documents SET status = 'processing' WHERE id = :id"),
            {"id": str(old_id)},
        )
    scope = SourceWorkerLease(
        kind="drive", source_id=source_id, space_id=space_id, actor_id=owner, worker_id=token
    )
    with source_worker_scope(scope):
        if ack == "known":
            created = await create_pending_document(
                async_session,
                space_id=space_id,
                user_id=owner,
                content=b"new",
                extension=".txt",
                original_name="new.txt",
                content_type="text/plain",
                source_fields={"drive_source_id": source_id, "drive_file_id": "remote"},
                replaces=document,
            )
            assert created["document_id"] != old_id
        else:
            with pytest.raises((OSError, asyncio.CancelledError, SourceLeaseLost)):
                await create_pending_document(
                    async_session,
                    space_id=space_id,
                    user_id=owner,
                    content=b"new",
                    extension=".txt",
                    original_name="new.txt",
                    content_type="text/plain",
                    source_fields={"drive_source_id": source_id, "drive_file_id": "remote"},
                    replaces=document,
                )
            await async_session.rollback()
    rows = list(
        (
            await async_session.scalars(select(RAGDocument).where(RAGDocument.space_id == space_id))
        ).all()
    )
    assert len(rows) == 1
    assert (rows[0].id == old_id) is (ack in {"failed", "insert_failed", "active_job"})
    assert old_file.exists() is (ack != "known")
    if ack in {"known", "lost", "cancelled"}:
        assert stored_file_path(owner, space_id, rows[0].filename).read_bytes() == b"new"
    elif ack in {"insert_failed", "active_job"}:
        assert list(old_file.parent.iterdir()) == [old_file]
