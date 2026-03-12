"""
Comprehensive unit tests for UserService.

Coverage target: 85%+ from 16%

This test suite covers:
- get_user_by_id: User retrieval and not found handling
- get_all_users: Pagination, filtering by is_active
- update_user: Profile updates, timezone changes, no-op updates
- delete_user: Soft delete and hard delete
- search_users_by_email: Email pattern search
- search_users: Admin search with filters and sorting
- update_user_activation: Activate/deactivate with audit logs and email
- delete_user_gdpr: GDPR-compliant deletion with cascade
- _invalidate_all_user_sessions: Redis session invalidation
- Error handling and edge cases
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.auth.models import User
from src.domains.users.models import AdminAuditLog
from src.domains.users.schemas import (
    UserActivationResponse,
    UserActivationUpdate,
    UserListResponse,
    UserListWithStatsResponse,
    UserProfile,
    UserSearchParams,
    UserUpdate,
)
from src.domains.users.service import UserService
from tests.fixtures.factories import UserFactory

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_db() -> AsyncMock:
    """Create mock database session."""
    db = AsyncMock(spec=AsyncSession)
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    return db


@pytest.fixture
def mock_repository() -> AsyncMock:
    """Create mock repository."""
    repo = AsyncMock()
    return repo


@pytest.fixture
def service(mock_db: AsyncMock, mock_repository: AsyncMock) -> UserService:
    """Create service instance with mocked repository."""
    service = UserService(mock_db)
    service.repository = mock_repository
    return service


@pytest.fixture
def sample_user() -> User:
    """Create sample user for testing."""
    user = UserFactory.create(
        email="test@example.com",
        full_name="Test User",
        is_active=True,
        is_verified=True,
    )
    user.id = uuid4()
    user.timezone = "Europe/Paris"
    user.created_at = datetime.now(UTC)
    user.updated_at = datetime.now(UTC)
    return user


@pytest.fixture
def admin_user() -> User:
    """Create admin user for testing."""
    user = UserFactory.create_superuser(
        email="admin@example.com",
        full_name="Admin User",
    )
    user.id = uuid4()
    user.timezone = "Europe/Paris"
    user.created_at = datetime.now(UTC)
    user.updated_at = datetime.now(UTC)
    return user


@pytest.fixture
def mock_request() -> MagicMock:
    """Create mock FastAPI request."""
    request = MagicMock()  # Don't use spec=Request as it breaks attribute assignment
    # Properly configure client mock
    client_mock = MagicMock()
    client_mock.host = "192.168.1.100"
    request.client = client_mock
    # Use MagicMock for headers to support .get() method
    headers_mock = MagicMock()
    headers_mock.get.return_value = "Mozilla/5.0 Test"
    request.headers = headers_mock
    return request


# ============================================================================
# Test: get_user_by_id
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.unit
class TestGetUserById:
    """Test UserService.get_user_by_id()"""

    async def test_get_user_by_id_success(self, service, mock_repository, sample_user):
        """Test successfully getting user by ID."""
        # Arrange
        mock_repository.get_by_id.return_value = sample_user

        # Act
        result = await service.get_user_by_id(sample_user.id)

        # Assert
        assert isinstance(result, UserProfile)
        assert result.id == sample_user.id
        assert result.email == sample_user.email
        assert result.full_name == sample_user.full_name
        mock_repository.get_by_id.assert_called_once_with(sample_user.id)

    async def test_get_user_by_id_not_found(self, service, mock_repository):
        """Test getting non-existent user raises HTTPException."""
        # Arrange
        user_id = uuid4()
        mock_repository.get_by_id.return_value = None

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await service.get_user_by_id(user_id)

        assert exc_info.value.status_code == 404
        assert "not found" in str(exc_info.value.detail).lower()
        mock_repository.get_by_id.assert_called_once_with(user_id)

    async def test_get_user_by_id_validates_profile(self, service, mock_repository, sample_user):
        """Test that returned user is validated as UserProfile."""
        # Arrange
        mock_repository.get_by_id.return_value = sample_user

        # Act
        result = await service.get_user_by_id(sample_user.id)

        # Assert
        assert isinstance(result, UserProfile)
        assert hasattr(result, "id")
        assert hasattr(result, "email")
        assert hasattr(result, "is_active")
        assert hasattr(result, "is_verified")


# ============================================================================
# Test: get_all_users
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.unit
class TestGetAllUsers:
    """Test UserService.get_all_users()"""

    async def test_get_all_users_default_pagination(self, service, mock_repository, sample_user):
        """Test getting all users with default pagination."""
        # Arrange
        users = [sample_user]
        mock_repository.get_all_with_count.return_value = (users, 1)

        # Act
        result = await service.get_all_users()

        # Assert
        assert isinstance(result, UserListResponse)
        assert result.total == 1
        assert len(result.users) == 1
        assert result.page == 1
        assert result.page_size == 50
        assert result.total_pages == 1
        mock_repository.get_all_with_count.assert_called_once()

    async def test_get_all_users_custom_pagination(self, service, mock_repository, sample_user):
        """Test getting users with custom pagination."""
        # Arrange
        users = [sample_user]
        mock_repository.get_all_with_count.return_value = (users, 25)

        # Act
        result = await service.get_all_users(page=2, page_size=10)

        # Assert
        assert result.total == 25
        assert result.page == 2
        assert result.page_size == 10
        assert result.total_pages == 3  # ceil(25/10)

    async def test_get_all_users_filter_active(self, service, mock_repository, sample_user):
        """Test filtering users by active status."""
        # Arrange
        users = [sample_user]
        mock_repository.get_all_with_count.return_value = (users, 1)

        # Act
        result = await service.get_all_users(is_active=True)

        # Assert
        assert result.total == 1
        call_args = mock_repository.get_all_with_count.call_args
        assert call_args.kwargs["is_active"] is True

    async def test_get_all_users_filter_inactive(self, service, mock_repository):
        """Test filtering users by inactive status."""
        # Arrange
        inactive_user = UserFactory.create(is_active=False)
        inactive_user.id = uuid4()
        inactive_user.timezone = "Europe/Paris"
        inactive_user.created_at = datetime.now(UTC)
        inactive_user.updated_at = datetime.now(UTC)
        mock_repository.get_all_with_count.return_value = ([inactive_user], 1)

        # Act
        result = await service.get_all_users(is_active=False)

        # Assert
        assert result.total == 1
        assert result.users[0].is_active is False

    async def test_get_all_users_empty(self, service, mock_repository):
        """Test getting users when none exist."""
        # Arrange
        mock_repository.get_all_with_count.return_value = ([], 0)

        # Act
        result = await service.get_all_users()

        # Assert
        assert result.total == 0
        assert len(result.users) == 0
        assert result.total_pages == 0

    async def test_get_all_users_many_pages(self, service, mock_repository, sample_user):
        """Test pagination calculation with many users."""
        # Arrange
        users = [sample_user] * 10
        mock_repository.get_all_with_count.return_value = (users, 250)

        # Act
        result = await service.get_all_users(page=3, page_size=10)

        # Assert
        assert result.total == 250
        assert result.page == 3
        assert result.total_pages == 25  # ceil(250/10)


# ============================================================================
# Test: update_user
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.unit
class TestUpdateUser:
    """Test UserService.update_user()"""

    async def test_update_user_success(self, service, mock_repository, mock_db, sample_user):
        """Test successfully updating user."""
        # Arrange
        updated_user = sample_user
        updated_user.full_name = "Updated Name"
        mock_repository.get_by_id.return_value = sample_user
        mock_repository.update.return_value = updated_user

        update_data = UserUpdate(full_name="Updated Name")

        # Act
        result = await service.update_user(sample_user.id, update_data)

        # Assert
        assert isinstance(result, UserProfile)
        assert result.full_name == "Updated Name"
        mock_repository.get_by_id.assert_called_once_with(sample_user.id)
        mock_repository.update.assert_called_once()
        mock_db.commit.assert_called_once()

    async def test_update_user_not_found(self, service, mock_repository):
        """Test updating non-existent user raises HTTPException."""
        # Arrange
        user_id = uuid4()
        mock_repository.get_by_id.return_value = None
        update_data = UserUpdate(full_name="New Name")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await service.update_user(user_id, update_data)

        assert exc_info.value.status_code == 404
        mock_repository.update.assert_not_called()

    async def test_update_user_email(self, service, mock_repository, mock_db, sample_user):
        """Test updating user email."""
        # Arrange
        updated_user = sample_user
        updated_user.email = "newemail@example.com"
        mock_repository.get_by_id.return_value = sample_user
        mock_repository.update.return_value = updated_user

        update_data = UserUpdate(email="newemail@example.com")

        # Act
        result = await service.update_user(sample_user.id, update_data)

        # Assert
        assert result.email == "newemail@example.com"
        update_call_args = mock_repository.update.call_args[0]
        assert update_call_args[1]["email"] == "newemail@example.com"

    async def test_update_user_timezone(self, service, mock_repository, mock_db, sample_user):
        """Test updating user timezone triggers special logging."""
        # Arrange
        old_timezone = sample_user.timezone
        updated_user = sample_user
        updated_user.timezone = "America/New_York"
        mock_repository.get_by_id.return_value = sample_user
        mock_repository.update.return_value = updated_user

        update_data = UserUpdate(timezone="America/New_York")

        # Act
        with patch("src.domains.users.service.logger") as mock_logger:
            result = await service.update_user(sample_user.id, update_data)

            # Assert
            assert result.timezone == "America/New_York"
            # Verify special logging for timezone change
            log_call = mock_logger.info.call_args
            # Check that timezone change fields are present in log
            assert log_call[1].get("timezone_changed") == "true" or "timezone" in log_call[1].get(
                "fields", []
            )
            if "timezone_changed" in log_call[1]:
                assert log_call[1]["old_timezone"] == old_timezone
                assert log_call[1]["new_timezone"] == "America/New_York"

    async def test_update_user_timezone_no_change(
        self, service, mock_repository, mock_db, sample_user
    ):
        """Test updating user with same timezone doesn't trigger special logging."""
        # Arrange
        mock_repository.get_by_id.return_value = sample_user
        mock_repository.update.return_value = sample_user

        # Update with same timezone
        update_data = UserUpdate(timezone=sample_user.timezone)

        # Act
        with patch("src.domains.users.service.logger") as mock_logger:
            await service.update_user(sample_user.id, update_data)

            # Assert
            log_call = mock_logger.info.call_args
            assert "timezone_changed" not in log_call[1]

    async def test_update_user_picture_url(self, service, mock_repository, mock_db, sample_user):
        """Test updating user picture URL."""
        # Arrange
        updated_user = sample_user
        updated_user.picture_url = "https://example.com/avatar.jpg"
        mock_repository.get_by_id.return_value = sample_user
        mock_repository.update.return_value = updated_user

        update_data = UserUpdate(picture_url="https://example.com/avatar.jpg")

        # Act
        result = await service.update_user(sample_user.id, update_data)

        # Assert
        assert result.picture_url == "https://example.com/avatar.jpg"

    async def test_update_user_no_fields(self, service, mock_repository, sample_user):
        """Test updating user with no fields returns unchanged user."""
        # Arrange
        mock_repository.get_by_id.return_value = sample_user
        update_data = UserUpdate()

        # Act
        result = await service.update_user(sample_user.id, update_data)

        # Assert
        assert result.id == sample_user.id
        # Should not call update or commit for no-op
        mock_repository.update.assert_not_called()

    async def test_update_user_multiple_fields(
        self, service, mock_repository, mock_db, sample_user
    ):
        """Test updating multiple user fields at once."""
        # Arrange
        updated_user = sample_user
        updated_user.full_name = "New Name"
        updated_user.timezone = "Asia/Tokyo"
        mock_repository.get_by_id.return_value = sample_user
        mock_repository.update.return_value = updated_user

        update_data = UserUpdate(full_name="New Name", timezone="Asia/Tokyo")

        # Act
        result = await service.update_user(sample_user.id, update_data)

        # Assert
        assert result.full_name == "New Name"
        assert result.timezone == "Asia/Tokyo"
        update_call_args = mock_repository.update.call_args[0]
        assert "full_name" in update_call_args[1]
        assert "timezone" in update_call_args[1]


