"""
Rate limiting infrastructure.

Provides distributed rate limiting using Redis for horizontal scaling.

Phase: PHASE 2.4 - Rate Limiting Distribué Redis
Created: 2025-11-20
"""

from .redis_limiter import RedisRateLimiter

__all__ = ["RedisRateLimiter"]
