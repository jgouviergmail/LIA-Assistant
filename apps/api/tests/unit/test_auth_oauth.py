"""
Unit tests for OAuth 2.0 authentication methods in AuthService.

Tests cover:
- Google OAuth flow initiation with PKCE
- State token generation and validation
- Code verifier and code challenge generation (tested in test_security.py)
- OAuth callback handling
- Security aspects (PKCE, state token CSRF protection)

Note: These tests mock SessionService since it's the abstraction layer used by AuthService.
"""

import re
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from src.core.security import (
    generate_code_challenge,
    generate_code_verifier,
    generate_state_token,
)
from src.domains.auth.service import AuthService


@pytest.mark.unit
class TestGoogleOAuthInitiation:
    """Test Google OAuth flow initiation."""

    @pytest.mark.asyncio
    async def test_initiate_google_oauth_generates_state_and_pkce(self):
        """Test OAuth initiation generates state token and PKCE parameters."""
        mock_db = AsyncMock()
        service = AuthService(mock_db)

        with (
            patch("src.domains.auth.service.get_redis_session") as mock_redis,
            patch("src.domains.auth.service.SessionService") as mock_session_service_class,
        ):
            mock_redis_instance = AsyncMock()
            mock_redis.return_value = mock_redis_instance

            mock_session_service = AsyncMock()
            mock_session_service_class.return_value = mock_session_service

            auth_url, state = await service.initiate_google_oauth()

            # Verify state token is generated
            assert isinstance(state, str)
            assert len(state) > 0

            # Verify authorization URL contains required parameters
            assert "https://accounts.google.com/o/oauth2/v2/auth" in auth_url
            assert "client_id" in auth_url
            assert "redirect_uri" in auth_url
            assert "response_type=code" in auth_url
            assert "scope" in auth_url
            assert f"state={state}" in auth_url

            # Verify PKCE parameters in URL
            assert "code_challenge" in auth_url
            assert "code_challenge_method=S256" in auth_url

            # Verify SessionService.store_oauth_state was called once with state + code_verifier
            mock_session_service.store_oauth_state.assert_called_once()
            call_args = mock_session_service.store_oauth_state.call_args
            assert call_args[0][0] == state  # First arg is state
            assert "code_verifier" in call_args[0][1]  # Second arg contains code_verifier
            assert call_args[0][1]["provider"] == "google"

    @pytest.mark.asyncio
    async def test_initiate_google_oauth_stores_state_with_ttl(self):
        """Test OAuth initiation stores state token with 5 minute expiration."""
        mock_db = AsyncMock()
        service = AuthService(mock_db)

        with (
            patch("src.domains.auth.service.get_redis_session") as mock_redis,
            patch("src.domains.auth.service.SessionService") as mock_session_service_class,
        ):
            mock_redis_instance = AsyncMock()
            mock_redis.return_value = mock_redis_instance

            mock_session_service = AsyncMock()
            mock_session_service_class.return_value = mock_session_service

            _auth_url, state = await service.initiate_google_oauth()

            # Verify expire_minutes=5 parameter
            call_args = mock_session_service.store_oauth_state.call_args
            assert call_args[1]["expire_minutes"] == 5  # Keyword arg
            assert state  # Verify state was generated

    @pytest.mark.asyncio
    async def test_initiate_google_oauth_unique_state_tokens(self):
        """Test that multiple OAuth initiations generate unique state tokens."""
        mock_db = AsyncMock()
        service = AuthService(mock_db)

        states = []

        with (
            patch("src.domains.auth.service.get_redis_session") as mock_redis,
            patch("src.domains.auth.service.SessionService") as mock_session_service_class,
        ):
            mock_redis_instance = AsyncMock()
            mock_redis.return_value = mock_redis_instance

            mock_session_service = AsyncMock()
            mock_session_service_class.return_value = mock_session_service

            for _ in range(5):
                _, state = await service.initiate_google_oauth()
                states.append(state)

        # All state tokens should be unique
        assert len(states) == len(set(states))


