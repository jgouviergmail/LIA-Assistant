"""
Base API Key client with common functionality.

Provides shared functionality for all API Key-based clients:
- API key authentication (header or query parameter)
- Rate limiting (Redis + local fallback for horizontal scaling)
- HTTP client with connection pooling
- Retry logic with exponential backoff
- Key validation and masking for logs
- Circuit breaker pattern for fault tolerance (Sprint 16.1)

Unlike OAuth clients (BaseGoogleClient), API Key clients:
- Don't require token refresh
- Have simpler authentication flow
- May have static or user-managed keys

Subclasses must implement:
- connector_type: ConnectorType for this client
- api_base_url: Base URL for the API
- auth_header_name: Header name for API key (default: "Authorization")
- auth_header_prefix: Header value prefix (default: "Bearer")

Sprint 16.2 - Added Redis rate limiting for horizontal scaling consistency.
"""

import asyncio
import time
from abc import ABC
from typing import Any
from uuid import UUID

import httpx
import structlog
from fastapi import HTTPException, status

from src.core.config import settings
from src.core.constants import DEFAULT_RATE_LIMIT_PER_SECOND, HTTP_TIMEOUT_CONNECTOR_LONG
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.schemas import APIKeyCredentials
from src.infrastructure.cache.redis import get_redis_session
from src.infrastructure.rate_limiting import RedisRateLimiter
from src.infrastructure.resilience import CircuitBreaker, CircuitBreakerError, get_circuit_breaker

logger = structlog.get_logger(__name__)


