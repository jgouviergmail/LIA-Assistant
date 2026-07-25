"""
Rate limiting configuration utilities.

Historically this module also formatted SlowAPI limit strings
(``"60/minute"``) and built English 429 payloads for a ``slowapi.Limiter``
that was never on the request path. SEC-016 replaced that limiter with
``RateLimitMiddleware`` (``core/middleware.py``), which is Redis-backed and
actually enforced, so those helpers were deleted rather than kept as
test-covered dead code.

What remains is the single feature switch every HTTP limiter reads.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.config import Settings


def rate_limiting_enabled(settings: Settings) -> bool:
    """
    Check if HTTP rate limiting is enabled globally.

    Args:
        settings: Application settings instance

    Returns:
        True if rate limiting should be enforced, False otherwise

    Example:
        >>> settings = Settings(rate_limit_enabled=True)
        >>> rate_limiting_enabled(settings)
        True
    """
    return settings.rate_limit_enabled
