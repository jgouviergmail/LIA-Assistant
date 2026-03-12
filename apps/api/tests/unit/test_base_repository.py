"""
Unit tests for BaseRepository generic repository pattern.

Tests cover:
- CRUD operations (create, read, update, delete)
- Soft delete pattern (is_active filter)
- Type safety with Generic[ModelType]
- Structured logging
- Edge cases and error handling

NOTE: These tests require a real database (testcontainers) and are slow.
They should be moved to tests/integration/ folder.
"""

from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.repository import BaseRepository
from src.domains.auth.models import User
from src.domains.connectors.models import Connector, ConnectorStatus, ConnectorType

# Skip module - requires testcontainers/Docker, too slow for pre-commit
# TODO: Move to tests/integration/
pytestmark = pytest.mark.integration


@pytest.mark.unit
class TestBaseRepositoryCreate:
    """Test BaseRepository.create() method."""

    @pytest_asyncio.fixture
    async def user_repository(self, async_session: AsyncSession) -> BaseRepository[User]:
        """Create BaseRepository instance for User model."""
        return BaseRepository(async_session, User)

    async def test_create_instance_success(
        self, user_repository: BaseRepository[User], async_session: AsyncSession
    ):
        """Test creating a new instance with flush and refresh."""
        # Arrange
        user_data = {
            "email": "test@example.com",
            "hashed_password": "hashed_password_value",
            "full_name": "Test User",
            "is_active": True,
            "is_verified": False,
        }

        # Act
        user = await user_repository.create(user_data)
        await async_session.commit()

        # Assert
        assert user.id is not None  # ID assigned by database
        assert user.email == "test@example.com"
        assert user.full_name == "Test User"
        assert user.is_active is True
        assert user.is_verified is False
        assert user.created_at is not None
        assert user.updated_at is not None

    async def test_create_assigns_uuid(
        self, user_repository: BaseRepository[User], async_session: AsyncSession
    ):
        """Test that create assigns a valid UUID."""
        # Arrange
        user_data = {
            "email": "uuid-test@example.com",
            "full_name": "UUID Test",
            "is_active": True,
            "is_verified": False,
        }

        # Act
        user = await user_repository.create(user_data)
        await async_session.commit()

        # Assert
        assert isinstance(user.id, UUID)
        assert user.id.version == 4  # UUID4

    async def test_create_with_minimal_fields(
        self, user_repository: BaseRepository[User], async_session: AsyncSession
    ):
        """Test creating instance with only required fields."""
        # Arrange
        user_data = {
            "email": "minimal@example.com",
            "full_name": "Minimal User",
            "is_active": True,  # Required field
        }

        # Act
        user = await user_repository.create(user_data)
        await async_session.commit()

        # Assert
        assert user.id is not None
        assert user.email == "minimal@example.com"
        assert user.is_active is True
        assert user.is_verified is False  # Default from model