@pytest.mark.unit
class TestGoogleOAuthCallback:
    """Test Google OAuth callback handling."""

    @pytest.mark.asyncio
    async def test_handle_google_callback_validates_state_token(self):
        """Test callback validates state token from Redis."""
        mock_db = AsyncMock()
        service = AuthService(mock_db)

        code = "auth_code_123"
        state = str(uuid4())

        with (
            patch("src.domains.auth.service.get_redis_session") as mock_redis,
            patch("src.domains.auth.service.SessionService") as mock_session_service_class,
        ):
            mock_redis_instance = AsyncMock()
            mock_redis.return_value = mock_redis_instance

            mock_session_service = AsyncMock()
            mock_session_service_class.return_value = mock_session_service
            # Simulate state not found in Redis (expired or invalid)
            mock_session_service.get_oauth_state.return_value = None

            with pytest.raises(HTTPException) as exc_info:
                await service.handle_google_callback(code, state)

            assert exc_info.value.status_code == 400
            assert "invalid" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_handle_google_callback_rejects_wrong_provider(self):
        """Test callback rejects state with wrong provider."""
        mock_db = AsyncMock()
        service = AuthService(mock_db)

        code = "auth_code_123"
        state = str(uuid4())

        with (
            patch("src.domains.auth.service.get_redis_session") as mock_redis,
            patch("src.domains.auth.service.SessionService") as mock_session_service_class,
        ):
            mock_redis_instance = AsyncMock()
            mock_redis.return_value = mock_redis_instance

            mock_session_service = AsyncMock()
            mock_session_service_class.return_value = mock_session_service
            # Return state but with wrong provider
            mock_session_service.get_oauth_state.return_value = {
                "provider": "facebook",  # Wrong provider
                "code_verifier": "verifier123",
            }

            with pytest.raises(HTTPException) as exc_info:
                await service.handle_google_callback(code, state)

            assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_handle_google_callback_requires_code_verifier(self):
        """Test callback requires PKCE code_verifier in stored state."""
        mock_db = AsyncMock()
        service = AuthService(mock_db)

        code = "auth_code_123"
        state = str(uuid4())

        with (
            patch("src.domains.auth.service.get_redis_session") as mock_redis,
            patch("src.domains.auth.service.SessionService") as mock_session_service_class,
        ):
            mock_redis_instance = AsyncMock()
            mock_redis.return_value = mock_redis_instance

            mock_session_service = AsyncMock()
            mock_session_service_class.return_value = mock_session_service
            # Return state but WITHOUT code_verifier
            mock_session_service.get_oauth_state.return_value = {
                "provider": "google",
                # Missing code_verifier
            }

            with pytest.raises(HTTPException) as exc_info:
                await service.handle_google_callback(code, state)

            assert exc_info.value.status_code == 400


@pytest.mark.unit
@pytest.mark.security
class TestOAuthSecurity:
    """Test OAuth security aspects."""

    @pytest.mark.asyncio
    async def test_pkce_code_challenge_matches_verifier(self):
        """Test that code_challenge is correctly derived from code_verifier."""
        verifier = generate_code_verifier()
        challenge = generate_code_challenge(verifier)

        # Challenge should be deterministic for same verifier
        challenge2 = generate_code_challenge(verifier)
        assert challenge == challenge2

        # Different verifier should produce different challenge
        verifier2 = generate_code_verifier()
        challenge3 = generate_code_challenge(verifier2)
        assert challenge != challenge3

    @pytest.mark.asyncio
    async def test_state_token_csrf_protection(self):
        """Test state token provides CSRF protection."""
        state1 = generate_state_token()
        state2 = generate_state_token()

        # Each state token should be unique
        assert state1 != state2

        # State tokens should be long enough (RFC 6749 recommends 128+ bits = 32 hex chars)
        assert len(state1) >= 32
        assert len(state2) >= 32

    @pytest.mark.asyncio
    async def test_code_verifier_length_meets_rfc7636(self):
        """Test PKCE code_verifier meets RFC 7636 requirements (43-128 chars)."""
        verifier = generate_code_verifier()

        # RFC 7636 requires 43-128 characters
        assert 43 <= len(verifier) <= 128

        # Should contain only unreserved characters
        assert re.match(r"^[A-Za-z0-9_-]+$", verifier)

    @pytest.mark.asyncio
    async def test_code_challenge_sha256_format(self):
        """Test code_challenge uses SHA-256 as required by RFC 7636."""
        verifier = generate_code_verifier()
        challenge = generate_code_challenge(verifier)

        # SHA-256 base64url encoded without padding = 43 characters
        assert len(challenge) == 43

        # Should not contain padding
        assert "=" not in challenge

        # Should contain only base64url characters
        assert re.match(r"^[A-Za-z0-9_-]+$", challenge)

    @pytest.mark.asyncio
    async def test_oauth_state_data_structure(self):
        """Test OAuth state stores both provider and code_verifier."""
        mock_db = AsyncMock()
        service = AuthService(mock_db)

        with (
            patch("src.domains.auth.service.get_redis_session") as mock_redis,
            patch("src.domains.auth.service.SessionService") as mock_session_service_class,
        ):
            mock_redis_instance = AsyncMock()
            mock_redis.return_value = mock_redis_instance

            mock_session_service = AsyncMock()
            mock_session_service_class.return_value = mock_session_service

            await service.initiate_google_oauth()

            # Verify stored data structure
            call_args = mock_session_service.store_oauth_state.call_args
            stored_data = call_args[0][1]

            assert "provider" in stored_data
            assert stored_data["provider"] == "google"
            assert "code_verifier" in stored_data
            assert isinstance(stored_data["code_verifier"], str)
            assert len(stored_data["code_verifier"]) >= 43  # RFC 7636 min length

    @pytest.mark.asyncio
    async def test_oauth_callback_uses_get_oauth_state(self):
        """Test callback uses get_oauth_state which deletes after reading."""
        mock_db = AsyncMock()
        service = AuthService(mock_db)

        code = "auth_code_123"
        state = str(uuid4())

        with (
            patch("src.domains.auth.service.get_redis_session") as mock_redis,
            patch("src.domains.auth.service.SessionService") as mock_session_service_class,
        ):
            mock_redis_instance = AsyncMock()
            mock_redis.return_value = mock_redis_instance

            mock_session_service = AsyncMock()
            mock_session_service_class.return_value = mock_session_service
            mock_session_service.get_oauth_state.return_value = None

            try:
                await service.handle_google_callback(code, state)
            except HTTPException:
                pass

            # Verify get_oauth_state was called (which auto-deletes the state)
            mock_session_service.get_oauth_state.assert_called_once_with(state)
