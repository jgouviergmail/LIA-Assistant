"""
Comprehensive unit tests for AuthService.

Coverage target: 85%+ from 19%

This test suite covers:
- User registration with email/password
- User login with email/password
- Email verification with tokens
- Password reset flow (request + confirm)
- Google OAuth flow (initiate + callback)
- Logout operations (single device, all devices)
- Get current user
- Helper methods (_send_verification_email, _send_password_reset_email)
- Error handling and edge cases
- Security validations
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.auth.schemas import UserLoginRequest, UserRegisterRequest
from src.domains.auth.service import AuthService
from src.domains.users.models import User
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
    """Create mock AuthRepository."""
    repo = AsyncMock()
    return repo


@pytest.fixture
def service(mock_db: AsyncMock, mock_repository: AsyncMock) -> AuthService:
    """Create AuthService instance with mocked repository."""
    service = AuthService(mock_db)
    service.repository = mock_repository
    return service


@pytest.fixture
def sample_user() -> User:
    """Create sample user for testing."""
    user = UserFactory.create(
        email="test@example.com",
        full_name="Test User",
        password="TestPass123!!",
        is_active=True,
        is_verified=True,
    )
    user.id = uuid4()
    user.timezone = "Europe/Paris"
    user.created_at = datetime.now(UTC)
    user.updated_at = datetime.now(UTC)
    user.is_superuser = False
    return user


@pytest.fixture
def unverified_user() -> User:
    """Create unverified user for testing."""
    user = UserFactory.create(
        email="unverified@example.com",
        full_name="Unverified User",
        password="TestPass123!!",
        is_active=False,
        is_verified=False,
    )
    user.id = uuid4()
    user.timezone = "Europe/Paris"
    user.created_at = datetime.now(UTC)
    user.updated_at = datetime.now(UTC)
    user.is_superuser = False
    return user


@pytest.fixture
def oauth_user() -> User:
    """Create OAuth user for testing."""
    user = UserFactory.create_oauth_user(
        provider="google",
        email="oauth@example.com",
        full_name="OAuth User",
    )
    user.id = uuid4()
    user.timezone = "Europe/Paris"
    user.created_at = datetime.now(UTC)
    user.updated_at = datetime.now(UTC)
    user.is_superuser = False
    return user


# ============================================================================
# Test: register
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.unit
class TestRegister:
    """Test AuthService.register() method."""

    async def test_register_new_user_success(self, service, mock_repository, mock_db):
        """Test successful user registration."""
        # Arrange
        register_data = UserRegisterRequest(
            email="newuser@example.com",
            password="SecurePass123!!",
            full_name="New User",
            timezone="America/New_York",
        )

        mock_repository.get_by_email.return_value = None  # User doesn't exist
        new_user = UserFactory.create(
            email=register_data.email,
            full_name=register_data.full_name,
            is_active=False,
            is_verified=False,
        )
        new_user.id = uuid4()
        new_user.timezone = "America/New_York"
        new_user.created_at = datetime.now(UTC)
        new_user.updated_at = datetime.now(UTC)
        new_user.is_superuser = False
        mock_repository.create.return_value = new_user

        with patch("src.domains.auth.service.create_verification_token") as mock_create_token:
            with patch.object(service, "_send_verification_email") as mock_send_email:
                mock_create_token.return_value = "verification-token-123"

                # Act
                result = await service.register(register_data)

        # Assert
        mock_repository.get_by_email.assert_called_once_with(register_data.email)
        mock_repository.create.assert_called_once()

        # Check user data passed to create
        create_call_args = mock_repository.create.call_args[0][0]
        assert create_call_args["email"] == register_data.email
        assert create_call_args["full_name"] == register_data.full_name
        assert create_call_args["timezone"] == "America/New_York"
        assert create_call_args["is_active"] is False
        assert create_call_args["is_verified"] is False
        assert "hashed_password" in create_call_args

        mock_db.commit.assert_called()
        # Verify email sent with new signature (includes user_name and language)
        mock_send_email.assert_called_once_with(
            email="newuser@example.com",
            token="verification-token-123",
            user_name="New User",
            language="fr",  # Default language
        )

        assert result.email == register_data.email
        assert result.full_name == register_data.full_name

    async def test_register_default_timezone(self, service, mock_repository, mock_db):
        """Test registration with default timezone when not provided."""
        # Arrange
        register_data = UserRegisterRequest(
            email="notz@example.com",
            password="SecurePass123!!",
            full_name="No Timezone User",
            timezone=None,
        )

        mock_repository.get_by_email.return_value = None
        new_user = UserFactory.create(email=register_data.email)
        new_user.id = uuid4()
        new_user.timezone = "Europe/Paris"
        new_user.created_at = datetime.now(UTC)
        new_user.updated_at = datetime.now(UTC)
        new_user.is_superuser = False
        mock_repository.create.return_value = new_user

        with patch("src.domains.auth.service.create_verification_token"):
            with patch.object(service, "_send_verification_email"):
                # Act
                await service.register(register_data)

        # Assert - Default timezone should be "Europe/Paris"
        create_call_args = mock_repository.create.call_args[0][0]
        assert create_call_args["timezone"] == "Europe/Paris"

    async def test_register_user_already_exists(self, service, mock_repository, sample_user):
        """Test registration fails when email already exists."""
        # Arrange
        register_data = UserRegisterRequest(
            email=sample_user.email,
            password="SecurePass123!!",
            full_name="Duplicate User",
        )

        mock_repository.get_by_email.return_value = sample_user

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await service.register(register_data)

        assert exc_info.value.status_code == 409
        assert (
            "already registered" in exc_info.value.detail.lower()
            or "already exists" in exc_info.value.detail.lower()
        )
        mock_repository.create.assert_not_called()

    async def test_register_password_hashed(self, service, mock_repository, mock_db):
        """Test that password is properly hashed during registration."""
        # Arrange
        register_data = UserRegisterRequest(
            email="hashtest@example.com",
            password="PlainText123!!",
            full_name="Hash Test User",
        )

        mock_repository.get_by_email.return_value = None
        new_user = UserFactory.create(email=register_data.email)
        new_user.id = uuid4()
        new_user.timezone = "Europe/Paris"
        new_user.created_at = datetime.now(UTC)
        new_user.updated_at = datetime.now(UTC)
        new_user.is_superuser = False
        mock_repository.create.return_value = new_user

        with patch("src.domains.auth.service.get_password_hash") as mock_hash:
            with patch("src.domains.auth.service.create_verification_token"):
                with patch.object(service, "_send_verification_email"):
                    mock_hash.return_value = "hashed_password_value"

                    # Act
                    await service.register(register_data)

        # Assert
        mock_hash.assert_called_once_with("PlainText123!!")
        create_call_args = mock_repository.create.call_args[0][0]
        assert create_call_args["hashed_password"] == "hashed_password_value"


# ============================================================================
# Test: login
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.unit
class TestLogin:
    """Test AuthService.login() method."""

    async def test_login_success(self, service, mock_repository, sample_user):
        """Test successful login with valid credentials."""
        # Arrange
        login_data = UserLoginRequest(
            email=sample_user.email,
            password="TestPass123!!",
        )

        mock_repository.get_by_email.return_value = sample_user

        with patch("src.domains.auth.service.verify_password") as mock_verify:
            mock_verify.return_value = True

            # Act
            result = await service.login(login_data)

        # Assert
        mock_repository.get_by_email.assert_called_once_with(sample_user.email)
        mock_verify.assert_called_once_with("TestPass123!!", sample_user.hashed_password)
        assert result.email == sample_user.email
        assert result.id == sample_user.id

    async def test_login_user_not_found(self, service, mock_repository):
        """Test login fails when user doesn't exist."""
        # Arrange
        login_data = UserLoginRequest(
            email="nonexistent@example.com",
            password="SomePass123!!",
        )

        mock_repository.get_by_email.return_value = None

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await service.login(login_data)

        assert exc_info.value.status_code == 401
        assert "invalid credentials" in exc_info.value.detail.lower()

    async def test_login_no_password(self, service, mock_repository, oauth_user):
        """Test login fails for OAuth user without password."""
        # Arrange
        oauth_user.hashed_password = None  # OAuth users don't have passwords
        login_data = UserLoginRequest(
            email=oauth_user.email,
            password="SomePass123!!",
        )

        mock_repository.get_by_email.return_value = oauth_user

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await service.login(login_data)

        assert exc_info.value.status_code == 401
        assert "invalid credentials" in exc_info.value.detail.lower()

    async def test_login_wrong_password(self, service, mock_repository, sample_user):
        """Test login fails with incorrect password."""
        # Arrange
        login_data = UserLoginRequest(
            email=sample_user.email,
            password="WrongPass123!!",
        )

        mock_repository.get_by_email.return_value = sample_user

        with patch("src.domains.auth.service.verify_password") as mock_verify:
            mock_verify.return_value = False

            # Act & Assert
            with pytest.raises(HTTPException) as exc_info:
                await service.login(login_data)

        assert exc_info.value.status_code == 401
        assert "invalid credentials" in exc_info.value.detail.lower()


