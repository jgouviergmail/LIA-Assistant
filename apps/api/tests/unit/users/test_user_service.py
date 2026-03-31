"""
Unit tests for UserService (domains/users/service.py).

Session 30 - PHASE 4.1 Coverage Tests
Target: 80%+ coverage

Test Structure:
1. TestUserServiceInit - Initialization tests
2. TestGetUserById - Get user by ID
3. TestDeleteUser - Soft/hard delete
4. TestSearchUsersByEmail - Email pattern search
5. TestGetAllUsers - Pagination tests
6. TestUpdateUser - Update with tracking
7. TestSearchUsers - Admin search
8. TestUpdateUserActivation - Admin activation
9. TestDeleteUserGDPR - GDPR compliance
10. TestInvalidateAllUserSessions - Redis session invalidation
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.users.models import User
from src.domains.users.schemas import UserActivationUpdate, UserSearchParams, UserUpdate
from src.domains.users.service import UserService
from src.infrastructure.database.registry import import_all_models

# Ensure all SQLAlchemy models are loaded so relationship() references resolve
import_all_models()

# ==============================================================================
# FACTORY FUNCTIONS
# ==============================================================================


def create_mock_user(
    user_id: uuid.UUID | None = None,
    email: str = "test@example.com",
    full_name: str = "Test User",
    is_active: bool = True,
    is_verified: bool = True,
    is_superuser: bool = False,
    language: str = "fr",
    timezone: str = "Europe/Paris",
    memory_enabled: bool = True,
    voice_enabled: bool = False,
    theme: str = "system",
    color_theme: str = "default",
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
) -> User:
    """
    Factory function to create mock User with all required fields.

    Returns a User model instance with BaseModel fields (id, created_at, updated_at)
    automatically populated if not provided.
    """
    now = datetime.now(UTC)
    user = User(
        id=user_id or uuid.uuid4(),
        email=email,
        full_name=full_name,
        hashed_password="hashed_password_123",  # Required field
        is_active=is_active,
        is_verified=is_verified,
        is_superuser=is_superuser,
        language=language,
        timezone=timezone,
        memory_enabled=memory_enabled,
        voice_enabled=voice_enabled,
        theme=theme,
        color_theme=color_theme,
        created_at=created_at or now,
        updated_at=updated_at or now,
        # Image generation defaults (required by UserProfile schema)
        image_generation_enabled=True,
        image_generation_default_quality="low",
        image_generation_default_size="portrait",
        image_generation_output_format="png",
    )
    return user


# ==============================================================================
# PHASE 1: TESTS BASIQUES (10 tests, 1h)
# ==============================================================================


class TestUserServiceInit:
    """Test UserService initialization."""

    @pytest.mark.asyncio
    async def test_init_sets_db_and_repository(self):
        """Test that __init__ correctly sets db and initializes UserRepository."""
        # Arrange
        mock_db = MagicMock(spec=AsyncSession)

        # Act
        service = UserService(mock_db)

        # Assert
        assert service.db == mock_db
        assert service.repository is not None
        # Verify repository was initialized with same db session
        assert service.repository.db == mock_db


class TestGetUserById:
    """Test get_user_by_id method."""

    @pytest.mark.asyncio
    async def test_get_user_by_id_success(self):
        """Test getting user by ID successfully returns user profile."""
        # Arrange
        mock_db = MagicMock(spec=AsyncSession)
        service = UserService(mock_db)

        user_id = uuid.uuid4()
        mock_user = create_mock_user(
            user_id=user_id,
            email="user@example.com",
            full_name="John Doe",
        )

        # Mock repository.get_by_id to return mock user
        service.repository.get_by_id = AsyncMock(return_value=mock_user)

        # Act
        result = await service.get_user_by_id(user_id)

        # Assert
        assert result.id == user_id
        assert result.email == "user@example.com"
        assert result.full_name == "John Doe"
        service.repository.get_by_id.assert_awaited_once_with(user_id)

    @pytest.mark.asyncio
    async def test_get_user_by_id_not_found_raises(self):
        """Test getting non-existent user raises HTTPException."""
        # Arrange
        from fastapi import HTTPException

        mock_db = MagicMock(spec=AsyncSession)
        service = UserService(mock_db)

        user_id = uuid.uuid4()

        # Mock repository.get_by_id to return None (not found)
        service.repository.get_by_id = AsyncMock(return_value=None)

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await service.get_user_by_id(user_id)

        assert exc_info.value.status_code == 404
        assert "User not found" in str(exc_info.value.detail)


class TestDeleteUser:
    """Test delete_user method (soft/hard delete)."""

    @pytest.mark.asyncio
    async def test_delete_user_soft_delete_default(self):
        """Test soft delete (default) calls repository.delete()."""
        # Arrange
        mock_db = MagicMock(spec=AsyncSession)
        mock_db.commit = AsyncMock()
        service = UserService(mock_db)

        user_id = uuid.uuid4()
        mock_user = create_mock_user(user_id=user_id, is_active=True)

        service.repository.get_by_id = AsyncMock(return_value=mock_user)
        service.repository.delete = AsyncMock(return_value=None)

        # Act
        result = await service.delete_user(user_id, hard_delete=False)

        # Assert
        assert result is None  # Method returns None
        service.repository.delete.assert_awaited_once_with(mock_user)
        mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_user_hard_delete(self):
        """Test hard delete permanently removes user from database."""
        # Arrange
        mock_db = MagicMock(spec=AsyncSession)
        mock_db.commit = AsyncMock()
        service = UserService(mock_db)

        user_id = uuid.uuid4()
        mock_user = create_mock_user(user_id=user_id)

        service.repository.get_by_id = AsyncMock(return_value=mock_user)
        service.repository.hard_delete = AsyncMock(return_value=None)

        # Act
        result = await service.delete_user(user_id, hard_delete=True)

        # Assert
        assert result is None  # Method returns None
        service.repository.hard_delete.assert_awaited_once_with(mock_user)
        mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_user_not_found_raises(self):
        """Test deleting non-existent user raises HTTPException."""
        # Arrange
        from fastapi import HTTPException

        mock_db = MagicMock(spec=AsyncSession)
        service = UserService(mock_db)

        user_id = uuid.uuid4()
        service.repository.get_by_id = AsyncMock(return_value=None)

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await service.delete_user(user_id)

        assert exc_info.value.status_code == 404


class TestSearchUsersByEmail:
    """Test search_users_by_email method."""

    @pytest.mark.asyncio
    async def test_search_users_by_email_pattern_match(self):
        """Test searching users by email pattern returns matching users."""
        # Arrange
        mock_db = MagicMock(spec=AsyncSession)
        service = UserService(mock_db)

        mock_users = [
            create_mock_user(email="john@example.com", full_name="John Doe"),
            create_mock_user(email="jane@example.com", full_name="Jane Doe"),
        ]

        service.repository.search_by_email = AsyncMock(return_value=mock_users)

        # Act
        result = await service.search_users_by_email("@example.com")

        # Assert
        assert len(result) == 2
        assert result[0].email == "john@example.com"
        assert result[1].email == "jane@example.com"
        service.repository.search_by_email.assert_awaited_once_with("@example.com")

    @pytest.mark.asyncio
    async def test_search_users_by_email_no_match(self):
        """Test searching with no matches returns empty list."""
        # Arrange
        mock_db = MagicMock(spec=AsyncSession)
        service = UserService(mock_db)

        service.repository.search_by_email = AsyncMock(return_value=[])

        # Act
        result = await service.search_users_by_email("nonexistent@example.com")

        # Assert
        assert len(result) == 0
        assert result == []

    @pytest.mark.asyncio
    async def test_search_users_by_email_multiple_results(self):
        """Test searching returns all matching users."""
        # Arrange
        mock_db = MagicMock(spec=AsyncSession)
        service = UserService(mock_db)

        mock_users = [create_mock_user(email=f"user{i}@test.com") for i in range(5)]

        service.repository.search_by_email = AsyncMock(return_value=mock_users)

        # Act
        result = await service.search_users_by_email("@test.com")

        # Assert
        assert len(result) == 5
        for i, user in enumerate(result):
            assert user.email == f"user{i}@test.com"


# ==============================================================================
# PHASE 2: TESTS PAGINATION (11 tests, 1h30)
# ==============================================================================


class TestGetAllUsers:
    """Test get_all_users method with pagination."""

    @pytest.mark.asyncio
    @patch("src.core.pagination_helpers.validate_pagination")
    @patch("src.core.pagination_helpers.calculate_skip")
    @patch("src.core.pagination_helpers.calculate_total_pages")
    async def test_get_all_users_default_pagination(
        self, mock_calc_pages, mock_calc_skip, mock_validate
    ):
        """Test getting all users with default pagination (page=1, page_size=20)."""
        # Arrange
        mock_db = MagicMock(spec=AsyncSession)
        service = UserService(mock_db)

        mock_users = [create_mock_user(email=f"user{i}@example.com") for i in range(20)]
        total_count = 50

        # Mock pagination helpers (local imports in method)
        mock_validate.return_value = (1, 20)  # Returns tuple (page, page_size)
        mock_calc_skip.return_value = 0  # First page, skip=0
        mock_calc_pages.return_value = 3  # 50 users / 20 per page = 3 pages

        service.repository.get_all_with_count = AsyncMock(return_value=(mock_users, total_count))

        # Act
        result = await service.get_all_users(page=1, page_size=20)

        # Assert
        assert result.total == 50
        assert result.page == 1
        assert result.page_size == 20
        assert result.total_pages == 3
        assert len(result.users) == 20
        mock_validate.assert_called_once_with(1, 20)
        mock_calc_skip.assert_called_once_with(1, 20)
        service.repository.get_all_with_count.assert_awaited_once_with(
            skip=0, limit=20, is_active=None
        )

    @pytest.mark.asyncio
    @patch("src.core.pagination_helpers.validate_pagination")
    @patch("src.core.pagination_helpers.calculate_skip")
    @patch("src.core.pagination_helpers.calculate_total_pages")
    async def test_get_all_users_with_filter_active(
        self, mock_calc_pages, mock_calc_skip, mock_validate
    ):
        """Test filtering users by is_active=True."""
        # Arrange
        mock_db = MagicMock(spec=AsyncSession)
        service = UserService(mock_db)

        mock_users = [
            create_mock_user(email=f"active{i}@example.com", is_active=True) for i in range(10)
        ]
        total_count = 10

        mock_validate.return_value = (1, 20)
        mock_calc_skip.return_value = 0
        mock_calc_pages.return_value = 1

        service.repository.get_all_with_count = AsyncMock(return_value=(mock_users, total_count))

        # Act
        result = await service.get_all_users(page=1, page_size=20, is_active=True)

        # Assert
        assert result.total == 10
        assert len(result.users) == 10
        for user in result.users:
            assert user.is_active is True
        service.repository.get_all_with_count.assert_awaited_once_with(
            skip=0, limit=20, is_active=True
        )

    @pytest.mark.asyncio
    @patch("src.core.pagination_helpers.validate_pagination")
    @patch("src.core.pagination_helpers.calculate_skip")
    @patch("src.core.pagination_helpers.calculate_total_pages")
    async def test_get_all_users_with_filter_inactive(
        self, mock_calc_pages, mock_calc_skip, mock_validate
    ):
        """Test filtering users by is_active=False."""
        # Arrange
        mock_db = MagicMock(spec=AsyncSession)
        service = UserService(mock_db)

        mock_users = [
            create_mock_user(email=f"inactive{i}@example.com", is_active=False) for i in range(5)
        ]
        total_count = 5

        mock_validate.return_value = (1, 20)
        mock_calc_skip.return_value = 0
        mock_calc_pages.return_value = 1

        service.repository.get_all_with_count = AsyncMock(return_value=(mock_users, total_count))

        # Act
        result = await service.get_all_users(page=1, page_size=20, is_active=False)

        # Assert
        assert result.total == 5
        assert len(result.users) == 5
        for user in result.users:
            assert user.is_active is False

    @pytest.mark.asyncio
    @patch("src.core.pagination_helpers.validate_pagination")
    async def test_get_all_users_pagination_validation(self, mock_validate):
        """Test that invalid pagination parameters raise HTTPException."""
        # Arrange
        from fastapi import HTTPException

        mock_db = MagicMock(spec=AsyncSession)
        service = UserService(mock_db)

        # Mock validation to raise HTTPException
        mock_validate.side_effect = HTTPException(status_code=400, detail="Invalid page")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await service.get_all_users(page=-1, page_size=20)

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    @patch("src.core.pagination_helpers.validate_pagination")
    @patch("src.core.pagination_helpers.calculate_skip")
    @patch("src.core.pagination_helpers.calculate_total_pages")
    async def test_get_all_users_empty_result(self, mock_calc_pages, mock_calc_skip, mock_validate):
        """Test getting all users when database is empty."""
        # Arrange
        mock_db = MagicMock(spec=AsyncSession)
        service = UserService(mock_db)

        mock_validate.return_value = (1, 20)
        mock_calc_skip.return_value = 0
        mock_calc_pages.return_value = 0

        service.repository.get_all_with_count = AsyncMock(return_value=([], 0))

        # Act
        result = await service.get_all_users(page=1, page_size=20)

        # Assert
        assert result.total == 0
        assert result.total_pages == 0
        assert len(result.users) == 0


class TestUpdateUser:
    """Test update_user method."""

    @pytest.mark.asyncio
    async def test_update_user_name_success(self):
        """Test updating user full name."""
        # Arrange
        mock_db = MagicMock(spec=AsyncSession)
        mock_db.commit = AsyncMock()
        service = UserService(mock_db)

        user_id = uuid.uuid4()
        mock_user = create_mock_user(user_id=user_id, full_name="Old Name")

        service.repository.get_by_id = AsyncMock(return_value=mock_user)

        # Mock update to return updated user
        updated_user = create_mock_user(user_id=user_id, full_name="New Name")
        service.repository.update = AsyncMock(return_value=updated_user)

        update_data = UserUpdate(full_name="New Name")

        # Act
        result = await service.update_user(user_id, update_data)

        # Assert
        assert result.full_name == "New Name"
        service.repository.update.assert_awaited_once()
        mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_user_email_success(self):
        """Test updating user email."""
        # Arrange
        mock_db = MagicMock(spec=AsyncSession)
        mock_db.commit = AsyncMock()
        service = UserService(mock_db)

        user_id = uuid.uuid4()
        mock_user = create_mock_user(user_id=user_id, email="old@example.com")

        service.repository.get_by_id = AsyncMock(return_value=mock_user)

        updated_user = create_mock_user(user_id=user_id, email="new@example.com")
        service.repository.update = AsyncMock(return_value=updated_user)

        update_data = UserUpdate(email="new@example.com")

        # Act
        result = await service.update_user(user_id, update_data)

        # Assert
        assert result.email == "new@example.com"
        mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_user_timezone_change_logged(self):
        """Test that timezone changes are logged with logger.info."""
        # Arrange
        mock_db = MagicMock(spec=AsyncSession)
        mock_db.commit = AsyncMock()
        service = UserService(mock_db)

        user_id = uuid.uuid4()
        mock_user = create_mock_user(user_id=user_id, timezone="Europe/Paris")

        service.repository.get_by_id = AsyncMock(return_value=mock_user)

        updated_user = create_mock_user(user_id=user_id, timezone="America/New_York")
        service.repository.update = AsyncMock(return_value=updated_user)

        update_data = UserUpdate(timezone="America/New_York")

        # Act
        with patch("src.domains.users.service.logger") as mock_logger:
            result = await service.update_user(user_id, update_data)

            # Assert
            assert result.timezone == "America/New_York"
            # Verify logger.info was called with timezone change
            mock_logger.info.assert_called()
            call_args = str(mock_logger.info.call_args)
            assert "timezone" in call_args.lower()

    @pytest.mark.asyncio
    async def test_update_user_language_change_logged(self):
        """Test that language changes are logged with logger.info."""
        # Arrange
        mock_db = MagicMock(spec=AsyncSession)
        mock_db.commit = AsyncMock()
        service = UserService(mock_db)

        user_id = uuid.uuid4()
        mock_user = create_mock_user(user_id=user_id, language="fr")

        service.repository.get_by_id = AsyncMock(return_value=mock_user)

        updated_user = create_mock_user(user_id=user_id, language="en")
        service.repository.update = AsyncMock(return_value=updated_user)

        update_data = UserUpdate(language="en")

        # Act
        with patch("src.domains.users.service.logger") as mock_logger:
            result = await service.update_user(user_id, update_data)

            # Assert
            assert result.language == "en"
            # Verify logger.info was called with language change
            mock_logger.info.assert_called()
            call_args = str(mock_logger.info.call_args)
            assert "language" in call_args.lower()

    @pytest.mark.asyncio
    async def test_update_user_not_found_raises(self):
        """Test updating non-existent user raises HTTPException."""
        # Arrange
        from fastapi import HTTPException

        mock_db = MagicMock(spec=AsyncSession)
        service = UserService(mock_db)

        user_id = uuid.uuid4()
        service.repository.get_by_id = AsyncMock(return_value=None)

        update_data = UserUpdate(full_name="New Name")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await service.update_user(user_id, update_data)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_update_user_no_changes_returns_profile(self):
        """Test updating user with no changes returns current profile without calling update."""
        # Arrange
        mock_db = MagicMock(spec=AsyncSession)
        service = UserService(mock_db)

        user_id = uuid.uuid4()
        mock_user = create_mock_user(user_id=user_id, full_name="Test User")

        service.repository.get_by_id = AsyncMock(return_value=mock_user)
        service.repository.update = AsyncMock(return_value=mock_user)

        # Empty update (no fields changed)
        update_data = UserUpdate()

        # Act
        result = await service.update_user(user_id, update_data)

        # Assert
        assert result.full_name == "Test User"
        # Update should NOT be called when no fields changed (early return at line 148)
        service.repository.update.assert_not_awaited()


# ==============================================================================
# PHASE 3: TESTS ADMIN SEARCH (6 tests, 1h)
# ==============================================================================


class TestSearchUsers:
    """Test search_users method (admin search)."""

    @pytest.fixture(autouse=True)
    def _mock_batch_counts(self):
        """Mock batch count methods that require real DB access."""
        with patch.object(
            UserService, "_get_memory_counts_batch", new_callable=AsyncMock, return_value={}
        ):
            with patch.object(
                UserService, "_get_interests_counts_batch", new_callable=AsyncMock, return_value={}
            ):
                yield

    @pytest.mark.asyncio
    @patch("src.core.pagination_helpers.calculate_total_pages")
    async def test_search_users_by_email_query(self, mock_calc_pages):
        """Test searching users by email query."""
        # Arrange
        mock_db = MagicMock(spec=AsyncSession)
        service = UserService(mock_db)

        admin_user_id = uuid.uuid4()
        mock_users = [
            create_mock_user(email="john@example.com", full_name="John Doe"),
            create_mock_user(email="jane@example.com", full_name="Jane Doe"),
        ]
        total_count = 2

        mock_calc_pages.return_value = 1

        # Return tuples of (user, stats) where stats is None
        service.repository.get_users_with_stats_paginated = AsyncMock(
            return_value=[(u, None, 0, None, 0, 0, 0, 0, False, 0, 0) for u in mock_users]
        )
        service.repository.count_users = AsyncMock(return_value=total_count)

        search_params = UserSearchParams(q="example.com", page=1, page_size=20)

        # Act
        result = await service.search_users(search_params, admin_user_id)

        # Assert
        assert result.total == 2
        assert len(result.users) == 2
        service.repository.get_users_with_stats_paginated.assert_awaited_once()
        service.repository.count_users.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("src.core.pagination_helpers.calculate_total_pages")
    async def test_search_users_by_name_query(self, mock_calc_pages):
        """Test searching users by name query."""
        # Arrange
        mock_db = MagicMock(spec=AsyncSession)
        service = UserService(mock_db)

        admin_user_id = uuid.uuid4()
        mock_users = [create_mock_user(full_name="John Smith")]
        total_count = 1

        mock_calc_pages.return_value = 1

        service.repository.get_users_with_stats_paginated = AsyncMock(
            return_value=[(u, None, 0, None, 0, 0, 0, 0, False, 0, 0) for u in mock_users]
        )
        service.repository.count_users = AsyncMock(return_value=total_count)

        search_params = UserSearchParams(q="John", page=1, page_size=20)

        # Act
        result = await service.search_users(search_params, admin_user_id)

        # Assert
        assert result.total == 1
        assert result.users[0].full_name == "John Smith"

    @pytest.mark.asyncio
    @patch("src.core.pagination_helpers.calculate_total_pages")
    async def test_search_users_with_active_filter(self, mock_calc_pages):
        """Test filtering users by is_active=True."""
        # Arrange
        mock_db = MagicMock(spec=AsyncSession)
        service = UserService(mock_db)

        admin_user_id = uuid.uuid4()
        mock_users = [create_mock_user(email="active@example.com", is_active=True)]
        total_count = 1

        mock_calc_pages.return_value = 1

        service.repository.get_users_with_stats_paginated = AsyncMock(
            return_value=[(u, None, 0, None, 0, 0, 0, 0, False, 0, 0) for u in mock_users]
        )
        service.repository.count_users = AsyncMock(return_value=total_count)

        search_params = UserSearchParams(is_active=True, page=1, page_size=20)

        # Act
        result = await service.search_users(search_params, admin_user_id)

        # Assert
        assert result.total == 1
        assert result.users[0].is_active is True

    @pytest.mark.asyncio
    @patch("src.core.pagination_helpers.calculate_total_pages")
    async def test_search_users_with_verified_filter(self, mock_calc_pages):
        """Test filtering users by is_verified=True."""
        # Arrange
        mock_db = MagicMock(spec=AsyncSession)
        service = UserService(mock_db)

        admin_user_id = uuid.uuid4()
        mock_users = [create_mock_user(email="verified@example.com", is_verified=True)]
        total_count = 1

        mock_calc_pages.return_value = 1

        service.repository.get_users_with_stats_paginated = AsyncMock(
            return_value=[(u, None, 0, None, 0, 0, 0, 0, False, 0, 0) for u in mock_users]
        )
        service.repository.count_users = AsyncMock(return_value=total_count)

        search_params = UserSearchParams(is_verified=True, page=1, page_size=20)

        # Act
        result = await service.search_users(search_params, admin_user_id)

        # Assert
        assert result.total == 1
        assert result.users[0].is_verified is True

    @pytest.mark.asyncio
    @patch("src.core.pagination_helpers.calculate_total_pages")
    async def test_search_users_with_sorting(self, mock_calc_pages):
        """Test sorting users by email."""
        # Arrange
        mock_db = MagicMock(spec=AsyncSession)
        service = UserService(mock_db)

        admin_user_id = uuid.uuid4()
        mock_users = [
            create_mock_user(email="a@example.com"),
            create_mock_user(email="b@example.com"),
        ]
        total_count = 2

        mock_calc_pages.return_value = 1

        service.repository.get_users_with_stats_paginated = AsyncMock(
            return_value=[(u, None, 0, None, 0, 0, 0, 0, False, 0, 0) for u in mock_users]
        )
        service.repository.count_users = AsyncMock(return_value=total_count)

        search_params = UserSearchParams(page=1, page_size=20, sort_by="email", sort_order="asc")

        # Act
        result = await service.search_users(search_params, admin_user_id)

        # Assert
        assert result.total == 2
        # Verify sort_by and sort_order were passed to repository
        call_args = service.repository.get_users_with_stats_paginated.call_args
        assert call_args.kwargs["sort_by"] == "email"
        assert call_args.kwargs["sort_order"] == "asc"

    @pytest.mark.asyncio
    @patch("src.core.pagination_helpers.calculate_total_pages")
    async def test_search_users_no_results(self, mock_calc_pages):
        """Test searching with no matching results."""
        # Arrange
        mock_db = MagicMock(spec=AsyncSession)
        service = UserService(mock_db)

        admin_user_id = uuid.uuid4()
        total_count = 0

        mock_calc_pages.return_value = 0

        service.repository.get_users_with_stats_paginated = AsyncMock(return_value=[])
        service.repository.count_users = AsyncMock(return_value=total_count)

        search_params = UserSearchParams(q="nonexistent", page=1, page_size=20)

        # Act
        result = await service.search_users(search_params, admin_user_id)

        # Assert
        assert result.total == 0
        assert len(result.users) == 0


# ==============================================================================
# PHASE 4: TESTS ADMIN ACTIVATION (8 tests, 1h30-2h)
# ==============================================================================


class TestUpdateUserActivation:
    """Test update_user_activation method (admin actions)."""

    @pytest.mark.asyncio
    @patch("src.domains.users.service.get_email_service")
    async def test_update_user_activation_activate_success(self, mock_get_email):
        """Test activating user account."""
        # Arrange
        mock_db = MagicMock(spec=AsyncSession)
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        service = UserService(mock_db)

        user_id = uuid.uuid4()
        admin_user_id = uuid.uuid4()
        mock_user = create_mock_user(user_id=user_id, is_active=False)

        service.repository.get_by_id = AsyncMock(return_value=mock_user)
        service.repository.update = AsyncMock(return_value=mock_user)
        service.repository.create_audit_log = AsyncMock()

        # Mock email service
        mock_email_service = AsyncMock()
        mock_email_service.send_user_activated_notification = AsyncMock(return_value=True)
        mock_get_email.return_value = mock_email_service

        update_data = UserActivationUpdate(is_active=True)

        # Act
        result = await service.update_user_activation(
            user_id, update_data, admin_user_id, request=None
        )

        # Assert
        assert result.user.id == user_id
        assert result.email_notification_sent is True
        assert result.email_notification_error is None
        service.repository.create_audit_log.assert_awaited_once()
        mock_email_service.send_user_activated_notification.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("src.domains.users.service.get_email_service")
    async def test_update_user_activation_deactivate_success(self, mock_get_email):
        """Test deactivating user account."""
        # Arrange
        mock_db = MagicMock(spec=AsyncSession)
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        service = UserService(mock_db)

        user_id = uuid.uuid4()
        admin_user_id = uuid.uuid4()
        mock_user = create_mock_user(user_id=user_id, is_active=True)

        service.repository.get_by_id = AsyncMock(return_value=mock_user)
        service.repository.update = AsyncMock(return_value=mock_user)
        service.repository.create_audit_log = AsyncMock()
        service._invalidate_all_user_sessions = AsyncMock()

        # Mock email service
        mock_email_service = AsyncMock()
        mock_email_service.send_user_deactivated_notification = AsyncMock(return_value=True)
        mock_get_email.return_value = mock_email_service

        update_data = UserActivationUpdate(is_active=False, reason="Policy violation")

        # Act
        result = await service.update_user_activation(
            user_id, update_data, admin_user_id, request=None
        )

        # Assert
        assert result.user.id == user_id
        assert result.email_notification_sent is True
        service._invalidate_all_user_sessions.assert_awaited_once_with(user_id)

    @pytest.mark.asyncio
    @patch("src.infrastructure.email.get_email_service")
    async def test_update_user_activation_deactivate_invalidates_sessions(self, mock_get_email):
        """Test that deactivating user invalidates all sessions."""
        # Arrange
        mock_db = MagicMock(spec=AsyncSession)
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        service = UserService(mock_db)

        user_id = uuid.uuid4()
        admin_user_id = uuid.uuid4()
        mock_user = create_mock_user(user_id=user_id, is_active=True)

        service.repository.get_by_id = AsyncMock(return_value=mock_user)
        service.repository.update = AsyncMock(return_value=mock_user)
        service.repository.create_audit_log = AsyncMock()
        service._invalidate_all_user_sessions = AsyncMock()

        # Mock email service
        mock_email_service = AsyncMock()
        mock_email_service.send_user_deactivated_notification = AsyncMock(return_value=True)
        mock_get_email.return_value = mock_email_service

        update_data = UserActivationUpdate(is_active=False)

        # Act
        await service.update_user_activation(user_id, update_data, admin_user_id, request=None)

        # Assert
        # Verify session invalidation was called
        service._invalidate_all_user_sessions.assert_awaited_once_with(user_id)

    @pytest.mark.asyncio
    @patch("src.domains.users.service.get_email_service")
    async def test_update_user_activation_sends_email_deactivate(self, mock_get_email):
        """Test email is sent when deactivating user."""
        # Arrange
        mock_db = MagicMock(spec=AsyncSession)
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        service = UserService(mock_db)

        user_id = uuid.uuid4()
        admin_user_id = uuid.uuid4()
        mock_user = create_mock_user(
            user_id=user_id, email="user@example.com", full_name="Test User"
        )

        service.repository.get_by_id = AsyncMock(return_value=mock_user)
        service.repository.update = AsyncMock(return_value=mock_user)
        service.repository.create_audit_log = AsyncMock()
        service._invalidate_all_user_sessions = AsyncMock()

        # Mock email service
        mock_email_service = AsyncMock()
        mock_email_service.send_user_deactivated_notification = AsyncMock(return_value=True)
        mock_get_email.return_value = mock_email_service

        update_data = UserActivationUpdate(is_active=False, reason="Test reason")

        # Act
        result = await service.update_user_activation(
            user_id, update_data, admin_user_id, request=None
        )

        # Assert
        assert result.email_notification_sent is True
        mock_email_service.send_user_deactivated_notification.assert_awaited_once()
        # Verify email was sent with correct parameters
        call_args = mock_email_service.send_user_deactivated_notification.call_args
        assert call_args.kwargs["user_email"] == "user@example.com"
        assert call_args.kwargs["user_name"] == "Test User"
        assert call_args.kwargs["reason"] == "Test reason"

    @pytest.mark.asyncio
    @patch("src.domains.users.service.get_email_service")
    async def test_update_user_activation_sends_email_activate(self, mock_get_email):
        """Test email is sent when activating user."""
        # Arrange
        mock_db = MagicMock(spec=AsyncSession)
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        service = UserService(mock_db)

        user_id = uuid.uuid4()
        admin_user_id = uuid.uuid4()
        mock_user = create_mock_user(
            user_id=user_id, email="user@example.com", full_name="Test User"
        )

        service.repository.get_by_id = AsyncMock(return_value=mock_user)
        service.repository.update = AsyncMock(return_value=mock_user)
        service.repository.create_audit_log = AsyncMock()

        # Mock email service
        mock_email_service = AsyncMock()
        mock_email_service.send_user_activated_notification = AsyncMock(return_value=True)
        mock_get_email.return_value = mock_email_service

        update_data = UserActivationUpdate(is_active=True)

        # Act
        result = await service.update_user_activation(
            user_id, update_data, admin_user_id, request=None
        )

        # Assert
        assert result.email_notification_sent is True
        mock_email_service.send_user_activated_notification.assert_awaited_once()
        # Verify email was sent with correct parameters
        call_args = mock_email_service.send_user_activated_notification.call_args
        assert call_args.kwargs["user_email"] == "user@example.com"
        assert call_args.kwargs["user_name"] == "Test User"

    @pytest.mark.asyncio
    @patch("src.domains.users.service.get_email_service")
    async def test_update_user_activation_email_failure_tracked(self, mock_get_email):
        """Test email failure is tracked in response."""
        # Arrange
        mock_db = MagicMock(spec=AsyncSession)
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        service = UserService(mock_db)

        user_id = uuid.uuid4()
        admin_user_id = uuid.uuid4()
        mock_user = create_mock_user(user_id=user_id)

        service.repository.get_by_id = AsyncMock(return_value=mock_user)
        service.repository.update = AsyncMock(return_value=mock_user)
        service.repository.create_audit_log = AsyncMock()

        # Mock email service to fail
        mock_email_service = AsyncMock()
        mock_email_service.send_user_activated_notification = AsyncMock(return_value=False)
        mock_get_email.return_value = mock_email_service

        update_data = UserActivationUpdate(is_active=True)

        # Act
        result = await service.update_user_activation(
            user_id, update_data, admin_user_id, request=None
        )

        # Assert
        assert result.email_notification_sent is False
        assert result.email_notification_error is not None

    @pytest.mark.asyncio
    async def test_update_user_activation_creates_audit_log(self):
        """Test that audit log is created with correct details."""
        # Arrange

        mock_db = MagicMock(spec=AsyncSession)
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        service = UserService(mock_db)

        user_id = uuid.uuid4()
        admin_user_id = uuid.uuid4()
        mock_user = create_mock_user(user_id=user_id, email="user@example.com")

        service.repository.get_by_id = AsyncMock(return_value=mock_user)
        service.repository.update = AsyncMock(return_value=mock_user)
        service.repository.create_audit_log = AsyncMock()

        # Mock email service
        with patch("src.domains.users.service.get_email_service") as mock_get_email:
            mock_email_service = AsyncMock()
            mock_email_service.send_user_activated_notification = AsyncMock(return_value=True)
            mock_get_email.return_value = mock_email_service

            # Mock Request object (don't use spec=Request as it makes mock falsy)
            mock_request = MagicMock()
            mock_request.client = MagicMock()
            mock_request.client.host = "127.0.0.1"
            mock_headers = MagicMock()
            mock_headers.get = MagicMock(return_value="Mozilla/5.0")
            mock_request.headers = mock_headers

            update_data = UserActivationUpdate(is_active=True)

            # Act
            await service.update_user_activation(
                user_id, update_data, admin_user_id, request=mock_request
            )

            # Assert
            service.repository.create_audit_log.assert_awaited_once()
            call_args = service.repository.create_audit_log.call_args
            assert call_args.kwargs["admin_user_id"] == admin_user_id
            assert call_args.kwargs["action"] == "user_activated"
            assert call_args.kwargs["resource_type"] == "user"
            assert call_args.kwargs["resource_id"] == user_id
            assert call_args.kwargs["ip_address"] == "127.0.0.1"
            assert call_args.kwargs["user_agent"] == "Mozilla/5.0"

    @pytest.mark.asyncio
    async def test_update_user_activation_not_found_raises(self):
        """Test updating activation for non-existent user raises exception."""
        # Arrange
        from fastapi import HTTPException

        mock_db = MagicMock(spec=AsyncSession)
        service = UserService(mock_db)

        user_id = uuid.uuid4()
        admin_user_id = uuid.uuid4()

        service.repository.get_by_id = AsyncMock(return_value=None)

        update_data = UserActivationUpdate(is_active=False)

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await service.update_user_activation(user_id, update_data, admin_user_id, request=None)

        assert exc_info.value.status_code == 404


# ==============================================================================
# PHASE 5: TESTS GDPR + INFRASTRUCTURE (11 tests, 1h30-2h)
# ==============================================================================


class TestDeleteUserGDPR:
    """Test delete_user_gdpr method (GDPR compliance)."""

    @pytest.mark.asyncio
    @patch("src.domains.users.service.get_redis_session")
    async def test_delete_user_gdpr_success(self, mock_get_redis):
        """Test GDPR deletion with full cascade."""
        # Arrange
        mock_db = MagicMock(spec=AsyncSession)
        mock_db.commit = AsyncMock()
        service = UserService(mock_db)

        user_id = uuid.uuid4()
        admin_user_id = uuid.uuid4()
        mock_user = create_mock_user(user_id=user_id, email="user@example.com", is_superuser=False)
        mock_user.deleted_at = datetime.now(UTC)  # Must be soft-deleted first

        service.repository.get_by_id = AsyncMock(return_value=mock_user)
        service.repository.count_user_connectors = AsyncMock(return_value=3)
        service.repository.create_audit_log = AsyncMock()
        service.repository.hard_delete = AsyncMock()

        # Mock Redis for session invalidation
        mock_redis = AsyncMock()
        mock_redis.scan = AsyncMock(return_value=(0, []))
        mock_get_redis.return_value = mock_redis

        # Act
        await service.delete_user_gdpr(user_id, admin_user_id, request=None)

        # Assert
        service.repository.create_audit_log.assert_awaited_once()
        call_args = service.repository.create_audit_log.call_args
        assert call_args.kwargs["action"] == "user_deleted_gdpr"
        assert call_args.kwargs["details"]["had_connectors"] == 3
        service.repository.hard_delete.assert_awaited_once_with(mock_user)
        mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_user_gdpr_not_found_raises(self):
        """Test GDPR deletion raises when user not found."""
        # Arrange
        from fastapi import HTTPException

        mock_db = MagicMock(spec=AsyncSession)
        service = UserService(mock_db)

        user_id = uuid.uuid4()
        admin_user_id = uuid.uuid4()

        service.repository.get_by_id = AsyncMock(return_value=None)

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await service.delete_user_gdpr(user_id, admin_user_id, request=None)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_user_gdpr_superuser_rejected(self):
        """Test GDPR deletion rejects superusers."""
        # Arrange
        from fastapi import HTTPException

        mock_db = MagicMock(spec=AsyncSession)
        service = UserService(mock_db)

        user_id = uuid.uuid4()
        admin_user_id = uuid.uuid4()
        mock_user = create_mock_user(user_id=user_id, is_superuser=True)

        service.repository.get_by_id = AsyncMock(return_value=mock_user)

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await service.delete_user_gdpr(user_id, admin_user_id, request=None)

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    @patch("src.domains.users.service.get_redis_session")
    async def test_delete_user_gdpr_invalidates_sessions(self, mock_get_redis):
        """Test GDPR deletion invalidates all user sessions."""
        # Arrange
        mock_db = MagicMock(spec=AsyncSession)
        mock_db.commit = AsyncMock()
        service = UserService(mock_db)

        user_id = uuid.uuid4()
        admin_user_id = uuid.uuid4()
        mock_user = create_mock_user(user_id=user_id, is_superuser=False)
        mock_user.deleted_at = datetime.now(UTC)  # Must be soft-deleted first

        service.repository.get_by_id = AsyncMock(return_value=mock_user)
        service.repository.count_user_connectors = AsyncMock(return_value=0)
        service.repository.create_audit_log = AsyncMock()
        service.repository.hard_delete = AsyncMock()

        # Mock Redis session invalidation
        mock_redis = AsyncMock()
        mock_redis.scan = AsyncMock(return_value=(0, [b"session:123"]))
        mock_redis.type = AsyncMock(return_value="string")
        mock_redis.get = AsyncMock(return_value='{"user_id": "' + str(user_id) + '"}')
        mock_redis.pipeline = MagicMock()
        mock_pipeline = AsyncMock()
        mock_pipeline.delete = MagicMock()
        mock_pipeline.execute = AsyncMock(return_value=[1])
        mock_redis.pipeline.return_value = mock_pipeline
        mock_get_redis.return_value = mock_redis

        # Act
        await service.delete_user_gdpr(user_id, admin_user_id, request=None)

        # Assert - Verify session invalidation was called
        mock_redis.scan.assert_awaited()
        mock_pipeline.execute.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("src.domains.users.service.get_redis_session")
    async def test_delete_user_gdpr_creates_audit_log(self, mock_get_redis):
        """Test GDPR deletion creates detailed audit log."""
        # Arrange
        mock_db = MagicMock(spec=AsyncSession)
        mock_db.commit = AsyncMock()
        service = UserService(mock_db)

        user_id = uuid.uuid4()
        admin_user_id = uuid.uuid4()
        mock_user = create_mock_user(
            user_id=user_id,
            email="user@example.com",
            full_name="Test User",
            is_verified=True,
            is_active=True,
        )
        mock_user.deleted_at = datetime.now(UTC)  # Must be soft-deleted first

        service.repository.get_by_id = AsyncMock(return_value=mock_user)
        service.repository.count_user_connectors = AsyncMock(return_value=5)
        service.repository.create_audit_log = AsyncMock()
        service.repository.hard_delete = AsyncMock()

        # Mock Redis
        mock_redis = AsyncMock()
        mock_redis.scan = AsyncMock(return_value=(0, []))
        mock_get_redis.return_value = mock_redis

        # Act
        await service.delete_user_gdpr(user_id, admin_user_id, request=None)

        # Assert
        service.repository.create_audit_log.assert_awaited_once()
        call_args = service.repository.create_audit_log.call_args
        assert call_args.kwargs["action"] == "user_deleted_gdpr"
        assert call_args.kwargs["resource_type"] == "user"
        assert call_args.kwargs["resource_id"] == user_id
        assert call_args.kwargs["admin_user_id"] == admin_user_id
        details = call_args.kwargs["details"]
        assert details["user_email"] == "user@example.com"
        assert details["user_name"] == "Test User"
        assert details["had_connectors"] == 5
        assert details["was_verified"] is True
        assert details["was_active"] is True

    @pytest.mark.asyncio
    @patch("src.domains.users.service.get_redis_session")
    async def test_delete_user_gdpr_counts_connectors(self, mock_get_redis):
        """Test GDPR deletion counts connectors before deletion."""
        # Arrange
        mock_db = MagicMock(spec=AsyncSession)
        mock_db.commit = AsyncMock()
        service = UserService(mock_db)

        user_id = uuid.uuid4()
        admin_user_id = uuid.uuid4()
        mock_user = create_mock_user(user_id=user_id)
        mock_user.deleted_at = datetime.now(UTC)  # Must be soft-deleted first

        service.repository.get_by_id = AsyncMock(return_value=mock_user)
        service.repository.count_user_connectors = AsyncMock(return_value=7)
        service.repository.create_audit_log = AsyncMock()
        service.repository.hard_delete = AsyncMock()

        # Mock Redis
        mock_redis = AsyncMock()
        mock_redis.scan = AsyncMock(return_value=(0, []))
        mock_get_redis.return_value = mock_redis

        # Act
        await service.delete_user_gdpr(user_id, admin_user_id, request=None)

        # Assert
        service.repository.count_user_connectors.assert_awaited_once_with(user_id)
        call_args = service.repository.create_audit_log.call_args
        assert call_args.kwargs["details"]["had_connectors"] == 7


class TestInvalidateAllUserSessions:
    """Test _invalidate_all_user_sessions method (Redis operations)."""

    @pytest.mark.asyncio
    @patch("src.domains.users.service.get_redis_session")
    async def test_invalidate_all_user_sessions_single_session(self, mock_get_redis):
        """Test invalidating a single user session."""
        # Arrange
        mock_db = MagicMock(spec=AsyncSession)
        service = UserService(mock_db)

        user_id = uuid.uuid4()

        # Mock Redis
        mock_redis = AsyncMock()
        mock_redis.scan = AsyncMock(return_value=(0, [b"session:abc123"]))
        mock_redis.type = AsyncMock(return_value="string")
        mock_redis.get = AsyncMock(return_value='{"user_id": "' + str(user_id) + '"}')
        mock_redis.pipeline = MagicMock()
        mock_pipeline = AsyncMock()
        mock_pipeline.delete = MagicMock()
        mock_pipeline.execute = AsyncMock(return_value=[1])
        mock_redis.pipeline.return_value = mock_pipeline
        mock_get_redis.return_value = mock_redis

        # Act
        await service._invalidate_all_user_sessions(user_id)

        # Assert
        mock_redis.scan.assert_awaited_once()
        mock_pipeline.delete.assert_called_once_with(b"session:abc123")
        mock_pipeline.execute.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("src.domains.users.service.get_redis_session")
    async def test_invalidate_all_user_sessions_multiple_sessions(self, mock_get_redis):
        """Test invalidating multiple user sessions."""
        # Arrange
        mock_db = MagicMock(spec=AsyncSession)
        service = UserService(mock_db)

        user_id = uuid.uuid4()

        # Mock Redis with 2 sessions
        mock_redis = AsyncMock()
        mock_redis.scan = AsyncMock(return_value=(0, [b"session:abc123", b"session:def456"]))
        mock_redis.type = AsyncMock(return_value="string")
        mock_redis.get = AsyncMock(return_value='{"user_id": "' + str(user_id) + '"}')
        mock_redis.pipeline = MagicMock()
        mock_pipeline = AsyncMock()
        mock_pipeline.delete = MagicMock()
        mock_pipeline.execute = AsyncMock(return_value=[1, 1])
        mock_redis.pipeline.return_value = mock_pipeline
        mock_get_redis.return_value = mock_redis

        # Act
        await service._invalidate_all_user_sessions(user_id)

        # Assert
        assert mock_pipeline.delete.call_count == 2
        mock_pipeline.execute.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("src.domains.users.service.get_redis_session")
    async def test_invalidate_all_user_sessions_no_sessions(self, mock_get_redis):
        """Test invalidating when user has no sessions."""
        # Arrange
        mock_db = MagicMock(spec=AsyncSession)
        service = UserService(mock_db)

        user_id = uuid.uuid4()

        # Mock Redis with no matching sessions
        mock_redis = AsyncMock()
        mock_redis.scan = AsyncMock(return_value=(0, []))
        mock_get_redis.return_value = mock_redis

        # Act
        await service._invalidate_all_user_sessions(user_id)

        # Assert - Should not error, pipeline not executed
        mock_redis.scan.assert_awaited_once()
        # Pipeline should not be created if no keys
        mock_redis.pipeline.assert_not_called()

    @pytest.mark.asyncio
    @patch("src.domains.users.service.get_redis_session")
    async def test_invalidate_all_user_sessions_redis_error_handled(self, mock_get_redis):
        """Test Redis errors are caught and logged."""
        # Arrange
        mock_db = MagicMock(spec=AsyncSession)
        service = UserService(mock_db)

        user_id = uuid.uuid4()

        # Mock Redis to raise exception
        mock_redis = AsyncMock()
        mock_redis.scan = AsyncMock(side_effect=Exception("Redis connection failed"))
        mock_get_redis.return_value = mock_redis

        # Act - Should not raise, errors are logged
        await service._invalidate_all_user_sessions(user_id)

        # Assert
        mock_redis.scan.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("src.domains.users.service.get_redis_session")
    async def test_invalidate_all_user_sessions_skip_non_string_keys(self, mock_get_redis):
        """Test skipping non-string Redis keys (e.g., SETs)."""
        # Arrange
        mock_db = MagicMock(spec=AsyncSession)
        service = UserService(mock_db)

        user_id = uuid.uuid4()

        # Mock Redis with mixed key types
        mock_redis = AsyncMock()
        mock_redis.scan = AsyncMock(return_value=(0, [b"session:abc123", b"session:user_tokens"]))
        # First key is string, second is set
        mock_redis.type = AsyncMock(side_effect=["string", "set"])
        mock_redis.get = AsyncMock(return_value='{"user_id": "' + str(user_id) + '"}')
        mock_redis.pipeline = MagicMock()
        mock_pipeline = AsyncMock()
        mock_pipeline.delete = MagicMock()
        mock_pipeline.execute = AsyncMock(return_value=[1])
        mock_redis.pipeline.return_value = mock_pipeline
        mock_get_redis.return_value = mock_redis

        # Act
        await service._invalidate_all_user_sessions(user_id)

        # Assert - Only 1 key deleted (the string key)
        mock_pipeline.delete.assert_called_once_with(b"session:abc123")
