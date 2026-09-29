"""Account-wide TTS capacity shared by all API workers and voice surfaces.

Each in-flight HTTP request owns an expiring Redis lease. Waiting sentences
consume no provider slot. A crashed worker cannot permanently exhaust capacity;
the client bounds the whole synthesis by its timeout, shorter than the lease.
"""

from __future__ import annotations

import asyncio
import hashlib
import math
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

import structlog
from redis.exceptions import RedisError

from src.core.config import settings
from src.core.constants import REDIS_KEY_ELEVENLABS_TTS_SLOTS_PREFIX
from src.domains.voice.exceptions import TTSProviderError
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.rate_limiting.slot_waiter import DEFAULT_POLL_SECONDS

logger = structlog.get_logger(__name__)

# Use Redis's clock so workers with different wall clocks agree on expiry.
_ACQUIRE = """
local clock = redis.call('TIME')
local now = clock[1] * 1000 + math.floor(clock[2] / 1000)
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now)
if redis.call('ZCARD', KEYS[1]) >= tonumber(ARGV[1]) then return 0 end
redis.call('ZADD', KEYS[1], now + tonumber(ARGV[2]), ARGV[3])
local last = redis.call('ZRANGE', KEYS[1], -1, -1, 'WITHSCORES')
redis.call('PEXPIRE', KEYS[1], math.ceil(tonumber(last[2]) - now))
return 1
"""


@asynccontextmanager
async def tts_slot(api_key: str, *, timeout_seconds: float) -> AsyncIterator[None]:
    """Wait for a shared slot; release it on success, failure or cancellation.

    The caller must enforce ``timeout_seconds`` around both this wait and the
    HTTP request. Redis failures refuse synthesis rather than exceed capacity.
    Only a digest of the credential is stored, never the provider key itself.
    """
    redis = await get_redis_cache()
    key = REDIS_KEY_ELEVENLABS_TTS_SLOTS_PREFIX + hashlib.sha256(api_key.encode()).hexdigest()
    token = uuid4().hex
    lease_ms = math.ceil((timeout_seconds + 1) * 1000)
    try:
        while not await redis.eval(
            _ACQUIRE, 1, key, settings.elevenlabs_tts_max_concurrency, lease_ms, token
        ):
            await asyncio.sleep(DEFAULT_POLL_SECONDS)
        yield
    except RedisError as exc:
        raise TTSProviderError(
            code="provider_network_error",
            message="ElevenLabs TTS capacity could not be reserved.",
            details={"stage": "capacity_reservation"},
        ) from exc
    finally:
        # Remove our token even if cancellation raced with the acquisition reply.
        try:
            await redis.zrem(key, token)
        except RedisError:
            logger.warning("elevenlabs_tts_slot_release_failed", lease_ms=lease_ms)
