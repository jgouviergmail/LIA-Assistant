"""
Base API Key client with common functionality.

Provides shared functionality for all API Key-based clients:
- API key authentication (header or query parameter)
- Rate limiting (Redis + local fallback for horizontal scaling)
- HTTP client with connection pooling
- Retry logic with exponential backoff
- Key validation and masking for logs
- Circuit breaker pattern for fault tolerance (Sprint 16.1)

A 429 is the provider ANSWERING about one account's key: it never counts against
the breaker every account shares, its retries are jittered, and once they are
spent it is handed back as a typed ``ConnectorAPIError`` carrying the delay
(ADR-108 amendment 2026-10-13).

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
import math
import random
import time
from abc import ABC
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

import httpx
import structlog

from src.core.config import settings
from src.core.constants import (
    API_KEY_CLIENT_RATE_LIMIT_ATTEMPTS,
    API_KEY_CLIENT_RETRY_AFTER_MAX_SECONDS,
    DEFAULT_RATE_LIMIT_PER_SECOND,
)
from src.core.exceptions import (
    ConnectorAPIError,
    ExternalServiceError,
    MaxRetriesExceededError,
    RateLimitError,
)
from src.core.read_budget import source_http_hooks
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.schemas import APIKeyCredentials
from src.infrastructure.rate_limiting import RedisRateLimiter, get_rate_limiter
from src.infrastructure.resilience import CircuitBreaker, CircuitBreakerError, get_circuit_breaker

logger = structlog.get_logger(__name__)

#: The verbs ``_make_request`` sends.
_HTTP_METHODS = frozenset({"GET", "POST", "PUT", "DELETE", "PATCH"})


def _retry_after_header(seconds: float | None) -> dict[str, str] | None:
    """A ``Retry-After`` header for a delay, rounded up to whole seconds.

    Args:
        seconds: The delay, or None when nobody named one.

    Returns:
        The header, or None.
    """
    return None if seconds is None else {"Retry-After": str(max(1, math.ceil(seconds)))}


def _rate_limit_delay(response: httpx.Response, attempt: int) -> float:
    """The delay a 429 asks for: its ``Retry-After``, else the exponential step.

    RFC 7231 allows ``Retry-After`` to be an HTTP-date; anything that is not
    delta-seconds falls back to the backoff schedule.

    Args:
        response: The 429 response.
        attempt: The attempt that drew it, 0-indexed.

    Returns:
        The delay in seconds, before any jitter.
    """
    header = response.headers.get("Retry-After")
    try:
        return float(int(header)) if header is not None else float(2**attempt)
    except ValueError:
        return float(2**attempt)


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
    follow_redirects: bool = False  # Some APIs (e.g. Brave) redirect on search

    def __init__(
        self,
        user_id: UUID | None,
        credentials: APIKeyCredentials,
        rate_limit_per_second: float = DEFAULT_RATE_LIMIT_PER_SECOND,
    ) -> None:
        """
        Initialize API Key client.

        Args:
            user_id: User ID for logging and rate-limit scoping. ``None`` is
                allowed for system-level callers (e.g. reverse geocoding);
                their requests share one anonymous rate-limit bucket.
            credentials: API key credentials (decrypted).
            rate_limit_per_second: Maximum requests per second (default: 10).
                Accepts fractional rates (e.g. 0.9 for free-tier APIs).
        """
        self.user_id = user_id
        self.credentials = credentials
        self._rate_limit_per_second = rate_limit_per_second
        self._rate_limit_interval = 1.0 / rate_limit_per_second
        self._last_request_time = 0.0
        self._http_client: httpx.AsyncClient | None = None
        self._circuit_breaker: CircuitBreaker | None = None
        self._redis_rate_limiter: RedisRateLimiter | None = None

    def _get_http_timeout(self) -> float:
        """
        HTTP timeout for this client (seconds).

        Override in subclasses whose API has a dedicated timeout setting
        (e.g. ``settings.http_timeout_brave_search``).

        Returns:
            Timeout in seconds (default: the long connector timeout).
        """
        return float(settings.http_timeout_connector_long)

    async def _get_client(self) -> httpx.AsyncClient:
        """
        Get or create reusable HTTP client with connection pooling.

        Returns:
            Configured httpx.AsyncClient instance.
        """
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                event_hooks=source_http_hooks(self.user_id),
                timeout=self._get_http_timeout(),
                follow_redirects=self.follow_redirects,
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
        """Get the shared Redis rate limiter (module-level singleton, cache DB)."""
        if self._redis_rate_limiter is None:
            self._redis_rate_limiter = await get_rate_limiter()
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

            # Convert per-second limit to per-minute for sliding window.
            # int() for the Redis limiter contract; max(1, ...) so fractional
            # rates (e.g. 0.01/s) never collapse to a zero-call window.
            max_calls = max(1, int(self._rate_limit_per_second * 60))
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
        Called when the client-side rate limit is exceeded after all retries.

        Raises:
            RateLimitError: 429 with the effective per-minute limit.
        """
        raise RateLimitError(
            limit=max(1, int(self._rate_limit_per_second * 60)),
            window_seconds=60,
            retry_after=60,
            connector_type=self.connector_type.value,
        )

    async def _check_circuit(self) -> None:
        """Refuse at once while the breaker of this connector type is open.

        Raises:
            ExternalServiceError: The circuit is open; its delay rides ``Retry-After``.
        """
        if not self._is_circuit_breaker_enabled():
            return
        try:
            await self._get_circuit_breaker().check()
        except CircuitBreakerError as e:
            logger.warning(
                "circuit_breaker_rejected_request",
                service=e.service,
                state=e.state.value,
                connector_type=self.connector_type.value,
                user_id=str(self.user_id),
                retry_after=e.retry_after,
            )
            raise ExternalServiceError(
                service_name=self.connector_type.value,
                detail=(
                    f"{self.connector_type.value} service temporarily unavailable"
                    " (circuit open). Please try again later."
                ),
                headers=_retry_after_header(e.retry_after),
                error_type="circuit_open",
                retry_after=e.retry_after,
            ) from e

    def _merged_params(self, params: dict[str, Any] | None) -> dict[str, Any] | None:
        """The call's query parameters, with the key's when the key travels there.

        Args:
            params: The caller's parameters.

        Returns:
            The merged parameters, or None when there are none at all.
        """
        auth_params = self._build_auth_params()
        if params:
            return {**params, **auth_params}
        return auth_params or None

    async def _breaker_success(self) -> None:
        """Record an answered call on the breaker — a refusal is an answer too."""
        if self._is_circuit_breaker_enabled():
            await self._get_circuit_breaker().record_success()

    async def _breaker_failure(self, error: Exception) -> None:
        """Record a call the service itself failed on the breaker."""
        if self._is_circuit_breaker_enabled():
            await self._get_circuit_breaker().record_failure(RuntimeError(type(error).__name__))

    async def _send_once(
        self,
        client: httpx.AsyncClient,
        verb: str,
        url: str,
        params: dict[str, Any] | None,
        headers: dict[str, str],
        json_data: dict[str, Any] | None,
    ) -> httpx.Response:
        """One HTTP exchange through the client's own verb.

        Args:
            client: The pooled client.
            verb: An upper-case member of ``_HTTP_METHODS``.
            url: The absolute URL.
            params: Query parameters, authentication included when it travels there.
            headers: Request headers, authentication included when it travels there.
            json_data: The JSON body of a POST, PUT or PATCH.

        Returns:
            The response, whatever its status.
        """
        if verb == "GET":
            return await client.get(url, params=params, headers=headers)
        if verb == "POST":
            return await client.post(url, params=params, headers=headers, json=json_data)
        if verb == "PUT":
            return await client.put(url, params=params, headers=headers, json=json_data)
        if verb == "DELETE":
            return await client.delete(url, params=params, headers=headers)
        return await client.patch(url, params=params, headers=headers, json=json_data)

    async def _send_through_rate_limits(
        self, send: Callable[[], Awaitable[httpx.Response]]
    ) -> httpx.Response:
        """Send, waiting out the 429s the provider answers on this account's key.

        A 429 is the provider ANSWERING: it limits this account's key and says
        nothing of the service's health. Counted as a failure it opened the
        breaker every account shares, which then refused the siblings of the same
        parallel round as « unavailable » (dev, 2026-10-13). It has a budget of its
        own (``API_KEY_CLIENT_RATE_LIMIT_ATTEMPTS``), its waits are jittered — never
        below what was asked, at most a second past it, because the siblings drew
        their 429 on the same tick — and a delay past
        ``API_KEY_CLIENT_RETRY_AFTER_MAX_SECONDS`` is handed back, not waited.

        Args:
            send: One exchange, sent again on every attempt.

        Returns:
            The first answer that is not a 429.

        Raises:
            ConnectorAPIError: The 429 handed back, its delay in ``Retry-After``.
        """
        attempt = 0
        while True:
            response = await send()
            if response.status_code != 429:
                return response
            await self._breaker_success()
            delay = _rate_limit_delay(response, attempt)
            attempt += 1
            if (
                attempt >= API_KEY_CLIENT_RATE_LIMIT_ATTEMPTS
                or delay > API_KEY_CLIENT_RETRY_AFTER_MAX_SECONDS
            ):
                raise self._rate_limited(delay, attempts=attempt)
            wait_time = delay + random.uniform(0.0, min(delay, 1.0))  # noqa: S311
            logger.warning(
                "api_rate_limited_retrying",
                user_id=str(self.user_id),
                connector_type=self.connector_type.value,
                attempt=attempt,
                wait_time=round(wait_time, 2),
            )
            await asyncio.sleep(wait_time)

    def _rate_limited(self, delay: float, *, attempts: int) -> ConnectorAPIError:
        """The refusal a spent 429 hands back: typed, with the delay it asked for.

        Args:
            delay: The provider's ``Retry-After``, else the next backoff step.
            attempts: The calls made, every one refused.

        Returns:
            A 429 ``ConnectorAPIError`` carrying the delay in ``Retry-After``.
        """
        logger.warning(
            "api_rate_limited_handed_back",
            user_id=str(self.user_id),
            connector_type=self.connector_type.value,
            attempts=attempts,
            retry_after_seconds=delay,
        )
        return ConnectorAPIError(
            connector_type=self.connector_type.value,
            status_code=429,
            detail=f"{self.connector_type.value} rate-limited this account's key",
            headers=_retry_after_header(delay),
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
            max_retries: Attempts against 5xx answers, malformed bodies and network
                errors; the backoff precedes a retry, never follows the last.

        Returns:
            Parsed JSON response.

        Raises:
            ExternalServiceError: If the circuit breaker is open, or on
                authentication errors (401/403 — invalid or expired API key).
            ConnectorAPIError: A 429 once its own attempts are spent
                (``API_KEY_CLIENT_RATE_LIMIT_ATTEMPTS``, apart from ``max_retries``),
                or whose ``Retry-After`` exceeds
                ``API_KEY_CLIENT_RETRY_AFTER_MAX_SECONDS``, with the delay in its
                ``Retry-After`` header.
            httpx.HTTPStatusError: On non-auth 4xx client errors.
            MaxRetriesExceededError: When retries are exhausted
                (5xx server errors, malformed bodies, or network errors).
            ValueError: On unsupported HTTP method.
        """
        operation = f"{self.connector_type.value} {method.upper()} {endpoint}"

        # Check circuit breaker first (fail fast if service is down)
        await self._check_circuit()

        # Apply rate limiting
        await self._rate_limit()

        # Build URL and auth
        url = f"{self.api_base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        headers = self._build_auth_headers()
        params = self._merged_params(params)

        client = await self._get_client()
        verb = method.upper()
        if verb not in _HTTP_METHODS:
            raise ValueError(f"Unsupported HTTP method: {method}")

        async def send() -> httpx.Response:
            return await self._send_once(client, verb, url, params, headers, json_data)

        last_error: Exception | None = None
        for attempt in range(max_retries):
            if attempt:
                # The backoff precedes a retry: nothing is slept after the last one.
                await asyncio.sleep(2 ** (attempt - 1))
            try:
                response = await self._send_through_rate_limits(send)
            except httpx.RequestError as e:
                # Network errors should trip the circuit breaker
                last_error = e
                await self._breaker_failure(e)
                logger.warning(
                    "api_request_error_retrying",
                    user_id=str(self.user_id),
                    connector_type=self.connector_type.value,
                    error_type=type(e).__name__,
                    attempt=attempt + 1,
                    max_retries=max_retries,
                )
                logger.debug("api_request_error_detail", error=str(e))
                continue

            # Handle server errors (5xx) - retry and record failure for circuit breaker
            if response.status_code >= 500:
                last_error = Exception(f"Server error: HTTP {response.status_code}")
                await self._breaker_failure(last_error)
                logger.warning(
                    "api_server_error_retrying",
                    user_id=str(self.user_id),
                    connector_type=self.connector_type.value,
                    status_code=response.status_code,
                    attempt=attempt + 1,
                    max_retries=max_retries,
                )
                continue

            # Handle authentication errors (401, 403) - no retry, record success (valid response)
            if response.status_code in (401, 403):
                # Auth errors are valid API responses, not service failures
                await self._breaker_success()
                logger.error(
                    "api_authentication_error",
                    user_id=str(self.user_id),
                    connector_type=self.connector_type.value,
                    status_code=response.status_code,
                    masked_key=self._mask_api_key(self.credentials.api_key),
                )
                raise ExternalServiceError(
                    service_name=self.connector_type.value,
                    detail=f"{self.connector_type.value}: Invalid or expired API key",
                    error_type="unauthorized",
                    http_status=response.status_code,
                )

            # Handle other client errors (4xx) - no retry, record success (valid response)
            if response.status_code >= 400:
                # Client errors are valid API responses, not service failures
                await self._breaker_success()
                logger.error(
                    "api_client_error",
                    user_id=str(self.user_id),
                    connector_type=self.connector_type.value,
                    status_code=response.status_code,
                )
                logger.debug("api_client_error_detail", text=response.text)
                raise httpx.HTTPStatusError(
                    f"{operation}: HTTP {response.status_code}",
                    request=response.request,
                    response=response,
                )

            # Success - parse BEFORE recording success: a malformed body on
            # a 200 is a service failure, retried like a transient error.
            if not response.text:
                await self._breaker_success()
                return {}
            try:
                result: dict[str, Any] = response.json()
            except ValueError as decode_err:  # json.JSONDecodeError
                last_error = decode_err
                await self._breaker_failure(decode_err)
                logger.warning(
                    "api_response_decode_error_retrying",
                    user_id=str(self.user_id),
                    connector_type=self.connector_type.value,
                    attempt=attempt + 1,
                    max_retries=max_retries,
                    error_type=type(decode_err).__name__,
                )
                logger.debug("api_response_decode_error_detail", error=str(decode_err))
                continue
            await self._breaker_success()
            return result

        # Max retries exceeded (5xx, malformed bodies or network errors on every attempt)
        raise MaxRetriesExceededError(
            operation=operation,
            max_retries=max_retries,
            last_error=last_error,
        ) from last_error