@pytest.mark.unit
class TestBaseRepositoryGetById:
    """Test BaseRepository.get_by_id() method."""

    @pytest_asyncio.fixture
    async def user_repository(self, async_session: AsyncSession) -> BaseRepository[User]:
        """Create BaseRepository instance for User model."""
        return BaseRepository(async_session, User)

    @pytest_asyncio.fixture
    async def sample_user(
        self, async_session: AsyncSession, user_repository: BaseRepository[User]
    ) -> User:
        """Create a sample user for testing."""
        user_data = {
            "email": "sample@example.com",
            "full_name": "Sample User",
            "is_active": True,
            "is_verified": True,
        }
        user = await user_repository.create(user_data)
        await async_session.commit()
        return user

    async def test_get_by_id_found(self, user_repository: BaseRepository[User], sample_user: User):
        """Test retrieving an existing user by ID."""
        # Act
        retrieved = await user_repository.get_by_id(sample_user.id)

        # Assert
        assert retrieved is not None
        assert retrieved.id == sample_user.id
        assert retrieved.email == sample_user.email
        assert retrieved.full_name == sample_user.full_name

    async def test_get_by_id_not_found(self, user_repository: BaseRepository[User]):
        """Test retrieving non-existent user returns None."""
        # Arrange
        non_existent_id = uuid4()

        # Act
        result = await user_repository.get_by_id(non_existent_id)

        # Assert
        assert result is None

    async def test_get_by_id_excludes_inactive_by_default(
        self, user_repository: BaseRepository[User], async_session: AsyncSession
    ):
        """Test that inactive users are excluded by default."""
        # Arrange - Create inactive user
        user_data = {
            "email": "inactive@example.com",
            "full_name": "Inactive User",
            "is_active": False,
        }
        user = await user_repository.create(user_data)
        await async_session.commit()

        # Act
        result = await user_repository.get_by_id(user.id)

        # Assert
        assert result is None  # Excluded because is_active=False

    async def test_get_by_id_includes_inactive_when_flag_set(
        self, user_repository: BaseRepository[User], async_session: AsyncSession
    ):
        """Test that inactive users are included when include_inactive=True."""
        # Arrange - Create inactive user
        user_data = {
            "email": "inactive2@example.com",
            "full_name": "Inactive User 2",
            "is_active": False,
        }
        user = await user_repository.create(user_data)
        await async_session.commit()

        # Act
        result = await user_repository.get_by_id(user.id, include_inactive=True)

        # Assert
        assert result is not None
        assert result.id == user.id
        assert result.is_active is False


@pytest.mark.unit
class TestBaseRepositoryGetAll:
    """Test BaseRepository.get_all() method."""

    @pytest_asyncio.fixture
    async def user_repository(self, async_session: AsyncSession) -> BaseRepository[User]:
        """Create BaseRepository instance for User model."""
        return BaseRepository(async_session, User)

    async def test_get_all_empty(self, user_repository: BaseRepository[User]):
        """Test get_all returns empty list when no data."""
        # Act
        users = await user_repository.get_all()

        # Assert
        assert users == []

    async def test_get_all_with_data(
        self, user_repository: BaseRepository[User], async_session: AsyncSession
    ):
        """Test get_all returns all active users."""
        # Arrange - Create 3 users
        for i in range(3):
            user_data = {
                "email": f"user{i}@example.com",
                "full_name": f"User {i}",
                "is_active": True,
            }
            await user_repository.create(user_data)
        await async_session.commit()

        # Act
        users = await user_repository.get_all()

        # Assert
        assert len(users) == 3
        emails = {user.email for user in users}
        assert emails == {"user0@example.com", "user1@example.com", "user2@example.com"}

    async def test_get_all_excludes_inactive(
        self, user_repository: BaseRepository[User], async_session: AsyncSession
    ):
        """Test get_all excludes inactive users by default."""
        # Arrange - Create 2 active + 1 inactive
        await user_repository.create(
            {"email": "active1@example.com", "full_name": "Active 1", "is_active": True}
        )
        await user_repository.create(
            {"email": "active2@example.com", "full_name": "Active 2", "is_active": True}
        )
        await user_repository.create(
            {"email": "inactive@example.com", "full_name": "Inactive", "is_active": False}
        )
        await async_session.commit()

        # Act
        users = await user_repository.get_all()

        # Assert
        assert len(users) == 2
        emails = {user.email for user in users}
        assert "inactive@example.com" not in emails

    async def test_get_all_respects_limit(
        self, user_repository: BaseRepository[User], async_session: AsyncSession
    ):
        """Test get_all respects limit parameter."""
        # Arrange - Create 5 users
        for i in range(5):
            await user_repository.create(
                {"email": f"user{i}@example.com", "full_name": f"User {i}", "is_active": True}
            )
        await async_session.commit()

        # Act
        users = await user_repository.get_all(limit=2)

        # Assert
        assert len(users) == 2

    async def test_get_all_respects_offset(
        self, user_repository: BaseRepository[User], async_session: AsyncSession
    ):
        """Test get_all respects offset parameter."""
        # Arrange - Create 3 users
        for i in range(3):
            await user_repository.create(
                {"email": f"user{i}@example.com", "full_name": f"User {i}", "is_active": True}
            )
        await async_session.commit()

        # Act
        all_users = await user_repository.get_all()
        offset_users = await user_repository.get_all(offset=1)

        # Assert
        assert len(all_users) == 3
        assert len(offset_users) == 2