# ============================================================================
# Test: delete_user
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.unit
class TestDeleteUser:
    """Test UserService.delete_user()"""

    async def test_delete_user_soft_delete(self, service, mock_repository, mock_db, sample_user):
        """Test soft deleting user (default behavior)."""
        # Arrange
        mock_repository.get_by_id.return_value = sample_user

        # Act
        await service.delete_user(sample_user.id)

        # Assert
        mock_repository.delete.assert_called_once_with(sample_user)
        mock_repository.hard_delete.assert_not_called()
        mock_db.commit.assert_called_once()

    async def test_delete_user_hard_delete(self, service, mock_repository, mock_db, sample_user):
        """Test hard deleting user (permanent)."""
        # Arrange
        mock_repository.get_by_id.return_value = sample_user

        # Act
        await service.delete_user(sample_user.id, hard_delete=True)

        # Assert
        mock_repository.hard_delete.assert_called_once_with(sample_user)
        mock_repository.delete.assert_not_called()
        mock_db.commit.assert_called_once()

    async def test_delete_user_not_found(self, service, mock_repository):
        """Test deleting non-existent user raises HTTPException."""
        # Arrange
        user_id = uuid4()
        mock_repository.get_by_id.return_value = None

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await service.delete_user(user_id)

        assert exc_info.value.status_code == 404
        mock_repository.delete.assert_not_called()

    async def test_delete_user_logs_soft_delete(
        self, service, mock_repository, mock_db, sample_user
    ):
        """Test soft delete logs appropriately."""
        # Arrange
        mock_repository.get_by_id.return_value = sample_user

        # Act
        with patch("src.domains.users.service.logger") as mock_logger:
            await service.delete_user(sample_user.id, hard_delete=False)

            # Assert
            mock_logger.info.assert_called_once()
            assert "user_soft_deleted" in mock_logger.info.call_args[0]

    async def test_delete_user_logs_hard_delete(
        self, service, mock_repository, mock_db, sample_user
    ):
        """Test hard delete logs appropriately."""
        # Arrange
        mock_repository.get_by_id.return_value = sample_user

        # Act
        with patch("src.domains.users.service.logger") as mock_logger:
            await service.delete_user(sample_user.id, hard_delete=True)

            # Assert
            mock_logger.info.assert_called_once()
            assert "user_hard_deleted" in mock_logger.info.call_args[0]