# ============================================================================
# Test: verify_email
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.unit
class TestVerifyEmail:
    """Test AuthService.verify_email() method."""

    async def test_verify_email_success(self, service, mock_repository, mock_db):
        """Test successful email verification.

        Email verification marks the email as verified but keeps account inactive.
        Admin notification is sent AFTER email verification so admin can activate.
        """
        # Arrange
        token = "valid-verification-token"

        # Create unverified user
        unverified_user = UserFactory.create(
            email="unverified@example.com",
            is_active=False,
            is_verified=False,
        )
        unverified_user.id = uuid4()
        unverified_user.timezone = "Europe/Paris"
        unverified_user.language = "fr"
        unverified_user.created_at = datetime.now(UTC)
        unverified_user.updated_at = datetime.now(UTC)
        unverified_user.is_superuser = False

        mock_repository.get_by_email.return_value = unverified_user

        with (
            patch("src.domains.auth.service.verify_single_use_token") as mock_verify,
            patch("src.domains.auth.service.mark_token_used") as mock_mark_used,
            patch.object(
                service, "_notify_admins_of_new_registration", new_callable=AsyncMock
            ) as mock_notify,
        ):
            # verify_single_use_token returns (payload, jti) tuple
            mock_verify.return_value = (
                {
                    "type": "email_verification",
                    "sub": unverified_user.email,
                },
                "test-jti-123",
            )

            # Act
            result = await service.verify_email(token)

        # Assert
        mock_verify.assert_called_once_with(token, "email_verification")
        mock_repository.get_by_email.assert_called_once_with(unverified_user.email)
        # Email is verified but account stays inactive (admin must activate)
        assert unverified_user.is_verified is True
        assert unverified_user.is_active is False  # Account not activated yet
        mock_db.commit.assert_called_once()
        # Token should be marked as used
        mock_mark_used.assert_called_once_with("test-jti-123", "email_verification")
        # Admin notification is sent after email verification
        mock_notify.assert_called_once_with(
            user_email=unverified_user.email,
            user_name=unverified_user.full_name,
            registration_method="email",
        )
        assert result.email == unverified_user.email

    async def test_verify_email_invalid_token(self, service):
        """Test email verification fails with invalid token."""
        # Arrange
        token = "invalid-token"

        with patch("src.domains.auth.service.verify_single_use_token") as mock_verify:
            # verify_single_use_token raises HTTPException for invalid tokens
            mock_verify.side_effect = HTTPException(
                status_code=401, detail="Invalid email verification token"
            )

            # Act & Assert
            with pytest.raises(HTTPException) as exc_info:
                await service.verify_email(token)

        assert exc_info.value.status_code == 401
        assert "invalid" in exc_info.value.detail.lower()

    async def test_verify_email_wrong_token_type(self, service):
        """Test email verification fails with wrong token type."""
        # Arrange
        token = "password-reset-token"

        with patch("src.domains.auth.service.verify_single_use_token") as mock_verify:
            # verify_single_use_token raises HTTPException for wrong type
            mock_verify.side_effect = HTTPException(
                status_code=401, detail="Invalid email verification token"
            )

            # Act & Assert
            with pytest.raises(HTTPException) as exc_info:
                await service.verify_email(token)

        assert exc_info.value.status_code == 401
        assert "invalid" in exc_info.value.detail.lower()

    async def test_verify_email_user_not_found(self, service, mock_repository):
        """Test email verification fails when user not found."""
        # Arrange
        token = "valid-token"

        mock_repository.get_by_email.return_value = None

        with patch("src.domains.auth.service.verify_single_use_token") as mock_verify:
            # verify_single_use_token returns (payload, jti) tuple
            mock_verify.return_value = (
                {
                    "type": "email_verification",
                    "sub": "nonexistent@example.com",
                },
                None,
            )

            # Act & Assert
            with pytest.raises(HTTPException) as exc_info:
                await service.verify_email(token)

        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail.lower()

    async def test_verify_email_already_verified(self, service, mock_repository, sample_user):
        """Test email verification when user already verified."""
        # Arrange
        token = "valid-token"
        sample_user.is_verified = True

        mock_repository.get_by_email.return_value = sample_user

        with (
            patch("src.domains.auth.service.verify_single_use_token") as mock_verify,
            patch("src.domains.auth.service.mark_token_used") as mock_mark_used,
        ):
            # verify_single_use_token returns (payload, jti) tuple
            mock_verify.return_value = (
                {
                    "type": "email_verification",
                    "sub": sample_user.email,
                },
                "test-jti-456",
            )

            # Act
            result = await service.verify_email(token)

        # Assert - Should return user without calling activate
        mock_repository.activate_user.assert_not_called()
        # Token should still be marked as used even if already verified
        mock_mark_used.assert_called_once_with("test-jti-456", "email_verification")
        assert result.email == sample_user.email


