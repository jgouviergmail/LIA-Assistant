"""A native repeat sync counts ready data and cannot complete failed indexing."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import select, text

from src.core.config import settings
from src.domains.rag_spaces import drive_sync, source_worker_runtime
from src.domains.rag_spaces.drive_walk import DriveTree
from src.domains.rag_spaces.models import RAGDocument, RAGDriveSource, RAGSpace
from src.domains.rag_spaces.source_worker_lease import SourceWorkerLease
from src.domains.rag_spaces.storage_paths import stored_file_path
from tests.unit.domains.rag_spaces.drive_fakes import FakeDetachedConnectors

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("scenario", ["unchanged_ready", "retry_error", "embedding_failed"])
async def test_native_drive_completion_agrees_with_persisted_document_results(
    async_session, test_user, monkeypatch, tmp_path, scenario
):
    for flag in (
        "application_tools_enabled",
        "rag_spaces_enabled",
        "rag_spaces_drive_sync_enabled",
    ):
        monkeypatch.setattr(settings, flag, True)
    monkeypatch.setattr(settings, "rag_spaces_storage_path", str(tmp_path))
    monkeypatch.setattr("src.domains.shared.consultation_sink._collector_factory", None)
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
    stamp = datetime(2026, 10, 1, tzinfo=UTC)
    if scenario != "embedding_failed":
        async_session.add(
            RAGDocument(
                user_id=owner,
                space_id=space_id,
                drive_source_id=source_id,
                drive_file_id="remote",
                drive_modified_time=stamp,
                filename="old.pdf",
                original_filename="old.pdf",
                content_type="application/pdf",
                file_size=3,
                status="ready" if scenario == "unchanged_ready" else "error",
            )
        )
        path = stored_file_path(owner, space_id, "old.pdf")
        path.parent.mkdir(parents=True)
        path.write_bytes(b"old")
    await async_session.execute(
        text(
            "UPDATE rag_drive_sources SET lease_expires_at = clock_timestamp() + interval '1 minute' WHERE id = :id"
        ),
        {"id": str(source_id)},
    )
    await async_session.commit()

    @asynccontextmanager
    async def database():
        yield async_session

    for module in (drive_sync, source_worker_runtime):
        monkeypatch.setattr(module, "get_db_context", database)
    client = AsyncMock()
    client.get_file_content.return_value = b"new"
    connector = AsyncMock()
    connector.get_connector_credentials.return_value = {"token": "controlled"}
    monkeypatch.setattr(
        drive_sync, "DetachedConnectorService", lambda: FakeDetachedConnectors(connector)
    )
    monkeypatch.setattr(drive_sync, "GoogleDriveClient", lambda *args: client)
    monkeypatch.setattr(
        drive_sync,
        "walk_drive_tree",
        AsyncMock(
            return_value=DriveTree(
                files=[
                    {
                        "id": "remote",
                        "name": "Document",
                        "mimeType": "application/pdf",
                        "modifiedTime": stamp.isoformat(),
                    }
                ],
                folder_ids=["root"],
            )
        ),
    )

    async def processing(**kwargs):
        document = await async_session.get(RAGDocument, kwargs["document_id"])
        document.status = "error" if scenario == "embedding_failed" else "ready"
        await async_session.commit()
        return scenario != "embedding_failed"

    monkeypatch.setattr(drive_sync, "process_document", processing)
    await source_worker_runtime.run_native_source_worker(
        SourceWorkerLease("drive", source_id, space_id, owner, token)
    )
    current = await async_session.scalar(
        select(RAGDriveSource)
        .where(RAGDriveSource.id == source_id)
        .execution_options(populate_existing=True)
    )
    assert current.sync_status == ("error" if scenario == "embedding_failed" else "completed")
    assert current.synced_file_count == int(scenario != "embedding_failed")
    if scenario == "retry_error":
        client.get_file_content.assert_awaited_once()
        documents = list(
            (
                await async_session.scalars(
                    select(RAGDocument).where(RAGDocument.space_id == space_id)
                )
            ).all()
        )
        assert len(documents) == 1 and documents[0].status == "ready"
