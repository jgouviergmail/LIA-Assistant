"""Redis-owned rolling scan windows and fixed bans, shared by every API worker."""

import asyncio
from ipaddress import ip_address
from typing import Literal

import structlog

from src.core.config import settings
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.observability.metrics_http_scan import http_scan_degraded_total

logger = structlog.get_logger(__name__)
ScanReason = Literal["not_found", "credentials"]

# Redis time keeps workers on one clock. Path digests make stale-URL retries
# one member. At most `limit` members exist. An existing ban never slides.
_RECORD_SCRIPT = """
if redis.call('EXISTS', KEYS[2]) == 1 then return 0 end
local clock = redis.call('TIME')
local now = tonumber(clock[1]) + tonumber(clock[2]) / 1000000
local window = tonumber(ARGV[1])
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now - window)
redis.call('ZADD', KEYS[1], now, ARGV[4])
redis.call('EXPIRE', KEYS[1], window + 1)
if redis.call('ZCARD', KEYS[1]) < tonumber(ARGV[2]) then return 0 end
local created = redis.call('SET', KEYS[2], ARGV[5], 'NX', 'EX', ARGV[3])
redis.call('DEL', KEYS[1])
if created then return 1 end
return 0
"""


class RedisHTTPScanGuard:
    """Reuse the cache pool and bound every operation's wait; own no connections."""

    @staticmethod
    def _prefix(client_ip: str) -> str:
        return f"http:scan:{{{ip_address(client_ip).compressed}}}"

    async def remaining(self, client_ip: str) -> int:
        """Remaining seconds, zero when clear or temporarily unable to check."""
        try:
            async with asyncio.timeout(settings.http_scan_redis_timeout_seconds):
                redis = await get_redis_cache()
                milliseconds = await redis.pttl(f"{self._prefix(client_ip)}:ban")
                return max(0, (milliseconds + 999) // 1000)
        except Exception as exc:
            self._degraded("check", exc)
            return 0

    async def record(self, client_ip: str, reason: ScanReason, fingerprint: str) -> bool:
        """Record a qualified failure; true only to the atomic ban's creator."""
        if reason == "not_found":
            window, limit = settings.http_scan_window_seconds, settings.http_scan_not_found_limit
        else:
            window = settings.http_scan_auth_window_seconds
            limit = settings.http_scan_auth_failure_limit
        prefix = self._prefix(client_ip)
        try:
            async with asyncio.timeout(settings.http_scan_redis_timeout_seconds):
                redis = await get_redis_cache()
                result = await redis.eval(
                    _RECORD_SCRIPT,
                    2,
                    f"{prefix}:{reason}",
                    f"{prefix}:ban",
                    window,
                    limit,
                    settings.http_scan_ban_seconds,
                    fingerprint,
                    reason,
                )
                return bool(result)
        except Exception as exc:
            self._degraded("record", exc)
            return False

    @staticmethod
    def _degraded(operation: str, exc: Exception) -> None:
        http_scan_degraded_total.labels(operation=operation).inc()
        logger.warning("http_scan_check_failed", operation=operation, error_type=type(exc).__name__)