# ============================================================================
# Test: request_password_reset
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.unit
class TestRequestPasswordReset:
    """Test AuthService.request_password_reset() method."""

    async def test_request_password_reset_success(self, service, mock_repository, sample_user):
        """Test successful password reset request."""
        # Arrange
        email = sample_user.email
        mock_repository.get_by_email.return_value = sample_user

        with patch("src.domains.auth.service.create_password_reset_token") as mock_create_token:
            with patch.object(service, "_send_password_reset_email") as mock_send_email:
                mock_create_token.return_value = "reset-token-123"

                # Act
                result = await service.request_password_reset(email)

        # Assert
        mock_repository.get_by_email.assert_called_once_with(email)
        mock_create_token.assert_called_once_with(email)
        # Verify email sent with new signature (includes user_name and language)
        mock_send_email.assert_called_once_with(
            email=email,
            token="reset-token-123",
            user_name=sample_user.full_name,
            language=sample_user.language,
        )
        assert result is None

    async def test_request_password_reset_user_not_found(self, service, mock_repository):
        """Test password reset request doesn't reveal if user exists (security)."""
        # Arrange
        email = "nonexistent@example.com"
        mock_repository.get_by_email.return_value = None

        with patch.object(service, "_send_password_reset_email") as mock_send_email:
            # Act
            result = await service.request_password_reset(email)

        # Assert - Should not reveal user doesn't exist, should not send email
        mock_send_email.assert_not_called()
        assert result is None


