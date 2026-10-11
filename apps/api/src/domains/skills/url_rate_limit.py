"""Original shared per-account URL import limiter, reused by UI and native tools."""

from fastapi import Depends, HTTPException

from src.core.config import settings
from src.core.session_dependencies import get_current_active_session
from src.domains.users.models import User
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


async def rate_limit_url_import(
    user: User = Depends(get_current_active_session),
) -> None:
    """Per-user sliding-window limit on outbound skill fetches.

    Failed imports consume no skill quota, so without this an authenticated
    user could hammer arbitrary https hosts through the API. Same Redis
    limiter and fail-open policy as the auth dependencies
    (``domains/auth/dependencies.py``).

    Raises:
        RateLimitError: 429 when the window is exhausted.
    """
    from src.core.exceptions import raise_rate_limit_exceeded
    from src.infrastructure.rate_limiting.redis_limiter import get_rate_limiter

    max_calls = settings.skills_url_import_rate_max_calls
    window_seconds = settings.skills_url_import_rate_window_seconds
    try:
        limiter = await get_rate_limiter()
        allowed = await limiter.acquire(
            key=f"skills:url_import:{user.id}",
            max_calls=max_calls,
            window_seconds=window_seconds,
        )
        if not allowed:
            logger.warning(
                "skill_url_import_rate_limited",
                user_id=str(user.id),
                max_calls=max_calls,
                window_seconds=window_seconds,
            )
            raise_rate_limit_exceeded(
                limit=max_calls,
                window_seconds=window_seconds,
                retry_after=window_seconds,
                headers={"Retry-After": str(window_seconds)},
            )
    except HTTPException:
        raise
    except Exception as exc:
        # Fail-open policy — matches RedisRateLimiter's own behavior: a
        # Redis outage must not take the import feature down with it.
        logger.error("skill_url_import_rate_check_failed", error=str(exc))