# ============================================================================
# Test: search_users_by_email
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.unit
class TestSearchUsersByEmail:
    """Test UserService.search_users_by_email()"""

    async def test_search_users_by_email_found(self, service, mock_repository, sample_user):
        """Test searching users by email pattern."""
        # Arrange
        mock_repository.search_by_email.return_value = [sample_user]

        # Act
        result = await service.search_users_by_email("test@example.com")

        # Assert
        assert len(result) == 1
        assert isinstance(result[0], UserProfile)
        assert result[0].email == sample_user.email
        mock_repository.search_by_email.assert_called_once_with("test@example.com")

    async def test_search_users_by_email_pattern(self, service, mock_repository, sample_user):
        """Test searching users by email pattern with wildcard."""
        # Arrange
        mock_repository.search_by_email.return_value = [sample_user]

        # Act
        result = await service.search_users_by_email("%@example.com")

        # Assert
        assert len(result) == 1
        mock_repository.search_by_email.assert_called_once_with("%@example.com")

    async def test_search_users_by_email_not_found(self, service, mock_repository):
        """Test searching users returns empty list when not found."""
        # Arrange
        mock_repository.search_by_email.return_value = []

        # Act
        result = await service.search_users_by_email("nonexistent@example.com")

        # Assert
        assert len(result) == 0
        assert isinstance(result, list)

    async def test_search_users_by_email_multiple(self, service, mock_repository, sample_user):
        """Test searching users returns multiple matches."""
        # Arrange
        user2 = UserFactory.create(email="test2@example.com")
        user2.id = uuid4()
        user2.timezone = "Europe/Paris"
        user2.created_at = datetime.now(UTC)
        user2.updated_at = datetime.now(UTC)
        mock_repository.search_by_email.return_value = [sample_user, user2]

        # Act
        result = await service.search_users_by_email("%@example.com")

        # Assert
        assert len(result) == 2
        emails = {user.email for user in result}
        assert sample_user.email in emails
        assert user2.email in emails


