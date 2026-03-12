"""
Unit tests for AuthService refactored methods (Sprint 5).

Tests cover:
- handle_google_callback() decomposed into 3 helpers
- _exchange_oauth_code() - OAuth token exchange
- _fetch_google_userinfo() - Fetch user info from Google API
- _find_or_create_google_user() - Find existing or create new user
- Full OAuth flow scenarios

NOTE: These tests require a real database (testcontainers) and are slow.
They should be moved to tests/integration/ folder.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.auth.service import AuthService
from tests.fixtures.factories import UserFactory

# Skip module - requires testcontainers/Docker, too slow for pre-commit
# TODO: Move to tests/integration/
pytestmark = pytest.mark.integration


@pytest.fixture
def mock_oauth_flow_handler():
    """Create mock OAuthFlowHandler."""
    handler = MagicMock()
    handler.handle_callback = AsyncMock()
    return handler


@pytest_asyncio.fixture
async def auth_service(async_session: AsyncSession) -> AuthService:
    """Create AuthService instance with async session."""
    return AuthService(async_session)


@pytest.mark.unit
class TestHandleGoogleCallbackRefactored:
    """Test AuthService.handle_google_callback() refactored method."""

    async def test_full_oauth_flow_new_user(self, auth_service, async_session):
        """Test complete OAuth flow creating a new user."""
        # Arrange
        code = "test-code"
        state = "test-state"

        # Mock token response
        mock_token_response = MagicMock()
        mock_token_response.access_token = "access-token-123"

        # Mock Google userinfo response
        userinfo = {
            "id": "google-user-123",
            "email": "newuser@example.com",
            "name": "New User",
            "picture": "https://example.com/photo.jpg",
        }

        with patch.object(
            auth_service, "_exchange_oauth_code", return_value=mock_token_response
        ) as mock_exchange:
            with patch.object(
                auth_service, "_fetch_google_userinfo", return_value=userinfo
            ) as mock_fetch:
                # Act
                user_response = await auth_service.handle_google_callback(code, state)
                await async_session.commit()

        # Assert
        mock_exchange.assert_called_once_with(code, state)
        mock_fetch.assert_called_once_with("access-token-123")

        assert user_response.email == "newuser@example.com"
        assert user_response.full_name == "New User"

    async def test_links_oauth_to_existing_email(self, auth_service, async_session, test_user):
        """Test OAuth flow links Google account to existing email user."""
        # Arrange - User exists with email but no OAuth
        existing_email = test_user.email
        code = "test-code"
        state = "test-state"

        mock_token_response = MagicMock()
        mock_token_response.access_token = "access-token"

        userinfo = {
            "id": "google-123",
            "email": existing_email,  # Same email as existing user
            "name": "Updated Name",
            "picture": "https://example.com/pic.jpg",
        }

        with patch.object(auth_service, "_exchange_oauth_code", return_value=mock_token_response):
            with patch.object(auth_service, "_fetch_google_userinfo", return_value=userinfo):
                # Act
                await auth_service.handle_google_callback(code, state)
                await async_session.commit()
                await async_session.refresh(test_user)

        # Assert - OAuth linked to existing user
        assert test_user.oauth_provider == "google"
        assert test_user.oauth_provider_id == "google-123"
        assert test_user.is_verified is True  # Google verifies emails

    async def test_returns_existing_oauth_user(self, auth_service, async_session):
        """Test OAuth flow returns existing user by OAuth provider ID."""
        # Arrange - Create user with OAuth already linked
        oauth_user = UserFactory.create_oauth_user(provider="google")
        async_session.add(oauth_user)
        await async_session.commit()

        code = "test-code"
        state = "test-state"

        mock_token_response = MagicMock()
        mock_token_response.access_token = "access-token"

        userinfo = {
            "id": oauth_user.oauth_provider_id,  # Same OAuth ID
            "email": oauth_user.email,
            "name": oauth_user.full_name,
        }

        with patch.object(auth_service, "_exchange_oauth_code", return_value=mock_token_response):
            with patch.object(auth_service, "_fetch_google_userinfo", return_value=userinfo):
                # Act
                user_response = await auth_service.handle_google_callback(code, state)

        # Assert - Returns existing user
        assert user_response.id == oauth_user.id
        assert user_response.email == oauth_user.email


@pytest.mark.unit
class TestExchangeOAuthCode:
    """Test AuthService._exchange_oauth_code() private method."""

    async def test_delegates_to_oauth_flow_handler(self, auth_service):
        """Test that _exchange_oauth_code delegates to OAuthFlowHandler."""
        # Arrange
        code = "auth-code"
        state = "state-token"

        mock_token_response = MagicMock()
        mock_token_response.access_token = "token-xyz"
        mock_stored_state = {"provider": "google", "code_verifier": "verifier"}

        with patch("src.domains.auth.service.get_redis_session"):
            with patch("src.domains.auth.service.SessionService"):
                with patch("src.core.oauth.OAuthFlowHandler") as mock_handler_class:
                    mock_handler = mock_handler_class.return_value
                    mock_handler.handle_callback = AsyncMock(
                        return_value=(mock_token_response, mock_stored_state)
                    )

                    # Act
                    result = await auth_service._exchange_oauth_code(code, state)

        # Assert
        assert result == mock_token_response
        mock_handler.handle_callback.assert_called_once_with(code, state)

    async def test_raises_http_exception_on_error(self, auth_service):
        """Test that _exchange_oauth_code raises HTTPException on OAuth error."""
        # Arrange
        code = "invalid-code"
        state = "state"

        with patch("src.domains.auth.service.get_redis_session"):
            with patch("src.domains.auth.service.SessionService"):
                with patch("src.core.oauth.OAuthFlowHandler") as mock_handler_class:
                    mock_handler = mock_handler_class.return_value
                    mock_handler.handle_callback = AsyncMock(
                        side_effect=Exception("OAuth flow failed")
                    )

                    # Act & Assert
                    with pytest.raises(HTTPException) as exc_info:
                        await auth_service._exchange_oauth_code(code, state)

                    assert exc_info.value.status_code == 400
                    assert "OAuth flow failed" in exc_info.value.detail


@pytest.mark.unit
class TestFetchGoogleUserinfo:
    """Test AuthService._fetch_google_userinfo() private method."""

    async def test_makes_http_call_to_google_api(self, auth_service):
        """Test that _fetch_google_userinfo makes HTTP GET to Google userinfo API."""
        # Arrange
        access_token = "valid-access-token"

        userinfo_data = {
            "id": "123456",
            "email": "user@example.com",
            "name": "Test User",
            "picture": "https://example.com/pic.jpg",
        }

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = mock_client_class.return_value.__aenter__.return_value
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = userinfo_data
            mock_client.get = AsyncMock(return_value=mock_response)

            # Act
            result = await auth_service._fetch_google_userinfo(access_token)

        # Assert
        mock_client.get.assert_called_once()
        call_args = mock_client.get.call_args

        # Check URL
        assert "googleapis.com/oauth2/v2/userinfo" in call_args.args[0]

        # Check Authorization header
        assert call_args.kwargs["headers"]["Authorization"] == f"Bearer {access_token}"

        # Check result
        assert result == userinfo_data

    async def test_handles_http_400_error(self, auth_service):
        """Test handling of HTTP 400 error from Google API."""
        # Arrange
        access_token = "invalid-token"

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = mock_client_class.return_value.__aenter__.return_value
            mock_response = MagicMock()
            mock_response.status_code = 400
            mock_response.text = "Invalid token"
            mock_client.get = AsyncMock(return_value=mock_response)

            # Act & Assert
            with pytest.raises(HTTPException) as exc_info:
                await auth_service._fetch_google_userinfo(access_token)

            assert exc_info.value.status_code == 400
            assert "Failed to get user info" in exc_info.value.detail

    async def test_handles_http_500_error(self, auth_service):
        """Test handling of HTTP 500 error from Google API."""
        # Arrange
        access_token = "valid-token"

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = mock_client_class.return_value.__aenter__.return_value
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.text = "Internal server error"
            mock_client.get = AsyncMock(return_value=mock_response)

            # Act & Assert
            with pytest.raises(HTTPException) as exc_info:
                await auth_service._fetch_google_userinfo(access_token)

            assert exc_info.value.status_code == 400


@pytest.mark.unit
class TestFindOrCreateGoogleUser:
    """Test AuthService._find_or_create_google_user() private method."""

    async def test_finds_existing_user_by_provider_id(self, auth_service, async_session):
        """Test finding existing user by OAuth provider ID."""
        # Arrange - Create user with OAuth
        existing_user = UserFactory.create_oauth_user(provider="google")
        async_session.add(existing_user)
        await async_session.commit()

        userinfo = {
            "id": existing_user.oauth_provider_id,  # Same OAuth ID
            "email": existing_user.email,
            "name": existing_user.full_name,
        }

        # Act
        user = await auth_service._find_or_create_google_user(userinfo)

        # Assert - Found existing user
        assert user.id == existing_user.id
        assert user.oauth_provider_id == existing_user.oauth_provider_id

    async def test_finds_existing_user_by_email(self, auth_service, async_session):
        """Test finding existing user by email and linking OAuth."""
        # Arrange - Create user WITHOUT OAuth
        existing_user = UserFactory.create(
            email="existing@example.com",
            full_name="Existing User",
            oauth_provider=None,
            oauth_provider_id=None,
        )
        async_session.add(existing_user)
        await async_session.commit()

        userinfo = {
            "id": "google-new-123",
            "email": "existing@example.com",  # Same email
            "name": "Updated Name",
            "picture": "https://example.com/pic.jpg",
        }

        # Act
        user = await auth_service._find_or_create_google_user(userinfo)
        await async_session.commit()
        await async_session.refresh(user)

        # Assert - OAuth linked to existing user
        assert user.id == existing_user.id
        assert user.oauth_provider == "google"
        assert user.oauth_provider_id == "google-new-123"
        assert user.picture_url == "https://example.com/pic.jpg"
        assert user.is_verified is True
        assert user.is_active is True

    async def test_creates_new_user(self, auth_service, async_session):
        """Test creating new user when no existing user found."""
        # Arrange
        userinfo = {
            "id": "google-brand-new",
            "email": "brandnew@example.com",
            "name": "Brand New User",
            "picture": "https://example.com/new.jpg",
        }

        # Act
        user = await auth_service._find_or_create_google_user(userinfo)
        await async_session.commit()

        # Assert - New user created
        assert user.id is not None
        assert user.email == "brandnew@example.com"
        assert user.full_name == "Brand New User"
        assert user.oauth_provider == "google"
        assert user.oauth_provider_id == "google-brand-new"
        assert user.picture_url == "https://example.com/new.jpg"
        assert user.is_active is False  # New users disabled by default (admin approval required)
        assert user.is_verified is True
        assert user.hashed_password is None  # OAuth users don't have password

    async def test_handles_missing_name_in_userinfo(self, auth_service, async_session):
        """Test creating user with missing 'name' field in userinfo."""
        # Arrange
        userinfo = {
            "id": "google-no-name",
            "email": "noname@example.com",
            # Missing 'name'
        }

        # Act
        user = await auth_service._find_or_create_google_user(userinfo)
        await async_session.commit()

        # Assert - User created with None full_name
        assert user.email == "noname@example.com"
        assert user.full_name is None

    async def test_handles_missing_picture_in_userinfo(self, auth_service, async_session):
        """Test creating user with missing 'picture' field in userinfo."""
        # Arrange
        userinfo = {
            "id": "google-no-pic",
            "email": "nopicture@example.com",
            "name": "No Picture User",
            # Missing 'picture'
        }

        # Act
        user = await auth_service._find_or_create_google_user(userinfo)
        await async_session.commit()

        # Assert - User created with None picture_url
        assert user.picture_url is None

    async def test_verifies_new_user_but_inactive(self, auth_service, async_session):
        """Test that new OAuth users are verified but inactive (requires admin approval)."""
        # Arrange
        userinfo = {
            "id": "google-new-verified",
            "email": "verified@example.com",
            "name": "Verified User",
        }

        # Act
        user = await auth_service._find_or_create_google_user(userinfo)
        await async_session.commit()

        # Assert - OAuth users are verified (Google verifies email) but inactive by default
        assert user.is_active is False  # Requires admin approval
        assert user.is_verified is True


@pytest.mark.unit
class TestIntegrationScenarios:
    """Test integration scenarios combining multiple methods."""

    async def test_complete_new_user_registration_flow(self, auth_service, async_session):
        """Test complete flow: new user registers via Google OAuth."""
        # Arrange
        code = "new-user-code"
        state = "new-user-state"

        mock_token_response = MagicMock()
        mock_token_response.access_token = "new-user-token"

        userinfo = {
            "id": "google-completely-new",
            "email": "completelynew@example.com",
            "name": "Completely New User",
            "picture": "https://example.com/new-user.jpg",
        }

        with patch.object(auth_service, "_exchange_oauth_code", return_value=mock_token_response):
            with patch.object(auth_service, "_fetch_google_userinfo", return_value=userinfo):
                # Act
                user_response = await auth_service.handle_google_callback(code, state)
                await async_session.commit()

        # Assert - Complete new user created
        assert user_response.email == "completelynew@example.com"
        assert user_response.full_name == "Completely New User"
        # Verify in database
        from src.domains.auth.repository import AuthRepository

        repo = AuthRepository(async_session)
        db_user = await repo.get_by_email("completelynew@example.com")
        assert db_user is not None
        assert db_user.oauth_provider == "google"
        assert db_user.is_verified is True

    async def test_returning_oauth_user_flow(self, auth_service, async_session):
        """Test complete flow: existing OAuth user logs in again."""
        # Arrange - Create existing OAuth user
        oauth_user = UserFactory.create_oauth_user(provider="google", email="returning@example.com")
        async_session.add(oauth_user)
        await async_session.commit()

        code = "returning-code"
        state = "returning-state"

        mock_token_response = MagicMock()
        mock_token_response.access_token = "returning-token"

        userinfo = {
            "id": oauth_user.oauth_provider_id,
            "email": oauth_user.email,
            "name": oauth_user.full_name,
        }

        with patch.object(auth_service, "_exchange_oauth_code", return_value=mock_token_response):
            with patch.object(auth_service, "_fetch_google_userinfo", return_value=userinfo):
                # Act
                user_response = await auth_service.handle_google_callback(code, state)

        # Assert - Returns existing user
        assert user_response.id == oauth_user.id
        assert user_response.email == oauth_user.email
