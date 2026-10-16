"""One account's concurrent-request allowance, declared once per provider.

The leases themselves are proven on a real Redis in
``tests/integration/test_provider_capacity.py``; this module pins what needs
none: every pool reads a real ceiling, sits in a declared key family, and the
ElevenLabs key is the one running workers already hold (a rolling deploy must
not open a second allowance beside the first).
"""

from __future__ import annotations

import hashlib

import httpx
import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from src.core.config import settings
from src.core.constants import FISHAUDIO_MAX_CONCURRENCY_DEFAULT
from src.domains.llm_config.cache import LLMConfigOverrideCache
from src.domains.voice import provider_capacity
from src.domains.voice.elevenlabs_tts_client import ElevenLabsTTSClient
from src.domains.voice.exceptions import TTSProviderError
from src.domains.voice.provider_capacity import (
    CAPACITY_POOLS,
    ProviderCapacityUnavailable,
    capacity_key,
    provider_slot,
)
from src.infrastructure.cache.key_families import KeyScope, scope_of

pytestmark = pytest.mark.unit


class _BrokenRedis:
    """A Redis that refuses every command."""

    def __init__(self) -> None:
        self.released: list[str] = []

    async def eval(self, *_: object) -> int:
        raise RedisConnectionError("redis down")

    async def zrem(self, key: str, token: str) -> int:
        self.released.append(token)
        raise RedisConnectionError("redis down")


@pytest.fixture
def broken_redis(monkeypatch: pytest.MonkeyPatch) -> _BrokenRedis:
    redis = _BrokenRedis()

    async def get_redis() -> _BrokenRedis:
        return redis

    monkeypatch.setattr(provider_capacity, "get_redis_cache", get_redis)
    return redis


class TestThePools:
    def test_the_vendors_that_cap_an_account_have_a_pool(self) -> None:
        assert set(CAPACITY_POOLS) == {"elevenlabs", "fishaudio"}

    @pytest.mark.parametrize("provider", sorted(CAPACITY_POOLS))
    def test_every_pool_reads_a_positive_ceiling(self, provider: str) -> None:
        assert CAPACITY_POOLS[provider].limit() >= 1

    def test_the_ceiling_follows_the_setting_without_a_restart(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "fishaudio_max_concurrency", 2)
        assert CAPACITY_POOLS["fishaudio"].limit() == 2

    def test_fish_audio_caps_five_requests_by_default(self) -> None:
        """Measured 2026-10-13: ``ratelimit-limit-concurrency: 5``, shared by every
        request of the account — synthesis, transcription and voice design."""
        assert FISHAUDIO_MAX_CONCURRENCY_DEFAULT == 5
        assert type(settings).model_fields["fishaudio_max_concurrency"].default == 5

    @pytest.mark.parametrize("provider", sorted(CAPACITY_POOLS))
    def test_every_pool_is_a_declared_global_family(self, provider: str) -> None:
        """An allowance belongs to the vendor account, never to one person."""
        assert scope_of(capacity_key(provider, "key")) is KeyScope.GLOBAL

    def test_the_elevenlabs_key_is_the_one_running_workers_hold(self) -> None:
        digest = hashlib.sha256(b"secret-key").hexdigest()
        assert capacity_key("elevenlabs", "secret-key") == f"elevenlabs:tts_slots:{digest}"

    def test_a_key_carries_a_digest_never_the_credential(self) -> None:
        assert "secret-key" not in capacity_key("fishaudio", "secret-key")

    def test_a_provider_with_no_pool_is_a_programming_error(self) -> None:
        with pytest.raises(KeyError):
            capacity_key("openai", "key")


class TestARedisFailure:
    async def test_refuses_rather_than_exceeds_the_allowance(
        self, broken_redis: _BrokenRedis
    ) -> None:
        with pytest.raises(ProviderCapacityUnavailable) as caught:
            async with provider_slot("fishaudio", "key", timeout_seconds=1):
                raise AssertionError("no request may leave without a slot")
        assert caught.value.provider == "fishaudio"
        # The release is still attempted, and its own failure is not raised over the refusal.
        assert len(broken_redis.released) == 1

    async def test_reaches_the_elevenlabs_caller_as_its_own_failure(
        self, broken_redis: _BrokenRedis, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            LLMConfigOverrideCache, "get_api_key", classmethod(lambda cls, provider: "key")
        )
        sent: list[httpx.Request] = []
        client = ElevenLabsTTSClient(timeout_seconds=1)
        await client.close()
        client._http_client = httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: sent.append(request) or httpx.Response(200)
            )
        )
        try:
            with pytest.raises(TTSProviderError) as caught:
                await client.synthesize("Bonjour.", "voice")
        finally:
            await client.close()
        assert caught.value.code == "provider_network_error"
        assert caught.value.details == {"stage": "capacity_reservation"}
        assert sent == []