# ============================================================================
# Test: search_users (Admin)
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.unit
class TestSearchUsersAdmin:
    """Test UserService.search_users() - Admin search"""

    async def test_search_users_basic(self, service, mock_repository, sample_user, admin_user):
        """Test basic admin user search."""
        # Arrange
        mock_repository.get_users_with_stats_paginated.return_value = [(sample_user, None, 0, None)]
        mock_repository.count_users.return_value = 1

        params = UserSearchParams(page=1, page_size=10)

        # Act
        result = await service.search_users(params, admin_user.id)

        # Assert
        assert isinstance(result, UserListWithStatsResponse)
        assert result.total == 1
        assert len(result.users) == 1
        assert result.page == 1
        assert result.page_size == 10

    async def test_search_users_with_query(self, service, mock_repository, sample_user, admin_user):
        """Test searching users with query string."""
        # Arrange
        mock_repository.get_users_with_stats_paginated.return_value = [(sample_user, None, 0, None)]
        mock_repository.count_users.return_value = 1

        params = UserSearchParams(q="test@example.com", page=1, page_size=10)

        # Act
        result = await service.search_users(params, admin_user.id)

        # Assert
        assert len(result.users) == 1
        # Verify filters were built correctly
        call_args = mock_repository.get_users_with_stats_paginated.call_args
        assert "filters" in call_args.kwargs
        assert len(call_args.kwargs["filters"]) > 0

    async def test_search_users_filter_active(
        self, service, mock_repository, sample_user, admin_user
    ):
        """Test searching users filtered by active status."""
        # Arrange
        mock_repository.get_users_with_stats_paginated.return_value = [(sample_user, None, 0, None)]
        mock_repository.count_users.return_value = 1

        params = UserSearchParams(is_active=True, page=1, page_size=10)

        # Act
        result = await service.search_users(params, admin_user.id)

        # Assert
        assert result.total == 1
        call_args = mock_repository.get_users_with_stats_paginated.call_args
        filters = call_args.kwargs["filters"]
        assert len(filters) >= 1

    async def test_search_users_filter_verified(
        self, service, mock_repository, sample_user, admin_user
    ):
        """Test searching users filtered by verified status."""
        # Arrange
        mock_repository.get_users_with_stats_paginated.return_value = [(sample_user, None, 0, None)]
        mock_repository.count_users.return_value = 1

        params = UserSearchParams(is_verified=True, page=1, page_size=10)

        # Act
        result = await service.search_users(params, admin_user.id)

        # Assert
        assert result.total == 1

    async def test_search_users_filter_superuser(self, service, mock_repository, admin_user):
        """Test searching users filtered by superuser status."""
        # Arrange
        mock_repository.get_users_with_stats_paginated.return_value = [(admin_user, None, 0, None)]
        mock_repository.count_users.return_value = 1

        params = UserSearchParams(is_superuser=True, page=1, page_size=10)

        # Act
        result = await service.search_users(params, admin_user.id)

        # Assert
        assert result.total == 1
        assert result.users[0].is_superuser is True

    async def test_search_users_sort_by_email(
        self, service, mock_repository, sample_user, admin_user
    ):
        """Test searching users with custom sort."""
        # Arrange
        mock_repository.get_users_with_stats_paginated.return_value = [(sample_user, None, 0, None)]
        mock_repository.count_users.return_value = 1

        params = UserSearchParams(page=1, page_size=10, sort_by="email", sort_order="asc")

        # Act
        await service.search_users(params, admin_user.id)

        # Assert
        call_args = mock_repository.get_users_with_stats_paginated.call_args
        assert call_args.kwargs["sort_by"] == "email"
        assert call_args.kwargs["sort_order"] == "asc"

    async def test_search_users_pagination(self, service, mock_repository, sample_user, admin_user):
        """Test searching users with pagination."""
        # Arrange
        mock_repository.get_users_with_stats_paginated.return_value = [
            (sample_user, None, 0, None)
        ] * 10
        mock_repository.count_users.return_value = 50

        params = UserSearchParams(page=2, page_size=10)

        # Act
        result = await service.search_users(params, admin_user.id)

        # Assert
        assert result.page == 2
        assert result.page_size == 10
        assert result.total == 50
        assert result.total_pages == 5

    async def test_search_users_multiple_filters(
        self, service, mock_repository, sample_user, admin_user
    ):
        """Test searching users with multiple filters."""
        # Arrange
        mock_repository.get_users_with_stats_paginated.return_value = [(sample_user, None, 0, None)]
        mock_repository.count_users.return_value = 1

        params = UserSearchParams(
            q="test",
            is_active=True,
            is_verified=True,
            page=1,
            page_size=10,
        )

        # Act
        result = await service.search_users(params, admin_user.id)

        # Assert
        assert result.total == 1
        call_args = mock_repository.get_users_with_stats_paginated.call_args
        filters = call_args.kwargs["filters"]
        # Should have 3 filters: query, is_active, is_verified
        assert len(filters) == 3


