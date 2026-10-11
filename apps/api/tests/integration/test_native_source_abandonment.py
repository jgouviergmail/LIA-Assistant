"""Native abandoned work cannot fall through the unscoped legacy re-drive."""

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import select, text

from src.core.config import settings
from src.domains.rag_spaces import reapers
from src.domains.rag_spaces.models import RAGDocument, RAGDriveSource, RAGMailSource, RAGSpace
from src.domains.rag_spaces.native_job_abandonment import stop_abandoned_native_source
from src.domains.rag_spaces.source_worker_lease import SourceWorkerLease, source_worker_scope
from src.domains.rag_spaces.storage_paths import stored_file_path

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("kind", ["drive", "mail"])
@pytest.mark.parametrize(
    "scenario", ["expired", "renewed", "completed", "document_first", "failed_live"]
)
async def test_native_abandoned_work_is_closed_without_external_replay(
    async_session, test_user, monkeypatch, tmp_path, kind, scenario
):
    for flag in (
        "application_tools_enabled",
        "rag_spaces_enabled",
        "rag_spaces_drive_sync_enabled",
        "rag_spaces_mail_sync_enabled",
    ):
        monkeypatch.setattr(settings, flag, True)
    owner = test_user.id
    space = RAGSpace(user_id=owner, name="Destination")
    async_session.add(space)
    await async_session.flush()
    space_id = space.id
    model = RAGDriveSource if kind == "drive" else RAGMailSource
    keys = (
        {"folder_id": "root", "folder_name": "Root"}
        if kind == "drive"
        else {"label_id": "Label_1", "label_name": "Label"}
    )
    source = model(
        user_id=owner,
        space_id=space_id,
        worker_id=f"native-{uuid4()}",
        sync_status="syncing",
        **keys,
    )
    async_session.add(source)
    await async_session.flush()
    source_id = source.id
    reference = "drive_source_id" if kind == "drive" else "mail_source_id"
    document = RAGDocument(
        user_id=owner,
        space_id=space_id,
        filename="retained.txt",
        original_filename="retained.txt",
        file_size=3,
        content_type="text/plain",
        status="pending",
        **{reference: source_id},
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
    if scenario in {"renewed", "failed_live"}:
        await async_session.execute(
            text(
                f"UPDATE {model.__tablename__} SET lease_expires_at = clock_timestamp() + interval '1 minute' WHERE id = :id"
            ),
            {"id": str(source_id)},
        )
    elif scenario == "completed":
        await async_session.execute(
            text(f"UPDATE {model.__tablename__} SET sync_status = 'completed' WHERE id = :id"),
            {"id": str(source_id)},
        )
    await async_session.commit()
    monkeypatch.setattr(settings, "rag_spaces_storage_path", str(tmp_path))
    path = stored_file_path(owner, space_id, "retained.txt")
    path.parent.mkdir(parents=True)
    path.write_bytes(b"old")

    @asynccontextmanager
    async def context():
        yield async_session

    monkeypatch.setattr(reapers, "get_db_context", context)
    drive = AsyncMock()
    mail = AsyncMock()
    embed = AsyncMock()
    monkeypatch.setattr("src.domains.rag_spaces.drive_sync.sync_folder_background", drive)
    monkeypatch.setattr("src.domains.rag_spaces.mail_sync.sync_label_background", mail)
    monkeypatch.setattr("src.domains.rag_spaces.processing.process_document", embed)
    if scenario == "document_first":
        assert await reapers._recover_one(document_id, asyncio.Semaphore(1)) == "skipped"
    elif scenario == "failed_live":
        scope = SourceWorkerLease(kind, source_id, space_id, owner, source.worker_id)
        with source_worker_scope(scope):
            assert (
                await stop_abandoned_native_source(async_session, source, allow_live=True)
                == "failed"
            )
    else:
        recover = reapers._recover_source if kind == "drive" else reapers._recover_mail_source
        assert await recover(source_id, asyncio.Semaphore(1)) == (
            "failed" if scenario == "expired" else "skipped"
        )
    drive.assert_not_awaited()
    mail.assert_not_awaited()
    embed.assert_not_awaited()
    current = await async_session.scalar(
        select(model).where(model.id == source_id).execution_options(populate_existing=True)
    )
    document = await async_session.scalar(
        select(RAGDocument)
        .where(RAGDocument.id == document_id)
        .execution_options(populate_existing=True)
    )
    assert current.sync_status == (
        "error"
        if scenario in {"expired", "failed_live"}
        else "completed" if scenario == "completed" else "syncing"
    )
    assert document.status == ("error" if scenario in {"expired", "failed_live"} else "pending")
    assert path.read_bytes() == b"old"


@pytest.mark.parametrize("scenario", ["expired", "live", "takeover", "missing_lease"])
async def test_expired_native_document_is_not_reembedded_by_the_legacy_reaper(
    async_session, test_user, monkeypatch, scenario
):
    owner = test_user.id
    space = RAGSpace(user_id=owner, name="Destination")
    async_session.add(space)
    await async_session.flush()
    token = f"native-doc-{uuid4().hex}"
    document = RAGDocument(
        user_id=owner,
        space_id=space.id,
        filename="doc.txt",
        original_filename="doc.txt",
        file_size=3,
        content_type="text/plain",
        status="processing",
        worker_id=token,
    )
    async_session.add(document)
    await async_session.flush()
    document_id = document.id
    await async_session.execute(
        text(
            "UPDATE rag_documents SET lease_expires_at = clock_timestamp() - interval '1 second' WHERE id = :id"
        ),
        {"id": str(document_id)},
    )
    if scenario == "live":
        await async_session.execute(
            text(
                "UPDATE rag_documents SET lease_expires_at = clock_timestamp() + interval '1 minute' WHERE id = :id"
            ),
            {"id": str(document_id)},
        )
    elif scenario == "takeover":
        await async_session.execute(
            text("UPDATE rag_documents SET worker_id = 'current-document-worker' WHERE id = :id"),
            {"id": str(document_id)},
        )
    elif scenario == "missing_lease":
        await async_session.execute(
            text("UPDATE rag_documents SET lease_expires_at = NULL WHERE id = :id"),
            {"id": str(document_id)},
        )
    await async_session.commit()

    @asynccontextmanager
    async def context():
        yield async_session

    monkeypatch.setattr(reapers, "get_db_context", context)
    embed = AsyncMock()
    monkeypatch.setattr("src.domains.rag_spaces.processing.process_document", embed)
    expected = "failed" if scenario in {"expired", "missing_lease"} else "skipped"
    assert await reapers._recover_one(document_id, asyncio.Semaphore(1)) == expected
    embed.assert_not_awaited()
    current = await async_session.scalar(
        select(RAGDocument)
        .where(RAGDocument.id == document_id)
        .execution_options(populate_existing=True)
    )
    assert current.status == ("error" if expected == "failed" else "processing")
    if scenario == "takeover":
        assert current.worker_id == "current-document-worker"
