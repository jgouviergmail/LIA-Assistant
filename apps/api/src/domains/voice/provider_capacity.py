"""One provider account's in-flight request allowance, shared by every worker and surface.

Some vendors cap how many requests an ACCOUNT may have in flight — ElevenLabs
per plan, Fish Audio at five for synthesis, transcription and voice design
together (measured 2026-10-13, ``ratelimit-limit-concurrency: 5``). A burst past
it is refused (429), and a refused sentence is one the listener never hears.

Each in-flight request owns an expiring Redis lease under the account's key.
Waiting consumes no provider slot. A crashed worker cannot exhaust the
allowance for good: the caller bounds the wait and the request by its timeout,
which is shorter than the lease. Only a digest of the credential is stored,
never the provider key itself.
"""

from __future__ import annotations

import asyncio
import hashlib
import math
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final
from uuid import uuid4

import structlog
from redis.exceptions import RedisError

from src.core.config import settings
from src.core.constants import (
    REDIS_KEY_ELEVENLABS_TTS_SLOTS_PREFIX,
    REDIS_KEY_FISHAUDIO_CAPACITY_PREFIX,
)
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


class ProviderCapacityUnavailable(Exception):
    """The shared allowance could not be reserved: refused rather than exceeded.

    Attributes:
        provider: The provider whose allowance Redis could not reserve.
    """

    def __init__(self, provider: str) -> None:
        super().__init__(f"{provider} capacity could not be reserved")
        self.provider = provider


@dataclass(frozen=True, slots=True)
class CapacityPool:
    """One vendor's account allowance.

    Attributes:
        key_prefix: The Redis family its leases live under (``GLOBAL``).
        limit: The ceiling, read at call time so a changed setting applies
            without a restart.
    """

    key_prefix: str
    limit: Callable[[], int]


#: The vendors that cap an account's in-flight requests. The ElevenLabs key is
#: the one workers held before this table existed: a rolling deploy must never
#: open a second allowance beside the first.
CAPACITY_POOLS: Final[Mapping[str, CapacityPool]] = MappingProxyType(
    {
        "elevenlabs": CapacityPool(
            REDIS_KEY_ELEVENLABS_TTS_SLOTS_PREFIX, lambda: settings.elevenlabs_tts_max_concurrency
        ),
        "fishaudio": CapacityPool(
            REDIS_KEY_FISHAUDIO_CAPACITY_PREFIX, lambda: settings.fishaudio_max_concurrency
        ),
    }
)


def capacity_key(provider: str, api_key: str) -> str:
    """The Redis key of the account behind ``api_key``.

    Raises:
        KeyError: For a provider that declares no pool — a programming error.
    """
    return CAPACITY_POOLS[provider].key_prefix + hashlib.sha256(api_key.encode()).hexdigest()


@asynccontextmanager
async def provider_slot(
    provider: str, api_key: str, *, timeout_seconds: float
) -> AsyncIterator[None]:
    """Wait for a slot of the account's allowance; release it on every exit.

    The caller must bound both this wait and its request by ``timeout_seconds``.

    Args:
        provider: A key of :data:`CAPACITY_POOLS`.
        api_key: The credential the request is sent with.
        timeout_seconds: The caller's bound; the lease outlives it by a second.

    Raises:
        ProviderCapacityUnavailable: When Redis cannot reserve the slot — the
            request is refused rather than sent beyond the allowance.
    """
    pool = CAPACITY_POOLS[provider]
    key = capacity_key(provider, api_key)
    redis = await get_redis_cache()
    token = uuid4().hex
    lease_ms = math.ceil((timeout_seconds + 1) * 1000)
    try:
        while not await redis.eval(_ACQUIRE, 1, key, pool.limit(), lease_ms, token):
            await asyncio.sleep(DEFAULT_POLL_SECONDS)
        yield
    except RedisError as exc:
        raise ProviderCapacityUnavailable(provider) from exc
    finally:
        # Remove our token even if cancellation raced with the acquisition reply.
        try:
            await redis.zrem(key, token)
        except RedisError:
            logger.warning("provider_capacity_release_failed", provider=provider, lease_ms=lease_ms)


__all__ = [
    "CAPACITY_POOLS",
    "CapacityPool",
    "ProviderCapacityUnavailable",
    "capacity_key",
    "provider_slot",
]
