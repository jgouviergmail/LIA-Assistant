"""
Auth service containing business logic for authentication.
Handles user registration, login, OAuth, email verification, and password reset.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import (
    raise_email_already_exists,
    raise_invalid_credentials,
    raise_invalid_input,
    raise_oauth_flow_failed,
    raise_user_not_found,
)
from src.core.field_names import FIELD_IS_ACTIVE
from src.core.security import (
    # Removed: create_access_token, create_refresh_token (BFF Pattern migration v0.3.0)
    # OAuth helpers moved to src.core.oauth module (v0.4.0 refactoring)
    create_password_reset_token,
    create_verification_token,
    get_password_hash,
    mark_token_used,
    verify_password,
    verify_single_use_token,
)
from src.domains.auth.repository import AuthRepository
from src.domains.auth.schemas import (
    # Removed: AuthResponse, TokenResponse (BFF Pattern migration v0.3.0)
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)
from src.domains.users.models import User
from src.infrastructure.cache.redis import SessionService, get_redis_session

logger = structlog.get_logger(__name__)


class AuthService:
    """Service for authentication business logic."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repository = AuthRepository(db)

    async def register(self, data: UserRegisterRequest) -> UserResponse:
        """
        Register a new user with email and password.

        Args:
            data: User registration data

        Returns:
            UserResponse (BFF Pattern - no tokens)

        Raises:
            HTTPException: If email already exists
        """
        # Check if user already exists
        existing_user = await self.repository.get_by_email(data.email)
        if existing_user:
            raise_email_already_exists(data.email)

        # Hash password
        hashed_password = get_password_hash(data.password)

        # Create user
        user_data = {
            "email": data.email,
            "hashed_password": hashed_password,
            "full_name": data.full_name,
            "timezone": data.timezone or "Europe/Paris",  # Browser detection or default
            "language": data.language or "fr",  # Browser detection or default
            FIELD_IS_ACTIVE: False,  # Requires email verification
            "is_verified": False,
            "memory_enabled": True,  # Long-term memory enabled by default
        }

        user = await self.repository.create(user_data)
        await self.db.commit()

        # Send verification email
        # Note: Admin notification is sent AFTER email verification (in verify_email method)
        verification_token = create_verification_token(user.email)
        await self._send_verification_email(
            email=user.email,
            token=verification_token,
            user_name=user.full_name,
            language=user.language,
        )

        logger.info(
            "user_registered",
            user_id=str(user.id),
            email=user.email,
            timezone=user.timezone,
            language=user.language,
        )

        # BFF Pattern: Return user only, session created by router
        return UserResponse.model_validate(user)

    async def login(self, data: UserLoginRequest) -> UserResponse:
        """
        Login user with email and password.

        Args:
            data: User login credentials

        Returns:
            UserResponse (BFF Pattern - no tokens)

        Raises:
            HTTPException: If credentials are invalid
        """
        # Get user by email
        user = await self.repository.get_by_email(data.email)

        if not user or not user.hashed_password:
            raise_invalid_credentials(data.email)

        # Type narrowing: user is User (not None) and has hashed_password after check
        assert user is not None
        assert user.hashed_password is not None

        # Verify password
        if not verify_password(data.password, user.hashed_password):
            raise_invalid_credentials(data.email)

        # Update last_login timestamp
        user.last_login = datetime.now(UTC)
        await self.db.commit()

        logger.info("user_logged_in", user_id=str(user.id), email=user.email)

        # BFF Pattern: Return user only, session created by router
        return UserResponse.model_validate(user)

    # ========================================================================
    # REMOVED METHOD: refresh_access_token() (BFF Pattern Migration)
    # ========================================================================
    # This method was removed as part of BFF Pattern migration (v0.3.0).
    #
    # Token refresh is no longer needed:
    # - Sessions auto-refresh on each authenticated request
    # - HTTP-only cookies eliminate client-side token management
    #
    # See /auth/refresh endpoint (now returns HTTP 410 Gone)
    # ========================================================================

    async def verify_email(self, token: str) -> UserResponse:
        """
        Verify user email with verification token.

        Args:
            token: Email verification JWT token

        Returns:
            Updated UserResponse

        Raises:
            HTTPException: If token is invalid, expired, or already used (PROD)
        """
        # Verify token + JTI check (DRY helper)
        payload, jti = await verify_single_use_token(token, "email_verification")

        email = str(payload.get("sub"))
        user = await self.repository.get_by_email(email)

        if not user:
            raise_user_not_found(email)

        # Type narrowing: user is User (not None) after check
        assert user is not None

        if user.is_verified:
            logger.info("verification_already_verified", user_id=str(user.id))
            # Still blacklist token even if already verified (prevent info leakage)
            if jti:
                await mark_token_used(jti, "email_verification")
            return UserResponse.model_validate(user)

        # Mark email as verified (but account still inactive until admin activates)
        user.is_verified = True
        await self.db.commit()

        # Blacklist token after successful verification (PROD only)
        if jti:
            await mark_token_used(jti, "email_verification")

        logger.info("email_verified", user_id=str(user.id), email=user.email)

        # Now that email is verified, notify admins to activate the account
        await self._notify_admins_of_new_registration(
            user_email=user.email,
            user_name=user.full_name,
            registration_method="email",
        )

        # Notify user that their account is pending activation
        await self._send_pending_activation_notification(
            user_email=user.email,
            user_name=user.full_name,
            user_language=user.language or "fr",
        )

        return UserResponse.model_validate(user)

    async def request_password_reset(self, email: str) -> None:
        """
        Send password reset email to user.

        Args:
            email: User email address
        """
        user = await self.repository.get_by_email(email)

        # Don't reveal if email exists (security best practice)
        if not user:
            logger.warning("password_reset_requested_nonexistent_email", email=email)
            return

        # Generate reset token
        reset_token = create_password_reset_token(email)

        # Send reset email
        await self._send_password_reset_email(
            email=email,
            token=reset_token,
            user_name=user.full_name,
            language=user.language,
        )

        logger.info("password_reset_requested", user_id=str(user.id), email=email)

    async def reset_password(self, token: str, new_password: str) -> UserResponse:
        """
        Reset user password with reset token.

        Args:
            token: Password reset JWT token
            new_password: New password

        Returns:
            Updated UserResponse

        Raises:
            HTTPException: If token is invalid, expired, or already used (PROD)
        """
        # Verify token + JTI check (DRY helper)
        payload, jti = await verify_single_use_token(token, "password_reset")

        email = str(payload.get("sub"))
        user = await self.repository.get_by_email(email)

        if not user:
            raise_user_not_found(email)

        # Type narrowing: user is User (not None) after check
        assert user is not None

        # Hash new password and update
        hashed_password = get_password_hash(new_password)
        user = await self.repository.update_password(user, hashed_password)
        await self.db.commit()

        # Blacklist token after successful reset (PROD only)
        if jti:
            await mark_token_used(jti, "password_reset")

        # Revoke all refresh tokens (force re-login on all devices)
        redis = await get_redis_session()
        session_service = SessionService(redis)
        await session_service.remove_all_sessions(str(user.id))

        logger.info("password_reset_completed", user_id=str(user.id), email=email)

        return UserResponse.model_validate(user)

    async def initiate_google_oauth(self) -> tuple[str, str]:
        """
        Initiate Google OAuth flow with PKCE (Proof Key for Code Exchange).

        Returns:
            Tuple of (authorization_url, state_token)
        """
        # Use generic OAuth flow handler
        redis = await get_redis_session()
        session_service = SessionService(redis)

        from src.core.oauth import GoogleOAuthProvider, OAuthFlowHandler

        provider = GoogleOAuthProvider.for_authentication(settings)
        flow_handler = OAuthFlowHandler(provider, session_service)

        # Initiate flow with Google-specific params
        auth_url, state = await flow_handler.initiate_flow(
            additional_params={
                "access_type": "offline",  # Get refresh token
                "prompt": "consent",  # Force re-consent to get refresh token
            }
        )

        return auth_url, state

    async def handle_google_callback(self, code: str, state: str) -> UserResponse:
        """
        Handle Google OAuth callback.

        Args:
            code: Authorization code from Google
            state: CSRF state token

        Returns:
            UserResponse (BFF Pattern - no tokens)

        Raises:
            HTTPException: If OAuth flow fails
        """
        # Step 1: Exchange code for tokens (PKCE validation)
        token_response = await self._exchange_oauth_code(code, state)

        # Step 2: Fetch user info from Google
        userinfo = await self._fetch_google_userinfo(token_response.access_token)

        # Step 3: Find or create user
        user = await self._find_or_create_google_user(userinfo)

        await self.db.commit()

        logger.info(
            "google_oauth_completed",
            user_id=str(user.id),
            email=user.email,
            is_new_user=user.oauth_provider_id == userinfo["id"],
        )

        # BFF Pattern: Return user only, session created by router
        return UserResponse.model_validate(user)

    async def logout(self, user_id: str, refresh_token: str) -> None:
        """
        Logout user by revoking refresh token.

        Args:
            user_id: User ID
            refresh_token: Refresh token to revoke
        """
        redis = await get_redis_session()
        session_service = SessionService(redis)
        await session_service.remove_session(user_id, refresh_token)

        logger.info("user_logged_out", user_id=user_id)

    async def logout_all_devices(self, user_id: str) -> None:
        """
        Logout user from all devices by revoking all refresh tokens.

        Args:
            user_id: User ID
        """
        redis = await get_redis_session()
        session_service = SessionService(redis)
        await session_service.remove_all_sessions(user_id)

        logger.info("user_logged_out_all_devices", user_id=user_id)

    async def get_current_user(self, user_id: str) -> UserResponse:
        """
        Get current user by ID.

        Args:
            user_id: User UUID as string

        Returns:
            UserResponse

        Raises:
            HTTPException: If user not found
        """
        user = await self.repository.get_by_id(UUID(user_id))

        if not user:
            raise_user_not_found(user_id)

        return UserResponse.model_validate(user)

    # Private helper methods

    async def _exchange_oauth_code(self, code: str, state: str) -> Any:
        """
        Exchange OAuth authorization code for tokens with PKCE validation.

        Args:
            code: Authorization code
            state: CSRF state token

        Returns:
            TokenResponse from OAuth provider

        Raises:
            HTTPException: If token exchange fails
        """
        redis = await get_redis_session()
        session_service = SessionService(redis)

        from src.core.oauth import GoogleOAuthProvider, OAuthFlowHandler

        provider = GoogleOAuthProvider.for_authentication(settings)
        flow_handler = OAuthFlowHandler(provider, session_service)

        try:
            # Exchange code for tokens (handles state validation, PKCE, etc.)
            token_response, _stored_state = await flow_handler.handle_callback(code, state)
            return token_response
        except Exception as e:
            logger.error("oauth_token_exchange_failed", error=str(e), exc_info=True)
            raise_oauth_flow_failed("google", str(e))

    async def _fetch_google_userinfo(self, access_token: str) -> dict:
        """
        Fetch user info from Google OAuth API.

        Args:
            access_token: Google OAuth access token

        Returns:
            User info dictionary from Google

        Raises:
            HTTPException: If API call fails
        """
        async with httpx.AsyncClient() as client:
            userinfo_response = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )

            if userinfo_response.status_code != 200:
                logger.error(
                    "google_userinfo_api_failed",
                    status_code=userinfo_response.status_code,
                    response=userinfo_response.text,
                )
                raise_invalid_input(
                    "Failed to get user info from Google",
                    http_status=userinfo_response.status_code,
                )

            return userinfo_response.json()  # type: ignore[no-any-return]

    async def _find_or_create_google_user(self, userinfo: dict[Any, Any]) -> User:
        """
        Find existing user or create new one from Google OAuth user info.

        Handles three scenarios:
        1. User exists by OAuth provider ID → return existing user
        2. User exists by email → link OAuth to existing account
        3. New user → create with OAuth credentials

        Args:
            userinfo: User info from Google API

        Returns:
            User model instance
        """
        from src.infrastructure.observability.metrics_oauth import (
            oauth_user_creation_total,
            oauth_user_login_total,
        )

        google_id = userinfo["id"]
        email = userinfo["email"]
        full_name = userinfo.get("name")
        picture_url = userinfo.get("picture")

        # Detect language from Google's locale field
        # Google returns locale like "en", "fr", "es", "zh-CN", etc.
        from src.core.i18n import get_language_from_header

        detected_language = get_language_from_header(userinfo.get("locale", ""))

        # Check if user exists by OAuth provider
        user = await self.repository.get_by_oauth_provider("google", google_id)

        if user:
            # User already exists with this OAuth account - track login
            user.last_login = datetime.now(UTC)
            oauth_user_login_total.labels(provider="google").inc()
            logger.debug(
                "oauth_user_login",
                user_id=str(user.id),
                email=email,
                provider="google",
            )
            return user

        # Check if user exists by email
        user = await self.repository.get_by_email(email)

        if user:
            # Link OAuth to existing account
            await self.repository.update(
                user,
                {
                    "oauth_provider": "google",
                    "oauth_provider_id": google_id,
                    "picture_url": picture_url,
                    "is_verified": True,  # Google verifies emails
                    FIELD_IS_ACTIVE: True,
                    "last_login": datetime.now(UTC),
                },
            )
            # Track as login (existing user now using OAuth)
            oauth_user_login_total.labels(provider="google").inc()
            logger.info(
                "oauth_linked_to_existing_account",
                user_id=str(user.id),
                email=email,
                provider="google",
            )
            return user

        # Create new user
        user_data = {
            "email": email,
            "full_name": full_name,
            "oauth_provider": "google",
            "oauth_provider_id": google_id,
            "picture_url": picture_url,
            FIELD_IS_ACTIVE: False,  # New users disabled by default (admin approval required)
            "is_verified": True,  # Google verifies emails
            "language": detected_language,  # Auto-detect from Google locale
            "memory_enabled": True,  # Long-term memory enabled by default
            "last_login": datetime.now(UTC),  # Track first login
        }
        user = await self.repository.create(user_data)

        # Track new user creation via OAuth
        oauth_user_creation_total.labels(provider="google").inc()
        logger.info(
            "new_user_created_via_oauth",
            user_id=str(user.id),
            email=email,
            provider="google",
            language=detected_language,
            google_locale=userinfo.get("locale"),
        )

        # Notify admins of new registration via OAuth
        await self._notify_admins_of_new_registration(
            user_email=email,
            user_name=full_name,
            registration_method="google",
        )

        # Notify user that their account is pending activation
        await self._send_pending_activation_notification(
            user_email=email,
            user_name=full_name,
            user_language=detected_language,
        )

        return user

    # ========================================================================
    # REMOVED METHOD: _generate_tokens() (BFF Pattern Migration)
    # ========================================================================
    # This method was removed as part of BFF Pattern migration (v0.3.0).
    #
    # Previously generated JWT access + refresh tokens and stored session.
    # Now session management happens in router layer:
    # - Router creates session via SessionStore after service returns user
    # - HTTP-only cookies used instead of JWT tokens in response
    # - See auth/router.py for session creation in register/login/oauth endpoints
    # ========================================================================

    async def _send_verification_email(
        self, email: str, token: str, user_name: str | None = None, language: str = "fr"
    ) -> None:
        """Send email verification email via SMTP."""
        from src.core.constants import EMAIL_VERIFY_PATH
        from src.infrastructure.email import get_email_service

        verification_url = f"{settings.frontend_url}{EMAIL_VERIFY_PATH}?token={token}"

        email_service = get_email_service()
        sent = await email_service.send_email_verification(
            user_email=email,
            user_name=user_name,
            verification_url=verification_url,
            user_language=language,
        )

        if sent:
            logger.info(
                "verification_email_sent",
                email=email,
                verification_url=verification_url,
            )
        else:
            logger.error(
                "verification_email_failed",
                email=email,
            )

    async def _send_password_reset_email(
        self, email: str, token: str, user_name: str | None = None, language: str = "fr"
    ) -> None:
        """Send password reset email via SMTP."""
        from src.core.constants import EMAIL_RESET_PASSWORD_PATH
        from src.infrastructure.email import get_email_service

        reset_url = f"{settings.frontend_url}{EMAIL_RESET_PASSWORD_PATH}?token={token}"

        email_service = get_email_service()
        sent = await email_service.send_password_reset(
            user_email=email,
            user_name=user_name,
            reset_url=reset_url,
            user_language=language,
        )

        if sent:
            logger.info(
                "password_reset_email_sent",
                email=email,
                reset_url=reset_url,
            )
        else:
            logger.error(
                "password_reset_email_failed",
                email=email,
            )

    async def _notify_admins_of_new_registration(
        self, user_email: str, user_name: str | None, registration_method: str = "email"
    ) -> None:
        """Notify all admin users (superusers) of a new registration."""
        from src.infrastructure.email import get_email_service

        # Get all superusers
        admins = await self.repository.get_all_superusers()

        if not admins:
            logger.warning(
                "no_admins_to_notify",
                new_user_email=user_email,
            )
            return

        email_service = get_email_service()

        for admin in admins:
            sent = await email_service.send_new_registration_admin_notification(
                admin_email=admin.email,
                new_user_email=user_email,
                new_user_name=user_name,
                registration_method=registration_method,
            )

            if sent:
                logger.info(
                    "admin_notification_sent",
                    admin_email=admin.email,
                    new_user_email=user_email,
                )
            else:
                logger.error(
                    "admin_notification_failed",
                    admin_email=admin.email,
                    new_user_email=user_email,
                )

    async def _send_pending_activation_notification(
        self, user_email: str, user_name: str | None, user_language: str = "fr"
    ) -> None:
        """Send notification to user that their account is pending admin activation."""
        from src.infrastructure.email import get_email_service

        email_service = get_email_service()
        sent = await email_service.send_pending_activation_notification(
            user_email=user_email,
            user_name=user_name,
            user_language=user_language,
        )

        if sent:
            logger.info(
                "pending_activation_notification_sent",
                user_email=user_email,
            )
        else:
            logger.error(
                "pending_activation_notification_failed",
                user_email=user_email,
            )
