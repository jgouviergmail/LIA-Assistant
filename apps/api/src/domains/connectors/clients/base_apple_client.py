"""
Base Apple iCloud API client with common functionality.

Provides shared infrastructure for all Apple iCloud clients (Email, Calendar, Contacts):
- Rate limiting (Redis-based, same pattern as BaseOAuthClient)
- Circuit breaker pattern for fault tolerance
- Retry logic with exponential backoff
- Credential revocation detection (marks connector as ERROR on auth failure)

Apple authentication uses Apple ID + app-specific password (NOT OAuth).
No token refresh — credentials are static until the Apple ID password changes.

Created: 2026-03-10
"""

import asyncio
from abc import ABC, abstractmethod
from typing import Any
from uuid import UUID

import structlog

from src.core.config import settings
from src.domains.connectors.models import ConnectorStatus, ConnectorType
from src.domains.connectors.schemas import AppleCredentials
from src.infrastructure.cache.redis import get_redis_session
from src.infrastructure.rate_limiting import RedisRateLimiter
from src.infrastructure.resilience import (
    CircuitBreaker,
    CircuitBreakerError,
    CircuitState,
    get_circuit_breaker,
)

logger = structlog.get_logger(__name__)

# Apple-specific authentication errors to detect revoked credentials
_IMAP_AUTH_ERRORS = ("LOGIN failed", "AUTHENTICATIONFAILED", "Invalid credentials")
_HTTP_AUTH_STATUS_CODES = (401, 403)


class AppleAuthenticationError(Exception):
    """Raised when Apple credentials are invalid or revoked."""

    def __init__(self, connector_type: ConnectorType, message: str) -> None:
        self.connector_type = connector_type
        super().__init__(f"Apple authentication failed for {connector_type.value}: {message}")


