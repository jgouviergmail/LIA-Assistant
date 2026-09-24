"""A linked folder is synchronised WITH its sub-folders.

The synchronisation used to page the root folder alone; it now reads the
tree the walk found, indexes every supported file in it, counts them all,
and persists the folder set the push path routes on.
"""

from __future__ import annotations

import contextlib
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.constants import GOOGLE_DRIVE_FOLDER_MIME
from src.domains.rag_spaces import drive_ingest, drive_sync
from src.domains.rag_spaces.models import RAGDriveSyncStatus
from tests.unit.domains.rag_spaces.drive_fakes import (
    FakeDetachedConnectors,
    FakeDriveClient,
    drive_file,
)

pytestmark = pytest.mark.unit

FOLDER = GOOGLE_DRIVE_FOLDER_MIME


@contextlib.asynccontextmanager
async def _fake_db_context():
    db = AsyncMock()
    db.commit = AsyncMock()
    yield db


async def _run_sync(tmp_path, client: FakeDriveClient) -> tuple[list[dict], list[dict]]:
    """Drive one sync against the fake Drive; returns (source updates, created documents)."""
    space_id, source_id, user_id = uuid4(), uuid4(), uuid4()
    created: list[dict] = []
    updates: list[dict] = []

    def make_doc(payload):
        created.append(payload)
        doc = MagicMock()
        doc.id = uuid4()
        return doc

    async def fake_update(_source, payload):
        updates.append(payload)

    source = MagicMock()
    source.folder_id = "root"
    source_repo = AsyncMock()
    source_repo.get_by_id = AsyncMock(return_value=source)
    source_repo.update = AsyncMock(side_effect=fake_update)

    doc_repo = AsyncMock()
    doc_repo.get_by_drive_file_id = AsyncMock(return_value=None)
    doc_repo.count_for_space = AsyncMock(return_value=0)
    doc_repo.get_drive_file_ids_for_source = AsyncMock(return_value=set())
    doc_repo.create = AsyncMock(side_effect=make_doc)

    connector_service = AsyncMock()
    connector_service.get_connector_credentials = AsyncMock(return_value={"token": "x"})

    settings_mock = MagicMock()
    settings_mock.rag_spaces_storage_path = str(tmp_path)
    settings_mock.rag_spaces_max_docs_per_space = 100
    settings_mock.rag_spaces_max_file_size_mb = 10
    settings_mock.rag_job_lease_ttl_seconds = 60

    async def fake_process(**_kwargs):
        return True

    with (
        patch.object(drive_sync, "get_db_context", _fake_db_context),
        patch.object(drive_sync, "RAGDriveSourceRepository", return_value=source_repo),
        patch.object(drive_sync, "RAGDocumentRepository", return_value=doc_repo),
        patch.object(drive_sync, "RAGJobsRepository", return_value=AsyncMock()),
        patch.object(drive_ingest, "RAGDocumentRepository", return_value=doc_repo),
        patch.object(drive_ingest, "RAGChunkRepository", return_value=AsyncMock()),
        patch.object(
            drive_sync,
            "DetachedConnectorService",
            return_value=FakeDetachedConnectors(connector_service),
        ),
        patch.object(drive_sync, "GoogleDriveClient", return_value=client),
        patch.object(drive_sync, "process_document", side_effect=fake_process),
        patch.object(drive_sync, "settings", settings_mock),
        patch.object(drive_ingest, "settings", settings_mock),
    ):
        await drive_sync.sync_folder_background(space_id, source_id, user_id)
    return updates, created


@pytest.mark.asyncio
async def test_sync_indexes_the_files_of_every_sub_folder(tmp_path) -> None:
    client = FakeDriveClient(
        {
            "root": [drive_file("a"), drive_file("sub", FOLDER), drive_file("v", "video/mp4")],
            "sub": [drive_file("b"), drive_file("deep", FOLDER)],
            "deep": [drive_file("c")],
        }
    )
    updates, created = await _run_sync(tmp_path, client)
    assert sorted(d["drive_file_id"] for d in created) == ["a", "b", "c"]
    final = updates[-1]
    assert final["sync_status"] == RAGDriveSyncStatus.COMPLETED
    # Every supported file of the TREE, the unsupported one excluded.
    assert final["file_count"] == 3
    assert final["synced_file_count"] == 3
    # The folder set the push path routes on, root first.
    assert final["folder_ids"] == ["root", "sub", "deep"]


@pytest.mark.asyncio
async def test_sync_prunes_a_document_whose_file_left_the_tree(tmp_path) -> None:
    client = FakeDriveClient({"root": [drive_file("a")]})
    space_id, source_id, user_id = uuid4(), uuid4(), uuid4()
    removed: list[str] = []

    async def fake_remove(_db, **kwargs):
        removed.append(kwargs["file_id"])
        return True

    source = MagicMock()
    source.folder_id = "root"
    source_repo = AsyncMock()
    source_repo.get_by_id = AsyncMock(return_value=source)
    doc_repo = AsyncMock()
    doc_repo.get_by_drive_file_id = AsyncMock(return_value=None)
    doc_repo.count_for_space = AsyncMock(return_value=0)
    doc_repo.get_drive_file_ids_for_source = AsyncMock(return_value={"a", "gone"})
    doc_repo.create = AsyncMock(return_value=MagicMock(id=uuid4()))
    connector_service = AsyncMock()
    connector_service.get_connector_credentials = AsyncMock(return_value={"token": "x"})
    settings_mock = MagicMock()
    settings_mock.rag_spaces_storage_path = str(tmp_path)
    settings_mock.rag_spaces_max_docs_per_space = 100
    settings_mock.rag_spaces_max_file_size_mb = 10
    settings_mock.rag_job_lease_ttl_seconds = 60

    async def fake_process(**_kwargs):
        return True

    with (
        patch.object(drive_sync, "get_db_context", _fake_db_context),
        patch.object(drive_sync, "RAGDriveSourceRepository", return_value=source_repo),
        patch.object(drive_sync, "RAGDocumentRepository", return_value=doc_repo),
        patch.object(drive_sync, "RAGJobsRepository", return_value=AsyncMock()),
        patch.object(drive_ingest, "RAGDocumentRepository", return_value=doc_repo),
        patch.object(drive_ingest, "RAGChunkRepository", return_value=AsyncMock()),
        patch.object(drive_sync, "remove_drive_document", side_effect=fake_remove),
        patch.object(
            drive_sync,
            "DetachedConnectorService",
            return_value=FakeDetachedConnectors(connector_service),
        ),
        patch.object(drive_sync, "GoogleDriveClient", return_value=client),
        patch.object(drive_sync, "process_document", side_effect=fake_process),
        patch.object(drive_sync, "settings", settings_mock),
        patch.object(drive_ingest, "settings", settings_mock),
    ):
        await drive_sync.sync_folder_background(space_id, source_id, user_id)
    assert removed == ["gone"]


@pytest.mark.asyncio
async def test_unreadable_root_marks_the_source_in_error(tmp_path) -> None:
    client = FakeDriveClient({"root": []}, unreadable={"root"})
    updates, created = await _run_sync(tmp_path, client)
    assert created == []
    assert updates[-1]["sync_status"] == RAGDriveSyncStatus.ERROR
    assert "not accessible" in updates[-1]["error_message"]