# ============================================================================
# Test: reset_password
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.unit
class TestResetPassword:
    """Test AuthService.reset_password() method."""

    async def test_reset_password_success(self, service, mock_repository, sample_user, mock_db):
        """Test successful password reset."""
        # Arrange
        token = "valid-reset-token"
        new_password = "NewSecurePass123!!"

        mock_repository.get_by_email.return_value = sample_user
        mock_repository.update_password.return_value = sample_user

        mock_redis = AsyncMock()
        mock_session_store = AsyncMock()
        mock_session_store.delete_all_user_sessions = AsyncMock()

        with (
            patch("src.domains.auth.service.verify_single_use_token") as mock_verify,
            patch("src.domains.auth.service.mark_token_used") as mock_mark_used,
            patch("src.domains.auth.service.get_password_hash") as mock_hash,
            patch("src.domains.auth.service.get_redis_session", return_value=mock_redis),
            patch("src.domains.auth.service.SessionStore", return_value=mock_session_store),
        ):
            # verify_single_use_token returns (payload, jti) tuple
            mock_verify.return_value = (
                {
                    "type": "password_reset",
                    "sub": sample_user.email,
                },
                "test-jti-reset",
            )
            mock_hash.return_value = "new_hashed_password"

            # Act
            result = await service.reset_password(token, new_password)

        # Assert
        mock_verify.assert_called_once_with(token, "password_reset")
        mock_repository.get_by_email.assert_called_once_with(sample_user.email)
        mock_hash.assert_called_once_with(new_password)
        mock_repository.update_password.assert_called_once_with(sample_user, "new_hashed_password")
        mock_db.commit.assert_called_once()
        mock_mark_used.assert_called_once_with("test-jti-reset", "password_reset")
        mock_session_store.delete_all_user_sessions.assert_called_once_with(str(sample_user.id))
        assert result.email == sample_user.email

    async def test_reset_password_invalid_token(self, service):
        """Test password reset fails with invalid token."""
        # Arrange
        token = "invalid-token"
        new_password = "NewPass123!!"

        with patch("src.domains.auth.service.verify_single_use_token") as mock_verify:
            # verify_single_use_token raises HTTPException for invalid tokens
            mock_verify.side_effect = HTTPException(
                status_code=401, detail="Invalid password reset token"
            )

            # Act & Assert
            with pytest.raises(HTTPException) as exc_info:
                await service.reset_password(token, new_password)

        assert exc_info.value.status_code == 401
        assert "invalid" in exc_info.value.detail.lower()

    async def test_reset_password_wrong_token_type(self, service):
        """Test password reset fails with wrong token type."""
        # Arrange
        token = "verification-token"
        new_password = "NewPass123!!"

        with patch("src.domains.auth.service.verify_single_use_token") as mock_verify:
            # verify_single_use_token raises HTTPException for wrong type
            mock_verify.side_effect = HTTPException(
                status_code=401, detail="Invalid password reset token"
            )

            # Act & Assert
            with pytest.raises(HTTPException) as exc_info:
                await service.reset_password(token, new_password)

        assert exc_info.value.status_code == 401
        assert "invalid" in exc_info.value.detail.lower()

    async def test_reset_password_user_not_found(self, service, mock_repository):
        """Test password reset fails when user not found."""
        # Arrange
        token = "valid-token"
        new_password = "NewPass123!!"

        mock_repository.get_by_email.return_value = None

        with patch("src.domains.auth.service.verify_single_use_token") as mock_verify:
            # verify_single_use_token returns (payload, jti) tuple
            mock_verify.return_value = (
                {
                    "type": "password_reset",
                    "sub": "nonexistent@example.com",
                },
                None,
            )

            # Act & Assert
            with pytest.raises(HTTPException) as exc_info:
                await service.reset_password(token, new_password)

        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail.lower()


