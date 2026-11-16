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

from fastapi import Depends, Request

from src.core.constants import (
    RATE_LIMIT_AUTH_LOGIN_PER_MINUTE,
    RATE_LIMIT_AUTH_REGISTER_PER_MINUTE,
    RATE_LIMIT_NATIVE_CALLBACK_PER_MINUTE,
)
from src.domains.auth.turnstile_gate import TurnstileAction, require_turnstile
from src.infrastructure.rate_limiting.ip_limiter import create_ip_rate_limiter

# The per-account limiter lives beside the per-IP one (ADR-391); its existing callers
# still import it from here.
from src.infrastructure.rate_limiting.user_limiter import (
    create_user_rate_limiter as create_user_rate_limiter,
)


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
