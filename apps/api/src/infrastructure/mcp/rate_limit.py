"""Server-declared MCP cooldowns, shared across API workers.

An MCP tool can report quota exhaustion in an ordinary ``is_error`` result.
This is an expected refusal, not a transport crash. Honour its retry delay
before opening another connection, including when another worker handles it.
"""

from __future__ import annotations

import math
import re
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from uuid import UUID

import httpx2
import structlog
from redis.exceptions import RedisError

from src.infrastructure.cache.redis import get_redis_cache

logger = structlog.get_logger(__name__)

_QUOTA = re.compile(r"\b(?:rate limit exceeded|too many requests)\b", re.IGNORECASE)
_DELAY = re.compile(r"\bretry (?:after|in)\s+(\d+(?:\.\d+)?)\s*(?:s\b|seconds?\b)", re.IGNORECASE)
_EXTEND_COOLDOWN = """
local remaining = redis.call('PTTL', KEYS[1])
local delay = tonumber(ARGV[1])
if remaining < delay then
    redis.call('SET', KEYS[1], '1', 'PX', delay)
end
return math.max(remaining, delay)
"""


class MCPToolExecutionError(RuntimeError):
    """A server returned a failed tool result, rather than a broken transport."""


class MCPRateLimitError(MCPToolExecutionError):
    """A quota refusal with a retry delay; never retries automatically."""

    def __init__(self, retry_after: float) -> None:
        self.retry_after = max(1, math.ceil(retry_after))
        super().__init__(
            f"MCP server rate limit exceeded. Retry after {self.retry_after} seconds. "
            "Do not call this server's other methods before then; use another source "
            "or report the temporary limit."
        )


def _retry_delay(value: str, fallback: float) -> float:
    try:
        delay = float(value)
    except ValueError:
        try:
            deadline = parsedate_to_datetime(value)
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=UTC)
            delay = (deadline - datetime.now(UTC)).total_seconds()
        except ValueError, TypeError, OverflowError:
            return fallback
    # Redis's PX is an int64 number of milliseconds. Refuse malformed or
    # out-of-range server input rather than disabling the cooldown on write.
    return delay if math.isfinite(delay) and 0 < delay < 2**53 / 1000 else fallback


def quota_error(exc: BaseException, fallback: float) -> MCPRateLimitError | None:
    """Read HTTP 429/Retry-After or an explicit MCP tool quota refusal."""
    if isinstance(exc, MCPRateLimitError):
        return exc
    if isinstance(exc, httpx2.HTTPStatusError) and exc.response.status_code == 429:
        return MCPRateLimitError(
            _retry_delay(exc.response.headers.get("Retry-After", ""), fallback)
        )
    if isinstance(exc, MCPToolExecutionError) and _QUOTA.search(str(exc)):
        match = _DELAY.search(str(exc))
        return MCPRateLimitError(_retry_delay(match[1], fallback) if match else fallback)
    return None


class MCPServerCooldown:
    """Redis owns the shared TTL; local deadlines cover Redis outages."""

    def __init__(self) -> None:
        self._deadlines: dict[tuple[UUID, UUID], float] = {}

    async def remaining(self, key: tuple[UUID, UUID]) -> float:
        ttl = 0
        try:
            redis = await get_redis_cache()
            ttl = await redis.pttl(self._redis_key(key))
        except RedisError:
            logger.debug("mcp_cooldown_read_unavailable", exc_info=True)
        now = time.monotonic()
        if ttl > 0:
            # Another task may record a longer refusal while Redis is read.
            # Merge with the current deadline, never a pre-await snapshot.
            self._deadlines[key] = max(self._deadlines.get(key, 0.0), now + ttl / 1000)
        local = max(0.0, self._deadlines.get(key, 0.0) - now)
        if not local:
            self._deadlines.pop(key, None)
        return local

    async def record(self, key: tuple[UUID, UUID], retry_after: float) -> None:
        self._deadlines[key] = max(self._deadlines.get(key, 0.0), time.monotonic() + retry_after)
        try:
            redis = await get_redis_cache()
            remaining_ms = int(
                await redis.eval(
                    _EXTEND_COOLDOWN, 1, self._redis_key(key), math.ceil(retry_after * 1000)
                )
            )
            self._deadlines[key] = max(
                self._deadlines.get(key, 0.0), time.monotonic() + remaining_ms / 1000
            )
        except RedisError:
            logger.debug("mcp_cooldown_write_unavailable", exc_info=True)

    def forget_local(self, key: tuple[UUID, UUID]) -> None:
        """Prune expired state; a reconnect must retain a known provider refusal."""
        if self._deadlines.get(key, 0.0) <= time.monotonic():
            self._deadlines.pop(key, None)

    @staticmethod
    def _redis_key(key: tuple[UUID, UUID]) -> str:
        return f"mcp:cooldown:{key[0]}:{key[1]}"
