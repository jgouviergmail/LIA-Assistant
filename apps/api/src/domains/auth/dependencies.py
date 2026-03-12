"""
Authentication rate limiting dependencies.

This module provides rate limiting for authentication endpoints to prevent:
- Brute force attacks on login
- Spam account creation
- Email enumeration via password reset
- Token brute force attacks

Uses the existing RedisRateLimiter with sliding window algorithm.
"""

from collections.abc import Awaitable, Callable

import structlog
from fastapi import HTTPException, Request, status

from src.core.constants import (
    RATE_LIMIT_AUTH_LOGIN_PER_MINUTE,
    RATE_LIMIT_AUTH_REGISTER_PER_MINUTE,
)
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.rate_limiting.redis_limiter import RedisRateLimiter

logger = structlog.get_logger(__name__)


def _get_client_ip(request: Request) -> str:
    """
    Extract client IP from request, handling proxies.

    Checks X-Forwarded-For header first (for reverse proxy setups),
    falls back to direct client IP.

    Args:
        request: FastAPI request object

    Returns:
        Client IP address string
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # X-Forwarded-For can contain multiple IPs, take the first (original client)
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def create_auth_rate_limiter(
    action: str,
    max_calls: int,
    window_seconds: int = 60,
) -> Callable[[Request], Awaitable[None]]:
    """
    Factory function to create rate limit dependencies for auth endpoints.

    Creates a FastAPI dependency that checks rate limits using Redis sliding window.

    Args:
        action: Action name for the rate limit key (e.g., "login", "register")
        max_calls: Maximum number of calls allowed in the window
        window_seconds: Time window in seconds (default: 60)

    Returns:
        Async dependency function for FastAPI

    Example:
        >>> rate_limit_login = create_auth_rate_limiter("login", max_calls=10)
        >>> @router.post("/login")
        >>> async def login(..., _: None = Depends(rate_limit_login)):
        >>>     ...
    """

    async def rate_limit_dependency(request: Request) -> None:
        """
        Rate limit dependency that checks Redis and raises 429 if exceeded.

        Raises:
            HTTPException: 429 Too Many Requests if rate limit exceeded
        """
        try:
            redis = await get_redis_cache()
            limiter = RedisRateLimiter(redis)
            client_ip = _get_client_ip(request)
            key = f"auth:{action}:{client_ip}"

            allowed = await limiter.acquire(
                key=key,
                max_calls=max_calls,
                window_seconds=window_seconds,
            )

            if not allowed:
                logger.warning(
                    "auth_rate_limit_exceeded",
                    action=action,
                    client_ip=client_ip,
                    max_calls=max_calls,
                    window_seconds=window_seconds,
                )
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={
                        "error": "rate_limit_exceeded",
                        "message": f"Too many {action} attempts. Please try again later.",
                        "retry_after_seconds": window_seconds,
                    },
                    headers={"Retry-After": str(window_seconds)},
                )

        except HTTPException:
            # Re-raise HTTP exceptions (rate limit exceeded)
            raise
        except Exception as e:
            # Log error but allow request to proceed (fail-open policy)
            # This matches RedisRateLimiter's existing fail-open behavior
            logger.error(
                "auth_rate_limit_check_failed",
                action=action,
                error=str(e),
            )

    return rate_limit_dependency


# Pre-configured dependencies for each auth endpoint
# These use constants from src.core.constants for consistency

rate_limit_login = create_auth_rate_limiter(
    action="login",
    max_calls=RATE_LIMIT_AUTH_LOGIN_PER_MINUTE,  # 10/min
)

rate_limit_register = create_auth_rate_limiter(
    action="register",
    max_calls=RATE_LIMIT_AUTH_REGISTER_PER_MINUTE,  # 5/min
)

rate_limit_password_reset_request = create_auth_rate_limiter(
    action="password_reset_request",
    max_calls=3,  # Stricter limit for email enumeration protection
)

rate_limit_password_reset = create_auth_rate_limiter(
    action="password_reset",
    max_calls=5,  # Token brute force protection
)

rate_limit_forgot_password = create_auth_rate_limiter(
    action="forgot_password",
    max_calls=3,  # Same as password_reset_request
)
