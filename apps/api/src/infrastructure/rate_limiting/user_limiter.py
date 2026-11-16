"""
Per-account rate limit dependency for authenticated FastAPI endpoints.

The sibling of ``ip_limiter``, and it moved for the same reason: it lived in
``domains/auth/dependencies`` while every caller was a domain of its own, so a
domain the auth domain imports (``notifications``: the sign-in alert) could not
be limited without an import cycle (ADR-391). It sits here now so a new caller
does not have to import the auth domain; ``domains/auth/dependencies`` still
exposes it to its existing callers.

The Redis key stays ``auth:{action}:user:{user_id}`` and the log events keep
their names: a deployment upgrading mid-window keeps counting.

Fail-open is deliberate, as for the IP variant: Redis being unreachable must
not become an outage of the endpoints it protects.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import structlog
from fastapi import Depends, HTTPException

from src.core.exceptions import raise_rate_limit_exceeded
from src.core.session_dependencies import get_current_active_session
from src.domains.users.models import User
from src.infrastructure.rate_limiting.redis_limiter import get_rate_limiter

logger = structlog.get_logger(__name__)


def create_user_rate_limiter(
    action: str,
    max_calls: int,
    window_seconds: int = 60,
    *,
    authenticate: Callable[..., Awaitable[User]] = get_current_active_session,
) -> Callable[[User], Awaitable[None]]:
    """Factory for per-USER rate limit dependencies on authenticated endpoints.

    Unlike ``create_ip_rate_limiter`` (per-IP, anonymous endpoints), the
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
            # Fail-open policy, matching the IP variant.
            logger.error(
                "auth_user_rate_limit_check_failed",
                action=action,
                error=str(e),
            )

    return rate_limit_dependency


__all__ = ["create_user_rate_limiter"]
