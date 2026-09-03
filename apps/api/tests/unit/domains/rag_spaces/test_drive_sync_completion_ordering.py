"""Drive sync marks the source COMPLETED only after documents are processed (F001).

Characterization + regression test for the "premature COMPLETED" defect: the
background sync used to fire document processing (embedding) fire-and-forget and
immediately set the source ``sync_status = completed``, so the source claimed
completion while its documents were still ``processing``. Since
``sync_folder_background`` is itself a detached background coroutine, it can
await the processing before declaring completion without blocking anything
user-facing. This test pins the ordering: every ``process_document`` call must
complete before the ``completed`` status is written.
"""

from __future__ import annotations

import contextlib
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.constants import RAG_DRIVE_REGULAR_FILE_MAP
from src.domains.rag_spaces import drive_ingest, drive_sync
from tests.support.structlog_capture import fresh_module_logger


@pytest.fixture(autouse=True)
def _fresh_module_logger():
    """Keep `capture_logs` reliable under xdist — see `tests/support`."""
    yield from fresh_module_logger(drive_sync)


@contextlib.asynccontextmanager
async def _fake_db_context():
    db = AsyncMock()
    db.commit = AsyncMock()
    # Durable-job lease heartbeat (F001) runs raw db.execute; give it an int
    # rowcount so RAGJobsRepository.heartbeat_source resolves cleanly.
    db.execute = AsyncMock(return_value=MagicMock(rowcount=1))
    yield db


async def test_source_completed_only_after_all_documents_processed(tmp_path):
    """The 'completed' status must be written strictly after every process_document."""
    events: list[tuple[str, object]] = []
    space_id, source_id, user_id = uuid4(), uuid4(), uuid4()

    # A supported regular-file mime so the download path runs.
    mime = next(iter(RAG_DRIVE_REGULAR_FILE_MAP))
    files = [
        {"id": "f1", "mimeType": mime, "name": "a.bin", "modifiedTime": None},
        {"id": "f2", "mimeType": mime, "name": "b.bin", "modifiedTime": None},
    ]

    async def fake_process(**kwargs):
        events.append(("processed", kwargs["document_id"]))
        return True

    source = MagicMock()
    source_repo = AsyncMock()
    source_repo.get_by_id = AsyncMock(return_value=source)

    async def fake_update(_source, updates):
        if updates.get("sync_status"):
            events.append(("status", updates["sync_status"]))

    source_repo.update = AsyncMock(side_effect=fake_update)

    doc_repo = AsyncMock()
    doc_repo.get_by_drive_file_id = AsyncMock(return_value=None)
    doc_repo.count_for_space = AsyncMock(return_value=0)
    doc_repo.get_drive_file_ids_for_source = AsyncMock(return_value=set())

    def make_doc(_payload):
        doc = MagicMock()
        doc.id = uuid4()
        return doc

    doc_repo.create = AsyncMock(side_effect=make_doc)

    client = AsyncMock()
    client.list_files = AsyncMock(return_value={"files": files, "nextPageToken": None})
    client.get_file_content = AsyncMock(return_value=b"payload-bytes")
    client.close = AsyncMock()

    connector_service = AsyncMock()
    connector_service.get_connector_credentials = AsyncMock(return_value={"token": "x"})

    settings_mock = MagicMock()
    settings_mock.rag_spaces_storage_path = str(tmp_path)
    settings_mock.rag_spaces_max_docs_per_space = 100
    settings_mock.rag_spaces_max_file_size_mb = 10

    with (
        patch.object(drive_sync, "get_db_context", _fake_db_context),
        patch.object(drive_sync, "RAGDriveSourceRepository", return_value=source_repo),
        patch.object(drive_sync, "RAGDocumentRepository", return_value=doc_repo),
        patch.object(drive_ingest, "RAGDocumentRepository", return_value=doc_repo),
        patch.object(drive_ingest, "RAGChunkRepository", return_value=AsyncMock()),
        patch.object(drive_sync, "ConnectorService", return_value=connector_service),
        patch.object(drive_sync, "GoogleDriveClient", return_value=client),
        patch.object(drive_sync, "process_document", side_effect=fake_process),
        patch.object(drive_sync, "settings", settings_mock),
        patch.object(drive_ingest, "settings", settings_mock),
    ):
        await drive_sync.sync_folder_background(space_id, source_id, user_id)

    processed = [i for i, e in enumerate(events) if e[0] == "processed"]
    completed = [
        i for i, e in enumerate(events) if e == ("status", drive_sync.RAGDriveSyncStatus.COMPLETED)
    ]

    assert len(processed) == 2, f"both documents must be processed, events={events}"
    assert completed, f"a completed status must be written, events={events}"
    assert all(
        p < completed[0] for p in processed
    ), f"'completed' was written before processing finished (F001), events={events}"


