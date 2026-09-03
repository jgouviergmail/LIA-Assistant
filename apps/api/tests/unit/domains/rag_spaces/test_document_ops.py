"""Document operations on a knowledge space (ADR-259): download, archive, move, bulk delete.

The path builder is the only place that turns a row into a file: it refuses a
filename that escapes the space directory. A move updates the row and its
chunks, commits, THEN moves the file — a rename that fails reverts both and is
reported per document, never raised for the batch. The archive names its
members after the original filenames, deduplicated, and lists what was missing
instead of failing silently.
"""

from __future__ import annotations

import os
import uuid
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status

from src.core.config import settings
from src.core.exceptions import BaseAPIException
from src.domains.rag_spaces import document_ops
from src.domains.rag_spaces.models import RAGDocumentSourceType, RAGDocumentStatus
from src.domains.rag_spaces.schemas import RAGDocumentMoveRequest
from src.domains.rag_spaces.service import RAGSpaceService

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the storage root at a temporary directory."""
    monkeypatch.setattr(settings, "rag_spaces_storage_path", str(tmp_path))
    return tmp_path


@pytest.fixture
def user_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def space(user_id: uuid.UUID) -> MagicMock:
    space = MagicMock()
    space.id = uuid.uuid4()
    space.user_id = user_id
    space.name = "Projets"
    space.is_system = False
    return space


@pytest.fixture
def target(user_id: uuid.UUID) -> MagicMock:
    other = MagicMock()
    other.id = uuid.uuid4()
    other.user_id = user_id
    other.name = "Archives"
    other.is_system = False
    return other


@pytest.fixture
def service(space: MagicMock, target: MagicMock) -> RAGSpaceService:
    svc = RAGSpaceService(AsyncMock())
    svc.space_repo = AsyncMock()
    svc.doc_repo = AsyncMock()
    svc.chunk_repo = AsyncMock()

    async def get_by_id(space_id: uuid.UUID, include_inactive: bool = True) -> MagicMock | None:
        return {space.id: space, target.id: target}.get(space_id)

    svc.space_repo.get_by_id.side_effect = get_by_id
    svc.doc_repo.count_for_space.return_value = 0
    return svc


def document(
    space: MagicMock,
    *,
    filename: str = "abc.pdf",
    original: str = "report.pdf",
    source_type: str = RAGDocumentSourceType.UPLOAD,
    doc_status: str = RAGDocumentStatus.READY,
) -> MagicMock:
    doc = MagicMock()
    doc.id = uuid.uuid4()
    doc.space_id = space.id
    doc.user_id = space.user_id
    doc.filename = filename
    doc.original_filename = original
    doc.file_size = 5
    doc.status = doc_status
    doc.source_type = source_type
    return doc


def write_file(storage: Path, doc: MagicMock, content: bytes = b"hello") -> Path:
    path = storage / str(doc.user_id) / str(doc.space_id) / doc.filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def index_documents(service: RAGSpaceService, *docs: MagicMock) -> None:
    by_id = {doc.id: doc for doc in docs}

    async def get_by_id(document_id: uuid.UUID) -> MagicMock | None:
        return by_id.get(document_id)

    service.doc_repo.get_by_id.side_effect = get_by_id


# ---------------------------------------------------------------------------
# Path builder
# ---------------------------------------------------------------------------


def test_document_file_path_builds_the_scoped_path(storage: Path, space: MagicMock) -> None:
    doc = document(space)
    assert (
        document_ops.document_file_path(doc)
        == (storage / str(doc.user_id) / str(doc.space_id) / "abc.pdf").resolve()
    )


def test_document_file_path_refuses_a_filename_escaping_the_space(
    storage: Path, space: MagicMock
) -> None:
    doc = document(space, filename="../../etc/passwd")
    with pytest.raises(RuntimeError, match="integrity"):
        document_ops.document_file_path(doc)


# ---------------------------------------------------------------------------
# Ownership + download
# ---------------------------------------------------------------------------


async def test_owned_document_refuses_a_row_of_another_space(
    service: RAGSpaceService, space: MagicMock, target: MagicMock, user_id: uuid.UUID
) -> None:
    doc = document(target)
    index_documents(service, doc)
    with pytest.raises(BaseAPIException) as exc:
        await document_ops.owned_document(service, space.id, doc.id, user_id)
    assert exc.value.status_code == status.HTTP_404_NOT_FOUND


async def test_download_refuses_when_the_file_is_gone(
    storage: Path, service: RAGSpaceService, space: MagicMock, user_id: uuid.UUID
) -> None:
    doc = document(space)
    index_documents(service, doc)
    with pytest.raises(BaseAPIException) as exc:
        await document_ops.download_document(service, space.id, doc.id, user_id)
    assert exc.value.status_code == status.HTTP_404_NOT_FOUND
    assert exc.value.detail == {"code": "document_file_missing"}


async def test_download_returns_the_path_and_the_row(
    storage: Path, service: RAGSpaceService, space: MagicMock, user_id: uuid.UUID
) -> None:
    doc = document(space)
    expected = write_file(storage, doc)
    index_documents(service, doc)
    path, row = await document_ops.download_document(service, space.id, doc.id, user_id)
    assert path == expected.resolve()
    assert row is doc


# ---------------------------------------------------------------------------
# Archive
# ---------------------------------------------------------------------------


async def test_archive_names_members_after_the_originals_and_lists_the_missing(
    storage: Path, service: RAGSpaceService, space: MagicMock, user_id: uuid.UUID
) -> None:
    first = document(space, filename="a.pdf", original="report.pdf")
    second = document(space, filename="b.pdf", original="report.pdf")
    gone = document(space, filename="c.pdf", original="lost.pdf")
    write_file(storage, first, b"one")
    write_file(storage, second, b"two")
    index_documents(service, first, second, gone)

    path, name = await document_ops.build_archive(
        service, space.id, user_id, [first.id, second.id, gone.id]
    )
    try:
        assert name == "Projets.zip"
        with zipfile.ZipFile(path) as archive:
            assert archive.namelist() == ["report.pdf", "report (2).pdf", "_missing.txt"]
            assert archive.read("report (2).pdf") == b"two"
            assert "lost.pdf" in archive.read("_missing.txt").decode()
    finally:
        os.remove(path)


async def test_archive_refuses_beyond_the_size_ceiling(
    storage: Path,
    service: RAGSpaceService,
    space: MagicMock,
    user_id: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "rag_spaces_archive_max_mb", 1)
    big = document(space)
    big.file_size = 2 * 1024 * 1024
    index_documents(service, big)
    with pytest.raises(BaseAPIException) as exc:
        await document_ops.build_archive(service, space.id, user_id, [big.id])
    assert exc.value.status_code == status.HTTP_413_CONTENT_TOO_LARGE
    assert exc.value.detail == {"code": "archive_too_large", "max_mb": 1}


# ---------------------------------------------------------------------------
# Move
# ---------------------------------------------------------------------------


@pytest.fixture
def no_reindex(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        document_ops, "get_reindex_status", AsyncMock(return_value={"in_progress": False})
    )


async def test_move_refuses_wholesale_during_a_reindex(
    service: RAGSpaceService,
    space: MagicMock,
    target: MagicMock,
    user_id: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        document_ops, "get_reindex_status", AsyncMock(return_value={"in_progress": True})
    )
    request = RAGDocumentMoveRequest(ids=[uuid.uuid4()], target_space_id=target.id)
    with pytest.raises(BaseAPIException) as exc:
        await document_ops.move_documents(service, space.id, user_id, request)
    assert exc.value.status_code == status.HTTP_409_CONFLICT
    assert exc.value.detail == {"code": "reindex_in_progress"}
    service.doc_repo.update.assert_not_called()


async def test_move_refuses_a_system_target(
    no_reindex: None,
    service: RAGSpaceService,
    space: MagicMock,
    target: MagicMock,
    user_id: uuid.UUID,
) -> None:
    target.is_system = True
    request = RAGDocumentMoveRequest(ids=[uuid.uuid4()], target_space_id=target.id)
    with pytest.raises(BaseAPIException) as exc:
        await document_ops.move_documents(service, space.id, user_id, request)
    assert exc.value.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.parametrize(
    ("make", "code"),
    [
        (lambda space, target: document(target), "document_not_found"),
        (
            lambda space, target: document(space, source_type=RAGDocumentSourceType.DRIVE),
            "document_managed_by_drive",
        ),
        (
            lambda space, target: document(space, source_type=RAGDocumentSourceType.MEETING),
            "document_managed_by_meetings",
        ),
        (
            lambda space, target: document(space, doc_status=RAGDocumentStatus.PROCESSING),
            "document_busy",
        ),
    ],
)
async def test_move_skips_with_the_reason(
    no_reindex: None,
    storage: Path,
    service: RAGSpaceService,
    space: MagicMock,
    target: MagicMock,
    user_id: uuid.UUID,
    make,
    code: str,
) -> None:
    doc = make(space, target)
    index_documents(service, doc)
    request = RAGDocumentMoveRequest(ids=[doc.id], target_space_id=target.id)
    result = await document_ops.move_documents(service, space.id, user_id, request)
    assert result.done == []
    assert [(s.id, s.code) for s in result.skipped] == [(doc.id, code)]
    service.doc_repo.update.assert_not_called()


async def test_move_into_the_same_space_is_a_skip(
    no_reindex: None, service: RAGSpaceService, space: MagicMock, user_id: uuid.UUID
) -> None:
    doc = document(space)
    index_documents(service, doc)
    request = RAGDocumentMoveRequest(ids=[doc.id], target_space_id=space.id)
    result = await document_ops.move_documents(service, space.id, user_id, request)
    assert [s.code for s in result.skipped] == ["same_space"]


async def test_move_respects_the_target_room_and_deduplicates_ids(
    no_reindex: None,
    storage: Path,
    service: RAGSpaceService,
    space: MagicMock,
    target: MagicMock,
    user_id: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "rag_spaces_max_docs_per_space", 2)
    service.doc_repo.count_for_space.return_value = 1
    first, second = document(space, filename="a.pdf"), document(space, filename="b.pdf")
    write_file(storage, first)
    write_file(storage, second)
    index_documents(service, first, second)
    request = RAGDocumentMoveRequest(ids=[first.id, first.id, second.id], target_space_id=target.id)
    result = await document_ops.move_documents(service, space.id, user_id, request)
    assert result.done == [first.id]
    assert [(s.id, s.code) for s in result.skipped] == [(second.id, "document_limit_exceeded")]


async def test_move_updates_row_and_chunks_commits_then_moves_the_file(
    no_reindex: None,
    storage: Path,
    service: RAGSpaceService,
    space: MagicMock,
    target: MagicMock,
    user_id: uuid.UUID,
) -> None:
    doc = document(space)
    old_path = write_file(storage, doc, b"payload")
    index_documents(service, doc)
    order: list[str] = []

    async def update(row: MagicMock, values: dict) -> MagicMock:
        row.space_id = values["space_id"]
        order.append("update")
        return row

    async def move_to_space(document_id: uuid.UUID, space_id: uuid.UUID) -> int:
        order.append("chunks")
        return 3

    async def commit() -> None:
        order.append("commit")

    service.doc_repo.update.side_effect = update
    service.chunk_repo.move_to_space.side_effect = move_to_space
    service.db.commit.side_effect = commit
    real_replace = os.replace

    def replace(src: str, dst: str) -> None:
        order.append("file")
        real_replace(src, dst)

    with patch.object(document_ops.os, "replace", replace):
        result = await document_ops.move_documents(
            service,
            space.id,
            user_id,
            RAGDocumentMoveRequest(ids=[doc.id], target_space_id=target.id),
        )

    assert result.done == [doc.id] and result.skipped == []
    assert order == ["update", "chunks", "commit", "file"]
    service.doc_repo.update.assert_awaited_once_with(doc, {"space_id": target.id})
    service.chunk_repo.move_to_space.assert_awaited_once_with(doc.id, target.id)
    assert not old_path.exists()
    new_path = storage / str(user_id) / str(target.id) / doc.filename
    assert new_path.read_bytes() == b"payload"


async def test_move_reverts_row_and_chunks_when_the_rename_fails(
    no_reindex: None,
    storage: Path,
    service: RAGSpaceService,
    space: MagicMock,
    target: MagicMock,
    user_id: uuid.UUID,
) -> None:
    doc = document(space)
    old_path = write_file(storage, doc)
    index_documents(service, doc)

    async def update(row: MagicMock, values: dict) -> MagicMock:
        row.space_id = values["space_id"]
        return row

    service.doc_repo.update.side_effect = update

    with patch.object(document_ops.os, "replace", side_effect=OSError("disk full")):
        result = await document_ops.move_documents(
            service,
            space.id,
            user_id,
            RAGDocumentMoveRequest(ids=[doc.id], target_space_id=target.id),
        )

    assert result.done == []
    assert [(s.id, s.code) for s in result.skipped] == [(doc.id, "document_move_failed")]
    assert service.doc_repo.update.await_args_list[-1].args == (doc, {"space_id": space.id})
    assert service.chunk_repo.move_to_space.await_args_list[-1].args == (doc.id, space.id)
    assert service.db.commit.await_count == 2
    assert old_path.exists()


# ---------------------------------------------------------------------------
# Bulk delete
# ---------------------------------------------------------------------------


async def test_bulk_delete_reports_per_document(
    service: RAGSpaceService, space: MagicMock, user_id: uuid.UUID
) -> None:
    ok, broken = document(space, filename="a.pdf"), document(space, filename="b.pdf")
    missing = uuid.uuid4()
    index_documents(service, ok, broken)

    async def delete_document(space_id: uuid.UUID, document_id: uuid.UUID, uid: uuid.UUID) -> None:
        # The real method refuses a foreign id with 404 and may fail on the disk.
        if document_id == missing:
            document_ops.raise_document_not_found(document_id)
        if document_id == broken.id:
            raise RuntimeError("boom")

    with patch.object(service, "delete_document", AsyncMock(side_effect=delete_document)):
        result = await document_ops.bulk_delete_documents(
            service, space.id, user_id, [ok.id, broken.id, missing, ok.id]
        )

    assert result.done == [ok.id]
    assert [(s.id, s.code) for s in result.skipped] == [
        (broken.id, "delete_failed"),
        (missing, "document_not_found"),
    ]


async def test_archive_leaves_no_temporary_file_when_writing_fails(
    storage: Path,
    service: RAGSpaceService,
    space: MagicMock,
    user_id: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    doc = document(space)
    write_file(storage, doc)
    index_documents(service, doc)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(document_ops.tempfile, "tempdir", str(scratch))

    def broken_write(self, filename, arcname=None, **kwargs):
        raise OSError("disk full")

    with patch.object(document_ops.zipfile.ZipFile, "write", broken_write):
        with pytest.raises(OSError):
            await document_ops.build_archive(service, space.id, user_id, [doc.id])
    assert list(scratch.iterdir()) == []


async def test_move_relocates_a_row_whose_file_is_already_gone(
    no_reindex: None,
    storage: Path,
    service: RAGSpaceService,
    space: MagicMock,
    target: MagicMock,
    user_id: uuid.UUID,
) -> None:
    """The index is what retrieval reads; a lost file must not pin the row to its old space."""
    doc = document(space)
    index_documents(service, doc)

    async def update(row: MagicMock, values: dict) -> MagicMock:
        row.space_id = values["space_id"]
        return row

    service.doc_repo.update.side_effect = update
    result = await document_ops.move_documents(
        service, space.id, user_id, RAGDocumentMoveRequest(ids=[doc.id], target_space_id=target.id)
    )
    assert result.done == [doc.id] and result.skipped == []
    service.doc_repo.update.assert_awaited_once_with(doc, {"space_id": target.id})
    assert doc.space_id == target.id
