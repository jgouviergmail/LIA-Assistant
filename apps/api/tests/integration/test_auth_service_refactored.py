"""
Integration tests for AuthService refactored methods (Sprint 5).

Tests cover:
- handle_google_callback() decomposed into 3 helpers
- _exchange_oauth_code() - OAuth token exchange
- _fetch_google_userinfo() - Fetch user info from Google API
- _find_or_create_google_user() - Find existing or create new user
- Full OAuth flow scenarios

NOTE: These tests require a real database (external via TEST_DATABASE_URL or Testcontainers).
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.auth.google_identity import GoogleSignInRefusedError
from src.domains.auth.repository import AuthRepository
from src.domains.auth.service import AuthService
from src.domains.users.models import User
from src.infrastructure.cache.redis import get_redis_session
from src.infrastructure.cache.session_store import SessionStore
from tests.fixtures.factories import UserFactory

# Requires a real database (external via TEST_DATABASE_URL or Testcontainers).

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


# ============================================================================
# Linking a Google identity to an account found by e-mail
# ============================================================================


def _google_userinfo(email: str, google_id: str, *, verified: bool | None = True) -> dict:
    """A userinfo v2 payload shaped like Google's documented schema.

    ``verified=None`` omits the flag, which the schema allows (it declares a
    default of true).
    """
    payload: dict = {
        "id": google_id,
        "email": email,
        "name": "Google Name",
        "picture": "https://lh3.googleusercontent.com/a/photo",
        "locale": "fr",
    }
    if verified is not None:
        payload["verified_email"] = verified
    return payload


async def _persist(async_session: AsyncSession, user: User) -> User:
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


@pytest.fixture
def email_outbox():
    """The SMTP boundary, recording what would have been sent."""
    service = MagicMock()
    service.send_new_registration_admin_notification = AsyncMock(return_value=True)
    service.send_pending_activation_notification = AsyncMock(return_value=True)
    with patch("src.infrastructure.email.get_email_service", return_value=service):
        yield service


class TestGoogleLinkNeverChangesStanding:
    """A Google identity attached to an existing account grants it nothing.

    Measured in production on 2026-09-18: an account registered by e-mail —
    inactive, its address never verified — became active 68 seconds later by
    signing in with Google on the same address, because the link wrote
    ``is_active=True``. The admin approval it skipped was never even requested:
    that branch notified nobody.
    """

    async def test_a_pending_registration_stays_pending(
        self, auth_service, async_session, email_outbox
    ):
        pending = await _persist(
            async_session,
            UserFactory.create(email="pending@example.com", is_active=False, is_verified=False),
        )

        user = await auth_service._find_or_create_google_user(
            _google_userinfo("pending@example.com", "g-pending")
        )
        await async_session.commit()
        await async_session.refresh(user)

        assert user.id == pending.id
        assert user.oauth_provider_id == "g-pending"
        assert user.is_active is False

    async def test_an_account_the_admin_blocked_stays_blocked(
        self, auth_service, async_session, email_outbox
    ):
        blocked = await _persist(
            async_session,
            UserFactory.create(email="blocked@example.com", is_active=False, is_verified=True),
        )

        user = await auth_service._find_or_create_google_user(
            _google_userinfo("blocked@example.com", "g-blocked")
        )
        await async_session.commit()
        await async_session.refresh(user)

        assert user.id == blocked.id
        assert user.is_active is False
        # Its address was proven long ago: there is no new registration to report.
        email_outbox.send_new_registration_admin_notification.assert_not_awaited()

    async def test_proving_the_address_asks_the_admin_as_verification_does(
        self, auth_service, async_session, email_outbox
    ):
        await _persist(
            async_session,
            UserFactory.create(email="admin@example.com", is_superuser=True, is_active=True),
        )
        await _persist(
            async_session,
            UserFactory.create(email="pending@example.com", is_active=False, is_verified=False),
        )

        user = await auth_service._find_or_create_google_user(
            _google_userinfo("pending@example.com", "g-pending")
        )
        await async_session.commit()

        assert user.is_verified is True
        email_outbox.send_new_registration_admin_notification.assert_awaited_once()
        admin_mail = email_outbox.send_new_registration_admin_notification.await_args.kwargs
        assert admin_mail["admin_email"] == "admin@example.com"
        assert admin_mail["new_user_email"] == "pending@example.com"
        email_outbox.send_pending_activation_notification.assert_awaited_once()
        pending_mail = email_outbox.send_pending_activation_notification.await_args.kwargs
        assert pending_mail["user_email"] == "pending@example.com"

    async def test_the_unproven_password_does_not_survive_the_link(
        self, auth_service, async_session, email_outbox
    ):
        """Pre-account hijacking: whoever registered the address never proved it.

        Left in place, the registrant's password would open the account of the
        person who just proved the address, the day an admin approves it.
        """
        await _persist(
            async_session,
            UserFactory.create(email="claimed@example.com", is_active=False, is_verified=False),
        )

        user = await auth_service._find_or_create_google_user(
            _google_userinfo("claimed@example.com", "g-owner")
        )
        await async_session.commit()
        await async_session.refresh(user)

        assert user.hashed_password is None

    async def test_the_unproven_sessions_do_not_survive_the_link(
        self, auth_service, async_session, email_outbox
    ):
        """Registering opens a session: the same hijack, without any password."""
        registrant = await _persist(
            async_session,
            UserFactory.create(email="claimed@example.com", is_active=False, is_verified=False),
        )
        store = SessionStore(await get_redis_session())
        registration_session = await store.create_session(user_id=str(registrant.id))

        await auth_service._find_or_create_google_user(
            _google_userinfo("claimed@example.com", "g-owner")
        )

        assert await store.get_session(registration_session.session_id) is None

    async def test_an_approved_account_only_gains_the_identity(
        self, auth_service, async_session, email_outbox
    ):
        approved = await _persist(
            async_session,
            UserFactory.create(email="member@example.com", is_active=True, is_verified=True),
        )
        password_hash = approved.hashed_password
        store = SessionStore(await get_redis_session())
        other_device = await store.create_session(user_id=str(approved.id))

        user = await auth_service._find_or_create_google_user(
            _google_userinfo("member@example.com", "g-member")
        )
        await async_session.commit()
        await async_session.refresh(user)

        assert user.oauth_provider_id == "g-member"
        assert user.is_active is True
        assert user.hashed_password == password_hash
        assert await store.get_session(other_device.session_id) is not None
        email_outbox.send_new_registration_admin_notification.assert_not_awaited()

    async def test_an_account_approved_before_its_address_was_proven_is_not_reported_again(
        self, auth_service, async_session, email_outbox
    ):
        """An admin may approve an account whose address nobody proved yet."""
        await _persist(
            async_session,
            UserFactory.create(email="admin@example.com", is_superuser=True, is_active=True),
        )
        await _persist(
            async_session,
            UserFactory.create(email="approved@example.com", is_active=True, is_verified=False),
        )

        user = await auth_service._find_or_create_google_user(
            _google_userinfo("approved@example.com", "g-approved")
        )
        await async_session.commit()

        assert user.is_active is True
        email_outbox.send_new_registration_admin_notification.assert_not_awaited()

    async def test_a_deleted_account_is_refused_and_left_untouched(
        self, auth_service, async_session, email_outbox
    ):
        """Deletion keeps the row for billing; a sign-in must not revive it."""
        deleted = UserFactory.create(email="gone@example.com", is_active=False, is_verified=True)
        deleted.hashed_password = None
        deleted.deleted_at = datetime.now(UTC)
        deleted = await _persist(async_session, deleted)

        with pytest.raises(GoogleSignInRefusedError) as refusal:
            await auth_service._find_or_create_google_user(
                _google_userinfo("gone@example.com", "g-gone")
            )

        assert refusal.value.reason == "account_deleted"
        await async_session.refresh(deleted)
        assert deleted.oauth_provider_id is None
        assert deleted.is_active is False


class TestGoogleEmailClaim:
    """The address is trusted only when Google vouches for it.

    The userinfo v2 schema documents ``verified_email`` with a default of true
    ("Always verified because we only return the user's primary email address",
    discovery document read 2026-09-23). So only an explicit ``false`` refuses;
    reading an absent flag as false would contradict the provider's contract.
    """

    async def test_an_unverified_address_never_links(
        self, auth_service, async_session, email_outbox
    ):
        member = await _persist(async_session, UserFactory.create(email="member@example.com"))

        with pytest.raises(GoogleSignInRefusedError) as refusal:
            await auth_service._find_or_create_google_user(
                _google_userinfo("member@example.com", "g-impostor", verified=False)
            )

        assert refusal.value.reason == "email_not_verified"
        await async_session.refresh(member)
        assert member.oauth_provider_id is None

    async def test_an_unverified_address_never_creates_an_account(
        self, auth_service, async_session, email_outbox
    ):
        with pytest.raises(GoogleSignInRefusedError) as refusal:
            await auth_service._find_or_create_google_user(
                _google_userinfo("nobody@example.com", "g-nobody", verified=False)
            )

        assert refusal.value.reason == "email_not_verified"
        assert await AuthRepository(async_session).get_by_email("nobody@example.com") is None

    async def test_an_absent_flag_reads_as_the_documented_default(
        self, auth_service, async_session, email_outbox
    ):
        user = await auth_service._find_or_create_google_user(
            _google_userinfo("newcomer@example.com", "g-newcomer", verified=None)
        )
        await async_session.commit()

        assert user.email == "newcomer@example.com"
        assert user.is_active is False
