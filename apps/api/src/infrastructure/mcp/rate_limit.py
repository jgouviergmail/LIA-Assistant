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
from typing import Literal
from uuid import UUID

import httpx2
import structlog
from redis.exceptions import RedisError

from src.core.config import settings
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


#: Why a call built from an unverified catalogue was refused (spec 2026-10-21 §5.5).
DeclarationChangeReason = Literal["missing", "incompatible", "tightened"]


class MCPDeclarationChangedError(MCPToolExecutionError):
    """The tool's current declaration no longer admits the call: it was not sent."""

    def __init__(self, reason: DeclarationChangeReason) -> None:
        self.reason: DeclarationChangeReason = reason
        super().__init__(
            f"The server changed this tool since it was offered ({reason}); the call was "
            "not sent. Do not retry it this turn: its catalogue is being refreshed."
        )


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


# One consecutive failure more: the count survives the pause (so the next
# failure doubles it), the pause doubles up to its cap.
_RECORD_FAILURE = """
local failures = redis.call('INCR', KEYS[1])
redis.call('PEXPIRE', KEYS[1], ARGV[3])
local pause = tonumber(ARGV[1]) * 2 ^ (failures - 1)
if pause > tonumber(ARGV[2]) then
    pause = tonumber(ARGV[2])
end
pause = math.floor(pause)
redis.call('SET', KEYS[2], failures, 'PX', pause)
return pause
"""


class MCPServerPausedError(RuntimeError):
    """A personal MCP server is paused after failing to connect (point 29)."""

    def __init__(self, retry_in_seconds: float) -> None:
        self.retry_in_seconds = max(1, math.ceil(retry_in_seconds))
        super().__init__(
            "MCP server paused after repeated connection failures; "
            f"next attempt in {self.retry_in_seconds} seconds."
        )


class MCPServerFailures:
    """A server that failed to connect is not retried at every turn (point 29).

    A dead server used to be tried again at each turn, one after another, each
    attempt up to its timeout. A failure pauses it in Redis — shared by every
    worker — for ``mcp_user_failure_pause_base_seconds``, doubling at each
    consecutive failure up to ``mcp_user_failure_pause_max_seconds``; a success
    clears it. Redis unreachable, nothing pauses: the server is tried as before.
    """

    async def remaining(self, key: tuple[UUID, UUID]) -> float:
        """Seconds left in the server's pause; 0 when it may be tried."""
        try:
            redis = await get_redis_cache()
            ttl = await redis.pttl(self._pause_key(key))
        except RedisError:
            logger.debug("mcp_failure_pause_read_unavailable", exc_info=True)
            return 0.0
        return ttl / 1000 if ttl > 0 else 0.0

    async def record(self, key: tuple[UUID, UUID]) -> float:
        """Count one more consecutive failure and pause the server.

        Returns:
            The pause given, in seconds; 0 when Redis could not be written.
        """
        base_ms = settings.mcp_user_failure_pause_base_seconds * 1000
        cap_ms = settings.mcp_user_failure_pause_max_seconds * 1000
        try:
            redis = await get_redis_cache()
            # The count outlives the pause it set, so the next failure doubles it.
            pause_ms = await redis.eval(
                _RECORD_FAILURE,
                2,
                self._count_key(key),
                self._pause_key(key),
                base_ms,
                cap_ms,
                cap_ms * 4,
            )
        except RedisError:
            logger.debug("mcp_failure_pause_write_unavailable", exc_info=True)
            return 0.0
        return int(pause_ms) / 1000

    async def clear(self, key: tuple[UUID, UUID]) -> None:
        """Forget the server's failures: it answered."""
        try:
            redis = await get_redis_cache()
            await redis.delete(self._count_key(key), self._pause_key(key))
        except RedisError:
            logger.debug("mcp_failure_pause_clear_unavailable", exc_info=True)

    @staticmethod
    def _count_key(key: tuple[UUID, UUID]) -> str:
        return f"mcp:failure:count:{key[0]}:{key[1]}"

    @staticmethod
    def _pause_key(key: tuple[UUID, UUID]) -> str:
        return f"mcp:failure:pause:{key[0]}:{key[1]}"
