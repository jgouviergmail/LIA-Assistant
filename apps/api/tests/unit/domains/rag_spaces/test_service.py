"""Tests for RAGSpaceService business logic."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status
from sqlalchemy.exc import IntegrityError

from src.core.exceptions import BaseAPIException
from src.domains.rag_spaces.models import RAGDocumentStatus
from src.domains.rag_spaces.service import _EXT_TO_MIME, RAGSpaceService

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
    svc = RAGSpaceService(mock_db)
    svc.space_repo = AsyncMock()
    svc.doc_repo = AsyncMock()
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
    space.description = "A test knowledge space"
    space.is_active = True
    space.dict.return_value = {
        "id": space_id,
        "user_id": user_id,
        "name": "Test Space",
        "description": "A test knowledge space",
        "is_active": True,
    }
    return space


@pytest.fixture
def sample_document(user_id, space_id):
    """Create a mock RAGDocument instance."""
    doc = MagicMock()
    doc.id = uuid.uuid4()
    doc.space_id = space_id
    doc.user_id = user_id
    doc.filename = "abc123.pdf"
    doc.original_filename = "report.pdf"
    doc.file_size = 1024
    doc.content_type = "application/pdf"
    doc.status = RAGDocumentStatus.READY
    doc.dict.return_value = {
        "id": doc.id,
        "space_id": space_id,
        "user_id": user_id,
        "filename": "abc123.pdf",
        "original_filename": "report.pdf",
        "file_size": 1024,
        "content_type": "application/pdf",
        "status": RAGDocumentStatus.READY,
    }
    return doc


# ============================================================================
# TestListSpaces
# ============================================================================


@pytest.mark.unit
class TestListSpaces:
    """Tests for listing user spaces with computed stats."""

    @pytest.mark.asyncio
    async def test_list_spaces_returns_spaces_with_stats(
        self, service, user_id, sample_space
    ) -> None:
        """Should return spaces merged with document stats."""
        stats = {"document_count": 3, "total_size": 4096, "ready_document_count": 2}
        service.space_repo.get_all_for_user = AsyncMock(return_value=[sample_space])
        service.doc_repo.get_space_stats = AsyncMock(return_value=stats)

        result = await service.list_spaces(user_id)

        assert len(result) == 1
        assert result[0]["name"] == "Test Space"
        assert result[0]["document_count"] == 3
        assert result[0]["total_size"] == 4096
        assert result[0]["ready_document_count"] == 2
        service.space_repo.get_all_for_user.assert_awaited_once_with(user_id)

    @pytest.mark.asyncio
    async def test_list_spaces_empty(self, service, user_id) -> None:
        """Should return empty list when user has no spaces."""
        service.space_repo.get_all_for_user = AsyncMock(return_value=[])

        result = await service.list_spaces(user_id)

        assert result == []


# ============================================================================
# TestCreateSpace
# ============================================================================


@pytest.mark.unit
class TestCreateSpace:
    """Tests for space creation with limit enforcement."""

    @pytest.mark.asyncio
    @patch("src.domains.rag_spaces.service.settings")
    async def test_create_space_success(
        self, mock_settings, service, user_id, sample_space
    ) -> None:
        """Should create a space when under the limit."""
        mock_settings.rag_spaces_max_spaces_per_user = 10
        service.space_repo.count_for_user = AsyncMock(return_value=2)
        service.space_repo.create = AsyncMock(return_value=sample_space)

        result = await service.create_space(user_id, "Test Space", "A test knowledge space")

        assert result == sample_space
        service.space_repo.create.assert_awaited_once()
        create_data = service.space_repo.create.call_args[0][0]
        assert create_data["user_id"] == user_id
        assert create_data["name"] == "Test Space"
        assert create_data["description"] == "A test knowledge space"
        service.db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("src.domains.rag_spaces.service.settings")
    async def test_create_space_strips_whitespace(
        self, mock_settings, service, user_id, sample_space
    ) -> None:
        """Should strip leading/trailing whitespace from name and description."""
        mock_settings.rag_spaces_max_spaces_per_user = 10
        service.space_repo.count_for_user = AsyncMock(return_value=0)
        service.space_repo.create = AsyncMock(return_value=sample_space)

        await service.create_space(user_id, "  Test Space  ", "  description  ")

        create_data = service.space_repo.create.call_args[0][0]
        assert create_data["name"] == "Test Space"
        assert create_data["description"] == "description"

    @pytest.mark.asyncio
    @patch("src.domains.rag_spaces.service.settings")
    async def test_create_space_none_description(
        self, mock_settings, service, user_id, sample_space
    ) -> None:
        """Should handle None description without stripping."""
        mock_settings.rag_spaces_max_spaces_per_user = 10
        service.space_repo.count_for_user = AsyncMock(return_value=0)
        service.space_repo.create = AsyncMock(return_value=sample_space)

        await service.create_space(user_id, "Test Space", None)

        create_data = service.space_repo.create.call_args[0][0]
        assert create_data["description"] is None

    @pytest.mark.asyncio
    @patch("src.domains.rag_spaces.service.settings")
    async def test_create_space_limit_exceeded(self, mock_settings, service, user_id) -> None:
        """Should raise 400 when user has reached max spaces."""
        mock_settings.rag_spaces_max_spaces_per_user = 5
        service.space_repo.count_for_user = AsyncMock(return_value=5)

        with pytest.raises(BaseAPIException) as exc_info:
            await service.create_space(user_id, "New Space")

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "Maximum number of spaces" in exc_info.value.detail

    @pytest.mark.asyncio
    @patch("src.domains.rag_spaces.service.settings")
    async def test_create_space_duplicate_name(self, mock_settings, service, user_id) -> None:
        """Should raise 409 on IntegrityError (duplicate name)."""
        mock_settings.rag_spaces_max_spaces_per_user = 10
        service.space_repo.count_for_user = AsyncMock(return_value=0)
        service.space_repo.create = AsyncMock(
            side_effect=IntegrityError("stmt", "params", Exception("unique"))
        )

        with pytest.raises(BaseAPIException) as exc_info:
            await service.create_space(user_id, "Existing Space")

        assert exc_info.value.status_code == status.HTTP_409_CONFLICT
        assert "already exists" in exc_info.value.detail
        service.db.rollback.assert_awaited_once()


# ============================================================================
# TestGetSpace
# ============================================================================


@pytest.mark.unit
class TestGetSpace:
    """Tests for single space retrieval with ownership verification."""

    @pytest.mark.asyncio
    async def test_get_space_success(self, service, user_id, space_id, sample_space) -> None:
        """Should return space when found and owned by user."""
        service.space_repo.get_by_id = AsyncMock(return_value=sample_space)

        result = await service.get_space(space_id, user_id)

        assert result == sample_space
        service.space_repo.get_by_id.assert_awaited_once_with(space_id)

    @pytest.mark.asyncio
    async def test_get_space_not_found(self, service, user_id, space_id) -> None:
        """Should raise 404 when space does not exist."""
        service.space_repo.get_by_id = AsyncMock(return_value=None)

        with pytest.raises(BaseAPIException) as exc_info:
            await service.get_space(space_id, user_id)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_get_space_wrong_user(self, service, space_id, sample_space) -> None:
        """Should raise 404 when space belongs to a different user."""
        service.space_repo.get_by_id = AsyncMock(return_value=sample_space)
        other_user = uuid.uuid4()

        with pytest.raises(BaseAPIException) as exc_info:
            await service.get_space(space_id, other_user)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND


# ============================================================================
# TestGetSpaceDetail
# ============================================================================


@pytest.mark.unit
class TestGetSpaceDetail:
    """Tests for space detail retrieval with documents and stats."""

    @pytest.mark.asyncio
    async def test_get_space_detail_success(
        self, service, user_id, space_id, sample_space, sample_document
    ) -> None:
        """Should return space dict merged with stats and documents."""
        service.space_repo.get_by_id = AsyncMock(return_value=sample_space)
        stats = {"document_count": 1, "total_size": 1024, "ready_document_count": 1}
        service.doc_repo.get_space_stats = AsyncMock(return_value=stats)
        service.doc_repo.get_all_for_space = AsyncMock(return_value=[sample_document])
        service.source_repo.get_all_for_space = AsyncMock(return_value=[])

        result = await service.get_space_detail(space_id, user_id)

        assert result["name"] == "Test Space"
        assert result["document_count"] == 1
        assert result["total_size"] == 1024
        assert len(result["documents"]) == 1
        assert result["drive_sources"] == []


# ============================================================================
# TestUpdateSpace
# ============================================================================


@pytest.mark.unit
class TestUpdateSpace:
    """Tests for space update (partial update)."""

    @pytest.mark.asyncio
    async def test_update_space_name(self, service, user_id, space_id, sample_space) -> None:
        """Should update name and commit."""
        service.space_repo.get_by_id = AsyncMock(return_value=sample_space)
        updated_space = MagicMock()
        service.space_repo.update = AsyncMock(return_value=updated_space)

        result = await service.update_space(space_id, user_id, name="New Name")

        assert result == updated_space
        update_data = service.space_repo.update.call_args[0][1]
        assert update_data["name"] == "New Name"
        service.db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_space_description(self, service, user_id, space_id, sample_space) -> None:
        """Should update description and commit."""
        service.space_repo.get_by_id = AsyncMock(return_value=sample_space)
        service.space_repo.update = AsyncMock(return_value=sample_space)

        await service.update_space(space_id, user_id, description="Updated desc")

        update_data = service.space_repo.update.call_args[0][1]
        assert update_data["description"] == "Updated desc"

    @pytest.mark.asyncio
    async def test_update_space_no_changes(self, service, user_id, space_id, sample_space) -> None:
        """Should skip update and not commit when no fields provided."""
        service.space_repo.get_by_id = AsyncMock(return_value=sample_space)

        result = await service.update_space(space_id, user_id)

        assert result == sample_space
        service.space_repo.update.assert_not_awaited()
        service.db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_update_space_duplicate_name(
        self, service, user_id, space_id, sample_space
    ) -> None:
        """Should raise 409 on IntegrityError (duplicate name)."""
        service.space_repo.get_by_id = AsyncMock(return_value=sample_space)
        service.space_repo.update = AsyncMock(
            side_effect=IntegrityError("stmt", "params", Exception("unique"))
        )

        with pytest.raises(BaseAPIException) as exc_info:
            await service.update_space(space_id, user_id, name="Duplicate")

        assert exc_info.value.status_code == status.HTTP_409_CONFLICT
        service.db.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_space_strips_whitespace(
        self, service, user_id, space_id, sample_space
    ) -> None:
        """Should strip whitespace from name and description."""
        service.space_repo.get_by_id = AsyncMock(return_value=sample_space)
        service.space_repo.update = AsyncMock(return_value=sample_space)

        await service.update_space(space_id, user_id, name="  Trimmed  ", description="  Desc  ")

        update_data = service.space_repo.update.call_args[0][1]
        assert update_data["name"] == "Trimmed"
        assert update_data["description"] == "Desc"


# ============================================================================
# TestDeleteSpace
# ============================================================================


@pytest.mark.unit
class TestDeleteSpace:
    """Tests for space deletion with cascade cleanup."""

    @pytest.mark.asyncio
    @patch("src.domains.rag_spaces.service.settings")
    @patch("src.domains.rag_spaces.service.Path")
    async def test_delete_space_success(
        self, mock_path_cls, mock_settings, service, user_id, space_id, sample_space
    ) -> None:
        """Should delete chunks, space, commit, and clean up files."""
        mock_settings.rag_spaces_storage_path = "/tmp/rag_storage"
        service.space_repo.get_by_id = AsyncMock(return_value=sample_space)
        service.chunk_repo.delete_by_space = AsyncMock(return_value=5)
        service.space_repo.delete = AsyncMock()

        # Mock the storage directory path to simulate existing directory
        mock_storage_dir = MagicMock()
        mock_storage_dir.exists.return_value = True
        mock_path_cls.return_value.__truediv__ = MagicMock(return_value=mock_storage_dir)
        mock_storage_dir.__truediv__ = MagicMock(return_value=mock_storage_dir)

        await service.delete_space(space_id, user_id)

        service.chunk_repo.delete_by_space.assert_awaited_once_with(space_id)
        service.space_repo.delete.assert_awaited_once_with(sample_space)
        service.db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_space_not_found(self, service, space_id) -> None:
        """Should raise 404 when space does not exist."""
        service.space_repo.get_by_id = AsyncMock(return_value=None)
        other_user = uuid.uuid4()

        with pytest.raises(BaseAPIException) as exc_info:
            await service.delete_space(space_id, other_user)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_delete_space_wrong_user(self, service, space_id, sample_space) -> None:
        """Should raise 404 when space belongs to a different user."""
        service.space_repo.get_by_id = AsyncMock(return_value=sample_space)
        other_user = uuid.uuid4()

        with pytest.raises(BaseAPIException) as exc_info:
            await service.delete_space(space_id, other_user)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND


# ============================================================================
# TestToggleSpace
# ============================================================================


@pytest.mark.unit
class TestToggleSpace:
    """Tests for space activation toggle."""

    @pytest.mark.asyncio
    async def test_toggle_space_activates(self, service, user_id, space_id, sample_space) -> None:
        """Should toggle is_active from True to False."""
        sample_space.is_active = True
        service.space_repo.get_by_id = AsyncMock(return_value=sample_space)
        toggled = MagicMock()
        toggled.is_active = False
        service.space_repo.update = AsyncMock(return_value=toggled)

        result = await service.toggle_space(space_id, user_id)

        assert result.is_active is False
        update_data = service.space_repo.update.call_args[0][1]
        assert update_data["is_active"] is False
        service.db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_toggle_space_deactivates(self, service, user_id, space_id, sample_space) -> None:
        """Should toggle is_active from False to True."""
        sample_space.is_active = False
        service.space_repo.get_by_id = AsyncMock(return_value=sample_space)
        toggled = MagicMock()
        toggled.is_active = True
        service.space_repo.update = AsyncMock(return_value=toggled)

        result = await service.toggle_space(space_id, user_id)

        assert result.is_active is True
        update_data = service.space_repo.update.call_args[0][1]
        assert update_data["is_active"] is True

    @pytest.mark.asyncio
    async def test_toggle_space_not_found(self, service, space_id) -> None:
        """Should raise 404 when space does not exist."""
        service.space_repo.get_by_id = AsyncMock(return_value=None)

        with pytest.raises(BaseAPIException) as exc_info:
            await service.toggle_space(space_id, uuid.uuid4())

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND


# ============================================================================
# TestUploadDocument
# ============================================================================


@pytest.mark.unit
class TestUploadDocument:
    """Tests for document upload with validation."""

    @pytest.mark.asyncio
    @patch("src.domains.rag_spaces.service.settings")
    @patch("src.domains.rag_spaces.service.Path")
    async def test_upload_document_success(
        self, mock_path_cls, mock_settings, service, user_id, space_id, sample_space
    ) -> None:
        """Should validate, write file, and create DB record."""
        mock_settings.rag_spaces_max_docs_per_space = 50
        mock_settings.rag_spaces_allowed_types = "application/pdf,text/plain"
        mock_settings.rag_spaces_max_file_size_mb = 10
        mock_settings.rag_spaces_storage_path = "/tmp/rag_storage"

        service.space_repo.get_by_id = AsyncMock(return_value=sample_space)
        service.doc_repo.count_for_space = AsyncMock(return_value=3)

        # Mock file upload
        mock_file = AsyncMock()
        mock_file.content_type = "application/pdf"
        mock_file.filename = "report.pdf"
        # Simulate reading: first chunk returns data, second returns empty (EOF)
        file_content = b"PDF content here"
        mock_file.read = AsyncMock(side_effect=[file_content, b""])

        # Mock Path operations
        mock_storage_dir = MagicMock()
        mock_file_path = MagicMock()
        mock_path_cls.return_value.__truediv__ = MagicMock(return_value=mock_storage_dir)
        mock_storage_dir.__truediv__ = MagicMock(return_value=mock_storage_dir)
        mock_storage_dir.mkdir = MagicMock()
        mock_storage_dir.suffix = ".pdf"
        # Path(original_filename).suffix should return ".pdf"
        mock_path_cls.side_effect = lambda x: (
            MagicMock(suffix=".pdf")
            if x == "report.pdf"
            else MagicMock(__truediv__=MagicMock(return_value=mock_storage_dir))
        )
        # Reset to handle Path for storage dir
        mock_path_cls.side_effect = None
        mock_path_cls.return_value = MagicMock()
        mock_path_cls.return_value.__truediv__ = MagicMock(return_value=mock_storage_dir)
        mock_storage_dir.__truediv__ = MagicMock(return_value=mock_file_path)
        mock_storage_dir.mkdir = MagicMock()
        mock_file_path.write_bytes = MagicMock()

        mock_doc = MagicMock()
        mock_doc.id = uuid.uuid4()
        service.doc_repo.create = AsyncMock(return_value=mock_doc)

        with patch("src.domains.rag_spaces.service.Path") as path_mock:
            # Make Path(original_filename).suffix work
            def path_side_effect(arg):
                m = MagicMock()
                if arg == "report.pdf":
                    m.suffix = ".pdf"
                    return m
                # Path(storage_path) chain
                m.__truediv__ = MagicMock(return_value=mock_storage_dir)
                return m

            path_mock.side_effect = path_side_effect
            mock_storage_dir.__truediv__ = MagicMock(return_value=mock_storage_dir)
            mock_storage_dir.mkdir = MagicMock()
            # final file_path from storage_dir / stored_filename
            mock_final_path = MagicMock()
            mock_storage_dir.__truediv__ = MagicMock(return_value=mock_final_path)
            mock_final_path.write_bytes = MagicMock()

            result = await service.upload_document(space_id, user_id, mock_file)

        assert result == mock_doc
        service.doc_repo.create.assert_awaited_once()
        create_data = service.doc_repo.create.call_args[0][0]
        assert create_data["space_id"] == space_id
        assert create_data["user_id"] == user_id
        assert create_data["original_filename"] == "report.pdf"
        assert create_data["content_type"] == "application/pdf"
        assert create_data["file_size"] == len(file_content)
        assert create_data["status"] == RAGDocumentStatus.PROCESSING

    @pytest.mark.asyncio
    @patch("src.domains.rag_spaces.service.settings")
    async def test_upload_document_limit_exceeded(
        self, mock_settings, service, user_id, space_id, sample_space
    ) -> None:
        """Should raise 400 when space has reached max documents."""
        mock_settings.rag_spaces_max_docs_per_space = 10
        service.space_repo.get_by_id = AsyncMock(return_value=sample_space)
        service.doc_repo.count_for_space = AsyncMock(return_value=10)

        mock_file = AsyncMock()
        mock_file.content_type = "application/pdf"
        mock_file.filename = "doc.pdf"

        with pytest.raises(BaseAPIException) as exc_info:
            await service.upload_document(space_id, user_id, mock_file)

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "Maximum number of documents" in exc_info.value.detail

    @pytest.mark.asyncio
    @patch("src.domains.rag_spaces.service.settings")
    async def test_upload_document_unsupported_type(
        self, mock_settings, service, user_id, space_id, sample_space
    ) -> None:
        """Should raise 415 when file MIME type is not allowed."""
        mock_settings.rag_spaces_max_docs_per_space = 50
        mock_settings.rag_spaces_allowed_types = "application/pdf,text/plain"
        service.space_repo.get_by_id = AsyncMock(return_value=sample_space)
        service.doc_repo.count_for_space = AsyncMock(return_value=0)

        mock_file = AsyncMock()
        mock_file.content_type = "image/png"
        mock_file.filename = "image.png"

        with pytest.raises(BaseAPIException) as exc_info:
            await service.upload_document(space_id, user_id, mock_file)

        assert exc_info.value.status_code == status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
        assert "image/png" in exc_info.value.detail

    @pytest.mark.asyncio
    @patch("src.domains.rag_spaces.service.settings")
    async def test_upload_document_extension_mime_mismatch(
        self, mock_settings, service, user_id, space_id, sample_space
    ) -> None:
        """Should raise 415 when file extension does not match claimed MIME type."""
        mock_settings.rag_spaces_max_docs_per_space = 50
        mock_settings.rag_spaces_allowed_types = "text/plain,application/pdf"
        service.space_repo.get_by_id = AsyncMock(return_value=sample_space)
        service.doc_repo.count_for_space = AsyncMock(return_value=0)

        mock_file = AsyncMock()
        mock_file.content_type = "text/plain"
        mock_file.filename = "malicious.pdf"  # .pdf extension but claims text/plain

        with pytest.raises(BaseAPIException) as exc_info:
            await service.upload_document(space_id, user_id, mock_file)

        assert exc_info.value.status_code == status.HTTP_415_UNSUPPORTED_MEDIA_TYPE

    @pytest.mark.asyncio
    @patch("src.domains.rag_spaces.service.settings")
    async def test_upload_document_file_too_large(
        self, mock_settings, service, user_id, space_id, sample_space
    ) -> None:
        """Should raise 413 when file exceeds size limit."""
        mock_settings.rag_spaces_max_docs_per_space = 50
        mock_settings.rag_spaces_allowed_types = "text/plain"
        mock_settings.rag_spaces_max_file_size_mb = 1  # 1MB limit
        service.space_repo.get_by_id = AsyncMock(return_value=sample_space)
        service.doc_repo.count_for_space = AsyncMock(return_value=0)

        mock_file = AsyncMock()
        mock_file.content_type = "text/plain"
        mock_file.filename = "big.txt"
        # Return a chunk larger than 1MB to trigger size limit
        large_chunk = b"x" * (2 * 1024 * 1024)
        mock_file.read = AsyncMock(side_effect=[large_chunk, b""])

        with pytest.raises(BaseAPIException) as exc_info:
            await service.upload_document(space_id, user_id, mock_file)

        assert exc_info.value.status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE

    @pytest.mark.asyncio
    async def test_upload_document_space_not_found(self, service, space_id) -> None:
        """Should raise 404 when space does not exist."""
        service.space_repo.get_by_id = AsyncMock(return_value=None)
        other_user = uuid.uuid4()

        mock_file = AsyncMock()
        mock_file.content_type = "text/plain"
        mock_file.filename = "doc.txt"

        with pytest.raises(BaseAPIException) as exc_info:
            await service.upload_document(space_id, other_user, mock_file)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    @patch("src.domains.rag_spaces.service.settings")
    async def test_upload_document_no_content_type_defaults(
        self, mock_settings, service, user_id, space_id, sample_space
    ) -> None:
        """Should default to 'application/octet-stream' when content_type is None."""
        mock_settings.rag_spaces_max_docs_per_space = 50
        mock_settings.rag_spaces_allowed_types = "application/pdf"
        service.space_repo.get_by_id = AsyncMock(return_value=sample_space)
        service.doc_repo.count_for_space = AsyncMock(return_value=0)

        mock_file = AsyncMock()
        mock_file.content_type = None  # No content type
        mock_file.filename = "doc.pdf"

        # octet-stream is not in allowed types, so it should be rejected
        with pytest.raises(BaseAPIException) as exc_info:
            await service.upload_document(space_id, user_id, mock_file)

        assert exc_info.value.status_code == status.HTTP_415_UNSUPPORTED_MEDIA_TYPE


# ============================================================================
# TestDeleteDocument
# ============================================================================


@pytest.mark.unit
class TestDeleteDocument:
    """Tests for document deletion with cascade cleanup."""

    @pytest.mark.asyncio
    @patch("src.domains.rag_spaces.service.settings")
    @patch("src.domains.rag_spaces.service.Path")
    async def test_delete_document_success(
        self,
        mock_path_cls,
        mock_settings,
        service,
        user_id,
        space_id,
        sample_space,
        sample_document,
    ) -> None:
        """Should delete chunks, document record, and physical file."""
        mock_settings.rag_spaces_storage_path = "/tmp/rag_storage"
        service.space_repo.get_by_id = AsyncMock(return_value=sample_space)
        service.doc_repo.get_by_id = AsyncMock(return_value=sample_document)
        service.chunk_repo.delete_by_document = AsyncMock(return_value=3)
        service.doc_repo.delete = AsyncMock()

        # Mock file path existence check
        mock_file_path = MagicMock()
        mock_file_path.exists.return_value = True
        mock_storage = MagicMock()
        mock_storage.__truediv__ = MagicMock(return_value=mock_storage)
        mock_path_cls.return_value = mock_storage
        mock_storage.__truediv__ = MagicMock(return_value=mock_file_path)

        with patch("src.domains.rag_spaces.service.os.remove") as mock_remove:
            await service.delete_document(space_id, sample_document.id, user_id)
            mock_remove.assert_called_once()

        service.chunk_repo.delete_by_document.assert_awaited_once_with(sample_document.id)
        service.doc_repo.delete.assert_awaited_once_with(sample_document)
        service.db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_document_not_found(
        self, service, user_id, space_id, sample_space
    ) -> None:
        """Should raise 404 when document does not exist."""
        service.space_repo.get_by_id = AsyncMock(return_value=sample_space)
        service.doc_repo.get_by_id = AsyncMock(return_value=None)
        doc_id = uuid.uuid4()

        with pytest.raises(BaseAPIException) as exc_info:
            await service.delete_document(space_id, doc_id, user_id)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_delete_document_wrong_space(
        self, service, user_id, space_id, sample_space, sample_document
    ) -> None:
        """Should raise 404 when document belongs to a different space."""
        service.space_repo.get_by_id = AsyncMock(return_value=sample_space)
        # Document exists but belongs to a different space
        sample_document.space_id = uuid.uuid4()
        service.doc_repo.get_by_id = AsyncMock(return_value=sample_document)

        with pytest.raises(BaseAPIException) as exc_info:
            await service.delete_document(space_id, sample_document.id, user_id)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_delete_document_wrong_user(
        self, service, user_id, space_id, sample_space, sample_document
    ) -> None:
        """Should raise 404 when document belongs to a different user."""
        service.space_repo.get_by_id = AsyncMock(return_value=sample_space)
        # Document exists but belongs to a different user
        sample_document.user_id = uuid.uuid4()
        service.doc_repo.get_by_id = AsyncMock(return_value=sample_document)

        with pytest.raises(BaseAPIException) as exc_info:
            await service.delete_document(space_id, sample_document.id, user_id)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_delete_document_space_not_found(self, service, space_id) -> None:
        """Should raise 404 when parent space does not exist."""
        service.space_repo.get_by_id = AsyncMock(return_value=None)

        with pytest.raises(BaseAPIException) as exc_info:
            await service.delete_document(space_id, uuid.uuid4(), uuid.uuid4())

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND


# ============================================================================
# TestGetDocumentStatus
# ============================================================================


@pytest.mark.unit
class TestGetDocumentStatus:
    """Tests for document status retrieval."""

    @pytest.mark.asyncio
    async def test_get_document_status_success(
        self, service, user_id, space_id, sample_space, sample_document
    ) -> None:
        """Should return document when found and ownership matches."""
        service.space_repo.get_by_id = AsyncMock(return_value=sample_space)
        service.doc_repo.get_by_id = AsyncMock(return_value=sample_document)

        result = await service.get_document_status(space_id, sample_document.id, user_id)

        assert result == sample_document

    @pytest.mark.asyncio
    async def test_get_document_status_not_found(
        self, service, user_id, space_id, sample_space
    ) -> None:
        """Should raise 404 when document does not exist."""
        service.space_repo.get_by_id = AsyncMock(return_value=sample_space)
        service.doc_repo.get_by_id = AsyncMock(return_value=None)

        with pytest.raises(BaseAPIException) as exc_info:
            await service.get_document_status(space_id, uuid.uuid4(), user_id)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_get_document_status_wrong_space(
        self, service, user_id, space_id, sample_space, sample_document
    ) -> None:
        """Should raise 404 when document space_id does not match."""
        service.space_repo.get_by_id = AsyncMock(return_value=sample_space)
        sample_document.space_id = uuid.uuid4()
        service.doc_repo.get_by_id = AsyncMock(return_value=sample_document)

        with pytest.raises(BaseAPIException) as exc_info:
            await service.get_document_status(space_id, sample_document.id, user_id)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND


# ============================================================================
# TestUpdateSpaceWithStats
# ============================================================================


@pytest.mark.unit
class TestUpdateSpaceWithStats:
    """Tests for update_space_with_stats convenience method."""

    @pytest.mark.asyncio
    async def test_update_space_with_stats_returns_merged(
        self, service, user_id, space_id, sample_space
    ) -> None:
        """Should return updated space dict merged with stats."""
        service.space_repo.get_by_id = AsyncMock(return_value=sample_space)
        service.space_repo.update = AsyncMock(return_value=sample_space)
        stats = {"document_count": 5, "total_size": 8192, "ready_document_count": 4}
        service.doc_repo.get_space_stats = AsyncMock(return_value=stats)

        result = await service.update_space_with_stats(space_id, user_id, name="Updated")

        assert result["name"] == "Test Space"  # from mock dict()
        assert result["document_count"] == 5
        assert result["total_size"] == 8192
        assert result["ready_document_count"] == 4


# ============================================================================
# TestExtToMime
# ============================================================================


@pytest.mark.unit
class TestExtToMime:
    """Tests that _EXT_TO_MIME maps every extension to its expected MIME type."""

    @pytest.mark.parametrize(
        ("ext", "expected_mime"),
        [
            (".txt", "text/plain"),
            (".md", "text/markdown"),
            (".pdf", "application/pdf"),
            (".docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
            (".pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
            (".xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            (".csv", "text/csv"),
            (".rtf", "application/rtf"),
            (".html", "text/html"),
            (".htm", "text/html"),
            (".odt", "application/vnd.oasis.opendocument.text"),
            (".ods", "application/vnd.oasis.opendocument.spreadsheet"),
            (".odp", "application/vnd.oasis.opendocument.presentation"),
            (".epub", "application/epub+zip"),
            (".json", "application/json"),
            (".xml", "application/xml"),
        ],
    )
    def test_extension_maps_to_mime(self, ext: str, expected_mime: str) -> None:
        """Each file extension maps to the correct MIME type."""
        assert _EXT_TO_MIME[ext] == expected_mime

    def test_ext_to_mime_has_expected_count(self) -> None:
        """_EXT_TO_MIME contains exactly 16 entries."""
        assert len(_EXT_TO_MIME) == 16