def _files_metric(result: str) -> float:
    """Current value of the rag_drive_sync_files_total{result=...} counter."""
    return drive_sync.rag_drive_sync_files_total.labels(result=result)._value.get()


async def _run_sync(tmp_path, files: list[dict], fake_process) -> tuple[list[dict], list[dict]]:
    """Drive one sync_folder_background run against a fully mocked harness.

    Returns ``(source updates, created document payloads)`` so tests can assert
    both the persisted counters and the created documents' initial status.
    """
    space_id, source_id, user_id = uuid4(), uuid4(), uuid4()

    created_payloads: list[dict] = []

    def make_doc(payload):
        created_payloads.append(payload)
        doc = MagicMock()
        doc.id = uuid4()
        return doc

    updates: list[dict] = []

    async def fake_update(_source, payload):
        updates.append(payload)

    source_repo = AsyncMock()
    source_repo.get_by_id = AsyncMock(return_value=MagicMock())
    source_repo.update = AsyncMock(side_effect=fake_update)

    doc_repo = AsyncMock()
    doc_repo.get_by_drive_file_id = AsyncMock(return_value=None)
    doc_repo.count_for_space = AsyncMock(return_value=0)
    doc_repo.get_drive_file_ids_for_source = AsyncMock(return_value=set())
    doc_repo.create = AsyncMock(side_effect=make_doc)

    client = AsyncMock()
    client.list_files = AsyncMock(return_value={"files": files, "nextPageToken": None})
    client.get_file_content = AsyncMock(return_value=b"payload-bytes")
    client.close = AsyncMock()

    connector_service = AsyncMock()
    connector_service.get_connector_credentials = AsyncMock(return_value={"token": "x"})

    settings_mock = MagicMock()
    settings_mock.rag_spaces_storage_path = str(tmp_path)
    settings_mock.rag_spaces_max_docs_per_space = 100
    settings_mock.rag_spaces_max_file_size_mb = 10

    with (
        patch.object(drive_sync, "get_db_context", _fake_db_context),
        patch.object(drive_sync, "RAGDriveSourceRepository", return_value=source_repo),
        patch.object(drive_sync, "RAGDocumentRepository", return_value=doc_repo),
        patch.object(drive_ingest, "RAGDocumentRepository", return_value=doc_repo),
        patch.object(drive_ingest, "RAGChunkRepository", return_value=AsyncMock()),
        patch.object(drive_sync, "ConnectorService", return_value=connector_service),
        patch.object(drive_sync, "GoogleDriveClient", return_value=client),
        patch.object(drive_sync, "process_document", side_effect=fake_process),
        patch.object(drive_sync, "settings", settings_mock),
        patch.object(drive_ingest, "settings", settings_mock),
    ):
        await drive_sync.sync_folder_background(space_id, source_id, user_id)

    return updates, created_payloads


