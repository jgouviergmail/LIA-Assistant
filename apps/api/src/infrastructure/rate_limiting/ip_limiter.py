"""
Per-IP rate limit dependency for FastAPI endpoints.

This is the sliding-window throttle every anonymous endpoint shares. It lived in
``domains/auth/dependencies`` for as long as authentication was its only
caller — which is how four unrelated domains came to import their limiters from
the auth domain. It sits here now so a new caller does not have to.

The Redis key stays ``{namespace}:{action}:{ip}``, and auth keeps the ``auth``
namespace it has always written: a deployment upgrading mid-window keeps
counting instead of handing every caller a fresh budget.

Fail-open is deliberate: Redis being unreachable must not become an outage of
signing in.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import structlog
from fastapi import HTTPException, Request

from src.core.client_ip import resolve_client_ip
from src.core.exceptions import raise_rate_limit_exceeded
from src.infrastructure.rate_limiting.redis_limiter import get_rate_limiter

logger = structlog.get_logger(__name__)


def create_ip_rate_limiter(
    *,
    namespace: str,
    action: str,
    max_calls: int,
    window_seconds: int = 60,
) -> Callable[[Request], Awaitable[None]]:
    """
    Build a FastAPI dependency throttling an endpoint per client IP.

    Args:
        namespace: First key segment, scoping the counter to a subsystem
            (``auth``, ``push_relay``…).
        action: Second key segment, naming the endpoint.
        max_calls: Calls allowed inside the window.
        window_seconds: Width of the sliding window, in seconds.

    Returns:
        An async dependency raising ``RateLimitError`` (429) past the window,
        and returning ``None`` when the limiter itself is unavailable.

    Example:
        >>> rate_limit_login = create_ip_rate_limiter(
        ...     namespace="auth", action="login", max_calls=10
        ... )
        >>> @router.post("/login")
        >>> async def login(..., _: None = Depends(rate_limit_login)):
        ...     ...
    """

    async def rate_limit_dependency(request: Request) -> None:
        """Check the window; raise 429 when it is exceeded."""
        try:
            limiter = await get_rate_limiter()
            client_ip = resolve_client_ip(request)

            allowed = await limiter.acquire(
                key=f"{namespace}:{action}:{client_ip}",
                max_calls=max_calls,
                window_seconds=window_seconds,
            )

            if not allowed:
                logger.warning(
                    "ip_rate_limit_exceeded",
                    namespace=namespace,
                    action=action,
                    client_ip=client_ip,
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
            # The typed 429 above — it must escape, not be absorbed by the
            # fail-open arm that exists for infrastructure failures.
            raise
        except Exception as e:
            logger.error(
                "ip_rate_limit_check_failed",
                namespace=namespace,
                action=action,
                error=str(e),
            )

    return rate_limit_dependency