# ============================================================================
# Test: update_user_activation (Admin)
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.unit
class TestUpdateUserActivation:
    """Test UserService.update_user_activation() - Admin operation"""

    async def test_activate_user_success(
        self, service, mock_repository, mock_db, sample_user, admin_user, mock_request
    ):
        """Test activating an inactive user."""
        # Arrange
        sample_user.is_active = False
        mock_repository.get_by_id.return_value = sample_user
        mock_repository.update.return_value = sample_user
        mock_repository.create_audit_log.return_value = AdminAuditLog(
            id=uuid4(),
            admin_user_id=admin_user.id,
            action="user_activated",
            resource_type="user",
            resource_id=sample_user.id,
        )

        update_data = UserActivationUpdate(is_active=True)

        # Act
        with patch("src.domains.users.service.get_email_service") as mock_email:
            mock_email_service = AsyncMock()
            mock_email.return_value = mock_email_service

            result = await service.update_user_activation(
                sample_user.id, update_data, admin_user.id, mock_request
            )

            # Assert
            assert isinstance(result, UserActivationResponse)
            assert result.user.id == sample_user.id
            assert result.email_notification_sent is True
            mock_repository.get_by_id.assert_called_once_with(sample_user.id, include_inactive=True)
            mock_repository.update.assert_called_once()
            mock_db.commit.assert_called_once()
            mock_repository.create_audit_log.assert_called_once()
            mock_email_service.send_user_activated_notification.assert_called_once()

    async def test_deactivate_user_success(
        self, service, mock_repository, mock_db, sample_user, admin_user, mock_request
    ):
        """Test deactivating an active user."""
        # Arrange
        sample_user.is_active = True
        mock_repository.get_by_id.return_value = sample_user
        mock_repository.update.return_value = sample_user
        mock_repository.create_audit_log.return_value = AdminAuditLog(
            id=uuid4(),
            admin_user_id=admin_user.id,
            action="user_deactivated",
            resource_type="user",
            resource_id=sample_user.id,
        )

        update_data = UserActivationUpdate(is_active=False, reason="Policy violation")

        # Act
        with patch("src.domains.users.service.get_email_service") as mock_email:
            with patch.object(service, "_invalidate_all_user_sessions") as mock_invalidate:
                mock_email_service = AsyncMock()
                mock_email.return_value = mock_email_service

                result = await service.update_user_activation(
                    sample_user.id, update_data, admin_user.id, mock_request
                )

                # Assert
                assert isinstance(result, UserActivationResponse)
                assert result.user.id == sample_user.id
                assert result.email_notification_sent is True
                mock_invalidate.assert_called_once_with(sample_user.id)
                mock_email_service.send_user_deactivated_notification.assert_called_once()
                # Check notification includes reason
                call_args = mock_email_service.send_user_deactivated_notification.call_args
                assert "Policy violation" in call_args.kwargs["reason"]

    async def test_update_user_activation_not_found(self, service, mock_repository, admin_user):
        """Test activating non-existent user raises HTTPException."""
        # Arrange
        user_id = uuid4()
        mock_repository.get_by_id.return_value = None
        update_data = UserActivationUpdate(is_active=True)

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await service.update_user_activation(user_id, update_data, admin_user.id)

        assert exc_info.value.status_code == 404

    async def test_update_user_activation_creates_audit_log(
        self, service, mock_repository, mock_db, sample_user, admin_user, mock_request
    ):
        """Test activation creates audit log with request metadata."""
        # Arrange
        sample_user.is_active = False
        mock_repository.get_by_id.return_value = sample_user
        mock_repository.update.return_value = sample_user
        mock_repository.create_audit_log.return_value = AdminAuditLog(
            id=uuid4(),
            admin_user_id=admin_user.id,
            action="user_activated",
            resource_type="user",
            resource_id=sample_user.id,
        )

        update_data = UserActivationUpdate(is_active=True)

        # Act
        with patch("src.domains.users.service.get_email_service") as mock_email:
            mock_email_service = AsyncMock()
            mock_email.return_value = mock_email_service

            await service.update_user_activation(
                sample_user.id, update_data, admin_user.id, mock_request
            )

            # Assert
            call_args = mock_repository.create_audit_log.call_args
            assert call_args.kwargs["admin_user_id"] == admin_user.id
            assert call_args.kwargs["action"] == "user_activated"
            assert call_args.kwargs["resource_type"] == "user"
            assert call_args.kwargs["resource_id"] == sample_user.id
            assert call_args.kwargs["ip_address"] == "192.168.1.100"
            assert "Mozilla" in call_args.kwargs["user_agent"]

    async def test_update_user_activation_no_request(
        self, service, mock_repository, mock_db, sample_user, admin_user
    ):
        """Test activation works without request object."""
        # Arrange
        sample_user.is_active = False
        mock_repository.get_by_id.return_value = sample_user
        mock_repository.update.return_value = sample_user
        mock_repository.create_audit_log.return_value = AdminAuditLog(
            id=uuid4(),
            admin_user_id=admin_user.id,
            action="user_activated",
            resource_type="user",
            resource_id=sample_user.id,
        )

        update_data = UserActivationUpdate(is_active=True)

        # Act
        with patch("src.domains.users.service.get_email_service") as mock_email:
            mock_email_service = AsyncMock()
            mock_email.return_value = mock_email_service

            result = await service.update_user_activation(
                sample_user.id, update_data, admin_user.id, request=None
            )

            # Assert
            assert isinstance(result, UserActivationResponse)
            assert result.user.id == sample_user.id
            assert result.email_notification_sent is True
            # Audit log should have None for IP/user agent
            call_args = mock_repository.create_audit_log.call_args
            assert call_args.kwargs["ip_address"] is None
            assert call_args.kwargs["user_agent"] is None

    async def test_deactivate_user_with_reason(
        self, service, mock_repository, mock_db, sample_user, admin_user
    ):
        """Test deactivating user with explicit reason."""
        # Arrange
        sample_user.is_active = True
        mock_repository.get_by_id.return_value = sample_user
        mock_repository.update.return_value = sample_user
        mock_repository.create_audit_log.return_value = AdminAuditLog(
            id=uuid4(),
            admin_user_id=admin_user.id,
            action="user_deactivated",
            resource_type="user",
            resource_id=sample_user.id,
        )

        update_data = UserActivationUpdate(is_active=False, reason="Test reason")

        # Act
        with patch("src.domains.users.service.get_email_service") as mock_email:
            with patch.object(service, "_invalidate_all_user_sessions"):
                mock_email_service = AsyncMock()
                mock_email.return_value = mock_email_service

                await service.update_user_activation(sample_user.id, update_data, admin_user.id)

                # Assert - email should include the provided reason
                call_args = mock_email_service.send_user_deactivated_notification.call_args
                assert call_args.kwargs["reason"] == "Test reason"