class BaseAPIKeyClient(ABC):
    """
    Abstract base class for API Key-based clients.

    Provides common functionality for all API Key-based external service clients:
    - Rate limiting
    - HTTP connection pooling
    - Retry logic with exponential backoff
    - Consistent error handling
    - Secure key handling (never logs full keys)

    Subclasses must define:
    - connector_type: ConnectorType enum value
    - api_base_url: Base URL for the API

    Optional overrides:
    - auth_header_name: Header name for API key (default: "Authorization")
    - auth_header_prefix: Header value prefix (default: "Bearer")
    - auth_method: "header" or "query" (default: "header")

    Example:
        class OpenAIClient(BaseAPIKeyClient):
            connector_type = ConnectorType.OPENAI
            api_base_url = "https://api.openai.com/v1"
            auth_header_name = "Authorization"
            auth_header_prefix = "Bearer"
    """

    # Required class attributes (must be defined by subclasses)
    connector_type: ConnectorType
    api_base_url: str

    # Optional class attributes with defaults
    auth_header_name: str = "Authorization"
    auth_header_prefix: str = "Bearer"
    auth_method: str = "header"  # "header" or "query"
    auth_query_param: str = "api_key"  # Used if auth_method == "query"

    def __init__(
        self,
        user_id: UUID,
        credentials: "APIKeyCredentials",
        rate_limit_per_second: int = DEFAULT_RATE_LIMIT_PER_SECOND,
    ) -> None:
        """
        Initialize API Key client.

        Args:
            user_id: User ID for logging and tracking.
            credentials: API key credentials (decrypted).
            rate_limit_per_second: Maximum requests per second (default: 10).
        """
        self.user_id = user_id
        self.credentials = credentials
        self._rate_limit_per_second = rate_limit_per_second
        self._rate_limit_interval = 1.0 / rate_limit_per_second
        self._last_request_time = 0.0
        self._http_client: httpx.AsyncClient | None = None
        self._circuit_breaker: CircuitBreaker | None = None
        self._redis_rate_limiter: RedisRateLimiter | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """
        Get or create reusable HTTP client with connection pooling.

        Returns:
            Configured httpx.AsyncClient instance.
        """
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=HTTP_TIMEOUT_CONNECTOR_LONG,
                limits=httpx.Limits(
                    max_keepalive_connections=20,
                    max_connections=100,
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
    # CIRCUIT BREAKER (Sprint 16.1 - Fault Tolerance)
    # =========================================================================

    def _get_circuit_breaker_service_name(self) -> str:
        """
        Get the circuit breaker service name for this client.

        Returns:
            Service name for circuit breaker identification
        """
        return f"apikey_{self.connector_type.value}"

    def _is_circuit_breaker_enabled(self) -> bool:
        """
        Check if circuit breaker is enabled for this client type.

        Returns:
            True if circuit breaker should be used
        """
        # NOTE: Circuit breaker is always enabled
        return True

    def _get_circuit_breaker(self) -> CircuitBreaker:
        """
        Get or create circuit breaker for this client.

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

        Returns:
            Rate limit key string (e.g., "apikey:user:{user_id}:{connector_type}")
        """
        return f"apikey:user:{self.user_id}:{self.connector_type.value}"

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

            # Max retries exceeded
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

        Raises HTTPException with 429 status code.
        """
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded for {self.connector_type.value}. Please try again later.",
        )

    def _build_auth_headers(self) -> dict[str, str]:
        """
        Build authentication headers for API requests.

        Returns:
            Dictionary of headers to include in requests.
        """
        headers: dict[str, str] = {}

        if self.auth_method == "header":
            if self.auth_header_prefix:
                headers[self.auth_header_name] = (
                    f"{self.auth_header_prefix} {self.credentials.api_key}"
                )
            else:
                headers[self.auth_header_name] = self.credentials.api_key

        return headers

    def _build_auth_params(self) -> dict[str, str]:
        """
        Build authentication query parameters for API requests.

        Returns:
            Dictionary of query params to include in requests.
        """
        if self.auth_method == "query":
            return {self.auth_query_param: self.credentials.api_key}
        return {}

    def _mask_api_key(self, key: str) -> str:
        """
        Mask API key for safe logging.

        Shows first 4 and last 4 characters only.

        Args:
            key: Full API key.

        Returns:
            Masked key (e.g., "sk-a...xyz").
        """
        if len(key) <= 8:
            return "***"
        return f"{key[:4]}...{key[-4:]}"

    async def validate_api_key(self) -> bool:
        """
        Validate that the API key is functional.

        Override this method in subclasses to implement service-specific validation.
        Default implementation just checks the key is not empty.

        Returns:
            True if key is valid, False otherwise.
        """
        return bool(self.credentials.api_key and len(self.credentials.api_key) >= 8)

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        max_retries: int = 3,
    ) -> dict[str, Any]:
        """
        Make HTTP request with API key authentication and retry logic.

        Includes circuit breaker protection to prevent cascade failures when
        the external service is unavailable.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE, PATCH).
            endpoint: API endpoint (appended to api_base_url).
            params: Query parameters.
            json_data: JSON body data.
            max_retries: Maximum number of retry attempts.

        Returns:
            Parsed JSON response.

        Raises:
            HTTPException: On API errors after retries exhausted, or if circuit breaker is open.
        """
        # Check circuit breaker first (fail fast if service is down)
        if self._is_circuit_breaker_enabled():
            cb = self._get_circuit_breaker()
            try:
                async with cb._lock:
                    if not await cb._should_allow_request():
                        await cb._reject_request()
            except CircuitBreakerError as e:
                logger.warning(
                    "circuit_breaker_rejected_request",
                    service=e.service,
                    state=e.state.value,
                    connector_type=self.connector_type.value,
                    user_id=str(self.user_id),
                    retry_after=e.retry_after,
                )
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=f"{self.connector_type.value} service temporarily unavailable. Please try again later.",
                    headers={"Retry-After": str(int(e.retry_after))} if e.retry_after else None,
                ) from e

        # Apply rate limiting
        await self._rate_limit()

        # Build URL and auth
        url = f"{self.api_base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        headers = self._build_auth_headers()
        auth_params = self._build_auth_params()

        # Merge auth params with provided params
        if params:
            params = {**params, **auth_params}
        else:
            params = auth_params if auth_params else None

        client = await self._get_client()

        for attempt in range(max_retries):
            try:
                # Make request based on method
                if method.upper() == "GET":
                    response = await client.get(url, params=params, headers=headers)
                elif method.upper() == "POST":
                    response = await client.post(
                        url, params=params, headers=headers, json=json_data
                    )
                elif method.upper() == "PUT":
                    response = await client.put(url, params=params, headers=headers, json=json_data)
                elif method.upper() == "DELETE":
                    response = await client.delete(url, params=params, headers=headers)
                elif method.upper() == "PATCH":
                    response = await client.patch(
                        url, params=params, headers=headers, json=json_data
                    )
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")

                # Handle rate limit (429) - record failure for circuit breaker
                if response.status_code == 429:
                    if self._is_circuit_breaker_enabled():
                        await self._get_circuit_breaker().record_failure(
                            Exception("Rate limited: HTTP 429")
                        )
                    wait_time = int(response.headers.get("Retry-After", 2**attempt))
                    logger.warning(
                        "api_rate_limited_retrying",
                        user_id=str(self.user_id),
                        connector_type=self.connector_type.value,
                        attempt=attempt + 1,
                        wait_time=wait_time,
                    )
                    await asyncio.sleep(wait_time)
                    continue

                # Handle server errors (5xx) - retry and record failure for circuit breaker
                if response.status_code >= 500:
                    if self._is_circuit_breaker_enabled():
                        await self._get_circuit_breaker().record_failure(
                            Exception(f"Server error: HTTP {response.status_code}")
                        )
                    wait_time = 2**attempt
                    logger.warning(
                        "api_server_error_retrying",
                        user_id=str(self.user_id),
                        connector_type=self.connector_type.value,
                        status_code=response.status_code,
                        attempt=attempt + 1,
                        wait_time=wait_time,
                    )
                    await asyncio.sleep(wait_time)
                    continue

                # Handle authentication errors (401, 403) - no retry, record success (valid response)
                if response.status_code in (401, 403):
                    # Auth errors are valid API responses, not service failures
                    if self._is_circuit_breaker_enabled():
                        await self._get_circuit_breaker().record_success()
                    logger.error(
                        "api_authentication_error",
                        user_id=str(self.user_id),
                        connector_type=self.connector_type.value,
                        status_code=response.status_code,
                        masked_key=self._mask_api_key(self.credentials.api_key),
                    )
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail=f"{self.connector_type.value}: Invalid or expired API key",
                    )

                # Handle other client errors (4xx) - no retry, record success (valid response)
                if response.status_code >= 400:
                    # Client errors are valid API responses, not service failures
                    if self._is_circuit_breaker_enabled():
                        await self._get_circuit_breaker().record_success()
                    error_detail = response.text[:200] if response.text else "Unknown error"
                    logger.error(
                        "api_client_error",
                        user_id=str(self.user_id),
                        connector_type=self.connector_type.value,
                        status_code=response.status_code,
                        error=error_detail,
                    )
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=f"{self.connector_type.value} API error: {error_detail}",
                    )

                # Success - record for circuit breaker and parse JSON response
                if self._is_circuit_breaker_enabled():
                    await self._get_circuit_breaker().record_success()
                if response.text:
                    result: dict[str, Any] = response.json()
                    return result
                return {}

            except httpx.RequestError as e:
                # Network errors should trip the circuit breaker
                if self._is_circuit_breaker_enabled():
                    await self._get_circuit_breaker().record_failure(e)
                wait_time = 2**attempt
                logger.warning(
                    "api_request_error_retrying",
                    user_id=str(self.user_id),
                    connector_type=self.connector_type.value,
                    error=str(e),
                    attempt=attempt + 1,
                    wait_time=wait_time,
                )
                if attempt == max_retries - 1:
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail=f"{self.connector_type.value} API unavailable: {e!s}",
                    ) from e
                await asyncio.sleep(wait_time)

        # Max retries exceeded
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"{self.connector_type.value} API: max retries exceeded",
        )
