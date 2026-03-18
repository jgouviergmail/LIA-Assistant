"""Tests for RAGDriveSyncService business logic.

Covers link/unlink operations, sync lock acquisition, and MIME type
mapping constants used by the Drive sync pipeline.

Phase: evolution — RAG Spaces (Google Drive Integration)
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status

from src.core.constants import (
    RAG_DRIVE_GOOGLE_EXPORT_MAP,
    RAG_DRIVE_REGULAR_FILE_MAP,
)
from src.core.exceptions import BaseAPIException
from src.domains.rag_spaces.drive_sync import RAGDriveSyncService
from src.domains.rag_spaces.models import RAGDriveSyncStatus

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_db():
    """Create a mock async database session."""
    return AsyncMock()


@pytest.fixture
def service(mock_db):
    """Create service with mocked repository dependencies."""
    svc = RAGDriveSyncService(mock_db)
    svc.space_repo = AsyncMock()
    svc.doc_repo = AsyncMock()
    svc.source_repo = AsyncMock()
    svc.chunk_repo = AsyncMock()
    return svc


@pytest.fixture
def user_id():
    """Return a stable user UUID for tests."""
    return uuid.uuid4()


@pytest.fixture
def space_id():
    """Return a stable space UUID for tests."""
    return uuid.uuid4()


@pytest.fixture
def sample_space(user_id, space_id):
    """Create a mock RAGSpace instance."""
    space = MagicMock()
    space.id = space_id
    space.user_id = user_id
    space.name = "Test Space"
    space.is_active = True
    return space


@pytest.fixture
def sample_source(user_id, space_id):
    """Create a mock RAGDriveSource instance."""
    source = MagicMock()
    source.id = uuid.uuid4()
    source.space_id = space_id
    source.user_id = user_id
    source.folder_id = "drive_folder_abc123"
    source.folder_name = "My Documents"
    source.sync_status = RAGDriveSyncStatus.IDLE
    return source


# ============================================================================
# TestRAGDriveSyncServiceLinkFolder
# ============================================================================


@pytest.mark.unit
class TestRAGDriveSyncServiceLinkFolder:
    """Tests for linking a Google Drive folder to a RAG space."""

    @pytest.mark.asyncio
    @patch("src.domains.rag_spaces.drive_sync.settings")
    async def test_link_folder_success(
        self, mock_settings, service, user_id, space_id, sample_space
    ) -> None:
        """Should create a drive source when all validations pass."""
        mock_settings.rag_spaces_drive_sync_enabled = True
        mock_settings.rag_drive_max_sources_per_space = 5

        service.space_repo.get_by_id = AsyncMock(return_value=sample_space)
        service.source_repo.count_for_space = AsyncMock(return_value=1)
        service.source_repo.exists_for_space_and_folder = AsyncMock(return_value=False)

        created_source = MagicMock()
        created_source.id = uuid.uuid4()
        service.source_repo.create = AsyncMock(return_value=created_source)

        # Mock _get_drive_client to return a client that verifies folder
        mock_client = AsyncMock()
        mock_client.get_file_metadata = AsyncMock(
            return_value={"mimeType": "application/vnd.google-apps.folder"}
        )
        mock_client.close = AsyncMock()

        with patch.object(service, "_get_drive_client", return_value=mock_client):
            result = await service.link_folder(
                space_id, user_id, "drive_folder_abc123", "My Documents"
            )

        assert result == created_source
        service.source_repo.create.assert_awaited_once()
        create_data = service.source_repo.create.call_args[0][0]
        assert create_data["space_id"] == space_id
        assert create_data["user_id"] == user_id
        assert create_data["folder_id"] == "drive_folder_abc123"
        assert create_data["folder_name"] == "My Documents"
        assert create_data["sync_status"] == RAGDriveSyncStatus.IDLE
        service.db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("src.domains.rag_spaces.drive_sync.settings")
    async def test_link_folder_limit_exceeded(
        self, mock_settings, service, user_id, space_id, sample_space
    ) -> None:
        """Should raise 400 when source count has reached the maximum."""
        mock_settings.rag_spaces_drive_sync_enabled = True
        mock_settings.rag_drive_max_sources_per_space = 3

        service.space_repo.get_by_id = AsyncMock(return_value=sample_space)
        service.source_repo.count_for_space = AsyncMock(return_value=3)

        with pytest.raises(BaseAPIException) as exc_info:
            await service.link_folder(space_id, user_id, "folder_id", "Folder")

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "Maximum number of Drive sources" in exc_info.value.detail

    @pytest.mark.asyncio
    @patch("src.domains.rag_spaces.drive_sync.settings")
    async def test_link_folder_already_linked(
        self, mock_settings, service, user_id, space_id, sample_space
    ) -> None:
        """Should raise 409 when the folder is already linked to the space."""
        mock_settings.rag_spaces_drive_sync_enabled = True
        mock_settings.rag_drive_max_sources_per_space = 5

        service.space_repo.get_by_id = AsyncMock(return_value=sample_space)
        service.source_repo.count_for_space = AsyncMock(return_value=1)
        service.source_repo.exists_for_space_and_folder = AsyncMock(return_value=True)

        with pytest.raises(BaseAPIException) as exc_info:
            await service.link_folder(space_id, user_id, "already_linked_folder", "Folder")

        assert exc_info.value.status_code == status.HTTP_409_CONFLICT
        assert "already linked" in exc_info.value.detail

    @pytest.mark.asyncio
    @patch("src.domains.rag_spaces.drive_sync.settings")
    async def test_link_folder_connector_not_active(
        self, mock_settings, service, user_id, space_id, sample_space
    ) -> None:
        """Should raise 400 when Google Drive connector is not active."""
        mock_settings.rag_spaces_drive_sync_enabled = True
        mock_settings.rag_drive_max_sources_per_space = 5

        service.space_repo.get_by_id = AsyncMock(return_value=sample_space)
        service.source_repo.count_for_space = AsyncMock(return_value=0)
        service.source_repo.exists_for_space_and_folder = AsyncMock(return_value=False)

        # _get_drive_client raises when connector not active
        with patch.object(
            service,
            "_get_drive_client",
            side_effect=BaseAPIException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google Drive connector is not active",
                log_event="rag_drive_connector_not_active",
            ),
        ):
            with pytest.raises(BaseAPIException) as exc_info:
                await service.link_folder(space_id, user_id, "folder_id", "Folder")

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "connector" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    @patch("src.domains.rag_spaces.drive_sync.settings")
    async def test_link_folder_feature_disabled(
        self, mock_settings, service, user_id, space_id
    ) -> None:
        """Should raise 403 when Drive sync feature is disabled."""
        mock_settings.rag_spaces_drive_sync_enabled = False

        with pytest.raises(BaseAPIException) as exc_info:
            await service.link_folder(space_id, user_id, "folder_id", "Folder")

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert "disabled" in exc_info.value.detail.lower()


# ============================================================================
# TestRAGDriveSyncServiceUnlinkFolder
# ============================================================================


@pytest.mark.unit
class TestRAGDriveSyncServiceUnlinkFolder:
    """Tests for unlinking a Drive folder from a RAG space."""

    @pytest.mark.asyncio
    async def test_unlink_folder_keep_documents(
        self, service, user_id, space_id, sample_space, sample_source
    ) -> None:
        """Should set drive_source_id to NULL when delete_documents is False."""
        service.space_repo.get_by_id = AsyncMock(return_value=sample_space)
        service.source_repo.get_by_id_and_space = AsyncMock(return_value=sample_source)
        service.source_repo.delete = AsyncMock()

        await service.unlink_folder(space_id, sample_source.id, user_id, delete_documents=False)

        # Should execute SQL to set drive_source_id = NULL
        service.db.execute.assert_awaited_once()
        call_args = service.db.execute.call_args
        sql_text = str(call_args[0][0].text)
        assert "drive_source_id = NULL" in sql_text

        # Should delete the source record
        service.source_repo.delete.assert_awaited_once_with(sample_source)
        service.db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("src.domains.rag_spaces.drive_sync.settings")
    @patch("src.domains.rag_spaces.drive_sync.Path")
    async def test_unlink_folder_delete_documents(
        self,
        mock_path_cls,
        mock_settings,
        service,
        user_id,
        space_id,
        sample_space,
        sample_source,
    ) -> None:
        """Should delete documents, chunks, and physical files when requested."""
        mock_settings.rag_spaces_storage_path = "/tmp/rag_storage"

        service.space_repo.get_by_id = AsyncMock(return_value=sample_space)
        service.source_repo.get_by_id_and_space = AsyncMock(return_value=sample_source)
        service.source_repo.delete = AsyncMock()

        # Create mock documents
        doc1 = MagicMock()
        doc1.id = uuid.uuid4()
        doc1.filename = "file1.pdf"
        doc2 = MagicMock()
        doc2.id = uuid.uuid4()
        doc2.filename = "file2.txt"
        service.doc_repo.get_drive_documents_for_source = AsyncMock(return_value=[doc1, doc2])
        service.chunk_repo.delete_by_document = AsyncMock()
        service.doc_repo.delete = AsyncMock()

        # Mock Path for file deletion
        mock_file_path = MagicMock()
        mock_file_path.exists.return_value = True
        mock_file_path.unlink = MagicMock()
        mock_path_cls.return_value.__truediv__ = MagicMock(return_value=mock_file_path)
        mock_file_path.__truediv__ = MagicMock(return_value=mock_file_path)

        await service.unlink_folder(space_id, sample_source.id, user_id, delete_documents=True)

        # Should delete chunks for each document
        assert service.chunk_repo.delete_by_document.await_count == 2
        service.chunk_repo.delete_by_document.assert_any_await(doc1.id)
        service.chunk_repo.delete_by_document.assert_any_await(doc2.id)

        # Should delete document records
        assert service.doc_repo.delete.await_count == 2
        service.doc_repo.delete.assert_any_await(doc1)
        service.doc_repo.delete.assert_any_await(doc2)

        # Should delete the source record
        service.source_repo.delete.assert_awaited_once_with(sample_source)
        service.db.commit.assert_awaited_once()


# ============================================================================
# TestRAGDriveSyncServiceTryAcquireSyncLock
# ============================================================================


@pytest.mark.unit
class TestRAGDriveSyncServiceTryAcquireSyncLock:
    """Tests for the atomic sync lock acquisition mechanism."""

    @pytest.mark.asyncio
    async def test_acquire_lock_success(self, service) -> None:
        """Should return True when the UPDATE affects one row (lock acquired)."""
        mock_result = MagicMock()
        mock_result.rowcount = 1
        service.db.execute = AsyncMock(return_value=mock_result)

        source_id = uuid.uuid4()
        result = await service.try_acquire_sync_lock(source_id)

        assert result is True
        service.db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_acquire_lock_already_syncing(self, service) -> None:
        """Should return False when no row is updated (already syncing)."""
        mock_result = MagicMock()
        mock_result.rowcount = 0
        service.db.execute = AsyncMock(return_value=mock_result)

        source_id = uuid.uuid4()
        result = await service.try_acquire_sync_lock(source_id)

        assert result is False
        service.db.commit.assert_awaited_once()


# ============================================================================
# TestMimeTypeMapping
# ============================================================================


@pytest.mark.unit
class TestMimeTypeMapping:
    """Tests for the MIME type mapping constants used by Drive sync."""

    def test_google_export_map_contains_3_entries(self) -> None:
        """RAG_DRIVE_GOOGLE_EXPORT_MAP should contain exactly 3 Google native types."""
        assert len(RAG_DRIVE_GOOGLE_EXPORT_MAP) == 3

    def test_regular_file_map_covers_all_formats(self) -> None:
        """RAG_DRIVE_REGULAR_FILE_MAP should contain exactly 16 entries."""
        assert len(RAG_DRIVE_REGULAR_FILE_MAP) == 16

    @pytest.mark.parametrize(
        "google_mime",
        [
            "application/vnd.google-apps.document",
            "application/vnd.google-apps.spreadsheet",
            "application/vnd.google-apps.presentation",
        ],
    )
    def test_google_native_detected(self, google_mime: str) -> None:
        """Google Docs, Sheets, and Slides MIME types should be in the export map."""
        assert google_mime in RAG_DRIVE_GOOGLE_EXPORT_MAP

    @pytest.mark.parametrize(
        "unsupported_mime",
        [
            "image/png",
            "image/jpeg",
            "video/mp4",
            "audio/mpeg",
            "application/zip",
        ],
    )
    def test_unsupported_mime_not_in_maps(self, unsupported_mime: str) -> None:
        """Unsupported MIME types should not appear in either map."""
        assert unsupported_mime not in RAG_DRIVE_GOOGLE_EXPORT_MAP
        assert unsupported_mime not in RAG_DRIVE_REGULAR_FILE_MAP