# ============================================================================
# Test: delete_user_gdpr (Admin)
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.unit
class TestDeleteUserGDPR:
    """Test UserService.delete_user_gdpr() - GDPR deletion"""

    async def test_delete_user_gdpr_success(
        self, service, mock_repository, mock_db, sample_user, admin_user, mock_request
    ):
        """Test GDPR deletion of user."""
        # Arrange
        mock_repository.get_by_id.return_value = sample_user
        mock_repository.count_user_connectors.return_value = 3
        mock_repository.create_audit_log.return_value = AdminAuditLog(
            id=uuid4(),
            admin_user_id=admin_user.id,
            action="user_deleted_gdpr",
            resource_type="user",
            resource_id=sample_user.id,
        )

        # Act
        with patch.object(service, "_invalidate_all_user_sessions") as mock_invalidate:
            await service.delete_user_gdpr(sample_user.id, admin_user.id, mock_request)

            # Assert
            mock_repository.get_by_id.assert_called_once_with(sample_user.id, include_inactive=True)
            mock_repository.count_user_connectors.assert_called_once_with(sample_user.id)
            mock_repository.create_audit_log.assert_called_once()
            mock_invalidate.assert_called_once_with(sample_user.id)
            mock_repository.hard_delete.assert_called_once_with(sample_user)
            mock_db.commit.assert_called_once()

    async def test_delete_user_gdpr_not_found(self, service, mock_repository, admin_user):
        """Test GDPR deletion of non-existent user raises HTTPException."""
        # Arrange
        user_id = uuid4()
        mock_repository.get_by_id.return_value = None

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await service.delete_user_gdpr(user_id, admin_user.id)

        assert exc_info.value.status_code == 404
        mock_repository.hard_delete.assert_not_called()

    async def test_delete_user_gdpr_prevents_superuser_deletion(
        self, service, mock_repository, admin_user
    ):
        """Test GDPR deletion prevents deleting superusers."""
        # Arrange
        superuser = admin_user  # This is a superuser
        mock_repository.get_by_id.return_value = superuser

        another_admin_id = uuid4()

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await service.delete_user_gdpr(superuser.id, another_admin_id)

        # Should raise admin_required exception
        assert exc_info.value.status_code in [403, 400]
        mock_repository.hard_delete.assert_not_called()

    async def test_delete_user_gdpr_creates_audit_log(
        self, service, mock_repository, mock_db, sample_user, admin_user, mock_request
    ):
        """Test GDPR deletion creates detailed audit log."""
        # Arrange
        mock_repository.get_by_id.return_value = sample_user
        mock_repository.count_user_connectors.return_value = 5
        mock_repository.create_audit_log.return_value = AdminAuditLog(
            id=uuid4(),
            admin_user_id=admin_user.id,
            action="user_deleted_gdpr",
            resource_type="user",
            resource_id=sample_user.id,
        )

        # Act
        with patch.object(service, "_invalidate_all_user_sessions"):
            await service.delete_user_gdpr(sample_user.id, admin_user.id, mock_request)

            # Assert
            call_args = mock_repository.create_audit_log.call_args
            assert call_args.kwargs["action"] == "user_deleted_gdpr"
            assert call_args.kwargs["resource_type"] == "user"
            details = call_args.kwargs["details"]
            assert details["user_email"] == sample_user.email
            assert details["user_name"] == sample_user.full_name
            assert details["had_connectors"] == 5
            assert details["was_verified"] == sample_user.is_verified
            assert details["was_active"] == sample_user.is_active

    async def test_delete_user_gdpr_no_connectors(
        self, service, mock_repository, mock_db, sample_user, admin_user
    ):
        """Test GDPR deletion of user with no connectors."""
        # Arrange
        mock_repository.get_by_id.return_value = sample_user
        mock_repository.count_user_connectors.return_value = 0
        mock_repository.create_audit_log.return_value = AdminAuditLog(
            id=uuid4(),
            admin_user_id=admin_user.id,
            action="user_deleted_gdpr",
            resource_type="user",
            resource_id=sample_user.id,
        )

        # Act
        with patch.object(service, "_invalidate_all_user_sessions"):
            await service.delete_user_gdpr(sample_user.id, admin_user.id)

            # Assert
            call_args = mock_repository.create_audit_log.call_args
            assert call_args.kwargs["details"]["had_connectors"] == 0


