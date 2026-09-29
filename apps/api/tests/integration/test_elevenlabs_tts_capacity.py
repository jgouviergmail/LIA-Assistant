"""Real Redis capacity leases and mocked HTTP: no paid provider is contacted."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

import httpx
import pytest
from redis.asyncio import Redis

from src.core.config import settings
from src.core.constants import REDIS_KEY_ELEVENLABS_TTS_SLOTS_PREFIX
from src.domains.llm_config.cache import LLMConfigOverrideCache
from src.domains.voice import elevenlabs_concurrency as capacity
from src.domains.voice.elevenlabs_tts_client import ElevenLabsTTSClient
from src.domains.voice.exceptions import TTSProviderError

pytestmark = pytest.mark.integration


@pytest.fixture
async def account(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[tuple[Redis, str, str]]:
    """An isolated synthetic provider account; remove only its test lease key."""
    redis = Redis.from_url(str(settings.redis_url), decode_responses=True)
    await redis.ping()
    api_key = f"test-tts-{uuid4().hex}"
    key = REDIS_KEY_ELEVENLABS_TTS_SLOTS_PREFIX + hashlib.sha256(api_key.encode()).hexdigest()

    async def get_redis() -> Redis:
        return redis

    def get_key(provider: str) -> str:
        assert provider == "elevenlabs"
        return api_key

    monkeypatch.setattr(capacity, "get_redis_cache", get_redis)
    monkeypatch.setattr(LLMConfigOverrideCache, "get_api_key", get_key)
    monkeypatch.setattr(settings, "elevenlabs_tts_max_concurrency", 2)
    monkeypatch.setattr(capacity, "DEFAULT_POLL_SECONDS", 0.01)
    try:
        yield redis, key, api_key
    finally:
        await redis.delete(key)
        await redis.aclose()


@asynccontextmanager
async def client(
    transport: httpx.MockTransport, *, timeout: float = 2
) -> AsyncIterator[ElevenLabsTTSClient]:
    tts = ElevenLabsTTSClient(timeout_seconds=timeout)
    await tts.close()
    tts._http_client = httpx.AsyncClient(transport=transport)
    try:
        yield tts
    finally:
        await tts.close()


async def test_burst_across_clients_never_exceeds_account_capacity(
    account: tuple[Redis, str, str],
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
    async with client(transport) as first, client(transport) as second:
        results = await asyncio.gather(
            *(tts.synthesize("Hello", "voice") for tts in [first, second] * 5)
        )
    assert results == [b"audio"] * 10
    assert peak == settings.elevenlabs_tts_max_concurrency
    assert served == 10
    redis, key, _ = account
    assert await redis.zcard(key) == 0


async def test_cancelled_request_releases_its_slot(account: tuple[Redis, str, str]) -> None:
    entered = asyncio.Event()

    async def respond(request: httpx.Request) -> httpx.Response:
        entered.set()
        await asyncio.Future[None]()
        return httpx.Response(200)

    async with client(httpx.MockTransport(respond)) as tts:
        task = asyncio.create_task(tts.synthesize("Hello", "voice"))
        await asyncio.wait_for(entered.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    redis, key, _ = account
    assert await redis.zcard(key) == 0


async def test_wait_timeout_never_sends_http_or_removes_another_owners_slot(
    account: tuple[Redis, str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    redis, key, api_key = account
    monkeypatch.setattr(settings, "elevenlabs_tts_max_concurrency", 1)
    called = False

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200)

    async with asyncio.timeout(2):
        async with capacity.tts_slot(api_key, timeout_seconds=2):
            async with client(httpx.MockTransport(respond), timeout=0.03) as tts:
                with pytest.raises(TTSProviderError, match="timed out"):
                    await tts.synthesize("Hello", "voice")
            assert await redis.zcard(key) == 1
    assert not called
    assert await redis.zcard(key) == 0


@pytest.mark.parametrize("status", [400, 429, 500])
async def test_http_failure_releases_capacity(account: tuple[Redis, str, str], status: int) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"detail": "refused"})

    async with client(httpx.MockTransport(respond)) as tts:
        with pytest.raises(TTSProviderError):
            await tts.synthesize("Hello", "voice")
    redis, key, _ = account
    assert await redis.zcard(key) == 0


async def test_expired_crashed_worker_lease_is_reclaimed(
    account: tuple[Redis, str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    redis, key, api_key = account
    monkeypatch.setattr(settings, "elevenlabs_tts_max_concurrency", 1)
    await redis.zadd(key, {"crashed-worker": 0})
    async with asyncio.timeout(1):
        async with capacity.tts_slot(api_key, timeout_seconds=1):
            assert await redis.zcard(key) == 1
            assert await redis.zscore(key, "crashed-worker") is None
            assert await redis.pttl(key) > 0


async def test_short_request_does_not_shorten_a_long_requests_lease(
    account: tuple[Redis, str, str],
) -> None:
    redis, key, api_key = account
    async with asyncio.timeout(2):
        async with capacity.tts_slot(api_key, timeout_seconds=10):
            original_ttl = await redis.pttl(key)
            async with capacity.tts_slot(api_key, timeout_seconds=1):
                assert await redis.pttl(key) > original_ttl - 1000


async def test_http_timeout_cancels_provider_before_releasing_capacity(
    account: tuple[Redis, str, str],
) -> None:
    cancelled = False

    async def respond(request: httpx.Request) -> httpx.Response:
        nonlocal cancelled
        try:
            await asyncio.Future[None]()
        finally:
            cancelled = True
        return httpx.Response(200)

    async with client(httpx.MockTransport(respond), timeout=0.03) as tts:
        with pytest.raises(TTSProviderError, match="timed out"):
            await tts.synthesize("Hello", "voice")
    assert cancelled
    redis, key, _ = account
    assert await redis.zcard(key) == 0
