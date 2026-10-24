"""
Authentication rate limiting dependencies, and the password doors.

The doors (``login_guard``, ``register_guard``, ``password_reset_request_guard``)
compose a per-IP limiter with the Turnstile bot check (ADR-364).

This module provides rate limiting for authentication endpoints to prevent:
- Brute force attacks on login
- Spam account creation
- Email enumeration via password reset
- Token brute force attacks

Uses the existing RedisRateLimiter with sliding window algorithm.
"""

from collections.abc import Awaitable, Callable

import structlog
from fastapi import Depends, HTTPException, Request

from src.core.constants import (
    RATE_LIMIT_AUTH_LOGIN_PER_MINUTE,
    RATE_LIMIT_AUTH_REGISTER_PER_MINUTE,
    RATE_LIMIT_NATIVE_CALLBACK_PER_MINUTE,
)
from src.core.exceptions import raise_rate_limit_exceeded
from src.core.session_dependencies import get_current_active_session
from src.domains.auth.turnstile_gate import TurnstileAction, require_turnstile
from src.domains.users.models import User
from src.infrastructure.rate_limiting.ip_limiter import create_ip_rate_limiter
from src.infrastructure.rate_limiting.redis_limiter import get_rate_limiter

logger = structlog.get_logger(__name__)


def create_auth_rate_limiter(
    action: str,
    max_calls: int,
    window_seconds: int = 60,
) -> Callable[[Request], Awaitable[None]]:
    """
    Factory function to create rate limit dependencies for auth endpoints.

    Thin wrapper over the shared per-IP limiter, kept because five modules
    import the pre-configured dependencies below by name. The ``auth``
    namespace is what pins the Redis keys this has always written.

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
    return create_ip_rate_limiter(
        namespace="auth",
        action=action,
        max_calls=max_calls,
        window_seconds=window_seconds,
    )


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

rate_limit_native_callback = create_auth_rate_limiter(
    action="native_callback",
    max_calls=RATE_LIMIT_NATIVE_CALLBACK_PER_MINUTE,
)

rate_limit_password_reset_request = create_auth_rate_limiter(
    action="password_reset_request",
    max_calls=3,  # Stricter limit for email enumeration protection
)

rate_limit_password_reset = create_auth_rate_limiter(
    action="password_reset",
    max_calls=5,  # Token brute force protection
)

# The Turnstile bot check of each password door (ADR-364), and the door itself:
# the per-IP limiter first — a flood is refused locally before it costs a call
# to Cloudflare — then the check. FastAPI resolves them in this order.
turnstile_login = require_turnstile(TurnstileAction.LOGIN)
turnstile_register = require_turnstile(TurnstileAction.REGISTER)
turnstile_password_reset = require_turnstile(TurnstileAction.PASSWORD_RESET)


async def login_guard(
    _rate_limit: None = Depends(rate_limit_login),
    _bot_check: None = Depends(turnstile_login),
) -> None:
    """The password sign-in door: per-IP limiter, then the bot check."""


async def register_guard(
    _rate_limit: None = Depends(rate_limit_register),
    _bot_check: None = Depends(turnstile_register),
) -> None:
    """The sign-up door: per-IP limiter, then the bot check."""


async def password_reset_request_guard(
    _rate_limit: None = Depends(rate_limit_password_reset_request),
    _bot_check: None = Depends(turnstile_password_reset),
) -> None:
    """The reset-request door: per-IP limiter, then the bot check."""


def create_user_rate_limiter(
    action: str,
    max_calls: int,
    window_seconds: int = 60,
    *,
    authenticate: Callable[..., Awaitable[User]] = get_current_active_session,
) -> Callable[[User], Awaitable[None]]:
    """Factory for per-USER rate limit dependencies on authenticated endpoints.

    Unlike ``create_auth_rate_limiter`` (per-IP, anonymous endpoints), the
    sliding window is keyed on the authenticated user id — several devices
    behind one IP share nothing, and an attacker cannot rotate IPs to reset
    the budget of a targeted account (security program D1).

    Args:
        action: Action name for the rate limit key (e.g., "webauthn_enroll").
        max_calls: Maximum number of calls allowed in the window.
        window_seconds: Time window in seconds (default: 60).
        authenticate: The door the account is read through — the route's own,
            so a route that waits on the network (and authenticates on a session
            of its own, ADR-304) is limited without pinning a request session.

    Returns:
        Async dependency function for FastAPI (fail-open like the IP variant).
    """

    async def rate_limit_dependency(
        user: User = Depends(authenticate),
    ) -> None:
        """Per-user rate limit check; raises 429 when the window is exceeded."""
        try:
            limiter = await get_rate_limiter()
            key = f"auth:{action}:user:{user.id}"

            allowed = await limiter.acquire(
                key=key,
                max_calls=max_calls,
                window_seconds=window_seconds,
            )

            if not allowed:
                logger.warning(
                    "auth_user_rate_limit_exceeded",
                    action=action,
                    user_id=str(user.id),
                    max_calls=max_calls,
                    window_seconds=window_seconds,
                )
                raise_rate_limit_exceeded(
                    limit=max_calls,
                    window_seconds=window_seconds,
                    retry_after=window_seconds,
                    detail={
                        "error": "rate_limit_exceeded",
                        "message": f"Too many {action} attempts. Please try again later.",
                        "retry_after_seconds": window_seconds,
                    },
                    headers={"Retry-After": str(window_seconds)},
                )

        except HTTPException:
            raise
        except Exception as e:
            # Fail-open policy, matching create_auth_rate_limiter.
            logger.error(
                "auth_user_rate_limit_check_failed",
                action=action,
                error=str(e),
            )

    return rate_limit_dependency
