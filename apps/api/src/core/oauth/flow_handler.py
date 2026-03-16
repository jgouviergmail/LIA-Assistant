"""
Generic OAuth 2.1 flow handler with PKCE.

This module implements a secure, reusable OAuth flow following best practices:
- PKCE (RFC 7636) mandatory for all flows
- State token for CSRF protection
- Short-lived state storage (5 minutes)
- Automatic token exchange
- Provider abstraction via Protocol

Security Features:
- Cryptographically secure random generation
- State token single-use (deleted after validation)
- HTTPS enforcement
- Timeout protection on HTTP requests
"""

from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

import httpx
import structlog
from pydantic import BaseModel, ConfigDict

from src.core.config import settings
from src.core.field_names import FIELD_TIMESTAMP
from src.core.security import (
    generate_code_challenge,
    generate_code_verifier,
    generate_state_token,
)
from src.infrastructure.cache.redis import SessionService

from .exceptions import (
    OAuthProviderError,
    OAuthStateValidationError,
    OAuthTokenExchangeError,
)
from .providers.base import OAuthProvider

logger = structlog.get_logger(__name__)


class OAuthTokenResponse(BaseModel):
    """OAuth token response from provider."""

    access_token: str
    refresh_token: str | None = None
    expires_in: int | None = None
    scope: str | None = None
    token_type: str = "Bearer"
    id_token: str | None = None  # OpenID Connect

    model_config = ConfigDict(frozen=True)


