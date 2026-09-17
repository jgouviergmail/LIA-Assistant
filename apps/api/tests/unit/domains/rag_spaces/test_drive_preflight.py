"""What a synchronisation WOULD index, counted by the code that indexes.

A count shown to the person is a claim: exact, or it does not exist
(ADR-185). The preflight walks the same tree the synchronisation walks and
classifies every file with the predicate ``ingest_drive_file`` applies —
unsupported, unchanged, modified, new — under the space's document cap; the
walk's bounds are published with the figures, and a cut walk says so.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.constants import (
    GOOGLE_DRIVE_FOLDER_MIME,
    RAG_DRIVE_MAX_FILES_PER_SYNC,
    RAG_DRIVE_MAX_FOLDERS_PER_WALK,
)
from src.domains.rag_spaces import drive_ingest
from src.domains.rag_spaces.drive_sync import RAGDriveSyncService
from tests.unit.domains.rag_spaces.drive_fakes import FakeDriveClient, drive_file

pytestmark = pytest.mark.unit

FOLDER = GOOGLE_DRIVE_FOLDER_MIME
OLDER = "2026-09-01T00:00:00Z"
NEWER = "2026-09-17T10:00:00Z"


def _existing(modified: str | None) -> MagicMock:
    doc = MagicMock()
    doc.drive_modified_time = (
        datetime.fromisoformat(modified.replace("Z", "+00:00")) if modified else None
    )
    return doc


# ============================================================================
# The predicate, extracted so the preflight and the ingest cannot disagree
# ============================================================================


def test_unchanged_when_the_stored_stamp_is_not_older() -> None:
    assert drive_ingest.is_unchanged(_existing(NEWER), drive_file("a", modifiedTime=NEWER)) is True
    assert drive_ingest.is_unchanged(_existing(NEWER), drive_file("a", modifiedTime=OLDER)) is True


def test_modified_when_drive_is_newer_or_a_stamp_is_missing() -> None:
    assert drive_ingest.is_unchanged(_existing(OLDER), drive_file("a", modifiedTime=NEWER)) is False
    assert drive_ingest.is_unchanged(_existing(None), drive_file("a", modifiedTime=NEWER)) is False
    assert drive_ingest.is_unchanged(_existing(NEWER), {"id": "a"}) is False


# ============================================================================
# The preflight
# ============================================================================


@pytest.fixture
def service() -> RAGDriveSyncService:
    svc = RAGDriveSyncService(AsyncMock())
    svc.space_repo = AsyncMock()
    svc.doc_repo = AsyncMock()
    svc.source_repo = AsyncMock()
    return svc


def _source(space_id: uuid.UUID) -> MagicMock:
    source = MagicMock()
    source.id = uuid.uuid4()
    source.space_id = space_id
    source.folder_id = "root"
    return source


async def _run_preflight(service, client, existing_by_id, *, capacity_used=0, max_docs=100):
    space_id, user_id = uuid.uuid4(), uuid.uuid4()
    source = _source(space_id)
    service.space_repo.get_by_id = AsyncMock(return_value=MagicMock(user_id=user_id))
    service.source_repo.get_by_id_and_space = AsyncMock(return_value=source)
    service.doc_repo.get_by_drive_file_id = AsyncMock(
        side_effect=lambda _space, file_id: existing_by_id.get(file_id)
    )
    service.doc_repo.count_for_space = AsyncMock(return_value=capacity_used)
    settings_mock = MagicMock()
    settings_mock.rag_spaces_drive_sync_enabled = True
    settings_mock.rag_drive_sync_confirm_threshold = 10
    settings_mock.rag_spaces_max_docs_per_space = max_docs
    with (
        patch.object(service, "_get_drive_client", return_value=client),
        patch("src.domains.rag_spaces.drive_sync.settings", settings_mock),
    ):
        return await service.preflight(space_id, source.id, user_id)


@pytest.mark.asyncio
async def test_preflight_classifies_every_file_of_the_tree(service) -> None:
    client = FakeDriveClient(
        {
            "root": [
                drive_file("new1", modifiedTime=NEWER),
                drive_file("same", modifiedTime=OLDER),
                drive_file("video", "video/mp4"),
                drive_file("sub", FOLDER),
            ],
            "sub": [
                drive_file("changed", modifiedTime=NEWER),
                drive_file("new2", modifiedTime=NEWER),
            ],
        }
    )
    existing = {"same": _existing(OLDER), "changed": _existing(OLDER)}
    report = await _run_preflight(service, client, existing)
    assert report.total_files == 5
    assert report.unsupported == 1
    assert report.unchanged == 1
    assert report.modified == 1
    assert report.new == 2
    assert report.to_index == 3
    assert report.over_capacity == 0
    assert report.folders == 2
    assert report.unreadable_folders == 0
    assert report.truncated is False
    assert report.threshold == 10
    assert report.max_files == RAG_DRIVE_MAX_FILES_PER_SYNC
    assert report.max_folders == RAG_DRIVE_MAX_FOLDERS_PER_WALK
    assert report.requires_confirmation is False


@pytest.mark.asyncio
async def test_preflight_requires_confirmation_past_the_threshold(service) -> None:
    client = FakeDriveClient({"root": [drive_file(f"f{i}", modifiedTime=NEWER) for i in range(11)]})
    report = await _run_preflight(service, client, {})
    assert report.to_index == 11
    assert report.requires_confirmation is True


@pytest.mark.asyncio
async def test_preflight_counts_only_what_the_space_can_still_hold(service) -> None:
    client = FakeDriveClient(
        {
            "root": [drive_file("changed", modifiedTime=NEWER)]
            + [drive_file(f"n{i}", modifiedTime=NEWER) for i in range(4)]
        }
    )
    report = await _run_preflight(
        service, client, {"changed": _existing(OLDER)}, capacity_used=98, max_docs=100
    )
    # A modified file replaces its document (no new room needed); of the four
    # new ones only two fit.
    assert report.modified == 1
    assert report.new == 4
    assert report.to_index == 3
    assert report.over_capacity == 2


@pytest.mark.asyncio
async def test_preflight_says_when_the_walk_was_cut(service) -> None:
    client = FakeDriveClient(
        {"root": [drive_file(f"f{i}", modifiedTime=NEWER) for i in range(3)]}, page_size=1
    )
    with patch("src.domains.rag_spaces.drive_sync.RAG_DRIVE_MAX_FILES_PER_SYNC", 2):
        report = await _run_preflight(service, client, {})
    assert report.truncated is True
    assert report.to_index == 2
    assert report.max_files == 2
