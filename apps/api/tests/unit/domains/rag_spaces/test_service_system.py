"""Tests for RAGSpaceService system space protection."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import status

from src.core.exceptions import BaseAPIException
from src.domains.rag_spaces.service import RAGSpaceService

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def service(mock_db):
    svc = RAGSpaceService(mock_db)
    svc.space_repo = AsyncMock()
    svc.doc_repo = AsyncMock()
    svc.chunk_repo = AsyncMock()
    svc.source_repo = AsyncMock()
    return svc


@pytest.fixture
def system_space():
    """Create a mock system space."""
    space = MagicMock()
    space.id = uuid.uuid4()
    space.user_id = None
    space.name = "lia-faq"
    space.is_system = True
    space.is_active = True
    space.content_hash = "abc123"
    return space


@pytest.fixture
def user_space():
    """Create a mock user space."""
    space = MagicMock()
    space.id = uuid.uuid4()
    space.user_id = uuid.uuid4()
    space.name = "My Notes"
    space.is_system = False
    space.is_active = True
    space.dict.return_value = {
        "id": space.id,
        "user_id": space.user_id,
        "name": "My Notes",
        "is_system": False,
        "is_active": True,
    }
    return space


# ============================================================================
# TestSystemSpaceProtection
# ============================================================================


@pytest.mark.unit
class TestSystemSpaceProtection:
    """System spaces cannot be modified by user CRUD operations.

    get_space() checks ownership (space.user_id == user_id) BEFORE the is_system guard.
    Since system spaces have user_id=None, a normal user gets 404 (not found/not owned).
    The is_system guard is a defense-in-depth for cases where a user_id somehow matches.
    We test both layers.
    """

    @pytest.mark.asyncio
    async def test_system_space_invisible_to_users(self, service, system_space) -> None:
        """System spaces (user_id=None) are not found by get_space (ownership check)."""
        service.space_repo.get_by_id = AsyncMock(return_value=system_space)

        with pytest.raises(BaseAPIException) as exc_info:
            await service.delete_space(system_space.id, uuid.uuid4())

        # user_id=None != user_id → 404 (first layer of protection)
        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_delete_system_space_raises_403_if_owned(self, service, system_space) -> None:
        """Defense-in-depth: if ownership somehow passes, is_system guard raises 403."""
        # Simulate edge case where user_id matches (shouldn't happen, but defense-in-depth)
        user_id = uuid.uuid4()
        system_space.user_id = user_id
        service.space_repo.get_by_id = AsyncMock(return_value=system_space)

        with pytest.raises(BaseAPIException) as exc_info:
            await service.delete_space(system_space.id, user_id)

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert "delete" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_toggle_system_space_raises_403_if_owned(self, service, system_space) -> None:
        """Defense-in-depth: toggle blocked by is_system guard."""
        user_id = uuid.uuid4()
        system_space.user_id = user_id
        service.space_repo.get_by_id = AsyncMock(return_value=system_space)

        with pytest.raises(BaseAPIException) as exc_info:
            await service.toggle_space(system_space.id, user_id)

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert "toggle" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_update_system_space_raises_403_if_owned(self, service, system_space) -> None:
        """Defense-in-depth: update blocked by is_system guard."""
        user_id = uuid.uuid4()
        system_space.user_id = user_id
        service.space_repo.get_by_id = AsyncMock(return_value=system_space)

        with pytest.raises(BaseAPIException) as exc_info:
            await service.update_space(system_space.id, user_id, name="hacked")

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert "update" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_upload_to_system_space_raises_403_if_owned(self, service, system_space) -> None:
        """Defense-in-depth: upload blocked by is_system guard."""
        user_id = uuid.uuid4()
        system_space.user_id = user_id
        service.space_repo.get_by_id = AsyncMock(return_value=system_space)

        mock_file = AsyncMock()
        mock_file.content_type = "text/plain"
        mock_file.filename = "test.txt"

        with pytest.raises(BaseAPIException) as exc_info:
            await service.upload_document(system_space.id, user_id, mock_file)

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert "upload" in exc_info.value.detail.lower()


# ============================================================================
# TestListSpacesExcludesSystem
# ============================================================================


@pytest.mark.unit
class TestListSpacesExcludesSystem:
    """list_spaces should not return system spaces."""

    @pytest.mark.asyncio
    async def test_system_spaces_filtered_out(self, service, user_space, system_space) -> None:
        """System spaces should be excluded from user listing."""
        service.space_repo.get_all_for_user = AsyncMock(return_value=[user_space, system_space])
        service.doc_repo.get_space_stats = AsyncMock(
            return_value={"document_count": 0, "total_size": 0, "ready_document_count": 0}
        )

        result = await service.list_spaces(user_space.user_id)

        assert len(result) == 1
        assert result[0]["name"] == "My Notes"


# ============================================================================
# TestSystemSpaceCRUD
# ============================================================================


@pytest.mark.unit
class TestSystemSpaceCRUD:
    """Tests for system space admin operations."""

    @pytest.mark.asyncio
    async def test_get_system_spaces(self, service, system_space) -> None:
        """Should return system spaces with stats."""
        system_space.dict = MagicMock(
            return_value={
                "id": system_space.id,
                "name": "lia-faq",
                "is_system": True,
            }
        )
        service.space_repo.get_system_spaces = AsyncMock(return_value=[system_space])
        service.doc_repo.get_space_stats = AsyncMock(
            return_value={"document_count": 1, "total_size": 0, "ready_document_count": 1}
        )
        service.chunk_repo.count_for_space = AsyncMock(return_value=139)

        result = await service.get_system_spaces()

        assert len(result) == 1
        assert result[0]["name"] == "lia-faq"
        assert result[0]["chunk_count"] == 139

    @pytest.mark.asyncio
    async def test_get_system_space_by_name_not_found(self, service) -> None:
        """Should raise 404 when system space not found."""
        service.space_repo.get_system_space_by_name = AsyncMock(return_value=None)

        with pytest.raises(BaseAPIException) as exc_info:
            await service.get_system_space_by_name("nonexistent")

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_create_system_space(self, service) -> None:
        """Should create a system space with is_system=True and user_id=None."""
        created = MagicMock()
        created.id = uuid.uuid4()
        created.name = "lia-faq"
        service.space_repo.create = AsyncMock(return_value=created)

        result = await service.create_system_space("lia-faq", "FAQ description")

        create_data = service.space_repo.create.call_args[0][0]
        assert create_data["user_id"] is None
        assert create_data["is_system"] is True
        assert create_data["is_active"] is True
        assert result.name == "lia-faq"
