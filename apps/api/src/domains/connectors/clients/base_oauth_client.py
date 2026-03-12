"""
Base OAuth API client with common functionality.

Provides shared functionality for all OAuth-based API clients (Google, Microsoft, etc.):
- OAuth token management with automatic refresh
- Rate limiting (Redis + local fallback)
- HTTP client with connection pooling
- Retry logic with exponential backoff
- Circuit breaker pattern for fault tolerance (Sprint 16)

This is the super-abstraction that Google, Microsoft, and other OAuth clients inherit from.
Provider-specific token refresh is implemented by subclasses.

Sprint 14 - Gold-Grade Architecture
Sprint 16 - Added Circuit Breaker integration
Created: 2025-12-18
"""

import asyncio
import time
from abc import ABC
from datetime import UTC, datetime, timedelta
from typing import Any, Generic, TypeVar
from uuid import UUID

import httpx
import structlog

from src.core.config import settings
from src.core.constants import (
    DEFAULT_RATE_LIMIT_PER_SECOND,
    HTTP_MAX_CONNECTIONS,
    HTTP_MAX_KEEPALIVE_CONNECTIONS,
    OAUTH_TOKEN_REFRESH_MARGIN_SECONDS,
)
from src.domains.connectors.schemas import ConnectorCredentials
from src.infrastructure.cache.redis import get_redis_session
from src.infrastructure.locks import OAuthLock
from src.infrastructure.rate_limiting import RedisRateLimiter
from src.infrastructure.resilience import CircuitBreaker, CircuitBreakerError, get_circuit_breaker

logger = structlog.get_logger(__name__)

# Type variable for connector type (allows subclasses to use specific enum values)
ConnectorTypeT = TypeVar("ConnectorTypeT")


