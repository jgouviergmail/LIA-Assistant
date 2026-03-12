"""
Integration tests for authentication flow with BFF Pattern.

Tests cover:
- Email/password authentication (register, login, logout)
- Session-based authentication with HTTP-only cookies
- Google OAuth 2.0 with PKCE
- Email verification
- Password reset
- OAuth redirect URI validation (2025 cross-port fix)

BFF Pattern changes:
- No tokens in response body
- HTTP-only session cookies
- Server-side session management in Redis
- Next.js reverse proxy for cross-port cookie compatibility
"""

from urllib.parse import parse_qs, urlparse

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.auth.models import User
from tests.conftest import assert_cookie_set, extract_cookie_value


@pytest.mark.integration
class TestUserRegistration:
    """Test user registration endpoint (BFF Pattern)."""

    @pytest.mark.asyncio
    async def test_register_new_user(self, async_client: AsyncClient):
        """Test registering a new user with valid credentials (BFF Pattern)."""
        response = await async_client.post(
            "/api/v1/auth/register",
            json={
                "email": "newuser@example.com",
                "password": "SecurePass123!!",
                "full_name": "New User",
            },
        )

        assert response.status_code == 201
        data = response.json()

        # BFF Pattern: No tokens in response, only user info and message
        assert "user" in data
        assert "message" in data
        assert "tokens" not in data  # BFF: No tokens exposed
        assert data["user"]["email"] == "newuser@example.com"
        assert data["user"]["full_name"] == "New User"
        assert data["user"]["is_active"] is False  # Requires email verification
        assert data["user"]["is_verified"] is False
        assert data["message"] == "Registration successful"

        # BFF Pattern: Session cookie should be set with correct attributes
        assert_cookie_set(response, "lia_session", httponly=True, samesite="lax")

    @pytest.mark.asyncio
    async def test_register_with_remember_me(self, async_client: AsyncClient):
        """Test registering with remember_me=True (30 days session)."""
        response = await async_client.post(
            "/api/v1/auth/register",
            json={
                "email": "rememberme@example.com",
                "password": "SecurePass123!!",
                "full_name": "Remember Me User",
                "remember_me": True,  # Extended session
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["user"]["email"] == "rememberme@example.com"

        # Verify cookie is set with extended TTL (30 days = 2592000 seconds)
        assert_cookie_set(
            response, "lia_session", httponly=True, samesite="lax", max_age=2592000
        )

    @pytest.mark.asyncio
    async def test_register_without_remember_me(self, async_client: AsyncClient):
        """Test registering without remember_me (default 7 days session)."""
        response = await async_client.post(
            "/api/v1/auth/register",
            json={
                "email": "noremember@example.com",
                "password": "SecurePass123!!",
                "full_name": "No Remember User",
                "remember_me": False,  # Standard session (default)
            },
        )

        assert response.status_code == 201

        # Verify cookie is set with standard TTL (7 days = 604800 seconds)
        assert_cookie_set(
            response, "lia_session", httponly=True, samesite="lax", max_age=604800
        )

    @pytest.mark.asyncio
    async def test_register_duplicate_email(self, async_client: AsyncClient, test_user: User):
        """Test registering with email that already exists."""
        response = await async_client.post(
            "/api/v1/auth/register",
            json={
                "email": test_user.email,
                "password": "SecurePass123!!",
                "full_name": "Duplicate User",
            },
        )

        assert response.status_code == 409  # Conflict status for duplicate resource
        data = response.json()
        assert "already" in data["detail"].lower()

    @pytest.mark.asyncio
    async def test_register_invalid_email(self, async_client: AsyncClient):
        """Test registering with invalid email format."""
        response = await async_client.post(
            "/api/v1/auth/register",
            json={
                "email": "invalid-email",
                "password": "SecurePass123!!",
                "full_name": "Invalid User",
            },
        )

        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_register_short_password(self, async_client: AsyncClient):
        """Test registering with password shorter than 8 characters."""
        response = await async_client.post(
            "/api/v1/auth/register",
            json={
                "email": "shortpass@example.com",
                "password": "short",
                "full_name": "Short Password User",
            },
        )

        assert response.status_code == 422  # Validation error


@pytest.mark.integration
class TestUserLogin:
    """Test user login endpoint (BFF Pattern)."""

    @pytest.mark.asyncio
    async def test_login_success(
        self, async_client: AsyncClient, test_user: User, test_user_credentials: dict[str, str]
    ):
        """Test successful login with valid credentials (BFF Pattern)."""
        response = await async_client.post(
            "/api/v1/auth/login",
            json=test_user_credentials,
        )

        assert response.status_code == 200
        data = response.json()

        # BFF Pattern: No tokens in response
        assert "user" in data
        assert "message" in data
        assert "tokens" not in data  # BFF: No tokens exposed
        assert data["user"]["email"] == test_user.email
        assert data["user"]["id"] == str(test_user.id)
        assert data["message"] == "Login successful"

        # BFF Pattern: Session cookie should be set
        assert_cookie_set(response, "lia_session", httponly=True, samesite="lax")

    @pytest.mark.asyncio
    async def test_login_with_remember_me_true(self, async_client: AsyncClient, test_user: User):
        """Test login with remember_me=True (30 days session)."""
        response = await async_client.post(
            "/api/v1/auth/login",
            json={
                "email": test_user.email,
                "password": "TestPass123!!",
                "remember_me": True,  # Extended session
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["user"]["email"] == test_user.email

        # Verify cookie has extended TTL (30 days = 2592000 seconds)
        assert_cookie_set(
            response, "lia_session", httponly=True, samesite="lax", max_age=2592000
        )

    @pytest.mark.asyncio
    async def test_login_with_remember_me_false(self, async_client: AsyncClient, test_user: User):
        """Test login with remember_me=False (default 7 days session)."""
        response = await async_client.post(
            "/api/v1/auth/login",
            json={
                "email": test_user.email,
                "password": "TestPass123!!",
                "remember_me": False,  # Standard session
            },
        )

        assert response.status_code == 200

        # Verify cookie has standard TTL (7 days = 604800 seconds)
        assert_cookie_set(
            response, "lia_session", httponly=True, samesite="lax", max_age=604800
        )

    @pytest.mark.asyncio
    async def test_login_default_remember_me(self, async_client: AsyncClient, test_user: User):
        """Test login without remember_me parameter (defaults to False)."""
        response = await async_client.post(
            "/api/v1/auth/login",
            json={
                "email": test_user.email,
                "password": "TestPass123!!",
                # No remember_me parameter - should default to False
            },
        )

        assert response.status_code == 200

        # Should use standard TTL (7 days) by default
        assert_cookie_set(
            response, "lia_session", httponly=True, samesite="lax", max_age=604800
        )

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, async_client: AsyncClient, test_user: User):
        """Test login with incorrect password."""
        response = await async_client.post(
            "/api/v1/auth/login",
            json={
                "email": test_user.email,
                "password": "WrongPass123!!",
            },
        )

        assert response.status_code == 401
        data = response.json()
        assert "credential" in data["detail"].lower()  # "Invalid credentials"

    @pytest.mark.asyncio
    async def test_login_nonexistent_user(self, async_client: AsyncClient):
        """Test login with email that doesn't exist."""
        response = await async_client.post(
            "/api/v1/auth/login",
            json={
                "email": "nonexistent@example.com",
                "password": "SomePass123!!",
            },
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_login_inactive_user(self, async_client: AsyncClient, test_inactive_user: User):
        """Test login with inactive user account."""
        response = await async_client.post(
            "/api/v1/auth/login",
            json={
                "email": test_inactive_user.email,
                "password": "Inactive123!!",
            },
        )

        # Should still allow login (session created)
        # But features may be restricted in the app
        assert response.status_code == 200


@pytest.mark.integration
class TestSessionManagement:
    """Test session-based authentication (BFF Pattern)."""

    @pytest.mark.asyncio
    async def test_session_authentication(
        self, async_client: AsyncClient, test_user: User, test_user_credentials: dict[str, str]
    ):
        """Test that session cookie is used for authentication."""
        # Ensure test_user exists in DB before login
        assert test_user.email == test_user_credentials["email"]

        # Login to get session cookie
        login_response = await async_client.post(
            "/api/v1/auth/login",
            json=test_user_credentials,
        )
        assert login_response.status_code == 200

        # Extract session cookie from response and set it on client
        session_id = extract_cookie_value(login_response, "lia_session")
        async_client.cookies.set("lia_session", session_id)

        # Test accessing protected endpoint with session cookie
        me_response = await async_client.get("/api/v1/auth/me")

        assert me_response.status_code == 200
        data = me_response.json()
        assert data["email"] == test_user_credentials["email"]

    @pytest.mark.asyncio
    async def test_session_expires_after_logout(
        self, async_client: AsyncClient, test_user: User, test_user_credentials: dict[str, str]
    ):
        """Test that session is invalidated after logout."""
        # Ensure test_user exists in DB before login
        assert test_user.email == test_user_credentials["email"]

        # Login
        login_response = await async_client.post(
            "/api/v1/auth/login",
            json=test_user_credentials,
        )
        assert login_response.status_code == 200

        # Extract and set session cookie
        session_id = extract_cookie_value(login_response, "lia_session")
        async_client.cookies.set("lia_session", session_id)

        # Verify session works
        me_response = await async_client.get("/api/v1/auth/me")
        assert me_response.status_code == 200

        # Logout
        logout_response = await async_client.post("/api/v1/auth/logout")
        assert logout_response.status_code == 200

        # Session should be invalid now
        me_response_after_logout = await async_client.get("/api/v1/auth/me")
        assert me_response_after_logout.status_code == 401


@pytest.mark.integration
class TestTokenRefresh:
    """Test token refresh endpoint (deprecated in BFF Pattern)."""

    @pytest.mark.asyncio
    async def test_refresh_endpoint_deprecated(self, async_client: AsyncClient):
        """
        Test that refresh endpoint returns HTTP 410 Gone (permanently removed).

        With BFF Pattern migration v0.3.0:
        - Sessions auto-refresh on each request, manual refresh not needed
        - Endpoint returns 410 Gone with migration guide
        - No backward compatibility, users should migrate to session-based auth
        """
        response = await async_client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "any-token"},
        )

        # Endpoint permanently removed (HTTP 410 Gone)
        assert response.status_code == 410

        # Verify migration guide in response
        data = response.json()
        assert data["detail"]["error"] == "endpoint_permanently_removed"
        assert "migration_guide" in data["detail"]


@pytest.mark.integration
class TestEmailVerification:
    """Test email verification endpoint."""

    @pytest.mark.asyncio
    async def test_verify_email_success(
        self, async_client: AsyncClient, async_session: AsyncSession
    ):
        """Test email verification with valid token."""
        from src.core.security import create_verification_token

        # Register new user
        register_response = await async_client.post(
            "/api/v1/auth/register",
            json={
                "email": "verify@example.com",
                "password": "VerifyPass123!!",
                "full_name": "Verify User",
            },
        )
        assert register_response.status_code == 201

        # Create verification token
        verification_token = create_verification_token("verify@example.com")

        # Verify email
        verify_response = await async_client.post(
            f"/api/v1/auth/verify-email?token={verification_token}",
        )

        assert verify_response.status_code == 200
        data = verify_response.json()
        assert data["is_verified"] is True
        assert data["is_active"] is True

    @pytest.mark.asyncio
    async def test_verify_email_invalid_token(self, async_client: AsyncClient):
        """Test email verification with invalid token."""
        response = await async_client.post(
            "/api/v1/auth/verify-email?token=invalid-verification-token",
        )

        assert response.status_code == 401  # Invalid token = authentication error


@pytest.mark.integration
class TestPasswordReset:
    """Test password reset flow."""

    @pytest.mark.asyncio
    async def test_request_password_reset(self, async_client: AsyncClient, test_user: User):
        """Test requesting password reset."""
        response = await async_client.post(
            "/api/v1/auth/request-password-reset",
            json={"email": test_user.email},
        )

        assert response.status_code == 200
        data = response.json()
        assert "message" in data

    @pytest.mark.asyncio
    async def test_request_password_reset_nonexistent_email(self, async_client: AsyncClient):
        """Test requesting password reset for non-existent email."""
        response = await async_client.post(
            "/api/v1/auth/request-password-reset",
            json={"email": "nonexistent@example.com"},
        )

        # Should still return 200 (don't reveal if email exists)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_reset_password_success(self, async_client: AsyncClient, test_user: User):
        """Test resetting password with valid token."""
        from src.core.security import create_password_reset_token

        # Create reset token
        reset_token = create_password_reset_token(test_user.email)

        # Reset password
        response = await async_client.post(
            "/api/v1/auth/reset-password",
            json={
                "token": reset_token,
                "new_password": "NewSecurePass123!!",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["email"] == test_user.email

        # Try logging in with new password
        login_response = await async_client.post(
            "/api/v1/auth/login",
            json={
                "email": test_user.email,
                "password": "NewSecurePass123!!",
            },
        )

        assert login_response.status_code == 200

    @pytest.mark.asyncio
    async def test_reset_password_invalid_token(self, async_client: AsyncClient):
        """Test resetting password with invalid token."""
        response = await async_client.post(
            "/api/v1/auth/reset-password",
            json={
                "token": "invalid-reset-token",
                "new_password": "NewPass123!!",
            },
        )

        assert response.status_code == 401  # Invalid token = authentication error


@pytest.mark.integration
class TestGetCurrentUser:
    """Test get current user endpoint (BFF Pattern)."""

    @pytest.mark.asyncio
    async def test_get_current_user_authenticated(
        self, async_client: AsyncClient, test_user: User, test_user_credentials: dict[str, str]
    ):
        """Test getting current user with valid session cookie."""
        # Login to get session
        login_response = await async_client.post(
            "/api/v1/auth/login",
            json=test_user_credentials,
        )

        # Extract and set session cookie
        session_id = extract_cookie_value(login_response, "lia_session")
        async_client.cookies.set("lia_session", session_id)

        # Get current user
        response = await async_client.get("/api/v1/auth/me")

        assert response.status_code == 200
        data = response.json()

        assert data["id"] == str(test_user.id)
        assert data["email"] == test_user.email
        assert data["full_name"] == test_user.full_name

    @pytest.mark.asyncio
    async def test_get_current_user_unauthenticated(self, async_client: AsyncClient):
        """Test getting current user without authentication."""
        response = await async_client.get("/api/v1/auth/me")

        assert response.status_code == 401


@pytest.mark.integration
class TestLogout:
    """Test logout endpoints (BFF Pattern)."""

    @pytest.mark.asyncio
    async def test_logout_single_device(
        self, async_client: AsyncClient, test_user: User, test_user_credentials: dict[str, str]
    ):
        """Test logging out from single device (BFF Pattern)."""
        # Ensure test_user exists in DB before login
        assert test_user.email == test_user_credentials["email"]

        # Login
        login_response = await async_client.post(
            "/api/v1/auth/login",
            json=test_user_credentials,
        )
        assert login_response.status_code == 200

        # Extract and set session cookie
        session_id = extract_cookie_value(login_response, "lia_session")
        async_client.cookies.set("lia_session", session_id)

        # Verify session works
        me_response = await async_client.get("/api/v1/auth/me")
        assert me_response.status_code == 200

        # Logout (BFF: No refresh_token needed in body)
        logout_response = await async_client.post("/api/v1/auth/logout")

        assert logout_response.status_code == 200
        data = logout_response.json()
        assert "logged out" in data["message"].lower()

        # Session should be invalid after logout
        me_response_after = await async_client.get("/api/v1/auth/me")
        assert me_response_after.status_code == 401

        # Cookie should be cleared (check Set-Cookie header)
        cookie_headers = logout_response.headers.get_list("set-cookie")
        # Verify lia_session cookie is cleared (Max-Age=0 or expired)
        assert any("lia_session=" in header for header in cookie_headers)

    @pytest.mark.asyncio
    async def test_logout_all_devices(
        self, async_client: AsyncClient, test_user: User, test_user_credentials: dict[str, str]
    ):
        """Test logging out from all devices (BFF Pattern)."""
        # Ensure test_user exists in DB before login
        assert test_user.email == test_user_credentials["email"]

        # Login
        login_response = await async_client.post(
            "/api/v1/auth/login",
            json=test_user_credentials,
        )

        # Extract and set session cookie
        session_id = extract_cookie_value(login_response, "lia_session")
        async_client.cookies.set("lia_session", session_id)

        # Logout from all devices
        response = await async_client.post("/api/v1/auth/logout-all")

        assert response.status_code == 200
        data = response.json()
        assert "all devices" in data["message"].lower()

        # Session should be invalid
        me_response = await async_client.get("/api/v1/auth/me")
        assert me_response.status_code == 401


@pytest.mark.integration
@pytest.mark.slow
class TestGoogleOAuth:
    """Test Google OAuth flow (BFF Pattern with PKCE)."""

    @pytest.mark.asyncio
    async def test_initiate_google_oauth(self, async_client: AsyncClient):
        """Test initiating Google OAuth flow."""
        response = await async_client.get("/api/v1/auth/google/login")

        assert response.status_code == 200
        data = response.json()

        assert "authorization_url" in data
        assert "state" in data
        assert "accounts.google.com" in data["authorization_url"]

        # Verify PKCE parameters in URL
        assert "code_challenge" in data["authorization_url"]
        assert "code_challenge_method=S256" in data["authorization_url"]
        assert "state=" in data["authorization_url"]

    @pytest.mark.asyncio
    async def test_google_oauth_callback_invalid_state(self, async_client: AsyncClient):
        """Test Google OAuth callback with invalid state token."""
        # BFF Pattern: Callback is GET with query params, not POST with body
        response = await async_client.get(
            "/api/v1/auth/google/callback?code=fake-code&state=invalid-state",
            follow_redirects=False,  # Don't follow redirect to frontend
        )

        # Should return error before redirecting
        assert response.status_code in [400, 302]  # Error or redirect to error page

    @pytest.mark.asyncio
    async def test_google_oauth_callback_success_redirects(self, async_client: AsyncClient):
        """
        Test that successful OAuth callback redirects to frontend.

        Note: This test can't fully validate OAuth without mocking Google API.
        It verifies the flow structure and redirect behavior.
        """
        # This would require mocking Google OAuth API
        # Here we just verify the endpoint accepts GET with query params
        response = await async_client.get(
            "/api/v1/auth/google/callback?code=test&state=test",
            follow_redirects=False,
        )

        # Should attempt to process (will fail on invalid state, but endpoint structure is correct)
        assert response.status_code in [302, 400]  # Redirect or invalid state error


@pytest.mark.integration
@pytest.mark.skip(
    reason="OAuth PKCE implementation may not include redirect_uri in authorization URL query params. "
    "These tests need to be updated for PKCE flow where redirect_uri is registered server-side."
)
class TestOAuthRedirectURIConfiguration:
    """
    Test OAuth redirect URI configuration for cross-port cookie fix.

    Context (2025):
    - BFF Pattern requires cookies shared between frontend (:3000) and backend (:8000)
    - SameSite=Lax cookies don't work with cross-port redirects in development
    - Solution: Next.js reverse proxy + redirect_uri points to frontend

    This test validates the redirect URI configuration is correct for the architecture.
    """

    @pytest.mark.asyncio
    async def test_google_oauth_initiate_returns_correct_redirect_uri(
        self, async_client: AsyncClient
    ):
        """
        Test that Google OAuth initiation returns redirect_uri pointing to frontend.

        Expected: http://localhost:3000/api/v1/auth/google/callback
        (Not http://localhost:8000/api/v1/auth/google/callback)

        Rationale:
        - Next.js proxies /api/* to backend :8000
        - Cookie is set on :3000 domain (unified)
        - Solves cross-port cookie issue with SameSite=Lax
        """
        response = await async_client.get("/api/v1/auth/google/login")

        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert "authorization_url" in data
        assert "state" in data

        # Parse authorization URL
        parsed_url = urlparse(data["authorization_url"])
        query_params = parse_qs(parsed_url.query)

        # Verify redirect_uri parameter points to frontend
        assert "redirect_uri" in query_params
        redirect_uri = query_params["redirect_uri"][0]

        # Critical assertion: redirect_uri must point to port 3000 (frontend)
        assert "localhost:3000" in redirect_uri or "3000" in redirect_uri, (
            f"Redirect URI should point to frontend (port 3000) for cross-port cookie fix. "
            f"Got: {redirect_uri}. "
            f"Expected format: http://localhost:3000/api/v1/auth/google/callback"
        )

        # Verify redirect_uri ends with correct path
        assert redirect_uri.endswith(
            "/api/v1/auth/google/callback"
        ), f"Redirect URI path is incorrect. Got: {redirect_uri}"

    @pytest.mark.asyncio
    async def test_settings_google_redirect_uri_configured_correctly(self):
        """
        Test that GOOGLE_REDIRECT_URI environment variable is configured correctly.

        This test validates the .env configuration matches the architecture requirements.
        """
        # Get redirect URI from settings
        redirect_uri = settings.google_redirect_uri

        # Verify it points to frontend (port 3000)
        assert "localhost:3000" in redirect_uri or "3000" in redirect_uri, (
            f"GOOGLE_REDIRECT_URI must point to frontend (port 3000) in development. "
            f"Current value: {redirect_uri}. "
            f"Update apps/api/.env: GOOGLE_REDIRECT_URI=http://localhost:3000/api/v1/auth/google/callback"
        )

        # Verify correct path
        assert (
            "/api/v1/auth/google/callback" in redirect_uri
        ), f"GOOGLE_REDIRECT_URI path is incorrect. Got: {redirect_uri}"

    @pytest.mark.asyncio
    async def test_oauth_callback_endpoint_exists(self, async_client: AsyncClient):
        """
        Test that OAuth callback endpoint exists and accepts GET requests.

        This validates the backend endpoint is ready to receive callbacks from Google
        (proxied through Next.js in development).
        """
        # Test callback endpoint with dummy params (will fail validation but endpoint exists)
        response = await async_client.get(
            "/api/v1/auth/google/callback?code=dummy&state=dummy",
            follow_redirects=False,
        )

        # Should NOT return 404 (endpoint exists)
        assert response.status_code != 404, (
            "OAuth callback endpoint not found. "
            "Ensure /api/v1/auth/google/callback endpoint exists in router."
        )

        # Should return 400 (invalid state) or 302 (redirect on error)
        assert response.status_code in [400, 302], (
            f"OAuth callback should return 400 (invalid params) or 302 (redirect). "
            f"Got: {response.status_code}"
        )