class BaseAppleClient(ABC):
    """
    Abstract base class for Apple iCloud API clients.

    Uses composition (not inheritance) for rate limiting and circuit breaker,
    following the same patterns as BaseOAuthClient but without OAuth token management.

    Subclasses must define:
    - connector_type: The specific Apple connector type
    """

    connector_type: ConnectorType

    def __init__(
        self,
        user_id: UUID,
        credentials: AppleCredentials,
        connector_service: Any,  # ConnectorService (avoid circular import)
    ) -> None:
        """
        Initialize Apple iCloud client.

        Args:
            user_id: User UUID.
            credentials: Apple credentials (apple_id, app_password).
            connector_service: Service for connector status updates.
        """
        self.user_id = user_id
        self.credentials = credentials
        self.connector_service = connector_service
        self._redis_rate_limiter: RedisRateLimiter | None = None
        self._circuit_breaker: CircuitBreaker | None = None

    # =========================================================================
    # CIRCUIT BREAKER
    # =========================================================================

    def _get_circuit_breaker(self) -> CircuitBreaker:
        """Get or create circuit breaker for this Apple client (lazy init)."""
        if self._circuit_breaker is None:
            # connector_type.value is already "apple_calendar" etc.
            self._circuit_breaker = get_circuit_breaker(self.connector_type.value)
        return self._circuit_breaker

    # =========================================================================
    # RATE LIMITING (Redis-based)
    # =========================================================================

    async def _get_redis_rate_limiter(self) -> RedisRateLimiter:
        """Get or create Redis rate limiter (lazy init)."""
        if self._redis_rate_limiter is None:
            redis = await get_redis_session()
            self._redis_rate_limiter = RedisRateLimiter(redis)
        return self._redis_rate_limiter

    def _get_rate_limit_key(self) -> str:
        """Get rate limit key for this client."""
        return f"apple_rate_limit:{self.connector_type.value}:{self.user_id}"

    async def _rate_limit(self) -> None:
        """Apply distributed rate limiting using Redis sliding window."""
        if not settings.rate_limit_enabled:
            return

        try:
            limiter = await self._get_redis_rate_limiter()
            rate_limit_key = self._get_rate_limit_key()
            max_calls = settings.client_rate_limit_apple_per_second * 60
            window_seconds = 60

            max_retries = 5
            for attempt in range(max_retries):
                allowed = await limiter.acquire(
                    key=rate_limit_key,
                    max_calls=max_calls,
                    window_seconds=window_seconds,
                )
                if allowed:
                    return

                wait_time = 1.0 * (attempt + 1)
                logger.warning(
                    "apple_rate_limit_exceeded_retrying",
                    user_id=str(self.user_id),
                    client_type=self.__class__.__name__,
                    attempt=attempt + 1,
                    wait_time_seconds=wait_time,
                )
                await asyncio.sleep(wait_time)

            logger.error(
                "apple_rate_limit_max_retries_exceeded",
                user_id=str(self.user_id),
                client_type=self.__class__.__name__,
            )
            raise RuntimeError(
                f"Rate limit exceeded for {self.connector_type.value} "
                f"after {max_retries} retries"
            )

        except RuntimeError:
            raise
        except Exception as e:
            logger.warning(
                "apple_rate_limit_fallback",
                user_id=str(self.user_id),
                error=str(e),
            )

    # =========================================================================
    # RETRY WITH EXPONENTIAL BACKOFF
    # =========================================================================

    async def _execute_with_retry(
        self,
        operation: str,
        func: Any,
        *args: Any,
        max_retries: int = 3,
        base_delay: float = 1.0,
        **kwargs: Any,
    ) -> Any:
        """
        Execute an operation with retry logic, rate limiting, and circuit breaker.

        Args:
            operation: Operation name for logging.
            func: Async callable to execute.
            *args: Positional arguments for func.
            max_retries: Maximum number of retry attempts.
            base_delay: Base delay in seconds for exponential backoff.
            **kwargs: Keyword arguments for func.

        Returns:
            Result from the function call.

        Raises:
            AppleAuthenticationError: If credentials are revoked.
            CircuitBreakerError: If circuit breaker is open.
        """
        await self._rate_limit()

        cb = self._get_circuit_breaker()
        last_error: Exception | None = None

        # Check circuit breaker BEFORE entering retry loop.
        # Use _should_allow_request() which handles OPEN→HALF_OPEN timeout transition,
        # not is_open which blocks recovery.
        if not await cb._should_allow_request():
            raise CircuitBreakerError(
                service=self.connector_type.value,
                state=CircuitState.OPEN,
            )

        for attempt in range(max_retries + 1):
            try:
                result = await func(*args, **kwargs)
                await cb.record_success()
                return result

            except AppleAuthenticationError:
                # Auth errors are not retryable — mark connector as ERROR
                await cb.record_failure()
                await self._handle_auth_failure()
                raise

            except Exception as e:
                last_error = e

                if attempt < max_retries:
                    delay = base_delay * (2**attempt)
                    logger.warning(
                        "apple_operation_retry",
                        operation=operation,
                        user_id=str(self.user_id),
                        client_type=self.__class__.__name__,
                        attempt=attempt + 1,
                        max_retries=max_retries,
                        delay_seconds=delay,
                        error=str(e),
                    )
                    await asyncio.sleep(delay)

        # Record ONE failure in circuit breaker after all retries exhausted
        await cb.record_failure()
        logger.error(
            "apple_operation_failed",
            operation=operation,
            user_id=str(self.user_id),
            client_type=self.__class__.__name__,
            error=str(last_error),
        )
        raise last_error  # type: ignore[misc]

    # =========================================================================
    # CREDENTIAL REVOCATION HANDLING
    # =========================================================================

    async def _handle_auth_failure(self) -> None:
        """Mark connector as ERROR when credentials are revoked."""
        logger.error(
            "apple_credentials_revoked",
            user_id=str(self.user_id),
            connector_type=self.connector_type.value,
        )
        try:
            from src.domains.connectors.repository import ConnectorRepository
            from src.infrastructure.database.session import get_db_context

            async with get_db_context() as db:
                repo = ConnectorRepository(db)
                connector = await repo.get_by_user_and_type(self.user_id, self.connector_type)
                if connector and connector.status != ConnectorStatus.ERROR:
                    await repo.update(connector, {"status": ConnectorStatus.ERROR})
                    await db.commit()
                    logger.info(
                        "apple_connector_marked_error",
                        user_id=str(self.user_id),
                        connector_type=self.connector_type.value,
                    )
        except Exception as e:
            logger.error(
                "apple_connector_status_update_failed",
                user_id=str(self.user_id),
                error=str(e),
            )

    def _check_imap_auth_error(self, error: Exception) -> None:
        """
        Check if an IMAP error indicates authentication failure.

        Raises:
            AppleAuthenticationError: If the error is an auth failure.
        """
        error_str = str(error)
        for pattern in _IMAP_AUTH_ERRORS:
            if pattern.lower() in error_str.lower():
                raise AppleAuthenticationError(
                    self.connector_type,
                    f"IMAP authentication failed: {error_str}",
                )

    def _check_http_auth_error(self, status_code: int) -> None:
        """
        Check if an HTTP status code indicates authentication failure.

        Raises:
            AppleAuthenticationError: If the status code is 401 or 403.
        """
        if status_code in _HTTP_AUTH_STATUS_CODES:
            raise AppleAuthenticationError(
                self.connector_type,
                f"HTTP {status_code}: authentication failed",
            )

    # =========================================================================
    # CLEANUP
    # =========================================================================

    @abstractmethod
    async def close(self) -> None:
        """Cleanup resources (connections, caches, etc.)."""
