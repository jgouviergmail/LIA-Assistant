"""Drive push → targeted reindex of linked folders (ADR-261, P2).

The changes feed is drained from the channel's token; only files directly
under a linked folder are touched; a trashed or removed file removes its
document; a source already syncing is left alone (locked) and reported; the
channel's token advances only after the feed was drained.
"""

from __future__ import annotations

import contextlib
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.rag_spaces import drive_ingest

pytestmark = pytest.mark.unit


@contextlib.asynccontextmanager
async def _fake_db_context():
    db = AsyncMock()
    db.commit = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock(rowcount=1))
    yield db


def _source(folder_id: str) -> MagicMock:
    source = MagicMock()
    source.id = uuid.uuid4()
    source.space_id = uuid.uuid4()
    source.folder_id = folder_id
    source.synced_file_count = 3
    return source


def _change(file_id: str, parent: str, *, removed: bool = False, trashed: bool = False) -> dict:
    return {
        "fileId": file_id,
        "removed": removed,
        "file": {
            "id": file_id,
            "name": f"{file_id}.txt",
            "mimeType": "text/plain",
            "modifiedTime": "2026-09-03T10:00:00Z",
            "parents": [parent],
            "trashed": trashed,
        },
    }


def _harness(*, sources: list, changes: list[dict], lock: bool = True, channel_token: str = "t0"):
    source_repo = MagicMock()
    source_repo.get_all_for_user = AsyncMock(return_value=sources)
    source_repo.update = AsyncMock()
    connector_service = MagicMock()
    connector_service.get_connector_credentials = AsyncMock(return_value={"token": "x"})
    channel = MagicMock()
    channel.page_token = channel_token
    channel_repo = MagicMock()
    channel_repo.get_for_user = AsyncMock(return_value=channel)
    client = AsyncMock()
    client.list_changes = AsyncMock(return_value={"changes": changes, "newStartPageToken": "t1"})
    client.close = AsyncMock()
    sync_service = MagicMock()
    sync_service.try_acquire_sync_lock = AsyncMock(return_value=lock)
    jobs = MagicMock()
    jobs.heartbeat_source = AsyncMock(return_value=True)
    patches = (
        patch("src.infrastructure.database.session.get_db_context", _fake_db_context),
        patch.object(drive_ingest, "RAGDriveSourceRepository", return_value=source_repo),
        patch("src.domains.connectors.service.ConnectorService", return_value=connector_service),
        patch(
            "src.domains.push_channels.repository.PushChannelRepository", return_value=channel_repo
        ),
        patch(
            "src.domains.connectors.clients.google_drive_client.GoogleDriveClient",
            return_value=client,
        ),
        patch("src.domains.rag_spaces.drive_sync.RAGDriveSyncService", return_value=sync_service),
        patch("src.domains.rag_spaces.jobs_repository.RAGJobsRepository", return_value=jobs),
    )
    return patches, channel, client


async def test_no_linked_folder_touches_nothing() -> None:
    patches, _channel, client = _harness(sources=[], changes=[])
    with contextlib.ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        assert await drive_ingest.reindex_from_push(uuid.uuid4(), "t0") == "no_linked_folder"
    client.list_changes.assert_not_awaited()


async def test_changes_under_a_linked_folder_are_ingested_and_removed_and_the_token_advances() -> (
    None
):
    source = _source("folderA")
    changes = [
        _change("f1", "folderA"),
        _change("f2", "elsewhere"),
        _change("f3", "folderA", trashed=True),
        _change("f4", "folderA", removed=True),
    ]
    patches, channel, _client = _harness(sources=[source], changes=changes)
    ingest = AsyncMock(
        return_value=drive_ingest.IngestResult("queued", {"document_id": uuid.uuid4()})
    )
    remove = AsyncMock(return_value=True)
    process = AsyncMock(return_value=(1, 0))
    with contextlib.ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        stack.enter_context(patch.object(drive_ingest, "ingest_drive_file", ingest))
        stack.enter_context(patch.object(drive_ingest, "remove_drive_document", remove))
        stack.enter_context(patch.object(drive_ingest, "process_queued", process))
        outcome = await drive_ingest.reindex_from_push(uuid.uuid4(), "t0")
    assert outcome == "reindexed"
    assert [c.kwargs["drive_file"]["id"] for c in ingest.await_args_list] == ["f1"]
    assert sorted(c.kwargs["file_id"] for c in remove.await_args_list) == ["f3", "f4"]
    process.assert_awaited_once()
    assert channel.page_token == "t1"


async def test_a_source_already_syncing_is_reported_locked() -> None:
    source = _source("folderA")
    patches, _channel, _client = _harness(
        sources=[source], changes=[_change("f1", "folderA")], lock=False
    )
    ingest = AsyncMock()
    with contextlib.ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        stack.enter_context(patch.object(drive_ingest, "ingest_drive_file", ingest))
        assert await drive_ingest.reindex_from_push(uuid.uuid4(), "t0") == "locked"
    ingest.assert_not_awaited()


async def test_a_failure_releases_the_source_and_is_counted_as_error() -> None:
    source = _source("folderA")
    patches, _channel, _client = _harness(sources=[source], changes=[_change("f1", "folderA")])
    with contextlib.ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        stack.enter_context(
            patch.object(
                drive_ingest, "ingest_drive_file", AsyncMock(side_effect=RuntimeError("io"))
            )
        )
        outcome = await drive_ingest.reindex_from_push(uuid.uuid4(), "t0")
    # The per-source failure is contained: the source is set to ERROR and
    # released, and the sweep outcome says so rather than "nothing linked".
    assert outcome == "error"


def test_supported_drive_file_uses_the_shared_maps() -> None:
    assert drive_ingest.is_supported_drive_file({"mimeType": "text/plain"}) is True
    assert drive_ingest.is_supported_drive_file({"mimeType": "video/mp4"}) is False