# ============================================================================
# Test: _invalidate_all_user_sessions
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.unit
class TestInvalidateAllUserSessions:
    """Test UserService._invalidate_all_user_sessions()"""

    async def test_invalidate_all_user_sessions_success(self, service, sample_user):
        """Test invalidating all user sessions."""
        # Arrange
        import json

        # Create async mock for Redis
        mock_redis = AsyncMock()

        # Mock scan to return keys in 2 iterations
        async def mock_scan(cursor=0, match=None, count=None):
            if cursor == 0:
                return (100, [b"session:abc", b"session:def"])
            elif cursor == 100:
                return (0, [b"session:ghi"])
            return (0, [])

        mock_redis.scan = mock_scan

        # Mock type check (all strings)
        async def mock_type(key):
            return "string"

        mock_redis.type = mock_type

        # Mock get to return session data
        get_responses = [
            json.dumps({"user_id": str(sample_user.id)}),  # session:abc
            json.dumps({"user_id": "other-user-id"}),  # session:def
            json.dumps({"user_id": str(sample_user.id)}),  # session:ghi
        ]
        get_index = [0]  # Use list to allow modification in nested function

        async def mock_get(key):
            result = get_responses[get_index[0]]
            get_index[0] += 1
            return result

        mock_redis.get = mock_get

        # Mock pipeline
        mock_pipeline = AsyncMock()
        mock_pipeline.execute = AsyncMock(return_value=[1, 1])  # 2 successful deletions
        mock_redis.pipeline = Mock(return_value=mock_pipeline)

        # Act
        async def mock_get_redis():
            return mock_redis

        with patch("src.domains.users.service.get_redis_session", side_effect=mock_get_redis):
            await service._invalidate_all_user_sessions(sample_user.id)

            # Assert
            # Should call delete on pipeline 2 times (abc and ghi)
            assert mock_pipeline.delete.call_count == 2
            assert mock_pipeline.execute.call_count == 1

    async def test_invalidate_all_user_sessions_no_sessions(self, service, sample_user):
        """Test invalidating when user has no sessions."""
        # Arrange
        mock_redis = AsyncMock()
        mock_redis.scan.return_value = (0, [])  # No keys found

        # Act
        async def mock_get_redis():
            return mock_redis

        with patch("src.domains.users.service.get_redis_session", side_effect=mock_get_redis):
            await service._invalidate_all_user_sessions(sample_user.id)

            # Assert
            mock_redis.delete.assert_not_called()

    async def test_invalidate_all_user_sessions_skip_non_string_keys(self, service, sample_user):
        """Test skipping non-string Redis keys (like SETs)."""
        # Arrange
        import json

        mock_redis = AsyncMock()

        async def mock_scan(cursor=0, match=None, count=None):
            return (0, [b"session:abc", b"session:user_tokens"])

        mock_redis.scan = mock_scan

        type_responses = ["string", "set"]
        type_index = [0]

        async def mock_type(key):
            result = type_responses[type_index[0]]
            type_index[0] += 1
            return result

        mock_redis.type = mock_type

        async def mock_get(key):
            return json.dumps({"user_id": str(sample_user.id)})

        mock_redis.get = mock_get

        # Mock pipeline
        mock_pipeline = AsyncMock()
        mock_pipeline.execute = AsyncMock(return_value=[1])  # 1 successful deletion
        mock_redis.pipeline = Mock(return_value=mock_pipeline)

        # Act
        async def mock_get_redis():
            return mock_redis

        with patch("src.domains.users.service.get_redis_session", side_effect=mock_get_redis):
            await service._invalidate_all_user_sessions(sample_user.id)

            # Assert
            # Should only process the string key
            assert mock_pipeline.delete.call_count == 1
            assert mock_pipeline.execute.call_count == 1

    async def test_invalidate_all_user_sessions_handles_json_decode_error(
        self, service, sample_user
    ):
        """Test handling JSON decode errors gracefully."""
        # Arrange
        mock_redis = AsyncMock()
        mock_redis.scan.return_value = (0, [b"session:abc"])
        mock_redis.type.return_value = "string"
        mock_redis.get.return_value = "invalid-json"  # Not valid JSON

        # Act
        with patch("src.domains.users.service.get_redis_session", return_value=mock_redis):
            # Should not raise exception
            await service._invalidate_all_user_sessions(sample_user.id)

            # Assert
            mock_redis.delete.assert_not_called()

    async def test_invalidate_all_user_sessions_handles_redis_error(self, service, sample_user):
        """Test handling Redis errors gracefully."""
        # Arrange
        mock_redis = AsyncMock()
        mock_redis.scan.side_effect = Exception("Redis connection failed")

        # Act
        with patch("src.domains.users.service.get_redis_session", return_value=mock_redis):
            # Should not raise exception
            await service._invalidate_all_user_sessions(sample_user.id)

            # Assert - error should be logged but not raised
            mock_redis.delete.assert_not_called()

    async def test_invalidate_all_user_sessions_pagination(self, service, sample_user):
        """Test proper pagination through Redis SCAN."""
        # Arrange
        import json

        mock_redis = AsyncMock()

        scan_calls = [0]

        async def mock_scan(cursor=0, match=None, count=None):
            scan_calls[0] += 1
            if cursor == 0:
                return (1, [b"session:1"])
            elif cursor == 1:
                return (2, [b"session:2"])
            elif cursor == 2:
                return (0, [b"session:3"])
            return (0, [])

        mock_redis.scan = mock_scan

        async def mock_type(key):
            return "string"

        mock_redis.type = mock_type

        async def mock_get(key):
            return json.dumps({"user_id": str(sample_user.id)})

        mock_redis.get = mock_get

        # Mock pipeline
        mock_pipeline = AsyncMock()
        mock_pipeline.execute = AsyncMock(return_value=[1, 1, 1])  # 3 successful deletions
        mock_redis.pipeline = Mock(return_value=mock_pipeline)

        # Act
        async def mock_get_redis():
            return mock_redis

        with patch("src.domains.users.service.get_redis_session", side_effect=mock_get_redis):
            await service._invalidate_all_user_sessions(sample_user.id)

            # Assert
            # Should call scan 3 times (until cursor=0)
            assert scan_calls[0] == 3
            # Should delete all 3 sessions via pipeline
            assert mock_pipeline.delete.call_count == 3
            assert mock_pipeline.execute.call_count == 1