# ============================================================================
# Test: initiate_google_oauth
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.unit
class TestInitiateGoogleOAuth:
    """Test AuthService.initiate_google_oauth() method."""

    async def test_initiate_google_oauth_success(self, service):
        """Test successful Google OAuth flow initiation."""
        # Arrange
        mock_redis = AsyncMock()
        mock_session_store = AsyncMock()
        mock_provider = MagicMock()
        mock_flow_handler = AsyncMock()
        mock_flow_handler.initiate_flow = AsyncMock(
            return_value=("https://accounts.google.com/oauth?...", "state-token-123")
        )

        with patch("src.domains.auth.service.get_redis_session", return_value=mock_redis):
            with patch("src.domains.auth.service.SessionService", return_value=mock_session_store):
                with patch("src.core.oauth.GoogleOAuthProvider") as mock_provider_class:
                    with patch("src.core.oauth.OAuthFlowHandler", return_value=mock_flow_handler):
                        mock_provider_class.for_authentication.return_value = mock_provider

                        # Act
                        auth_url, state = await service.initiate_google_oauth()

        # Assert
        assert auth_url == "https://accounts.google.com/oauth?..."
        assert state == "state-token-123"
        mock_flow_handler.initiate_flow.assert_called_once()

        # Check additional params for Google
        call_kwargs = mock_flow_handler.initiate_flow.call_args[1]
        assert "additional_params" in call_kwargs
        assert call_kwargs["additional_params"]["access_type"] == "offline"
        assert call_kwargs["additional_params"]["prompt"] == "consent"