async def test_failed_document_is_not_counted_as_synced(tmp_path):
    """Base, final log AND Prometheus must agree: 2 downloaded, 1 ok, 1 failed.

    process_document swallows its own exceptions and returns False on failure —
    so the sync must read that return value, not a gather exception, or it would
    mark a failed embed as a success (audit F001 follow-up). The telemetry point
    moved after the processing oracle (audit F053): the result="synced" series
    and the ``synced`` log field must equal the persisted synced_file_count, and
    the failed embed must surface in both the log and the failed series.
    """
    import structlog.testing

    calls = {"n": 0}

    # First processed doc succeeds, second fails (returns False).
    async def fake_process(**_kwargs):
        calls["n"] += 1
        return calls["n"] == 1

    synced_before = _files_metric("synced")
    failed_before = _files_metric("failed")

    mime = next(iter(RAG_DRIVE_REGULAR_FILE_MAP))
    files = [
        {"id": "ok", "mimeType": mime, "name": "ok.bin", "modifiedTime": None},
        {"id": "bad", "mimeType": mime, "name": "bad.bin", "modifiedTime": None},
    ]
    with structlog.testing.capture_logs() as logs:
        updates, _created = await _run_sync(tmp_path, files, fake_process)

    completed = [
        u for u in updates if u.get("sync_status") == drive_sync.RAGDriveSyncStatus.COMPLETED
    ]
    assert completed, f"a completed update must exist, updates={updates}"
    # 2 downloaded, 1 embed failed → only 1 truly synced (persisted counter).
    assert completed[-1]["synced_file_count"] == 1

    # Final log publishes the SAME counters as the base (F053).
    final = [e for e in logs if e["event"] == "rag_drive_sync_complete"]
    assert final, f"rag_drive_sync_complete must be logged, logs={logs}"
    assert final[-1]["downloaded"] == 2
    assert final[-1]["synced"] == 1
    assert final[-1]["failed_embedding"] == 1
    assert final[-1]["failed_download"] == 0

    # Prometheus deltas match: exactly one synced, exactly one failed.
    assert _files_metric("synced") - synced_before == 1
    assert _files_metric("failed") - failed_before == 1


async def test_gather_exception_counts_as_failed_not_synced(tmp_path):
    """A processing coroutine that *raises* must count as failed, never synced."""
    calls = {"n": 0}

    async def fake_process(**_kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("embedding blew up")
        return True

    synced_before = _files_metric("synced")
    failed_before = _files_metric("failed")

    mime = next(iter(RAG_DRIVE_REGULAR_FILE_MAP))
    files = [
        {"id": "ok", "mimeType": mime, "name": "ok.bin", "modifiedTime": None},
        {"id": "boom", "mimeType": mime, "name": "boom.bin", "modifiedTime": None},
    ]
    updates, _created = await _run_sync(tmp_path, files, fake_process)

    completed = [
        u for u in updates if u.get("sync_status") == drive_sync.RAGDriveSyncStatus.COMPLETED
    ]
    assert completed and completed[-1]["synced_file_count"] == 1
    assert _files_metric("synced") - synced_before == 1
    assert _files_metric("failed") - failed_before == 1


async def test_zero_documents_completes_with_zero_counters(tmp_path):
    """An empty folder completes cleanly: zero counters, zero metric deltas."""
    import structlog.testing

    async def fake_process(**_kwargs):  # pragma: no cover - never called
        raise AssertionError("no document should be processed")

    synced_before = _files_metric("synced")
    failed_before = _files_metric("failed")

    with structlog.testing.capture_logs() as logs:
        updates, _created = await _run_sync(tmp_path, [], fake_process)

    completed = [
        u for u in updates if u.get("sync_status") == drive_sync.RAGDriveSyncStatus.COMPLETED
    ]
    assert completed and completed[-1]["synced_file_count"] == 0

    final = [e for e in logs if e["event"] == "rag_drive_sync_complete"]
    assert final and final[-1]["synced"] == 0 and final[-1]["downloaded"] == 0
    assert _files_metric("synced") == synced_before
    assert _files_metric("failed") == failed_before


async def test_drive_documents_are_created_pending_not_processing(tmp_path):
    """Drive documents must be born PENDING (audit F001 residual).

    A PROCESSING row without a lease is indistinguishable from a crashed job:
    the reaper would immediately requeue it while the live sync still owns it
    (double owner, duplicated chunks). PENDING routes Drive documents through
    the same atomic claim as uploads.
    """

    async def fake_process(**_kwargs):
        return True

    mime = next(iter(RAG_DRIVE_REGULAR_FILE_MAP))
    files = [{"id": "f1", "mimeType": mime, "name": "a.bin", "modifiedTime": None}]
    _updates, created = await _run_sync(tmp_path, files, fake_process)

    assert created, "the sync must create one document"
    from src.domains.rag_spaces.models import RAGDocumentStatus

    assert created[0]["status"] == RAGDocumentStatus.PENDING


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