class BaseOAuthClient(ABC, Generic[ConnectorTypeT]):  # noqa: UP046
    """
    Abstract base class for OAuth-based API clients.

    Provides common infrastructure for all OAuth clients:
    - Token expiration checking and refresh coordination
    - Distributed rate limiting via Redis (with local fallback)
    - HTTP client with connection pooling
    - Retry logic with exponential backoff

    Subclasses must implement:
    - connector_type: The specific connector type enum value
    - api_base_url: Base URL for the API
    - _refresh_access_token(): Provider-specific token refresh logic

    Example:
        class BaseGoogleClient(BaseOAuthClient[ConnectorType]):
            async def _refresh_access_token(self) -> str:
                # Google-specific OAuth refresh
                ...

        class BaseMicrosoftClient(BaseOAuthClient[ConnectorType]):
            async def _refresh_access_token(self) -> str:
                # Microsoft-specific OAuth refresh
                ...
    """

    # Must be defined by subclasses
    connector_type: ConnectorTypeT
    api_base_url: str

    def __init__(
        self,
        user_id: UUID,
        credentials: ConnectorCredentials,
        connector_service: Any,  # ConnectorService (avoid circular import)
        rate_limit_per_second: int = DEFAULT_RATE_LIMIT_PER_SECOND,
    ) -> None:
        """
        Initialize OAuth API client.

        Args:
            user_id: User UUID.
            credentials: OAuth credentials (access_token, refresh_token, expires_at).
            connector_service: Service for token refresh operations.
            rate_limit_per_second: Max requests per second (default: 10).
        """
        self.user_id = user_id
        self.credentials = credentials
        self.connector_service = connector_service
        self._rate_limit_per_second = rate_limit_per_second
        self._rate_limit_interval = 1.0 / rate_limit_per_second
        self._last_request_time = 0.0
        self._http_client: httpx.AsyncClient | None = None
        self._redis_rate_limiter: RedisRateLimiter | None = None
        self._circuit_breaker: CircuitBreaker | None = None

    # =========================================================================
    # HTTP CLIENT MANAGEMENT
    # =========================================================================

    async def _get_client(self) -> httpx.AsyncClient:
        """
        Get or create reusable HTTP client with connection pooling.

        Best practices 2025:
        - Connection pooling reduces latency (35-90ms saved per request)
        - Reuses TCP connections for same host
        - Default limits: max_keepalive_connections=20, max_connections=100
        """
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=settings.http_timeout_external_api,
                limits=httpx.Limits(
                    max_keepalive_connections=HTTP_MAX_KEEPALIVE_CONNECTIONS,
                    max_connections=HTTP_MAX_CONNECTIONS,
                    keepalive_expiry=30.0,
                ),
            )
        return self._http_client

    async def close(self) -> None:
        """
        Cleanup HTTP client and close connections.

        IMPORTANT: Call this when the client is no longer needed to prevent resource leaks.
        """
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    # =========================================================================
    # CIRCUIT BREAKER (Sprint 16 - Fault Tolerance)
    # =========================================================================

    def _get_circuit_breaker_service_name(self) -> str:
        """
        Get the circuit breaker service name for this client.

        Override in subclasses to customize the service name.
        Default uses connector_type value.

        Returns:
            Service name for circuit breaker identification
        """
        connector_type_value = (
            self.connector_type.value
            if hasattr(self.connector_type, "value")
            else str(self.connector_type)
        )
        return f"oauth_{connector_type_value}"

    def _is_circuit_breaker_enabled(self) -> bool:
        """
        Check if circuit breaker is enabled for this client type.

        Override in subclasses to customize enablement logic.

        Returns:
            True if circuit breaker should be used
        """
        # NOTE: Circuit breaker is always enabled
        return True

    def _get_circuit_breaker(self) -> CircuitBreaker:
        """
        Get or create circuit breaker for this client.

        Lazy initialization to avoid creating circuit breaker if not needed.

        Returns:
            CircuitBreaker instance for this service
        """
        if self._circuit_breaker is None:
            service_name = self._get_circuit_breaker_service_name()
            self._circuit_breaker = get_circuit_breaker(service_name)
        return self._circuit_breaker

    # =========================================================================
    # RATE LIMITING (Redis + Local Fallback)
    # =========================================================================

    async def _get_redis_rate_limiter(self) -> RedisRateLimiter:
        """
        Get or create Redis rate limiter instance.

        Lazy initialization to avoid creating Redis connection if rate limiting is disabled.
        """
        if self._redis_rate_limiter is None:
            redis = await get_redis_session()
            self._redis_rate_limiter = RedisRateLimiter(redis)
        return self._redis_rate_limiter

    def _get_rate_limit_key(self) -> str:
        """
        Get the rate limit key for this client.

        Override in subclasses if a different key pattern is needed.

        Returns:
            Rate limit key string (e.g., "user:{user_id}:{connector_type}")
        """
        connector_type_value = (
            self.connector_type.value
            if hasattr(self.connector_type, "value")
            else str(self.connector_type)
        )
        return f"user:{self.user_id}:{connector_type_value}"

    async def _rate_limit(self) -> None:
        """
        Apply distributed rate limiting using Redis.

        Uses Redis sliding window algorithm for accurate rate limiting across
        multiple application instances (horizontal scaling).

        Falls back to local time-based throttling if Redis is unavailable or
        rate limiting is disabled.
        """
        if not settings.rate_limit_enabled:
            logger.debug(
                "rate_limit_disabled",
                user_id=str(self.user_id),
                client_type=self.__class__.__name__,
            )
            return

        try:
            limiter = await self._get_redis_rate_limiter()
            rate_limit_key = self._get_rate_limit_key()

            # Convert per-second limit to per-minute for sliding window
            max_calls = self._rate_limit_per_second * 60
            window_seconds = 60

            # Try to acquire rate limit token with retries
            max_retries = 5
            for attempt in range(max_retries):
                allowed = await limiter.acquire(
                    key=rate_limit_key,
                    max_calls=max_calls,
                    window_seconds=window_seconds,
                )

                if allowed:
                    logger.debug(
                        "rate_limit_acquired",
                        user_id=str(self.user_id),
                        client_type=self.__class__.__name__,
                        max_calls=max_calls,
                    )
                    return

                # Rate limit exceeded, wait and retry
                wait_time = 1.0 * (attempt + 1)
                logger.warning(
                    "rate_limit_exceeded_retrying",
                    user_id=str(self.user_id),
                    client_type=self.__class__.__name__,
                    attempt=attempt + 1,
                    wait_time_seconds=wait_time,
                )
                await asyncio.sleep(wait_time)

            # Max retries exceeded - let subclass handle the error
            logger.error(
                "rate_limit_max_retries_exceeded",
                user_id=str(self.user_id),
                client_type=self.__class__.__name__,
            )
            self._on_rate_limit_exceeded()

        except Exception as e:
            # On Redis failure, fall back to local time-based throttling
            logger.warning(
                "rate_limit_redis_fallback",
                user_id=str(self.user_id),
                client_type=self.__class__.__name__,
                error=str(e),
            )
            await self._local_rate_limit()

    async def _local_rate_limit(self) -> None:
        """
        Apply local time-based rate limiting (fallback when Redis unavailable).
        """
        now = time.monotonic()
        elapsed = now - self._last_request_time

        if elapsed < self._rate_limit_interval:
            wait_time = self._rate_limit_interval - elapsed
            logger.debug(
                "rate_limit_local_throttle",
                user_id=str(self.user_id),
                client_type=self.__class__.__name__,
                wait_time_ms=int(wait_time * 1000),
            )
            await asyncio.sleep(wait_time)

        self._last_request_time = time.monotonic()

    def _on_rate_limit_exceeded(self) -> None:
        """
        Called when rate limit is exceeded after all retries.

        Override in subclasses to raise appropriate exceptions.
        Default implementation raises a generic exception.
        """
        from fastapi import HTTPException, status

        connector_type_value = (
            self.connector_type.value
            if hasattr(self.connector_type, "value")
            else str(self.connector_type)
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded for {connector_type_value}. Please try again later.",
        )

    # =========================================================================
    # TOKEN MANAGEMENT
    # =========================================================================

    def _is_token_expired_or_expiring_soon(self) -> bool:
        """
        Check if token is expired or will expire within the safety margin.

        The safety margin (OAUTH_TOKEN_REFRESH_MARGIN_SECONDS) prevents race conditions
        and clock skew issues between our server and the OAuth provider.

        Returns:
            True if token needs refresh, False otherwise.
        """
        if not self.credentials.expires_at:
            return False

        refresh_threshold = datetime.now(UTC) + timedelta(
            seconds=OAUTH_TOKEN_REFRESH_MARGIN_SECONDS
        )
        return self.credentials.expires_at < refresh_threshold

    async def _refresh_access_token(self) -> str:
        """
        Refresh the OAuth access token using Redis lock to prevent race conditions.

        Provider-agnostic: delegates actual token exchange to connector_service._refresh_oauth_token()
        which handles provider-specific differences (Google, Microsoft, etc.).

        Returns:
            Valid access token string.

        Raises:
            HTTPException: If token refresh fails.
        """
        from fastapi import HTTPException, status

        time_until_expiry = (
            (self.credentials.expires_at - datetime.now(UTC)).total_seconds()
            if self.credentials.expires_at
            else 0
        )

        connector_type_value = (
            self.connector_type.value
            if hasattr(self.connector_type, "value")
            else str(self.connector_type)
        )

        logger.info(
            "oauth_token_refresh_needed",
            user_id=str(self.user_id),
            connector_type=connector_type_value,
            expires_at=(
                self.credentials.expires_at.isoformat() if self.credentials.expires_at else None
            ),
            seconds_until_expiry=round(time_until_expiry),
            refresh_margin_seconds=OAUTH_TOKEN_REFRESH_MARGIN_SECONDS,
        )

        # Use Redis lock to prevent multiple refresh attempts
        redis_session = await get_redis_session()
        async with OAuthLock(redis_session, self.user_id, self.connector_type):
            # Double-check token still needs refresh (another coroutine might have refreshed)
            fresh_credentials = await self.connector_service.get_connector_credentials(
                self.user_id, self.connector_type
            )

            # Check if fresh credentials are valid with same safety margin
            if fresh_credentials and fresh_credentials.expires_at:
                fresh_threshold = datetime.now(UTC) + timedelta(
                    seconds=OAUTH_TOKEN_REFRESH_MARGIN_SECONDS
                )
                if fresh_credentials.expires_at > fresh_threshold:
                    logger.debug(
                        "oauth_token_already_refreshed_by_another_process",
                        user_id=str(self.user_id),
                        connector_type=connector_type_value,
                        new_expires_at=fresh_credentials.expires_at.isoformat(),
                    )
                    self.credentials = fresh_credentials
                    return str(fresh_credentials.access_token)

            # Refresh token
            from src.domains.connectors.repository import ConnectorRepository

            # Get connector from DB
            async with self.connector_service.db as db:
                repo = ConnectorRepository(db)
                connector = await repo.get_by_user_and_type(self.user_id, self.connector_type)

                if not connector:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"{connector_type_value} connector not found",
                    )

                # Ensure we have fresh credentials to use for refresh
                if not fresh_credentials:
                    logger.error(
                        "oauth_token_refresh_no_credentials",
                        user_id=str(self.user_id),
                        connector_type=connector_type_value,
                    )
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"No credentials found for {connector_type_value} connector",
                    )

                # Refresh via connector service using fresh_credentials from DB
                refreshed_credentials = await self.connector_service._refresh_oauth_token(
                    connector, fresh_credentials
                )
                self.credentials = refreshed_credentials
                logger.info(
                    "oauth_token_refreshed_success",
                    user_id=str(self.user_id),
                    connector_type=connector_type_value,
                )

        return self.credentials.access_token

    async def _ensure_valid_token(self) -> str:
        """
        Ensure we have a valid access token, refreshing if needed.

        This is the main entry point for token management. It checks if the
        current token is expired or expiring soon, and refreshes if needed.

        Returns:
            Valid access token string.
        """
        if self._is_token_expired_or_expiring_soon():
            logger.info(
                "oauth_token_refresh_needed",
                user_id=str(self.user_id),
                client_type=self.__class__.__name__,
                expires_at=(
                    self.credentials.expires_at.isoformat() if self.credentials.expires_at else None
                ),
            )
            return await self._refresh_access_token()

        return self.credentials.access_token

    # =========================================================================
    # HTTP REQUEST HELPERS
    # =========================================================================

    async def _make_authenticated_request(
        self,
        method: str,
        url: str,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """
        Make an authenticated HTTP request with the current access token.

        This is a low-level helper that handles token injection. Subclasses
        should use this in their _make_request implementations.

        Includes circuit breaker protection to prevent cascade failures when
        the external service is unavailable.

        Args:
            method: HTTP method (GET, POST, etc.)
            url: Full URL to request
            params: Query parameters
            json_data: JSON body for POST/PUT/PATCH
            headers: Additional headers (Authorization added automatically)

        Returns:
            httpx.Response object

        Raises:
            HTTPException: If circuit breaker is open (503 Service Unavailable)
        """
        # Check circuit breaker first (fail fast if service is down)
        if self._is_circuit_breaker_enabled():
            cb = self._get_circuit_breaker()
            try:
                # Check if we can proceed
                async with cb._lock:
                    if not await cb._should_allow_request():
                        await cb._reject_request()
            except CircuitBreakerError as e:
                # Convert to HTTPException for consistent API responses
                from fastapi import HTTPException, status

                connector_type_value = (
                    self.connector_type.value
                    if hasattr(self.connector_type, "value")
                    else str(self.connector_type)
                )
                logger.warning(
                    "circuit_breaker_rejected_request",
                    service=e.service,
                    state=e.state.value,
                    connector_type=connector_type_value,
                    user_id=str(self.user_id),
                    retry_after=e.retry_after,
                )
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=f"{connector_type_value} service temporarily unavailable. Please try again later.",
                    headers={"Retry-After": str(int(e.retry_after))} if e.retry_after else None,
                ) from e

        access_token = await self._ensure_valid_token()

        request_headers = {"Authorization": f"Bearer {access_token}"}
        if headers:
            request_headers.update(headers)

        client = await self._get_client()

        try:
            if method.upper() == "GET":
                response = await client.get(url, headers=request_headers, params=params)
            elif method.upper() == "POST":
                response = await client.post(
                    url, headers=request_headers, params=params, json=json_data
                )
            elif method.upper() == "PUT":
                response = await client.put(
                    url, headers=request_headers, params=params, json=json_data
                )
            elif method.upper() == "PATCH":
                response = await client.patch(
                    url, headers=request_headers, params=params, json=json_data
                )
            elif method.upper() == "DELETE":
                response = await client.delete(url, headers=request_headers, params=params)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            # Record circuit breaker success/failure based on response
            if self._is_circuit_breaker_enabled():
                cb = self._get_circuit_breaker()
                if response.status_code >= 500 or response.status_code == 429:
                    # Server error or rate limited - record failure
                    await cb.record_failure(
                        Exception(f"HTTP {response.status_code}: {response.text[:200]}")
                    )
                else:
                    # Success (including 4xx client errors - those are valid responses)
                    await cb.record_success()

            return response

        except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError) as e:
            # Network-level failures should trip the circuit breaker
            if self._is_circuit_breaker_enabled():
                cb = self._get_circuit_breaker()
                await cb.record_failure(e)
            raise

    def _should_retry_status(self, status_code: int) -> bool:
        """
        Check if a status code should trigger a retry.

        Override in subclasses for provider-specific retry logic.

        Args:
            status_code: HTTP status code

        Returns:
            True if the request should be retried
        """
        return status_code == 429 or status_code >= 500

    def _calculate_backoff(self, attempt: int) -> float:
        """
        Calculate backoff time for retry attempts.

        Uses exponential backoff: 1s, 2s, 4s, 8s...

        Args:
            attempt: Current attempt number (0-indexed)

        Returns:
            Wait time in seconds
        """
        return float(2**attempt)

    # =========================================================================
    # TEMPLATE METHOD: _make_request (with 3 hooks)
    # =========================================================================

    def _parse_error_detail(self, response: httpx.Response) -> str:
        """
        Extract human-readable error from response. Override for provider-specific formats.

        Default: returns response text (matches Google behavior).
        """
        return response.text

    def _get_retry_delay(self, response: httpx.Response, attempt: int) -> float:
        """
        Calculate retry delay for 429/5xx responses. Override to honor Retry-After.

        Default: exponential backoff (matches Google behavior).
        """
        return self._calculate_backoff(attempt)

    def _enrich_request_params(self, params: dict[str, Any] | None) -> dict[str, Any] | None:
        """
        Enrich request parameters before sending. Override for provider defaults.

        Default: pass-through (matches Google behavior).
        """
        return params

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        max_retries: int = 3,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        Make HTTP request to provider API with retry logic.

        Template Method: uses 3 hooks for provider customization:
        - _parse_error_detail(): Extract error from response
        - _get_retry_delay(): Calculate retry delay for 429/5xx
        - _enrich_request_params(): Enrich params before sending

        Args:
            method: HTTP method (GET, POST, etc.).
            endpoint: API endpoint path (e.g., /people/me/connections).
            params: Query parameters.
            json_data: JSON body for POST/PUT requests.
            max_retries: Max retry attempts for 429/5xx errors.
            extra_headers: Additional headers to include.

        Returns:
            JSON response from API.

        Raises:
            HTTPException: On 4xx errors or max retries exceeded.
        """
        from fastapi import HTTPException, status

        await self._rate_limit()

        # Hook: enrich params before sending
        params = self._enrich_request_params(params)

        url = f"{self.api_base_url}{endpoint}"
        client = await self._get_client()

        connector_type_value = (
            self.connector_type.value
            if hasattr(self.connector_type, "value")
            else str(self.connector_type)
        )

        for attempt in range(max_retries):
            # Fetch a fresh token on each attempt (token may expire between retries)
            access_token = await self._ensure_valid_token()
            headers: dict[str, str] = {"Authorization": f"Bearer {access_token}"}
            if extra_headers:
                headers.update(extra_headers)

            try:
                if method.upper() == "GET":
                    response = await client.get(url, headers=headers, params=params)
                elif method.upper() == "POST":
                    response = await client.post(
                        url, headers=headers, params=params, json=json_data
                    )
                elif method.upper() == "PUT":
                    response = await client.put(url, headers=headers, params=params, json=json_data)
                elif method.upper() == "PATCH":
                    response = await client.patch(
                        url, headers=headers, params=params, json=json_data
                    )
                elif method.upper() == "DELETE":
                    response = await client.delete(url, headers=headers, params=params)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")

                # Success
                if response.status_code < 400:
                    return response.json() if response.content else {}

                # Rate limited - retry with hook-based delay
                if response.status_code == 429:
                    wait_time = self._get_retry_delay(response, attempt)
                    logger.warning(
                        "api_rate_limited_retrying",
                        user_id=str(self.user_id),
                        connector_type=connector_type_value,
                        attempt=attempt + 1,
                        wait_time=wait_time,
                    )
                    await asyncio.sleep(wait_time)
                    continue

                # Server error - retry with backoff
                if response.status_code >= 500:
                    wait_time = self._get_retry_delay(response, attempt)
                    logger.warning(
                        "api_server_error_retrying",
                        user_id=str(self.user_id),
                        connector_type=connector_type_value,
                        status_code=response.status_code,
                        attempt=attempt + 1,
                        wait_time=wait_time,
                    )
                    await asyncio.sleep(wait_time)
                    continue

                # OAuth error (401) - invalidate connector and require reconnection
                if response.status_code == 401:
                    error_detail = self._parse_error_detail(response)
                    logger.error(
                        "oauth_authentication_failed",
                        user_id=str(self.user_id),
                        connector_type=connector_type_value,
                        status_code=response.status_code,
                        error=error_detail,
                        action="connector_invalidation_required",
                    )
                    await self._invalidate_connector_on_auth_failure(error_detail)
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail=(
                            f"Authentification {connector_type_value} invalide. "
                            f"Veuillez réactiver le connecteur dans les paramètres."
                        ),
                        headers={"X-Requires-Reconnect": "true"},
                    )

                # Other client errors - don't retry (use hook for error parsing)
                error_detail = self._parse_error_detail(response)
                logger.error(
                    "api_client_error",
                    user_id=str(self.user_id),
                    connector_type=connector_type_value,
                    status_code=response.status_code,
                    error=error_detail,
                )
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"{connector_type_value} API error: {error_detail}",
                )

            except httpx.RequestError as e:
                if attempt < max_retries - 1:
                    wait_time = self._calculate_backoff(attempt)
                    logger.warning(
                        "api_request_error_retrying",
                        user_id=str(self.user_id),
                        connector_type=connector_type_value,
                        error=str(e),
                        attempt=attempt + 1,
                        wait_time=wait_time,
                    )
                    await asyncio.sleep(wait_time)
                    continue
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=f"{connector_type_value} API unavailable: {e!s}",
                ) from e

        # Max retries exceeded
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"{connector_type_value} API: max retries exceeded",
        )

    # =========================================================================
    # CONNECTOR INVALIDATION (on auth failure)
    # =========================================================================

    async def _invalidate_connector_on_auth_failure(self, error_detail: str | None = None) -> None:
        """
        Invalidate connector in database after OAuth authentication failure.

        Called when a 401 Unauthorized response is received from the API.
        The connector is marked as ERROR status to prevent further API calls
        and prompt the user to reconnect.

        Args:
            error_detail: Optional error message from the API response.
        """
        connector_type_value = (
            self.connector_type.value
            if hasattr(self.connector_type, "value")
            else str(self.connector_type)
        )

        try:
            from src.domains.connectors.models import ConnectorStatus
            from src.domains.connectors.repository import ConnectorRepository

            async with self.connector_service.db as db:
                repo = ConnectorRepository(db)
                connector = await repo.get_by_user_and_type(self.user_id, self.connector_type)

                if connector:
                    connector.status = ConnectorStatus.ERROR

                    error_info = {
                        "last_error": (
                            error_detail[:500] if error_detail else "OAuth authentication failed"
                        ),
                        "error_at": datetime.now(UTC).isoformat(),
                        "error_type": "oauth_authentication_failed",
                    }
                    if connector.connector_metadata:
                        connector.connector_metadata.update(error_info)
                    else:
                        connector.connector_metadata = error_info

                    await db.flush()
                    await db.commit()

                    logger.warning(
                        "connector_invalidated_auth_failure",
                        user_id=str(self.user_id),
                        connector_id=str(connector.id),
                        connector_type=connector_type_value,
                        error_detail=error_detail[:200] if error_detail else None,
                    )

                    await self.connector_service._invalidate_user_connectors_cache(self.user_id)
                else:
                    logger.warning(
                        "connector_not_found_for_invalidation",
                        user_id=str(self.user_id),
                        connector_type=connector_type_value,
                    )

        except Exception as e:
            logger.error(
                "connector_invalidation_failed",
                user_id=str(self.user_id),
                connector_type=connector_type_value,
                error=str(e),
                error_type=type(e).__name__,
            )
