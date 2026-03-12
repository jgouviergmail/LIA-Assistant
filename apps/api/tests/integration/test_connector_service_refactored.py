"""
Unit tests for ConnectorService refactored methods (Sprint 5).

Tests cover:
- _handle_oauth_connector_callback() generic handler
- handle_gmail_callback() using generic handler
- handle_google_contacts_callback() using generic handler
- Token exchange, credential encryption, connector creation/update
- Error handling and edge cases
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import encrypt_data
from src.domains.connectors.models import ConnectorStatus, ConnectorType
from src.domains.connectors.service import ConnectorService
from tests.fixtures.factories import UserFactory


@pytest_asyncio.fixture
async def connector_service(async_session: AsyncSession) -> ConnectorService:
    """Create ConnectorService instance with async session."""
    return ConnectorService(async_session)


@pytest_asyncio.fixture
async def test_user_with_id(async_session: AsyncSession):
    """Create test user and commit to database."""
    user = UserFactory.create(email="connectortest@example.com", full_name="Connector Test")
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


@pytest.mark.integration  # Uses testcontainers (PostgreSQL) but mocks Redis
class TestHandleOAuthConnectorCallbackGeneric:
    """Test ConnectorService._handle_oauth_connector_callback() generic handler.

    Note: These tests use testcontainers for PostgreSQL. Redis is mocked.
    """

    @pytest.fixture(autouse=True)
    def mock_redis_cache(self):
        """Auto-use fixture to mock Redis cache for all tests in this class."""
        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock(return_value=True)
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.setex = AsyncMock(return_value=True)
        with patch("src.infrastructure.cache.redis.get_redis_cache", return_value=mock_redis):
            yield mock_redis

    async def test_creates_new_connector(self, connector_service, test_user_with_id, async_session):
        """Test creating new connector via generic handler."""
        # Arrange
        user_id = test_user_with_id.id
        code = "test-code"
        state = "test-state"

        # Mock OAuth token response
        mock_token_response = MagicMock()
        mock_token_response.token_type = "Bearer"
        mock_token_response.access_token = "access-token-123"
        mock_token_response.refresh_token = "refresh-token-456"
        mock_token_response.expires_in = 3600
        mock_token_response.scope = "https://www.googleapis.com/auth/gmail.readonly"

        mock_stored_state = {
            "provider": "google",
            "code_verifier": "verifier",
            "timestamp": "2025-01-01T00:00:00Z",
            "user_id": str(user_id),  # Required for state validation
            "connector_type": ConnectorType.GOOGLE_GMAIL.value,  # Required for state validation
        }

        # Mock provider factory
        def mock_provider_factory(settings):
            return MagicMock()

        with patch("src.domains.connectors.service.get_redis_session"):
            with patch("src.domains.connectors.service.SessionService"):
                with patch("src.core.oauth.OAuthFlowHandler") as mock_handler_class:
                    mock_handler = mock_handler_class.return_value
                    mock_handler.handle_callback = AsyncMock(
                        return_value=(mock_token_response, mock_stored_state)
                    )

                    # Act
                    result = await connector_service._handle_oauth_connector_callback(
                        user_id=user_id,
                        code=code,
                        state=state,
                        connector_type=ConnectorType.GOOGLE_GMAIL,
                        provider_factory_method=mock_provider_factory,
                        metadata={"last_synced": None},
                    )
                    await async_session.commit()

        # Assert
        assert result.connector_type == ConnectorType.GOOGLE_GMAIL
        assert result.status == ConnectorStatus.ACTIVE
        assert result.user_id == user_id

    async def test_updates_existing_connector(
        self, connector_service, test_user_with_id, async_session
    ):
        """Test updating existing connector with new tokens."""
        # Arrange - Create existing connector
        from src.domains.connectors.repository import ConnectorRepository

        repo = ConnectorRepository(async_session)

        existing_connector_data = {
            "user_id": test_user_with_id.id,
            "connector_type": ConnectorType.GOOGLE_GMAIL,
            "status": ConnectorStatus.ACTIVE,
            "scopes": ["old-scope"],
            "credentials_encrypted": encrypt_data('{"access_token": "old-token"}'),
            "metadata": {},
        }
        existing_connector = await repo.create(existing_connector_data)
        await async_session.commit()

        # Mock new OAuth response
        code = "new-code"
        state = "new-state"

        mock_token_response = MagicMock()
        mock_token_response.token_type = "Bearer"
        mock_token_response.access_token = "new-access-token"
        mock_token_response.refresh_token = "new-refresh-token"
        mock_token_response.expires_in = 3600
        mock_token_response.scope = "new-scope"

        mock_stored_state = {
            "provider": "google",
            "code_verifier": "verifier",
            "user_id": str(test_user_with_id.id),
            "connector_type": ConnectorType.GOOGLE_GMAIL.value,
        }

        def mock_provider_factory(settings):
            return MagicMock()

        with patch("src.domains.connectors.service.get_redis_session"):
            with patch("src.domains.connectors.service.SessionService"):
                with patch("src.core.oauth.OAuthFlowHandler") as mock_handler_class:
                    mock_handler = mock_handler_class.return_value
                    mock_handler.handle_callback = AsyncMock(
                        return_value=(mock_token_response, mock_stored_state)
                    )

                    # Act
                    result = await connector_service._handle_oauth_connector_callback(
                        user_id=test_user_with_id.id,
                        code=code,
                        state=state,
                        connector_type=ConnectorType.GOOGLE_GMAIL,
                        provider_factory_method=mock_provider_factory,
                        metadata={"updated": True},
                    )
                    await async_session.commit()

        # Assert - Same connector updated
        assert result.id == existing_connector.id
        assert result.status == ConnectorStatus.ACTIVE

    async def test_uses_provider_factory_method(
        self, connector_service, test_user_with_id, async_session
    ):
        """Test that provider factory method is called correctly."""
        # Arrange
        mock_factory = MagicMock()
        mock_provider = MagicMock()
        mock_factory.return_value = mock_provider

        mock_token_response = MagicMock()
        mock_token_response.token_type = "Bearer"
        mock_token_response.access_token = "token"
        mock_token_response.refresh_token = "refresh"
        mock_token_response.expires_in = 3600
        mock_token_response.scope = "scope"

        mock_stored_state = {
            "provider": "google",
            "code_verifier": "verifier",
            "user_id": str(test_user_with_id.id),
            "connector_type": ConnectorType.GOOGLE_CONTACTS.value,
        }

        with patch("src.domains.connectors.service.get_redis_session"):
            with patch("src.domains.connectors.service.SessionService"):
                with patch("src.core.oauth.OAuthFlowHandler") as mock_handler_class:
                    mock_handler = mock_handler_class.return_value
                    mock_handler.handle_callback = AsyncMock(
                        return_value=(mock_token_response, mock_stored_state)
                    )

                    # Act
                    await connector_service._handle_oauth_connector_callback(
                        user_id=test_user_with_id.id,
                        code="code",
                        state="state",
                        connector_type=ConnectorType.GOOGLE_CONTACTS,
                        provider_factory_method=mock_factory,
                    )
                    await async_session.commit()

        # Assert - Factory was called
        mock_factory.assert_called_once()

    async def test_applies_default_scopes(
        self, connector_service, test_user_with_id, async_session
    ):
        """Test that default_scopes parameter is used."""
        # Arrange
        default_scopes = [
            "https://www.googleapis.com/auth/contacts.readonly",
            "https://www.googleapis.com/auth/contacts.other.readonly",
        ]

        mock_token_response = MagicMock()
        mock_token_response.token_type = "Bearer"
        mock_token_response.access_token = "token"
        mock_token_response.refresh_token = "refresh"
        mock_token_response.expires_in = 3600
        mock_token_response.scope = None  # No scope in response

        mock_stored_state = {
            "provider": "google",
            "code_verifier": "verifier",
            "user_id": str(test_user_with_id.id),
            "connector_type": ConnectorType.GOOGLE_CONTACTS.value,
        }

        def mock_factory(settings):
            return MagicMock()

        with patch("src.domains.connectors.service.get_redis_session"):
            with patch("src.domains.connectors.service.SessionService"):
                with patch("src.core.oauth.OAuthFlowHandler") as mock_handler_class:
                    mock_handler = mock_handler_class.return_value
                    mock_handler.handle_callback = AsyncMock(
                        return_value=(mock_token_response, mock_stored_state)
                    )

                    # Act
                    result = await connector_service._handle_oauth_connector_callback(
                        user_id=test_user_with_id.id,
                        code="code",
                        state="state",
                        connector_type=ConnectorType.GOOGLE_CONTACTS,
                        provider_factory_method=mock_factory,
                        default_scopes=default_scopes,
                    )
                    await async_session.commit()

        # Assert - Default scopes used
        assert result.scopes == default_scopes

    async def test_stores_metadata(self, connector_service, test_user_with_id, async_session):
        """Test that metadata parameter is stored correctly."""
        # Arrange
        custom_metadata = {
            "created_via": "oauth_flow",
            "source": "google_contacts",
            "version": "1.0",
        }

        mock_token_response = MagicMock()
        mock_token_response.token_type = "Bearer"
        mock_token_response.access_token = "token"
        mock_token_response.refresh_token = "refresh"
        mock_token_response.expires_in = 3600
        mock_token_response.scope = "scope"

        mock_stored_state = {
            "provider": "google",
            "code_verifier": "verifier",
            "user_id": str(test_user_with_id.id),
            "connector_type": ConnectorType.GOOGLE_CONTACTS.value,
        }

        def mock_factory(settings):
            return MagicMock()

        with patch("src.domains.connectors.service.get_redis_session"):
            with patch("src.domains.connectors.service.SessionService"):
                with patch("src.core.oauth.OAuthFlowHandler") as mock_handler_class:
                    mock_handler = mock_handler_class.return_value
                    mock_handler.handle_callback = AsyncMock(
                        return_value=(mock_token_response, mock_stored_state)
                    )

                    # Act
                    result = await connector_service._handle_oauth_connector_callback(
                        user_id=test_user_with_id.id,
                        code="code",
                        state="state",
                        connector_type=ConnectorType.GOOGLE_CONTACTS,
                        provider_factory_method=mock_factory,
                        metadata=custom_metadata,
                    )
                    await async_session.commit()

        # Assert - Metadata stored
        assert result.metadata == custom_metadata

    async def test_encrypts_credentials(self, connector_service, test_user_with_id, async_session):
        """Test that credentials are encrypted before storage."""
        # Arrange
        mock_token_response = MagicMock()
        mock_token_response.token_type = "Bearer"
        mock_token_response.access_token = "sensitive-access-token"
        mock_token_response.refresh_token = "sensitive-refresh-token"
        mock_token_response.expires_in = 3600
        mock_token_response.scope = "scope"

        mock_stored_state = {
            "provider": "google",
            "code_verifier": "verifier",
            "user_id": str(test_user_with_id.id),
            "connector_type": ConnectorType.GOOGLE_GMAIL.value,
        }

        def mock_factory(settings):
            return MagicMock()

        with patch("src.domains.connectors.service.get_redis_session"):
            with patch("src.domains.connectors.service.SessionService"):
                with patch("src.core.oauth.OAuthFlowHandler") as mock_handler_class:
                    mock_handler = mock_handler_class.return_value
                    mock_handler.handle_callback = AsyncMock(
                        return_value=(mock_token_response, mock_stored_state)
                    )

                    # Act
                    result = await connector_service._handle_oauth_connector_callback(
                        user_id=test_user_with_id.id,
                        code="code",
                        state="state",
                        connector_type=ConnectorType.GOOGLE_GMAIL,
                        provider_factory_method=mock_factory,
                    )
                    await async_session.commit()

        # Assert - Credentials encrypted (not plaintext)
        # Need to fetch the database model to access encrypted credentials
        import json

        from src.core.security import decrypt_data
        from src.domains.connectors.repository import ConnectorRepository

        repo = ConnectorRepository(async_session)
        connector_model = await repo.get_by_id(result.id)

        assert connector_model.credentials_encrypted is not None
        assert "sensitive-access-token" not in connector_model.credentials_encrypted
        assert "sensitive-refresh-token" not in connector_model.credentials_encrypted

        # Verify can be decrypted
        decrypted = json.loads(decrypt_data(connector_model.credentials_encrypted))
        assert decrypted["access_token"] == "sensitive-access-token"
        assert decrypted["refresh_token"] == "sensitive-refresh-token"


@pytest.mark.integration  # Uses testcontainers (PostgreSQL) but mocks Redis
class TestHandleGmailCallback:
    """Test ConnectorService.handle_gmail_callback() using generic handler."""

    @pytest.fixture(autouse=True)
    def mock_redis_cache(self):
        """Auto-use fixture to mock Redis cache for all tests in this class."""
        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock(return_value=True)
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.setex = AsyncMock(return_value=True)
        with patch("src.infrastructure.cache.redis.get_redis_cache", return_value=mock_redis):
            yield mock_redis

    async def test_gmail_callback_creates_gmail_connector(
        self, connector_service, test_user_with_id, async_session
    ):
        """Test Gmail callback creates Gmail connector."""
        # Arrange
        code = "gmail-code"
        state = "gmail-state"

        mock_token_response = MagicMock()
        mock_token_response.token_type = "Bearer"
        mock_token_response.access_token = "gmail-token"
        mock_token_response.refresh_token = "gmail-refresh"
        mock_token_response.expires_in = 3600
        mock_token_response.scope = "https://www.googleapis.com/auth/gmail.readonly"

        mock_stored_state = {
            "provider": "google",
            "code_verifier": "verifier",
            "user_id": str(test_user_with_id.id),
            "connector_type": ConnectorType.GOOGLE_GMAIL.value,
        }

        with patch("src.domains.connectors.service.get_redis_session"):
            with patch("src.domains.connectors.service.SessionService"):
                with patch("src.core.oauth.OAuthFlowHandler") as mock_handler_class:
                    mock_handler = mock_handler_class.return_value
                    mock_handler.handle_callback = AsyncMock(
                        return_value=(mock_token_response, mock_stored_state)
                    )

                    # Act
                    result = await connector_service.handle_gmail_callback(
                        test_user_with_id.id, code, state
                    )
                    await async_session.commit()

        # Assert
        assert result.connector_type == ConnectorType.GOOGLE_GMAIL
        assert result.status == ConnectorStatus.ACTIVE
        assert result.metadata.get("last_synced") is None

    async def test_gmail_callback_delegates_to_generic_handler(
        self, connector_service, test_user_with_id, async_session
    ):
        """Test that Gmail callback delegates to generic _handle_oauth_connector_callback."""
        # Arrange
        mock_token_response = MagicMock()
        mock_token_response.token_type = "Bearer"
        mock_token_response.access_token = "token"
        mock_token_response.refresh_token = "refresh"
        mock_token_response.expires_in = 3600
        mock_token_response.scope = "scope"

        mock_stored_state = {
            "provider": "google",
            "code_verifier": "verifier",
            "user_id": str(test_user_with_id.id),
            "connector_type": ConnectorType.GOOGLE_GMAIL.value,
        }

        with patch("src.domains.connectors.service.get_redis_session"):
            with patch("src.domains.connectors.service.SessionService"):
                with patch("src.core.oauth.OAuthFlowHandler") as mock_handler_class:
                    mock_handler = mock_handler_class.return_value
                    mock_handler.handle_callback = AsyncMock(
                        return_value=(mock_token_response, mock_stored_state)
                    )

                    with patch.object(
                        connector_service, "_handle_oauth_connector_callback"
                    ) as mock_generic:
                        mock_generic.return_value = AsyncMock()

                        # Act
                        await connector_service.handle_gmail_callback(
                            test_user_with_id.id, "code", "state"
                        )

        # Assert - Generic handler was called
        mock_generic.assert_called_once()
        call_kwargs = mock_generic.call_args.kwargs
        assert call_kwargs["connector_type"] == ConnectorType.GOOGLE_GMAIL


@pytest.mark.integration  # Uses testcontainers (PostgreSQL) but mocks Redis
class TestHandleGoogleContactsCallback:
    """Test ConnectorService.handle_google_contacts_callback() using generic handler."""

    @pytest.fixture(autouse=True)
    def mock_redis_cache(self):
        """Auto-use fixture to mock Redis cache for all tests in this class."""
        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock(return_value=True)
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.setex = AsyncMock(return_value=True)
        with patch("src.infrastructure.cache.redis.get_redis_cache", return_value=mock_redis):
            yield mock_redis

    async def test_contacts_callback_creates_contacts_connector(
        self, connector_service, test_user_with_id, async_session
    ):
        """Test Contacts callback creates Google Contacts connector."""
        # Arrange
        code = "contacts-code"
        state = "contacts-state"

        mock_token_response = MagicMock()
        mock_token_response.token_type = "Bearer"
        mock_token_response.access_token = "contacts-token"
        mock_token_response.refresh_token = "contacts-refresh"
        mock_token_response.expires_in = 3600
        mock_token_response.scope = "https://www.googleapis.com/auth/contacts.readonly"

        mock_stored_state = {
            "provider": "google",
            "code_verifier": "verifier",
            "user_id": str(test_user_with_id.id),
            "connector_type": ConnectorType.GOOGLE_CONTACTS.value,
        }

        with patch("src.domains.connectors.service.get_redis_session"):
            with patch("src.domains.connectors.service.SessionService"):
                with patch("src.core.oauth.OAuthFlowHandler") as mock_handler_class:
                    mock_handler = mock_handler_class.return_value
                    mock_handler.handle_callback = AsyncMock(
                        return_value=(mock_token_response, mock_stored_state)
                    )

                    # Act
                    result = await connector_service.handle_google_contacts_callback(
                        test_user_with_id.id, code, state
                    )
                    await async_session.commit()

        # Assert
        assert result.connector_type == ConnectorType.GOOGLE_CONTACTS
        assert result.status == ConnectorStatus.ACTIVE
        assert result.metadata.get("created_via") == "oauth_flow"

    async def test_contacts_callback_uses_default_scopes(
        self, connector_service, test_user_with_id, async_session
    ):
        """Test that Contacts callback uses GOOGLE_CONTACTS_SCOPES."""
        # Arrange
        mock_token_response = MagicMock()
        mock_token_response.token_type = "Bearer"
        mock_token_response.access_token = "token"
        mock_token_response.refresh_token = "refresh"
        mock_token_response.expires_in = 3600
        mock_token_response.scope = None  # No scope in response

        mock_stored_state = {
            "provider": "google",
            "code_verifier": "verifier",
            "user_id": str(test_user_with_id.id),
            "connector_type": ConnectorType.GOOGLE_CONTACTS.value,
        }

        with patch("src.domains.connectors.service.get_redis_session"):
            with patch("src.domains.connectors.service.SessionService"):
                with patch("src.core.oauth.OAuthFlowHandler") as mock_handler_class:
                    mock_handler = mock_handler_class.return_value
                    mock_handler.handle_callback = AsyncMock(
                        return_value=(mock_token_response, mock_stored_state)
                    )

                    # Act
                    result = await connector_service.handle_google_contacts_callback(
                        test_user_with_id.id, "code", "state"
                    )
                    await async_session.commit()

        # Assert - Default scopes applied
        from src.domains.connectors.service import GOOGLE_CONTACTS_SCOPES

        assert result.scopes == GOOGLE_CONTACTS_SCOPES


@pytest.mark.integration  # Uses testcontainers (PostgreSQL) and Redis
class TestErrorHandling:
    """Test error handling in generic OAuth connector callback."""

    async def test_handles_token_exchange_failure(
        self, connector_service, test_user_with_id, async_session
    ):
        """Test handling of token exchange failure."""

        # Arrange
        def mock_factory(settings):
            return MagicMock()

        with patch("src.domains.connectors.service.get_redis_session"):
            with patch("src.domains.connectors.service.SessionService"):
                with patch("src.core.oauth.OAuthFlowHandler") as mock_handler_class:
                    mock_handler = mock_handler_class.return_value
                    mock_handler.handle_callback = AsyncMock(
                        side_effect=Exception("Token exchange failed")
                    )

                    # Act & Assert
                    with pytest.raises(HTTPException) as exc_info:
                        await connector_service._handle_oauth_connector_callback(
                            user_id=test_user_with_id.id,
                            code="code",
                            state="state",
                            connector_type=ConnectorType.GOOGLE_GMAIL,
                            provider_factory_method=mock_factory,
                        )

                    assert exc_info.value.status_code == 400
                    assert "OAuth flow failed" in exc_info.value.detail
