"""
Unit tests for core/session_helpers.py.

Tests session management helpers for BFF Pattern.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Response

from src.core.session_helpers import clear_session_cookie, create_authenticated_session_with_cookie


@pytest.mark.unit
class TestClearSessionCookie:
    """Tests for clear_session_cookie function."""

    def test_clears_session_cookie(self):
        """Test that session cookie is cleared."""
        response = MagicMock(spec=Response)

        with patch("src.core.session_helpers.settings") as mock_settings:
            mock_settings.session_cookie_name = "lia_session"
            mock_settings.session_cookie_domain = None
            mock_settings.session_cookie_samesite = "lax"

            clear_session_cookie(response)

            response.delete_cookie.assert_called_once_with(
                key="lia_session",
                domain=None,
                samesite="lax",
            )

    def test_clears_cookie_with_domain(self):
        """Test clearing cookie with domain set."""
        response = MagicMock(spec=Response)

        with patch("src.core.session_helpers.settings") as mock_settings:
            mock_settings.session_cookie_name = "session"
            mock_settings.session_cookie_domain = ".example.com"
            mock_settings.session_cookie_samesite = "strict"

            clear_session_cookie(response)

            response.delete_cookie.assert_called_once_with(
                key="session",
                domain=".example.com",
                samesite="strict",
            )


@pytest.mark.unit
class TestCreateAuthenticatedSessionWithCookie:
    """Tests for create_authenticated_session_with_cookie function."""

    @pytest.mark.asyncio
    async def test_creates_session_and_sets_cookie(self):
        """Test that session is created and cookie is set."""
        response = MagicMock(spec=Response)
        mock_session = MagicMock()
        mock_session.session_id = "test-session-id-123"
        mock_session.user_id = "user-456"

        with patch("src.core.session_helpers.get_redis_session") as mock_redis:
            with patch("src.core.session_helpers.SessionStore") as mock_store_class:
                with patch("src.core.session_helpers.settings") as mock_settings:
                    with patch("src.core.session_helpers.logger"):
                        mock_settings.session_cookie_max_age = 604800  # 7 days
                        mock_settings.session_cookie_max_age_remember = 2592000  # 30 days
                        mock_settings.session_cookie_name = "lia_session"
                        mock_settings.session_cookie_secure = True
                        mock_settings.session_cookie_httponly = True
                        mock_settings.session_cookie_samesite = "lax"
                        mock_settings.session_cookie_domain = None
                        mock_settings.is_production = False

                        mock_store = AsyncMock()
                        mock_store.create_session = AsyncMock(return_value=mock_session)
                        mock_store_class.return_value = mock_store
                        mock_redis.return_value = AsyncMock()

                        result = await create_authenticated_session_with_cookie(
                            response=response,
                            user_id="user-456",
                            remember_me=False,
                        )

                        assert result == mock_session
                        mock_store.create_session.assert_called_once_with(
                            user_id="user-456",
                            remember_me=False,
                        )
                        response.set_cookie.assert_called_once()

    @pytest.mark.asyncio
    async def test_remember_me_uses_extended_ttl(self):
        """Test that remember_me uses extended TTL."""
        response = MagicMock(spec=Response)
        mock_session = MagicMock()
        mock_session.session_id = "session-id"

        with patch("src.core.session_helpers.get_redis_session") as mock_redis:
            with patch("src.core.session_helpers.SessionStore") as mock_store_class:
                with patch("src.core.session_helpers.settings") as mock_settings:
                    with patch("src.core.session_helpers.logger"):
                        mock_settings.session_cookie_max_age = 604800  # 7 days
                        mock_settings.session_cookie_max_age_remember = 2592000  # 30 days
                        mock_settings.session_cookie_name = "session"
                        mock_settings.session_cookie_secure = True
                        mock_settings.session_cookie_httponly = True
                        mock_settings.session_cookie_samesite = "lax"
                        mock_settings.session_cookie_domain = None
                        mock_settings.is_production = False

                        mock_store = AsyncMock()
                        mock_store.create_session = AsyncMock(return_value=mock_session)
                        mock_store_class.return_value = mock_store
                        mock_redis.return_value = AsyncMock()

                        await create_authenticated_session_with_cookie(
                            response=response,
                            user_id="user-123",
                            remember_me=True,
                        )

                        # Verify extended TTL is used
                        call_args = response.set_cookie.call_args
                        assert call_args.kwargs["max_age"] == 2592000  # 30 days

    @pytest.mark.asyncio
    async def test_session_rotation_in_production(self):
        """Test that old session is deleted in production."""
        response = MagicMock(spec=Response)
        mock_session = MagicMock()
        mock_session.session_id = "new-session-id"

        with patch("src.core.session_helpers.get_redis_session") as mock_redis:
            with patch("src.core.session_helpers.SessionStore") as mock_store_class:
                with patch("src.core.session_helpers.settings") as mock_settings:
                    with patch("src.core.session_helpers.logger"):
                        mock_settings.session_cookie_max_age = 604800
                        mock_settings.session_cookie_max_age_remember = 2592000
                        mock_settings.session_cookie_name = "session"
                        mock_settings.session_cookie_secure = True
                        mock_settings.session_cookie_httponly = True
                        mock_settings.session_cookie_samesite = "lax"
                        mock_settings.session_cookie_domain = None
                        mock_settings.is_production = True  # Production mode

                        mock_store = AsyncMock()
                        mock_store.create_session = AsyncMock(return_value=mock_session)
                        mock_store.delete_session = AsyncMock()
                        mock_store_class.return_value = mock_store
                        mock_redis.return_value = AsyncMock()

                        await create_authenticated_session_with_cookie(
                            response=response,
                            user_id="user-123",
                            old_session_id="old-session-id",
                        )

                        # Old session should be deleted in production
                        mock_store.delete_session.assert_called_once_with("old-session-id")

    @pytest.mark.asyncio
    async def test_no_session_rotation_in_development(self):
        """Test that old session is NOT deleted in development."""
        response = MagicMock(spec=Response)
        mock_session = MagicMock()
        mock_session.session_id = "new-session-id"

        with patch("src.core.session_helpers.get_redis_session") as mock_redis:
            with patch("src.core.session_helpers.SessionStore") as mock_store_class:
                with patch("src.core.session_helpers.settings") as mock_settings:
                    with patch("src.core.session_helpers.logger"):
                        mock_settings.session_cookie_max_age = 604800
                        mock_settings.session_cookie_max_age_remember = 2592000
                        mock_settings.session_cookie_name = "session"
                        mock_settings.session_cookie_secure = False
                        mock_settings.session_cookie_httponly = True
                        mock_settings.session_cookie_samesite = "lax"
                        mock_settings.session_cookie_domain = None
                        mock_settings.is_production = False  # Development mode

                        mock_store = AsyncMock()
                        mock_store.create_session = AsyncMock(return_value=mock_session)
                        mock_store.delete_session = AsyncMock()
                        mock_store_class.return_value = mock_store
                        mock_redis.return_value = AsyncMock()

                        await create_authenticated_session_with_cookie(
                            response=response,
                            user_id="user-123",
                            old_session_id="old-session-id",
                        )

                        # Old session should NOT be deleted in development
                        mock_store.delete_session.assert_not_called()

    @pytest.mark.asyncio
    async def test_extra_context_included_in_logs(self):
        """Test that extra_context is logged."""
        response = MagicMock(spec=Response)
        mock_session = MagicMock()
        mock_session.session_id = "session-id"

        with patch("src.core.session_helpers.get_redis_session") as mock_redis:
            with patch("src.core.session_helpers.SessionStore") as mock_store_class:
                with patch("src.core.session_helpers.settings") as mock_settings:
                    with patch("src.core.session_helpers.logger") as mock_logger:
                        mock_settings.session_cookie_max_age = 604800
                        mock_settings.session_cookie_max_age_remember = 2592000
                        mock_settings.session_cookie_name = "session"
                        mock_settings.session_cookie_secure = True
                        mock_settings.session_cookie_httponly = True
                        mock_settings.session_cookie_samesite = "lax"
                        mock_settings.session_cookie_domain = None
                        mock_settings.is_production = False

                        mock_store = AsyncMock()
                        mock_store.create_session = AsyncMock(return_value=mock_session)
                        mock_store_class.return_value = mock_store
                        mock_redis.return_value = AsyncMock()

                        await create_authenticated_session_with_cookie(
                            response=response,
                            user_id="user-123",
                            event_name="custom_event",
                            extra_context={"email": "user@example.com"},
                        )

                        # Verify logger was called with event name
                        mock_logger.info.assert_called()
                        call_args = mock_logger.info.call_args
                        assert call_args[0][0] == "custom_event"
                        assert "email" in call_args[1]

    @pytest.mark.asyncio
    async def test_cookie_security_flags(self):
        """Test that cookie is set with correct security flags."""
        response = MagicMock(spec=Response)
        mock_session = MagicMock()
        mock_session.session_id = "secure-session"

        with patch("src.core.session_helpers.get_redis_session") as mock_redis:
            with patch("src.core.session_helpers.SessionStore") as mock_store_class:
                with patch("src.core.session_helpers.settings") as mock_settings:
                    with patch("src.core.session_helpers.logger"):
                        mock_settings.session_cookie_max_age = 604800
                        mock_settings.session_cookie_max_age_remember = 2592000
                        mock_settings.session_cookie_name = "secure_session"
                        mock_settings.session_cookie_secure = True
                        mock_settings.session_cookie_httponly = True
                        mock_settings.session_cookie_samesite = "strict"
                        mock_settings.session_cookie_domain = ".example.com"
                        mock_settings.is_production = True

                        mock_store = AsyncMock()
                        mock_store.create_session = AsyncMock(return_value=mock_session)
                        mock_store_class.return_value = mock_store
                        mock_redis.return_value = AsyncMock()

                        await create_authenticated_session_with_cookie(
                            response=response,
                            user_id="user-123",
                        )

                        call_kwargs = response.set_cookie.call_args.kwargs
                        assert call_kwargs["key"] == "secure_session"
                        assert call_kwargs["secure"] is True
                        assert call_kwargs["httponly"] is True
                        assert call_kwargs["samesite"] == "strict"
                        assert call_kwargs["domain"] == ".example.com"
