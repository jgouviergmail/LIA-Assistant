"""A stale native source worker cannot write a source, create bytes or remove old bytes."""

from uuid import uuid4

import pytest
from sqlalchemy import select, text

from src.core.config import settings
from src.domains.rag_spaces.drive_ingest import create_pending_document, discard_document
from src.domains.rag_spaces.models import RAGDocument, RAGDriveSource, RAGMailSource, RAGSpace
from src.domains.rag_spaces.repository import RAGDriveSourceRepository, RAGMailSourceRepository
from src.domains.rag_spaces.source_worker_lease import (
    SourceLeaseLost,
    SourceWorkerLease,
    source_worker_scope,
)
from src.domains.rag_spaces.storage_paths import stored_file_path

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("kind", ["drive", "mail"])
@pytest.mark.parametrize("effect", ["complete", "create", "delete", "expires_after_write"])
async def test_stale_worker_cannot_apply_later_source_or_document_effect(
    async_session, test_user, monkeypatch, tmp_path, kind, effect
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
    model = RAGDriveSource if kind == "drive" else RAGMailSource
    token = f"native-{uuid4()}"
    keys = (
        {"folder_id": "root", "folder_name": "Root"}
        if kind == "drive"
        else {"label_id": "Label_1", "label_name": "Label"}
    )
    source = model(user_id=owner, space_id=space_id, worker_id=token, sync_status="syncing", **keys)
    async_session.add(source)
    await async_session.flush()
    source_id = source.id
    reference = {"drive_source_id" if kind == "drive" else "mail_source_id": source_id}
    document = RAGDocument(
        user_id=owner,
        space_id=space_id,
        filename="old.txt",
        original_filename="old.txt",
        content_type="text/plain",
        file_size=3,
        **reference,
    )
    async_session.add(document)
    await async_session.flush()
    document_id = document.id
    await async_session.execute(
        text(
            f"UPDATE {model.__tablename__} SET lease_expires_at = clock_timestamp() - interval '1 second' WHERE id = :id"
        ),
        {"id": str(source_id)},
    )
    await async_session.commit()
    monkeypatch.setattr(settings, "rag_spaces_storage_path", str(tmp_path))
    file = stored_file_path(owner, space_id, "old.txt")
    file.parent.mkdir(parents=True)
    file.write_bytes(b"old")
    scope = SourceWorkerLease(
        kind=kind, source_id=source_id, space_id=space_id, actor_id=owner, worker_id=token
    )
    if effect == "expires_after_write":
        await async_session.execute(
            text(
                f"UPDATE {model.__tablename__} SET lease_expires_at = clock_timestamp() + interval '1 minute' WHERE id = :id"
            ),
            {"id": str(source_id)},
        )
        await async_session.commit()
        from src.domains.rag_spaces import drive_ingest

        original_io = drive_ingest.asyncio.to_thread

        async def expired_after_io(function, *args, **kwargs):
            result = await original_io(function, *args, **kwargs)
            if function is drive_ingest._write_stored_file:
                await async_session.execute(
                    text(
                        f"UPDATE {model.__tablename__} SET lease_expires_at = clock_timestamp() - interval '1 second' WHERE id = :id"
                    ),
                    {"id": str(source_id)},
                )
            return result

        monkeypatch.setattr(drive_ingest.asyncio, "to_thread", expired_after_io)
    with source_worker_scope(scope), pytest.raises(SourceLeaseLost):
        if effect == "complete":
            repository = (
                RAGDriveSourceRepository(async_session)
                if kind == "drive"
                else RAGMailSourceRepository(async_session)
            )
            await repository.update(source, {"sync_status": "completed"})
        elif effect in {"create", "expires_after_write"}:
            await create_pending_document(
                async_session,
                space_id=space_id,
                user_id=owner,
                content=b"new",
                extension=".txt",
                original_name="new.txt",
                content_type="text/plain",
                source_fields=reference,
            )
        else:
            await discard_document(async_session, document, user_id=owner, space_id=space_id)
    await async_session.rollback()
    assert file.read_bytes() == b"old" and list(file.parent.iterdir()) == [file]
    assert (
        await async_session.scalar(select(RAGDocument.id).where(RAGDocument.id == document_id))
        == document_id
    )
    assert (
        await async_session.scalar(select(model.sync_status).where(model.id == source_id))
        == "syncing"
    )
