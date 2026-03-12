"""
Unit tests for OAuthFlowHandler (refactored Sprint 5).

Tests cover:
- initiate_flow() with PKCE generation and state storage
- handle_callback() decomposed into 3 private helpers (refactored)
- _validate_state_and_get_verifier() - state validation
- _exchange_code_for_tokens() - HTTP token exchange
- _parse_token_response() - response parsing
- Security: PKCE (S256), state validation, single-use tokens
- Error handling: invalid state, HTTP errors, malformed responses
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.core.oauth.exceptions import (
    OAuthProviderError,
    OAuthStateValidationError,
    OAuthTokenExchangeError,
)
from src.core.oauth.flow_handler import OAuthFlowHandler, OAuthTokenResponse
from src.infrastructure.cache.redis import SessionService


class MockOAuthProvider:
    """Mock OAuth provider for testing."""

    def __init__(self):
        self.provider_name = "google"
        self.client_id = "test-client-id"
        self.client_secret = "test-client-secret"
        self.redirect_uri = "http://localhost:8000/callback"
        self.authorization_endpoint = "https://accounts.google.com/o/oauth2/auth"
        self.token_endpoint = "https://oauth2.googleapis.com/token"
        self.revocation_endpoint = "https://oauth2.googleapis.com/revoke"
        self.scopes = ["openid", "email", "profile"]


@pytest.fixture
def mock_provider() -> MockOAuthProvider:
    """Create mock OAuth provider."""
    return MockOAuthProvider()


@pytest.fixture
def mock_session_service() -> AsyncMock:
    """Create mock SessionService."""
    service = AsyncMock(spec=SessionService)
    service.store_oauth_state = AsyncMock()
    service.get_oauth_state = AsyncMock()
    return service


@pytest.fixture
def oauth_handler(mock_provider, mock_session_service) -> OAuthFlowHandler:
    """Create OAuthFlowHandler with mocks."""
    return OAuthFlowHandler(mock_provider, mock_session_service)


@pytest.mark.unit
class TestInitiateFlow:
    """Test OAuthFlowHandler.initiate_flow() method."""

    async def test_generates_crypto_secure_tokens(self, oauth_handler):
        """Test that initiate_flow generates cryptographically secure state and verifier."""
        # Act
        auth_url, state = await oauth_handler.initiate_flow()

        # Assert
        assert isinstance(state, str)
        assert len(state) >= 40  # Crypto-secure length
        assert state in auth_url  # State included in URL

    async def test_stores_state_in_redis_with_ttl(self, oauth_handler, mock_session_service):
        """Test that state is stored in Redis with 5-minute TTL."""
        # Act
        await oauth_handler.initiate_flow()

        # Assert
        mock_session_service.store_oauth_state.assert_called_once()
        call_args = mock_session_service.store_oauth_state.call_args

        # Check TTL parameter
        assert call_args.kwargs["expire_minutes"] == 5

    async def test_builds_authorization_url_correctly(self, oauth_handler, mock_provider):
        """Test that authorization URL is built with correct parameters."""
        # Act
        auth_url, state = await oauth_handler.initiate_flow()

        # Assert
        from urllib.parse import quote

        assert mock_provider.authorization_endpoint in auth_url
        assert f"client_id={mock_provider.client_id}" in auth_url
        # URL-encoded redirect_uri
        assert f"redirect_uri={quote(mock_provider.redirect_uri, safe='')}" in auth_url
        assert "response_type=code" in auth_url
        assert f"state={state}" in auth_url
        assert "code_challenge=" in auth_url
        assert "code_challenge_method=S256" in auth_url  # PKCE S256

    async def test_includes_scopes_in_url(self, oauth_handler, mock_provider):
        """Test that scopes are included in authorization URL."""
        # Act
        auth_url, state = await oauth_handler.initiate_flow()

        # Assert
        assert "scope=" in auth_url
        # Check at least one scope is present
        assert any(scope in auth_url for scope in mock_provider.scopes)

    async def test_includes_additional_params(self, oauth_handler):
        """Test that additional parameters are included in URL."""
        # Arrange
        additional_params = {"access_type": "offline", "prompt": "consent"}

        # Act
        auth_url, state = await oauth_handler.initiate_flow(additional_params=additional_params)

        # Assert
        assert "access_type=offline" in auth_url
        assert "prompt=consent" in auth_url

    async def test_stores_metadata_with_state(self, oauth_handler, mock_session_service):
        """Test that business metadata is stored with state."""
        # Arrange
        metadata = {"user_id": "123", "connector_type": "emails"}

        # Act
        await oauth_handler.initiate_flow(metadata=metadata)

        # Assert
        call_args = mock_session_service.store_oauth_state.call_args
        state_data = call_args.args[1]  # Second argument is state_data dict

        # Check metadata is included
        assert "user_id" in state_data
        assert state_data["user_id"] == "123"
        assert "connector_type" in state_data
        assert state_data["connector_type"] == "emails"

    async def test_stores_pkce_verifier_with_state(self, oauth_handler, mock_session_service):
        """Test that PKCE code_verifier is stored with state."""
        # Act
        await oauth_handler.initiate_flow()

        # Assert
        call_args = mock_session_service.store_oauth_state.call_args
        state_data = call_args.args[1]

        assert "code_verifier" in state_data
        assert len(state_data["code_verifier"]) >= 43  # PKCE minimum length

    async def test_stores_provider_name_with_state(self, oauth_handler, mock_session_service):
        """Test that provider name is stored with state."""
        # Act
        await oauth_handler.initiate_flow()

        # Assert
        call_args = mock_session_service.store_oauth_state.call_args
        state_data = call_args.args[1]

        assert "provider" in state_data
        assert state_data["provider"] == "google"

    async def test_stores_timestamp_with_state(self, oauth_handler, mock_session_service):
        """Test that timestamp is stored with state."""
        # Act
        await oauth_handler.initiate_flow()

        # Assert
        call_args = mock_session_service.store_oauth_state.call_args
        state_data = call_args.args[1]

        assert "timestamp" in state_data
        # Verify it's a valid ISO format timestamp
        datetime.fromisoformat(state_data["timestamp"])


@pytest.mark.unit
class TestHandleCallback:
    """Test OAuthFlowHandler.handle_callback() refactored method (Sprint 5)."""

    async def test_successful_callback_flow(
        self, oauth_handler, mock_session_service, mock_provider
    ):
        """Test complete successful OAuth callback flow."""
        # Arrange
        code = "test-authorization-code"
        state = "test-state-token"
        code_verifier = "test-code-verifier"

        # Mock state validation
        stored_state = {
            "provider": "google",
            "code_verifier": code_verifier,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        mock_session_service.get_oauth_state.return_value = stored_state

        # Mock HTTP token exchange
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "access_token": "test-access-token",
            "refresh_token": "test-refresh-token",
            "expires_in": 3600,
            "scope": "openid email",
            "token_type": "Bearer",
        }

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = mock_client_class.return_value.__aenter__.return_value
            mock_client.post = AsyncMock(return_value=mock_response)

            # Act
            token_response, returned_state = await oauth_handler.handle_callback(code, state)

        # Assert
        assert isinstance(token_response, OAuthTokenResponse)
        assert token_response.access_token == "test-access-token"
        assert token_response.refresh_token == "test-refresh-token"
        assert token_response.expires_in == 3600
        assert returned_state == stored_state

    async def test_validates_state_successfully(self, oauth_handler, mock_session_service):
        """Test that valid state is accepted."""
        # Arrange
        code = "test-code"
        state = "valid-state"
        stored_state = {
            "provider": "google",
            "code_verifier": "test-verifier",
            "timestamp": datetime.now(UTC).isoformat(),
        }
        mock_session_service.get_oauth_state.return_value = stored_state

        # Mock HTTP response
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = mock_client_class.return_value.__aenter__.return_value
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "access_token": "token",
                "token_type": "Bearer",
            }
            mock_client.post = AsyncMock(return_value=mock_response)

            # Act & Assert - Should not raise
            await oauth_handler.handle_callback(code, state)

        # Verify state was retrieved
        mock_session_service.get_oauth_state.assert_called_once_with(state)

    async def test_rejects_invalid_state(self, oauth_handler, mock_session_service):
        """Test that invalid/expired state is rejected."""
        # Arrange
        code = "test-code"
        state = "invalid-state"
        mock_session_service.get_oauth_state.return_value = None  # State not found

        # Act & Assert
        with pytest.raises(OAuthStateValidationError, match="Invalid or expired"):
            await oauth_handler.handle_callback(code, state)

    async def test_rejects_provider_mismatch(self, oauth_handler, mock_session_service):
        """Test that provider mismatch is rejected (security)."""
        # Arrange
        code = "test-code"
        state = "test-state"
        stored_state = {
            "provider": "facebook",  # Different provider!
            "code_verifier": "test-verifier",
            "timestamp": datetime.now(UTC).isoformat(),
        }
        mock_session_service.get_oauth_state.return_value = stored_state

        # Act & Assert
        with pytest.raises(OAuthStateValidationError, match="provider mismatch"):
            await oauth_handler.handle_callback(code, state)

    async def test_requires_code_verifier(self, oauth_handler, mock_session_service):
        """Test that missing code_verifier is rejected (PKCE required)."""
        # Arrange
        code = "test-code"
        state = "test-state"
        stored_state = {
            "provider": "google",
            # Missing code_verifier!
            "timestamp": datetime.now(UTC).isoformat(),
        }
        mock_session_service.get_oauth_state.return_value = stored_state

        # Act & Assert
        with pytest.raises(OAuthStateValidationError, match="code_verifier not found"):
            await oauth_handler.handle_callback(code, state)

    async def test_exchanges_code_for_tokens(self, oauth_handler, mock_session_service):
        """Test that code is exchanged for tokens via HTTP POST."""
        # Arrange
        code = "test-code"
        state = "test-state"
        code_verifier = "test-verifier"
        stored_state = {
            "provider": "google",
            "code_verifier": code_verifier,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        mock_session_service.get_oauth_state.return_value = stored_state

        # Mock HTTP request
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = mock_client_class.return_value.__aenter__.return_value
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "access_token": "token",
                "token_type": "Bearer",
            }
            mock_client.post = AsyncMock(return_value=mock_response)

            # Act
            await oauth_handler.handle_callback(code, state)

            # Assert - Verify HTTP POST was made
            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args

            # Check endpoint
            assert call_args.args[0] == oauth_handler.provider.token_endpoint

            # Check PKCE verifier in request data
            assert call_args.kwargs["data"]["code_verifier"] == code_verifier
            assert call_args.kwargs["data"]["code"] == code

    async def test_parses_token_response_correctly(self, oauth_handler, mock_session_service):
        """Test that token response is parsed correctly."""
        # Arrange
        code = "test-code"
        state = "test-state"
        stored_state = {
            "provider": "google",
            "code_verifier": "verifier",
            "timestamp": datetime.now(UTC).isoformat(),
        }
        mock_session_service.get_oauth_state.return_value = stored_state

        token_data = {
            "access_token": "my-access-token",
            "refresh_token": "my-refresh-token",
            "expires_in": 7200,
            "scope": "openid email profile",
            "token_type": "Bearer",
            "id_token": "eyJhbGci...",  # OpenID Connect
        }

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = mock_client_class.return_value.__aenter__.return_value
            mock_response = MagicMock()
            mock_response.json.return_value = token_data
            mock_client.post = AsyncMock(return_value=mock_response)

            # Act
            token_response, _ = await oauth_handler.handle_callback(code, state)

        # Assert
        assert token_response.access_token == "my-access-token"
        assert token_response.refresh_token == "my-refresh-token"
        assert token_response.expires_in == 7200
        assert token_response.scope == "openid email profile"
        assert token_response.token_type == "Bearer"
        assert token_response.id_token == "eyJhbGci..."

    async def test_handles_http_400_error(self, oauth_handler, mock_session_service):
        """Test handling of HTTP 400 error from OAuth provider."""
        # Arrange
        code = "invalid-code"
        state = "test-state"
        stored_state = {
            "provider": "google",
            "code_verifier": "verifier",
            "timestamp": datetime.now(UTC).isoformat(),
        }
        mock_session_service.get_oauth_state.return_value = stored_state

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = mock_client_class.return_value.__aenter__.return_value
            # Simulate HTTP 400 error
            error_response = MagicMock()
            error_response.status_code = 400
            error_response.text = "invalid_grant"
            mock_client.post = AsyncMock(
                side_effect=httpx.HTTPStatusError(
                    "Bad Request", request=MagicMock(), response=error_response
                )
            )

            # Act & Assert
            with pytest.raises(OAuthTokenExchangeError, match="Token exchange failed"):
                await oauth_handler.handle_callback(code, state)

    async def test_handles_network_error(self, oauth_handler, mock_session_service):
        """Test handling of network errors during token exchange."""
        # Arrange
        code = "test-code"
        state = "test-state"
        stored_state = {
            "provider": "google",
            "code_verifier": "verifier",
            "timestamp": datetime.now(UTC).isoformat(),
        }
        mock_session_service.get_oauth_state.return_value = stored_state

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = mock_client_class.return_value.__aenter__.return_value
            # Simulate network error
            mock_client.post = AsyncMock(side_effect=httpx.RequestError("Connection timeout"))

            # Act & Assert
            with pytest.raises(OAuthTokenExchangeError, match="Network error"):
                await oauth_handler.handle_callback(code, state)

    async def test_handles_missing_access_token(self, oauth_handler, mock_session_service):
        """Test handling of malformed response missing access_token."""
        # Arrange
        code = "test-code"
        state = "test-state"
        stored_state = {
            "provider": "google",
            "code_verifier": "verifier",
            "timestamp": datetime.now(UTC).isoformat(),
        }
        mock_session_service.get_oauth_state.return_value = stored_state

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = mock_client_class.return_value.__aenter__.return_value
            mock_response = MagicMock()
            # Missing access_token!
            mock_response.json.return_value = {"token_type": "Bearer"}
            mock_client.post = AsyncMock(return_value=mock_response)

            # Act & Assert
            with pytest.raises(OAuthProviderError, match="missing"):
                await oauth_handler.handle_callback(code, state)


@pytest.mark.unit
class TestPrivateHelpers:
    """Test private helper methods (refactored Sprint 5)."""

    async def test_validate_state_retrieves_verifier(self, oauth_handler, mock_session_service):
        """Test _validate_state_and_get_verifier retrieves code_verifier."""
        # Arrange
        state = "test-state"
        stored_state = {
            "provider": "google",
            "code_verifier": "my-verifier-123",
            "timestamp": datetime.now(UTC).isoformat(),
        }
        mock_session_service.get_oauth_state.return_value = stored_state

        # Act
        result = await oauth_handler._validate_state_and_get_verifier(state)

        # Assert
        assert result == stored_state
        assert result["code_verifier"] == "my-verifier-123"

    async def test_validate_state_enforces_provider_match(
        self, oauth_handler, mock_session_service
    ):
        """Test _validate_state_and_get_verifier enforces provider match."""
        # Arrange
        state = "test-state"
        stored_state = {
            "provider": "facebook",  # Wrong provider
            "code_verifier": "verifier",
            "timestamp": datetime.now(UTC).isoformat(),
        }
        mock_session_service.get_oauth_state.return_value = stored_state

        # Act & Assert
        with pytest.raises(OAuthStateValidationError, match="provider mismatch"):
            await oauth_handler._validate_state_and_get_verifier(state)

    async def test_exchange_code_uses_verifier(self, oauth_handler):
        """Test _exchange_code_for_tokens includes PKCE verifier in request."""
        # Arrange
        code = "auth-code"
        code_verifier = "pkce-verifier-xyz"

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = mock_client_class.return_value.__aenter__.return_value
            mock_response = MagicMock()
            mock_response.json.return_value = {"access_token": "token", "token_type": "Bearer"}
            mock_client.post = AsyncMock(return_value=mock_response)

            # Act
            await oauth_handler._exchange_code_for_tokens(code, code_verifier)

            # Assert
            call_data = mock_client.post.call_args.kwargs["data"]
            assert call_data["code_verifier"] == code_verifier
            assert call_data["code"] == code
            assert call_data["grant_type"] == "authorization_code"

    async def test_parse_token_validates_required_fields(self, oauth_handler):
        """Test _parse_token_response validates required fields."""
        # Arrange - Valid token data
        token_data = {
            "access_token": "token",
            "token_type": "Bearer",
        }

        # Act
        result = oauth_handler._parse_token_response(token_data)

        # Assert
        assert result.access_token == "token"
        assert result.token_type == "Bearer"

    async def test_parse_token_raises_on_missing_field(self, oauth_handler):
        """Test _parse_token_response raises OAuthProviderError on missing field."""
        # Arrange - Missing access_token
        token_data = {"token_type": "Bearer"}

        # Act & Assert
        with pytest.raises(OAuthProviderError, match="missing"):
            oauth_handler._parse_token_response(token_data)


@pytest.mark.unit
class TestRevokeToken:
    """Test token revocation functionality."""

    async def test_revokes_token_successfully(self, oauth_handler):
        """Test successful token revocation."""
        # Arrange
        token = "token-to-revoke"

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = mock_client_class.return_value.__aenter__.return_value
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_client.post = AsyncMock(return_value=mock_response)

            # Act
            await oauth_handler.revoke_token(token)

            # Assert
            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args
            assert call_args.args[0] == oauth_handler.provider.revocation_endpoint

    async def test_handles_revocation_error_gracefully(self, oauth_handler):
        """Test that revocation errors are logged but don't raise (best effort)."""
        # Arrange
        token = "token-to-revoke"

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = mock_client_class.return_value.__aenter__.return_value
            mock_client.post = AsyncMock(side_effect=httpx.RequestError("Network error"))

            # Act - Should not raise
            await oauth_handler.revoke_token(token)

            # Assert - Error was logged but didn't propagate
            mock_client.post.assert_called_once()