class OAuthFlowHandler:
    """
    Generic OAuth 2.1 flow handler with PKCE.

    This handler abstracts the OAuth flow for any provider implementing
    the OAuthProvider protocol.

    Best Practices Implemented:
    - PKCE (S256) mandatory
    - State token CSRF protection
    - Redis state storage with TTL
    - Single-use state tokens
    - Timeout protection
    - Structured logging

    Example:
        >>> provider = GoogleOAuthProvider.for_authentication(settings)
        >>> handler = OAuthFlowHandler(provider, session_service)
        >>> auth_url, state = await handler.initiate_flow()
        >>> # User redirected to auth_url, returns with code and state
        >>> tokens = await handler.handle_callback(code, state)
    """

    def __init__(self, provider: OAuthProvider, session_service: SessionService) -> None:
        """
        Initialize OAuth flow handler.

        Args:
            provider: OAuth provider configuration
            session_service: Session service for state storage
        """
        self.provider = provider
        self.session_service = session_service

    async def initiate_flow(
        self,
        additional_params: dict[str, str] | None = None,
        metadata: dict[str, str] | None = None,
    ) -> tuple[str, str]:
        """
        Initiate OAuth authorization flow with PKCE.

        This method:
        1. Generates crypto-secure state and PKCE verifier
        2. Stores state+verifier+metadata in Redis (5min TTL)
        3. Builds authorization URL with PKCE challenge

        Args:
            additional_params: Additional query params (e.g., access_type=offline, prompt=consent)
            metadata: Business logic metadata to store with state (e.g., user_id, connector_type)

        Returns:
            Tuple of (authorization_url, state_token)

        Example:
            >>> auth_url, state = await handler.initiate_flow(
            ...     additional_params={"access_type": "offline", "prompt": "consent"},
            ...     metadata={"user_id": "123", "connector_type": "gmail"},
            ... )
        """
        # Generate cryptographically secure tokens
        state = generate_state_token()  # 32 bytes hex
        code_verifier = generate_code_verifier()  # 43-128 chars
        code_challenge = generate_code_challenge(code_verifier)  # SHA-256

        # Prepare state data with PKCE and optional metadata
        state_data = {
            "provider": self.provider.provider_name,
            "code_verifier": code_verifier,
            FIELD_TIMESTAMP: datetime.now(UTC).isoformat(),
        }

        # Merge business logic metadata if provided
        if metadata:
            state_data.update(metadata)

        # Store state in Redis with short TTL
        await self.session_service.store_oauth_state(
            state,
            state_data,
            expire_minutes=5,  # Short-lived for security
        )

        # Build authorization URL
        params = {
            "client_id": self.provider.client_id,
            "redirect_uri": self.provider.redirect_uri,
            "response_type": "code",
            "scope": " ".join(self.provider.scopes),
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",  # SHA-256 (most secure)
            **(additional_params or {}),
        }

        auth_url = f"{self.provider.authorization_endpoint}?{urlencode(params)}"

        logger.info(
            "oauth_flow_initiated",
            provider=self.provider.provider_name,
            state=state,
            scopes=self.provider.scopes,
            pkce=True,
        )

        return auth_url, state

    async def handle_callback(
        self,
        code: str,
        state: str,
    ) -> tuple[OAuthTokenResponse, dict[str, str]]:
        """
        Handle OAuth callback and exchange authorization code for tokens.

        This method:
        1. Validates state token (CSRF protection)
        2. Retrieves PKCE code_verifier + metadata from Redis
        3. Exchanges authorization code for access/refresh tokens
        4. Deletes state token (single-use)

        Args:
            code: Authorization code from provider
            state: State token from provider (must match stored state)

        Returns:
            Tuple of (OAuthTokenResponse, stored_state_metadata)
            - OAuthTokenResponse: access_token, refresh_token, etc.
            - stored_state_metadata: dict with provider, code_verifier, timestamp, and any custom metadata

        Raises:
            OAuthStateValidationError: If state invalid or expired
            OAuthTokenExchangeError: If token exchange fails
            OAuthProviderError: If provider returns error

        Security:
        - State token validated against Redis (CSRF protection)
        - PKCE code_verifier required (prevents code interception)
        - State token deleted after use (single-use)
        - HTTP timeout protection (10s)
        """
        # Step 1: Validate state and retrieve PKCE verifier + metadata
        stored_state = await self._validate_state_and_get_verifier(state)

        # Step 2: Exchange authorization code for tokens
        token_data = await self._exchange_code_for_tokens(code, stored_state["code_verifier"])

        # Step 3: Parse and return token response
        token_response = self._parse_token_response(token_data)

        # Note: State token already deleted by get_oauth_state() (single-use pattern)
        logger.info(
            "oauth_token_exchange_success",
            provider=self.provider.provider_name,
            state=state,
            has_refresh_token=token_data.get("refresh_token") is not None,
            expires_in=token_data.get("expires_in"),
        )

        return token_response, stored_state

    # Private helper methods

    async def _validate_state_and_get_verifier(self, state: str) -> dict[str, Any]:
        """
        Validate OAuth state token and retrieve stored data including PKCE verifier.

        Args:
            state: State token from OAuth callback

        Returns:
            Stored state data containing code_verifier, provider, timestamp, and metadata

        Raises:
            OAuthStateValidationError: If state is invalid, expired, or provider mismatch
        """
        from src.infrastructure.observability.metrics_oauth import (
            oauth_pkce_validation_total,
            oauth_state_validation_total,
        )

        # Retrieve state from Redis (auto-deleted after retrieval for single-use pattern)
        stored_state = await self.session_service.get_oauth_state(state)

        if not stored_state:
            logger.warning(
                "oauth_invalid_state",
                provider=self.provider.provider_name,
                state=state,
            )
            # Track state validation failure
            oauth_state_validation_total.labels(
                provider=self.provider.provider_name, result="failed"
            ).inc()
            raise OAuthStateValidationError("Invalid or expired OAuth state token")

        # Verify provider matches (prevent cross-provider attacks)
        if stored_state.get("provider") != self.provider.provider_name:
            logger.warning(
                "oauth_provider_mismatch",
                expected=self.provider.provider_name,
                got=stored_state.get("provider"),
                state=state,
            )
            # Track state validation failure (provider mismatch)
            oauth_state_validation_total.labels(
                provider=self.provider.provider_name, result="failed"
            ).inc()
            raise OAuthStateValidationError("OAuth state provider mismatch")

        # Verify PKCE code_verifier exists (mandatory for security)
        code_verifier = stored_state.get("code_verifier")
        if not code_verifier:
            logger.error(
                "oauth_missing_code_verifier",
                provider=self.provider.provider_name,
                state=state,
            )
            # Track PKCE validation failure (missing code_verifier)
            oauth_pkce_validation_total.labels(
                provider=self.provider.provider_name, result="failed"
            ).inc()
            raise OAuthStateValidationError("PKCE code_verifier not found in state")

        # State validation succeeded
        oauth_state_validation_total.labels(
            provider=self.provider.provider_name, result="success"
        ).inc()

        # PKCE code_verifier found (validation will happen at provider side during token exchange)
        # Track PKCE validation success (code_verifier exists and will be sent to provider)
        oauth_pkce_validation_total.labels(
            provider=self.provider.provider_name, result="success"
        ).inc()

        logger.debug(
            "oauth_state_validated",
            provider=self.provider.provider_name,
            state=state,
            has_metadata=len(stored_state) > 3,  # More than provider, code_verifier, timestamp
        )

        return stored_state

    async def _exchange_code_for_tokens(self, code: str, code_verifier: str) -> dict[str, Any]:
        """
        Exchange authorization code for access/refresh tokens with PKCE verification.

        Args:
            code: Authorization code from OAuth provider
            code_verifier: PKCE code verifier (proves client initiated the flow)

        Returns:
            Token data dictionary from provider

        Raises:
            OAuthTokenExchangeError: If token exchange fails (HTTP errors or network issues)
        """
        async with httpx.AsyncClient(
            timeout=settings.http_timeout_oauth, follow_redirects=False
        ) as client:
            try:
                response = await client.post(
                    self.provider.token_endpoint,
                    data={
                        "code": code,
                        "client_id": self.provider.client_id,
                        "client_secret": self.provider.client_secret,
                        "redirect_uri": self.provider.redirect_uri,
                        "grant_type": "authorization_code",
                        "code_verifier": code_verifier,  # PKCE verification
                    },
                    headers={"Accept": "application/json"},
                )
                response.raise_for_status()
                return response.json()  # type: ignore[no-any-return]

            except httpx.HTTPStatusError as e:
                error_detail = e.response.text if e.response else str(e)
                logger.error(
                    "oauth_token_exchange_failed",
                    provider=self.provider.provider_name,
                    status_code=e.response.status_code if e.response else None,
                    error_detail=error_detail,
                )
                raise OAuthTokenExchangeError(
                    f"Token exchange failed with status {e.response.status_code if e.response else 'unknown'}",
                    original_error=e,
                ) from e

            except httpx.RequestError as e:
                logger.error(
                    "oauth_token_exchange_network_error",
                    provider=self.provider.provider_name,
                    error=str(e),
                )
                raise OAuthTokenExchangeError(
                    "Network error during token exchange",
                    original_error=e,
                ) from e

    def _parse_token_response(self, token_data: dict[str, Any]) -> OAuthTokenResponse:
        """
        Parse and validate token response from OAuth provider.

        Args:
            token_data: Raw token data from provider

        Returns:
            Validated OAuthTokenResponse object

        Raises:
            OAuthProviderError: If required fields are missing
        """
        try:
            return OAuthTokenResponse(
                access_token=token_data["access_token"],
                refresh_token=token_data.get("refresh_token"),
                expires_in=token_data.get("expires_in"),
                scope=token_data.get("scope"),
                token_type=token_data.get("token_type", "Bearer"),
                id_token=token_data.get("id_token"),  # OpenID Connect
            )
        except KeyError as e:
            logger.error(
                "oauth_invalid_token_response",
                provider=self.provider.provider_name,
                missing_field=str(e),
                token_data=token_data,
            )
            raise OAuthProviderError(
                f"Invalid token response from provider: missing {e}",
                provider_response=token_data,
            ) from e

    async def revoke_token(
        self,
        token: str,
        token_type: str = "access_token",
    ) -> None:
        """
        Revoke an OAuth token (best effort).

        This method attempts to revoke a token with the provider.
        If the provider doesn't support revocation or the request fails,
        it logs a warning but doesn't raise an exception.

        Args:
            token: Token to revoke (access_token or refresh_token)
            token_type: Type hint for provider ("access_token" or "refresh_token")

        Note:
            Token revocation is best-effort. Even if revocation fails,
            the token should be considered revoked locally.
        """
        if not self.provider.revocation_endpoint:
            logger.warning(
                "oauth_revocation_unsupported",
                provider=self.provider.provider_name,
            )
            return

        async with httpx.AsyncClient(
            timeout=settings.http_timeout_token, follow_redirects=False
        ) as client:
            try:
                response = await client.post(
                    self.provider.revocation_endpoint,
                    data={
                        "token": token,
                        "token_type_hint": token_type,
                    },
                    auth=(self.provider.client_id, self.provider.client_secret),
                )
                response.raise_for_status()

                logger.info(
                    "oauth_token_revoked",
                    provider=self.provider.provider_name,
                    token_type=token_type,
                )

            except Exception as e:
                # Best effort - don't fail on revocation errors
                logger.error(
                    "oauth_revocation_failed",
                    provider=self.provider.provider_name,
                    token_type=token_type,
                    error=str(e),
                    exc_info=True,
                )