# ============================================================================
# Test: handle_google_callback (already tested in test_auth_service_refactored.py)
# ============================================================================
# Note: handle_google_callback is comprehensively tested in test_auth_service_refactored.py
# Including: new user creation, linking to existing email, returning OAuth user
# We won't duplicate those tests here to avoid redundancy


# ============================================================================
# Test: logout
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.unit
class TestLogout:
    """Test AuthService.logout() method."""

    async def test_logout_success(self, service):
        """Test successful single device logout."""
        # Arrange
        user_id = str(uuid4())
        refresh_token = "refresh-token-123"

        mock_redis = AsyncMock()
        mock_session_store = AsyncMock()
        mock_session_store.remove_session = AsyncMock()

        with patch("src.domains.auth.service.get_redis_session", return_value=mock_redis):
            with patch("src.domains.auth.service.SessionService", return_value=mock_session_store):
                # Act
                await service.logout(user_id, refresh_token)

        # Assert
        mock_session_store.remove_session.assert_called_once_with(user_id, refresh_token)


# ============================================================================
# Test: logout_all_devices
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.unit
class TestLogoutAllDevices:
    """Test AuthService.logout_all_devices() method."""

    async def test_logout_all_devices_success(self, service):
        """Test successful logout from all devices."""
        # Arrange
        user_id = str(uuid4())

        mock_redis = AsyncMock()
        mock_session_service = AsyncMock()
        mock_session_service.remove_all_sessions = AsyncMock()

        with patch("src.domains.auth.service.get_redis_session", return_value=mock_redis):
            with patch(
                "src.domains.auth.service.SessionService", return_value=mock_session_service
            ):
                # Act
                await service.logout_all_devices(user_id)

        # Assert
        mock_session_service.remove_all_sessions.assert_called_once_with(user_id)


# ============================================================================
# Test: get_current_user
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.unit
class TestGetCurrentUser:
    """Test AuthService.get_current_user() method."""

    async def test_get_current_user_success(self, service, mock_repository, sample_user):
        """Test successful get current user."""
        # Arrange
        user_id = str(sample_user.id)
        mock_repository.get_by_id.return_value = sample_user

        # Act
        result = await service.get_current_user(user_id)

        # Assert
        mock_repository.get_by_id.assert_called_once()
        assert result.email == sample_user.email
        assert result.id == sample_user.id

    async def test_get_current_user_not_found(self, service, mock_repository):
        """Test get current user fails when user not found."""
        # Arrange
        user_id = str(uuid4())
        mock_repository.get_by_id.return_value = None

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await service.get_current_user(user_id)

        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail.lower()


# ============================================================================
# Test: _exchange_oauth_code (already tested in test_auth_service_refactored.py)
# ============================================================================
# Note: _exchange_oauth_code is tested in test_auth_service_refactored.py
# Including: successful exchange, error handling


# ============================================================================
# Test: _fetch_google_userinfo (already tested in test_auth_service_refactored.py)
# ============================================================================
# Note: _fetch_google_userinfo is tested in test_auth_service_refactored.py
# Including: successful API call, HTTP 400, HTTP 500 errors


