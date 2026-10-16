"""The ElevenLabs voice listing refuses by its facts, never by the vendor's words (ADR-317)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from src.domains.voice import voices_catalog
from src.domains.voice.voices_catalog import ElevenLabsVoicesError, get_elevenlabs_voices

pytestmark = pytest.mark.unit

QUOTED = "a vendor sentence that must never travel"


def _route(
    monkeypatch: pytest.MonkeyPatch, answer: Callable[[httpx.Request], httpx.Response]
) -> None:
    real_client = httpx.AsyncClient

    def _factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs.setdefault("transport", httpx.MockTransport(answer))
        return real_client(*args, **kwargs)

    monkeypatch.setattr(voices_catalog.httpx, "AsyncClient", _factory)


@pytest.mark.parametrize("status", [400, 401, 403, 500])
async def test_a_refused_listing_carries_its_facts_alone(
    monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    body = {"detail": {"status": "missing_permissions", "message": QUOTED}}
    _route(monkeypatch, lambda _: httpx.Response(status, json=body))
    with pytest.raises(ElevenLabsVoicesError) as caught:
        await get_elevenlabs_voices("key", "https://api.elevenlabs.io/v1")
    assert caught.value.details == {"status_code": status, "vendor_code": "missing_permissions"}
    assert QUOTED not in str(caught.value)


async def test_a_transport_failure_is_named_by_its_type(monkeypatch: pytest.MonkeyPatch) -> None:
    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("unreachable", request=request)

    _route(monkeypatch, unreachable)
    with pytest.raises(ElevenLabsVoicesError) as caught:
        await get_elevenlabs_voices("key", "https://api.elevenlabs.io/v1")
    assert caught.value.details == {"exception_type": "ConnectError"}


async def test_a_missing_key_is_refused_before_any_call() -> None:
    with pytest.raises(ElevenLabsVoicesError) as caught:
        await get_elevenlabs_voices("", "https://api.elevenlabs.io/v1")
    assert caught.value.details == {}


# --- The cached listing (ADR-345 amendment 2026-10-14) ------------------------


class _Redis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int) -> None:
        self.store[key] = value


VOICES = [
    voices_catalog.VoiceOption("v1", "Rachel", "female", "en", {"category": "premade"}),
    voices_catalog.VoiceOption("v2", "Adam", "male", None, {}),
]


@pytest.fixture
def listing(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []

    async def live(*, api_key: str, base_url: str) -> list[voices_catalog.VoiceOption]:
        calls.append(api_key)
        return VOICES

    monkeypatch.setattr(voices_catalog, "get_elevenlabs_voices", live)
    return calls


def _redis(monkeypatch: pytest.MonkeyPatch, cache: Any) -> None:
    async def get_redis() -> Any:
        if isinstance(cache, Exception):
            raise cache
        return cache

    monkeypatch.setattr(voices_catalog, "get_redis_cache", get_redis)


def test_a_voice_list_round_trips_through_the_cache_whole() -> None:
    assert (
        voices_catalog.decode_voice_options(voices_catalog.encode_voice_options(VOICES)) == VOICES
    )


@pytest.mark.parametrize("raw", ["not json", "{}", '[{"label": "no id"}]', "[1]"])
def test_an_unreadable_cache_is_no_cache(raw: str) -> None:
    assert voices_catalog.decode_voice_options(raw) is None


async def test_a_second_read_costs_no_vendor_request(
    monkeypatch: pytest.MonkeyPatch, listing: list[str]
) -> None:
    cache = _Redis()
    _redis(monkeypatch, cache)

    first = await voices_catalog.get_cached_elevenlabs_voices("secret-key", "https://x/v1")
    second = await voices_catalog.get_cached_elevenlabs_voices("secret-key", "https://x/v1")

    assert first == second == VOICES
    assert listing == ["secret-key"]
    (key,) = cache.store
    assert "secret-key" not in key  # a digest of the account, never the credential


async def test_an_unreachable_cache_reads_the_vendor(
    monkeypatch: pytest.MonkeyPatch, listing: list[str]
) -> None:
    _redis(monkeypatch, OSError("redis down"))

    assert await voices_catalog.get_cached_elevenlabs_voices("k", "https://x/v1") == VOICES
    assert listing == ["k"]


async def test_an_unreadable_entry_is_listed_again(
    monkeypatch: pytest.MonkeyPatch, listing: list[str]
) -> None:
    cache = _Redis()
    _redis(monkeypatch, cache)
    await voices_catalog.get_cached_elevenlabs_voices("k", "https://x/v1")
    (key,) = cache.store
    cache.store[key] = "garbage"

    assert await voices_catalog.get_cached_elevenlabs_voices("k", "https://x/v1") == VOICES
    assert listing == ["k", "k"]


async def test_a_peek_answers_from_the_cache_alone(
    monkeypatch: pytest.MonkeyPatch, listing: list[str]
) -> None:
    cache = _Redis()
    _redis(monkeypatch, cache)

    assert await voices_catalog.peek_elevenlabs_voices("k") is None
    await voices_catalog.get_cached_elevenlabs_voices("k", "https://x/v1")

    assert await voices_catalog.peek_elevenlabs_voices("k") == VOICES
    assert listing == ["k"]