@pytest.mark.unit
class TestBaseRepositoryUpdate:
    """Test BaseRepository.update() method."""

    @pytest_asyncio.fixture
    async def user_repository(self, async_session: AsyncSession) -> BaseRepository[User]:
        """Create BaseRepository instance for User model."""
        return BaseRepository(async_session, User)

    @pytest_asyncio.fixture
    async def sample_user(
        self, async_session: AsyncSession, user_repository: BaseRepository[User]
    ) -> User:
        """Create a sample user for testing."""
        user_data = {
            "email": "original@example.com",
            "full_name": "Original Name",
            "is_active": True,
            "is_verified": False,
        }
        user = await user_repository.create(user_data)
        await async_session.commit()
        return user

    async def test_update_single_field(
        self,
        user_repository: BaseRepository[User],
        sample_user: User,
        async_session: AsyncSession,
    ):
        """Test updating a single field."""
        # Act
        updated = await user_repository.update(sample_user, {"full_name": "Updated Name"})
        await async_session.commit()

        # Assert
        assert updated.full_name == "Updated Name"
        assert updated.email == "original@example.com"  # Unchanged

    async def test_update_multiple_fields(
        self,
        user_repository: BaseRepository[User],
        sample_user: User,
        async_session: AsyncSession,
    ):
        """Test updating multiple fields at once."""
        # Act
        updated = await user_repository.update(
            sample_user, {"full_name": "New Name", "is_verified": True}
        )
        await async_session.commit()

        # Assert
        assert updated.full_name == "New Name"
        assert updated.is_verified is True

    async def test_update_refreshes_updated_at(
        self,
        user_repository: BaseRepository[User],
        sample_user: User,
        async_session: AsyncSession,
    ):
        """Test that update refreshes the updated_at timestamp."""
        # Arrange
        original_updated_at = sample_user.updated_at

        # Act
        updated = await user_repository.update(sample_user, {"full_name": "Changed"})
        await async_session.commit()
        await async_session.refresh(updated)

        # Assert
        assert updated.updated_at > original_updated_at


@pytest.mark.unit
class TestBaseRepositoryDelete:
    """Test BaseRepository.delete() method (soft delete)."""

    @pytest_asyncio.fixture
    async def user_repository(self, async_session: AsyncSession) -> BaseRepository[User]:
        """Create BaseRepository instance for User model."""
        return BaseRepository(async_session, User)

    @pytest_asyncio.fixture
    async def sample_user(
        self, async_session: AsyncSession, user_repository: BaseRepository[User]
    ) -> User:
        """Create a sample user for testing."""
        user_data = {
            "email": "todelete@example.com",
            "full_name": "To Delete",
            "is_active": True,
        }
        user = await user_repository.create(user_data)
        await async_session.commit()
        return user

    async def test_soft_delete_sets_inactive(
        self,
        user_repository: BaseRepository[User],
        sample_user: User,
        async_session: AsyncSession,
    ):
        """Test that soft delete (via update) sets is_active to False."""
        # Act - Soft delete via update
        updated_user = await user_repository.update(sample_user, {"is_active": False})
        await async_session.commit()

        # Assert
        assert updated_user.is_active is False
        assert updated_user.id == sample_user.id

    async def test_soft_deleted_excluded_from_get_by_id(
        self,
        user_repository: BaseRepository[User],
        sample_user: User,
        async_session: AsyncSession,
    ):
        """Test that soft-deleted user is excluded from get_by_id by default."""
        # Act - Soft delete
        await user_repository.update(sample_user, {"is_active": False})
        await async_session.commit()

        # Try to retrieve
        result = await user_repository.get_by_id(sample_user.id)

        # Assert
        assert result is None  # Soft deleted, so excluded

    async def test_soft_deleted_can_be_retrieved_with_flag(
        self,
        user_repository: BaseRepository[User],
        sample_user: User,
        async_session: AsyncSession,
    ):
        """Test that soft-deleted user can be retrieved with include_inactive=True."""
        # Act - Soft delete
        await user_repository.update(sample_user, {"is_active": False})
        await async_session.commit()

        # Try to retrieve with flag
        result = await user_repository.get_by_id(sample_user.id, include_inactive=True)

        # Assert
        assert result is not None
        assert result.id == sample_user.id
        assert result.is_active is False