# ============================================================================
# Test: _find_or_create_google_user (already tested in test_auth_service_refactored.py)
# ============================================================================
# Note: _find_or_create_google_user is tested in test_auth_service_refactored.py
# Including: existing user by provider, existing by email, new user creation


# ============================================================================
# Test: _send_verification_email
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.unit
class TestSendVerificationEmail:
    """Test AuthService._send_verification_email() helper method."""

    async def test_send_verification_email(self, service):
        """Test verification email construction and logging."""
        # Arrange
        email = "test@example.com"
        token = "verification-token-123"

        with patch("src.core.config.settings") as mock_settings:
            mock_settings.frontend_url = "https://example.com"

            with patch("src.infrastructure.email.get_email_service") as mock_email_service:
                mock_email_service.return_value.send_email_verification = AsyncMock(
                    return_value=True
                )

                # Act
                await service._send_verification_email(
                    email=email,
                    token=token,
                    user_name="Test User",
                    language="fr",
                )

        # Assert - Just verify no exceptions


# ============================================================================
# Test: _send_password_reset_email
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.unit
class TestSendPasswordResetEmail:
    """Test AuthService._send_password_reset_email() helper method."""

    async def test_send_password_reset_email(self, service):
        """Test password reset email construction and logging."""
        # Arrange
        email = "test@example.com"
        token = "reset-token-123"

        with patch("src.core.config.settings") as mock_settings:
            mock_settings.frontend_url = "https://example.com"

            with patch("src.infrastructure.email.get_email_service") as mock_email_service:
                mock_email_service.return_value.send_password_reset = AsyncMock(return_value=True)

                # Act
                await service._send_password_reset_email(
                    email=email,
                    token=token,
                    user_name="Test User",
                    language="fr",
                )

        # Assert - Just verify no exceptions


# ============================================================================
# Test: Integration Scenarios
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.unit
class TestIntegrationScenarios:
    """Test end-to-end integration scenarios."""

    async def test_complete_registration_verification_flow(self, service, mock_repository, mock_db):
        """Test complete flow: register -> verify email.

        Registration sends verification email, verification marks email as verified
        and notifies admin (account stays inactive until admin activates).
        """
        # Arrange - Registration
        register_data = UserRegisterRequest(
            email="complete@example.com",
            password="TestPass123!!",
            full_name="Complete User",
        )

        unverified_user = UserFactory.create(
            email=register_data.email,
            full_name=register_data.full_name,
            is_active=False,
            is_verified=False,
        )
        unverified_user.id = uuid4()
        unverified_user.timezone = "Europe/Paris"
        unverified_user.language = "fr"
        unverified_user.created_at = datetime.now(UTC)
        unverified_user.updated_at = datetime.now(UTC)
        unverified_user.is_superuser = False

        mock_repository.get_by_email.side_effect = [
            None,  # First call: user doesn't exist
            unverified_user,  # Second call: user exists for verification
        ]
        mock_repository.create.return_value = unverified_user

        verification_token = "verification-token"

        with (
            patch(
                "src.domains.auth.service.create_verification_token",
                return_value=verification_token,
            ),
            patch.object(service, "_send_verification_email"),
            patch.object(
                service, "_notify_admins_of_new_registration", new_callable=AsyncMock
            ) as mock_notify,
            patch("src.domains.auth.service.verify_single_use_token") as mock_verify,
            patch("src.domains.auth.service.mark_token_used"),
        ):
            # verify_single_use_token returns (payload, jti) tuple
            mock_verify.return_value = (
                {
                    "type": "email_verification",
                    "sub": register_data.email,
                },
                "test-jti-flow",
            )

            # Act - Register
            register_result = await service.register(register_data)

            # Act - Verify
            verify_result = await service.verify_email(verification_token)

        # Assert
        assert register_result.email == register_data.email
        assert verify_result.email == register_data.email
        # Email is verified but account stays inactive
        assert unverified_user.is_verified is True
        assert unverified_user.is_active is False
        # Admin notification sent after email verification
        mock_notify.assert_called_once()

    async def test_password_reset_flow_with_session_invalidation(
        self, service, mock_repository, sample_user, mock_db
    ):
        """Test complete flow: request reset -> reset password -> sessions invalidated."""
        # Arrange
        email = sample_user.email
        reset_token = "reset-token-456"
        new_password = "NewSecurePass123!!"

        mock_repository.get_by_email.side_effect = [
            sample_user,  # First call: request reset
            sample_user,  # Second call: reset password
        ]
        mock_repository.update_password.return_value = sample_user

        mock_redis = AsyncMock()
        mock_session_store = AsyncMock()
        mock_session_store.delete_all_user_sessions = AsyncMock()

        with (
            patch("src.domains.auth.service.create_password_reset_token", return_value=reset_token),
            patch.object(service, "_send_password_reset_email") as mock_send,
            patch("src.domains.auth.service.verify_single_use_token") as mock_verify,
            patch("src.domains.auth.service.mark_token_used"),
            patch("src.domains.auth.service.get_password_hash", return_value="new_hash"),
            patch("src.domains.auth.service.get_redis_session", return_value=mock_redis),
            patch("src.domains.auth.service.SessionStore", return_value=mock_session_store),
        ):
            # verify_single_use_token returns (payload, jti) tuple
            mock_verify.return_value = (
                {
                    "type": "password_reset",
                    "sub": email,
                },
                "test-jti-reset-flow",
            )

            # Act - Request reset
            await service.request_password_reset(email)

            # Act - Reset password
            result = await service.reset_password(reset_token, new_password)

        # Assert
        mock_send.assert_called_once()
        mock_repository.update_password.assert_called_once()
        mock_session_store.delete_all_user_sessions.assert_called_once_with(str(sample_user.id))
        assert result.email == email