# ============================================================================
# Edge Cases and Integration Tests
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.unit
class TestEdgeCases:
    """Test edge cases and error scenarios."""

    async def test_update_user_refresh_after_update(
        self, service, mock_repository, mock_db, sample_user
    ):
        """Test that user is refreshed after update in activation flow."""
        # Arrange
        sample_user.is_active = False
        mock_repository.get_by_id.return_value = sample_user
        mock_repository.update.return_value = sample_user
        mock_repository.create_audit_log.return_value = AdminAuditLog(
            id=uuid4(),
            admin_user_id=uuid4(),
            action="user_activated",
            resource_type="user",
            resource_id=sample_user.id,
        )

        update_data = UserActivationUpdate(is_active=True)

        # Act
        with patch("src.domains.users.service.get_email_service") as mock_email:
            mock_email_service = AsyncMock()
            mock_email.return_value = mock_email_service

            await service.update_user_activation(sample_user.id, update_data, uuid4())

            # Assert
            # Should call refresh to get updated data
            mock_db.refresh.assert_called_once_with(sample_user)

    async def test_service_initialization(self, mock_db):
        """Test service initialization."""
        # Act
        service = UserService(mock_db)

        # Assert
        assert service.db == mock_db
        assert service.repository is not None
        from src.domains.users.repository import UserRepository

        assert isinstance(service.repository, UserRepository)

    async def test_pagination_helpers_imported(self, service, mock_repository):
        """Test that pagination helpers are imported correctly."""
        # Arrange
        mock_repository.get_all_with_count.return_value = ([], 0)

        # Act
        result = await service.get_all_users()

        # Assert - should not raise ImportError
        assert isinstance(result, UserListResponse)

    async def test_search_users_empty_query(
        self, service, mock_repository, sample_user, admin_user
    ):
        """Test searching users with empty query."""
        # Arrange
        mock_repository.get_users_with_stats_paginated.return_value = [(sample_user, None, 0, None)]
        mock_repository.count_users.return_value = 1

        params = UserSearchParams(q="", page=1, page_size=10)

        # Act
        result = await service.search_users(params, admin_user.id)

        # Assert
        assert result.total == 1
        # Empty query should not add filter
        call_args = mock_repository.get_users_with_stats_paginated.call_args
        filters = call_args.kwargs["filters"]
        assert len(filters) == 0

    async def test_search_users_none_query(self, service, mock_repository, sample_user, admin_user):
        """Test searching users with None query."""
        # Arrange
        mock_repository.get_users_with_stats_paginated.return_value = [(sample_user, None, 0, None)]
        mock_repository.count_users.return_value = 1

        params = UserSearchParams(q=None, page=1, page_size=10)

        # Act
        result = await service.search_users(params, admin_user.id)

        # Assert
        assert result.total == 1
        call_args = mock_repository.get_users_with_stats_paginated.call_args
        filters = call_args.kwargs["filters"]
        assert len(filters) == 0
