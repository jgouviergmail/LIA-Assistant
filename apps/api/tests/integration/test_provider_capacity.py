"""Real Redis capacity leases and mocked HTTP: no paid provider is contacted.

The lease mechanics are proven for EVERY declared pool; the client behaviour
(a burst, a cancellation, a refusal) through each client that takes a slot.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

import httpx
import pytest
from redis.asyncio import Redis

from src.core.config import settings
from src.domains.llm_config.cache import LLMConfigOverrideCache
from src.domains.voice import provider_capacity as capacity
from src.domains.voice.elevenlabs_tts_client import ElevenLabsTTSClient
from src.domains.voice.exceptions import TTSProviderError
from src.domains.voice.provider_capacity import CAPACITY_POOLS, capacity_key, provider_slot

pytestmark = pytest.mark.integration

#: The setting each pool's ceiling reads.
_LIMIT_SETTINGS = {
    "elevenlabs": "elevenlabs_tts_max_concurrency",
    "fishaudio": "fishaudio_max_concurrency",
}


@pytest.fixture
async def redis(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Redis]:
    connection = Redis.from_url(str(settings.redis_url), decode_responses=True)
    await connection.ping()

    async def get_redis() -> Redis:
        return connection

    monkeypatch.setattr(capacity, "get_redis_cache", get_redis)
    monkeypatch.setattr(capacity, "DEFAULT_POLL_SECONDS", 0.01)
    try:
        yield connection
    finally:
        await connection.aclose()


@pytest.fixture
async def account(
    redis: Redis, monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> AsyncIterator[tuple[str, str, str]]:
    """An isolated synthetic account of ``provider``; removes only its own lease key."""
    provider: str = getattr(request, "param", "elevenlabs")
    api_key = f"test-capacity-{uuid4().hex}"
    key = capacity_key(provider, api_key)
    monkeypatch.setattr(
        LLMConfigOverrideCache, "get_api_key", classmethod(lambda cls, name: api_key)
    )
    monkeypatch.setattr(settings, _LIMIT_SETTINGS[provider], 2)
    try:
        yield provider, key, api_key
    finally:
        await redis.delete(key)


def test_every_pool_has_its_setting_here() -> None:
    assert set(_LIMIT_SETTINGS) == set(CAPACITY_POOLS)


@asynccontextmanager
async def elevenlabs(
    transport: httpx.MockTransport, *, timeout: float = 2
) -> AsyncIterator[ElevenLabsTTSClient]:
    tts = ElevenLabsTTSClient(timeout_seconds=timeout)
    await tts.close()
    tts._http_client = httpx.AsyncClient(transport=transport)
    try:
        yield tts
    finally:
        await tts.close()


# --- The lease, for every pool ---------------------------------------------------------


@pytest.mark.parametrize("account", sorted(CAPACITY_POOLS), indirect=True)
async def test_a_burst_never_exceeds_the_allowance(
    redis: Redis, account: tuple[str, str, str]
) -> None:
    provider, key, api_key = account
    active = peak = 0

    async def request() -> None:
        nonlocal active, peak
        async with provider_slot(provider, api_key, timeout_seconds=2):
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.03)
            active -= 1

    async with asyncio.timeout(5):
        await asyncio.gather(*(request() for _ in range(9)))
    assert peak == 2
    assert await redis.zcard(key) == 0


@pytest.mark.parametrize("account", sorted(CAPACITY_POOLS), indirect=True)
async def test_a_waiter_never_removes_another_owners_slot(
    redis: Redis, account: tuple[str, str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    provider, key, api_key = account
    monkeypatch.setattr(settings, _LIMIT_SETTINGS[provider], 1)
    async with asyncio.timeout(2):
        async with provider_slot(provider, api_key, timeout_seconds=2):
            with pytest.raises(TimeoutError):
                async with asyncio.timeout(0.05):
                    async with provider_slot(provider, api_key, timeout_seconds=2):
                        raise AssertionError("a second slot was granted")
            assert await redis.zcard(key) == 1
    assert await redis.zcard(key) == 0


@pytest.mark.parametrize("account", sorted(CAPACITY_POOLS), indirect=True)
async def test_an_expired_crashed_worker_lease_is_reclaimed(
    redis: Redis, account: tuple[str, str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    provider, key, api_key = account
    monkeypatch.setattr(settings, _LIMIT_SETTINGS[provider], 1)
    await redis.zadd(key, {"crashed-worker": 0})
    async with asyncio.timeout(1):
        async with provider_slot(provider, api_key, timeout_seconds=1):
            assert await redis.zcard(key) == 1
            assert await redis.zscore(key, "crashed-worker") is None
            assert await redis.pttl(key) > 0


@pytest.mark.parametrize("account", sorted(CAPACITY_POOLS), indirect=True)
async def test_a_short_request_does_not_shorten_a_long_requests_lease(
    redis: Redis, account: tuple[str, str, str]
) -> None:
    provider, key, api_key = account
    async with asyncio.timeout(2):
        async with provider_slot(provider, api_key, timeout_seconds=10):
            original_ttl = await redis.pttl(key)
            async with provider_slot(provider, api_key, timeout_seconds=1):
                assert await redis.pttl(key) > original_ttl - 1000


def test_two_providers_never_share_an_allowance() -> None:
    """The same credential string on two vendors is two accounts."""
    assert capacity_key("elevenlabs", "same") != capacity_key("fishaudio", "same")


# --- Through the ElevenLabs client ---------------------------------------------------------


async def test_a_burst_across_clients_never_exceeds_the_account_allowance(
    redis: Redis, account: tuple[str, str, str]
) -> None:
    active = peak = served = 0

    async def respond(request: httpx.Request) -> httpx.Response:
        nonlocal active, peak, served
        active += 1
        peak = max(peak, active)
        try:
            await asyncio.sleep(0.03)
            served += 1
            return httpx.Response(200, content=b"audio")
        finally:
            active -= 1

    transport = httpx.MockTransport(respond)
    async with elevenlabs(transport) as first, elevenlabs(transport) as second:
        results = await asyncio.gather(
            *(tts.synthesize("Hello", "voice") for tts in [first, second] * 5)
        )
    assert results == [b"audio"] * 10
    assert peak == settings.elevenlabs_tts_max_concurrency
    assert served == 10
    _, key, _ = account
    assert await redis.zcard(key) == 0


async def test_a_cancelled_request_releases_its_slot(
    redis: Redis, account: tuple[str, str, str]
) -> None:
    entered = asyncio.Event()

    async def respond(request: httpx.Request) -> httpx.Response:
        entered.set()
        await asyncio.Future[None]()
        return httpx.Response(200)

    async with elevenlabs(httpx.MockTransport(respond)) as tts:
        task = asyncio.create_task(tts.synthesize("Hello", "voice"))
        await asyncio.wait_for(entered.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    _, key, _ = account
    assert await redis.zcard(key) == 0


async def test_a_wait_timeout_never_sends_http_or_removes_another_owners_slot(
    redis: Redis, account: tuple[str, str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    provider, key, api_key = account
    monkeypatch.setattr(settings, "elevenlabs_tts_max_concurrency", 1)
    called = False

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200)

    async with asyncio.timeout(2):
        async with provider_slot(provider, api_key, timeout_seconds=2):
            async with elevenlabs(httpx.MockTransport(respond), timeout=0.03) as tts:
                with pytest.raises(TTSProviderError, match="timed out"):
                    await tts.synthesize("Hello", "voice")
            assert await redis.zcard(key) == 1
    assert not called
    assert await redis.zcard(key) == 0


@pytest.mark.parametrize("status", [400, 429, 500])
async def test_an_http_failure_releases_capacity(
    redis: Redis, account: tuple[str, str, str], status: int
) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"detail": "refused"})

    async with elevenlabs(httpx.MockTransport(respond)) as tts:
        with pytest.raises(TTSProviderError):
            await tts.synthesize("Hello", "voice")
    _, key, _ = account
    assert await redis.zcard(key) == 0


async def test_an_http_timeout_cancels_the_provider_before_releasing_capacity(
    redis: Redis, account: tuple[str, str, str]
) -> None:
    cancelled = False

    async def respond(request: httpx.Request) -> httpx.Response:
        nonlocal cancelled
        try:
            await asyncio.Future[None]()
        finally:
            cancelled = True
        return httpx.Response(200)

    async with elevenlabs(httpx.MockTransport(respond), timeout=0.03) as tts:
        with pytest.raises(TTSProviderError, match="timed out"):
            await tts.synthesize("Hello", "voice")
    assert cancelled
    _, key, _ = account
    assert await redis.zcard(key) == 0