# ============================================================================
# Test: Edge Cases and Error Handling
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.unit
class TestEdgeCases:
    """Test edge cases and error handling."""

    async def test_register_with_empty_full_name(self, service, mock_repository, mock_db):
        """Test registration with None full_name."""
        # Arrange
        register_data = UserRegisterRequest(
            email="noname@example.com",
            password="TestPass123!!",
            full_name=None,
        )

        mock_repository.get_by_email.return_value = None

        # Create user directly to avoid factory defaults
        from src.domains.auth.models import User

        new_user = User(
            email=register_data.email,
            full_name=None,
            hashed_password="hashed",
            is_active=False,
            is_verified=False,
            is_superuser=False,
            timezone="Europe/Paris",
        )
        new_user.id = uuid4()
        new_user.created_at = datetime.now(UTC)
        new_user.updated_at = datetime.now(UTC)
        mock_repository.create.return_value = new_user

        with patch("src.domains.auth.service.create_verification_token"):
            with patch.object(service, "_send_verification_email"):
                # Act
                result = await service.register(register_data)

        # Assert
        assert result.full_name is None

    async def test_login_with_inactive_user(self, service, mock_repository, sample_user):
        """Test login with inactive user (should still work - activation is separate from login)."""
        # Arrange
        sample_user.is_active = False
        login_data = UserLoginRequest(
            email=sample_user.email,
            password="TestPass123!!",
        )

        mock_repository.get_by_email.return_value = sample_user

        with patch("src.domains.auth.service.verify_password") as mock_verify:
            mock_verify.return_value = True

            # Act
            result = await service.login(login_data)

        # Assert - Login succeeds even if user is inactive
        assert result.email == sample_user.email

    async def test_get_current_user_with_invalid_uuid(self, service, mock_repository):
        """Test get current user with malformed UUID string."""
        # Arrange
        invalid_user_id = "not-a-valid-uuid"

        # Act & Assert - UUID() constructor will raise ValueError
        with pytest.raises(ValueError):
            await service.get_current_user(invalid_user_id)