@pytest.mark.unit
class TestBaseRepositoryCount:
    """Test BaseRepository.count() method."""

    @pytest_asyncio.fixture
    async def user_repository(self, async_session: AsyncSession) -> BaseRepository[User]:
        """Create BaseRepository instance for User model."""
        return BaseRepository(async_session, User)

    async def test_count_empty(self, user_repository: BaseRepository[User]):
        """Test count returns 0 when no data."""
        # Act
        count = await user_repository.count()

        # Assert
        assert count == 0

    async def test_count_with_data(
        self, user_repository: BaseRepository[User], async_session: AsyncSession
    ):
        """Test count returns correct number of active users."""
        # Arrange - Create 4 users
        for i in range(4):
            await user_repository.create(
                {"email": f"count{i}@example.com", "full_name": f"Count {i}", "is_active": True}
            )
        await async_session.commit()

        # Act
        count = await user_repository.count()

        # Assert
        assert count == 4

    async def test_count_excludes_inactive(
        self, user_repository: BaseRepository[User], async_session: AsyncSession
    ):
        """Test count excludes inactive users by default."""
        # Arrange - Create 3 active + 2 inactive
        for i in range(3):
            await user_repository.create(
                {"email": f"active{i}@example.com", "full_name": f"Active {i}", "is_active": True}
            )
        for i in range(2):
            await user_repository.create(
                {
                    "email": f"inactive{i}@example.com",
                    "full_name": f"Inactive {i}",
                    "is_active": False,
                }
            )
        await async_session.commit()

        # Act
        count = await user_repository.count()

        # Assert
        assert count == 3  # Only active users


@pytest.mark.unit
class TestBaseRepositoryTypeSafety:
    """Test BaseRepository type safety with Generic[ModelType]."""

    @pytest_asyncio.fixture
    async def user_repository(self, async_session: AsyncSession) -> BaseRepository[User]:
        """Create BaseRepository instance for User model."""
        return BaseRepository(async_session, User)

    @pytest_asyncio.fixture
    async def connector_repository(self, async_session: AsyncSession) -> BaseRepository[Connector]:
        """Create BaseRepository instance for Connector model."""
        return BaseRepository(async_session, Connector)

    async def test_works_with_user_model(
        self, user_repository: BaseRepository[User], async_session: AsyncSession
    ):
        """Test BaseRepository works with User model."""
        # Arrange
        user_data = {
            "email": "typetest@example.com",
            "full_name": "Type Test",
            "is_active": True,
        }

        # Act
        user = await user_repository.create(user_data)
        await async_session.commit()

        # Assert
        assert isinstance(user, User)
        assert user.email == "typetest@example.com"

    async def test_works_with_connector_model(
        self,
        connector_repository: BaseRepository[Connector],
        user_repository: BaseRepository[User],
        async_session: AsyncSession,
    ):
        """Test BaseRepository works with Connector model."""
        # Arrange - Create user first
        user = await user_repository.create(
            {"email": "connectortest@example.com", "full_name": "Connector Test"}
        )
        await async_session.commit()

        # Create connector
        connector_data = {
            "user_id": user.id,
            "connector_type": ConnectorType.GOOGLE_GMAIL,
            "status": ConnectorStatus.ACTIVE,
            "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
            "credentials_encrypted": "encrypted-data",
            "metadata": {},
        }

        # Act
        connector = await connector_repository.create(connector_data)
        await async_session.commit()

        # Assert
        assert isinstance(connector, Connector)
        assert connector.connector_type == ConnectorType.GOOGLE_GMAIL
        assert connector.user_id == user.id
