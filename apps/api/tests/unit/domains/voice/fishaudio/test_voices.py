"""The Fish Audio voices LIA offers — own, pinned, licensed — read from the vendor's library.

Shapes measured 2026-10-13: ``GET /model`` pages at 100 at most with ``items``
and ``has_more``; ``licensed=true`` returns the 113 voices whose rights the
vendor secured, one language each; a model's gender is a TAG.
"""

from __future__ import annotations

import asyncio
import fnmatch
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import httpx
import pytest
from structlog.testing import capture_logs

from src.domains.voice import voices_catalog
from src.domains.voice.fishaudio import voices as module
from src.domains.voice.fishaudio.voices import (
    FishVoicesError,
    fetch_fish_voice,
    get_fish_voices,
    invalidate_fish_voices,
    list_fish_voices,
    peek_fish_voices,
    voice_option,
)
from src.domains.voice.voices_catalog import VoiceOption
from tests.support.structlog_capture import fresh_module_logger

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def initial_catalogue_revision(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module, "catalogue_revision", AsyncMock(return_value=None), raising=False)


OWN = "a" * 32
PINNED = "b" * 32
LICENSED = "c" * 32
TAKEN_DOWN = "d" * 32


def entity(voice_id: str, **fields: Any) -> dict[str, Any]:
    return {
        "_id": voice_id,
        "type": "tts",
        "state": "trained",
        "title": f"Voice {voice_id[0]}",
        "languages": ["fr"],
        "tags": ["female", "calm"],
        **fields,
    }


@pytest.fixture(autouse=True)
def _fresh_module_logger() -> Iterator[None]:
    yield from fresh_module_logger(module)


@pytest.fixture(autouse=True)
def slots(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    taken: list[str] = []

    @asynccontextmanager
    async def recording(
        provider: str, api_key: str, *, timeout_seconds: float
    ) -> AsyncIterator[None]:
        taken.append(provider)
        yield

    monkeypatch.setattr(module, "provider_slot", recording)
    return taken


def library(
    own: list[dict[str, Any]],
    licensed: list[dict[str, Any]],
    models: dict[str, dict[str, Any]] | None = None,
) -> tuple[httpx.MockTransport, list[httpx.Request]]:
    sent: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        assert request.headers["authorization"] == "Bearer key"
        if request.url.path == "/model":
            source = own if request.url.params.get("self") == "true" else licensed
            page = int(request.url.params["page_number"])
            size = int(request.url.params["page_size"])
            items = source[(page - 1) * size : page * size]
            return httpx.Response(200, json={"items": items, "has_more": page * size < len(source)})
        voice_id = request.url.path.rsplit("/", 1)[-1]
        found = (models or {}).get(voice_id)
        return httpx.Response(200, json=found) if found else httpx.Response(404, json={})

    return httpx.MockTransport(respond), sent


class TestOneVoice:
    def test_a_trained_speech_voice_is_offered_with_its_gender_and_language(self) -> None:
        option = voice_option(entity(OWN, tags=["Male", "warm"], languages=["de"]), "own")
        assert option == VoiceOption(
            voice_id=OWN, label="Voice a", gender="male", language="de", extra={"source": "own"}
        )

    @pytest.mark.parametrize(
        "fields",
        [{"type": "svc"}, {"state": "training"}, {"dmca_taken_down": True}, {"_id": None}],
    )
    def test_a_model_that_cannot_speak_is_not_offered(self, fields: dict[str, Any]) -> None:
        assert voice_option(entity(OWN, **fields), "own") is None

    def test_a_voice_of_several_languages_names_none(self) -> None:
        option = voice_option(entity(OWN, languages=["fr", "en"]), "own")
        assert option is not None and option.language is None

    def test_an_untitled_voice_is_named_by_its_id(self) -> None:
        option = voice_option(entity(OWN, title="  "), "own")
        assert option is not None and option.label == OWN


class TestTheList:
    async def test_own_then_pinned_then_licensed_each_once(self) -> None:
        transport, _ = library(
            own=[entity(OWN)],
            licensed=[entity(LICENSED), entity(OWN)],  # an own voice also licensed: kept once
            models={PINNED: entity(PINNED, languages=["en"])},
        )
        voices = await list_fish_voices("key", [PINNED], transport=transport)
        assert [(v.voice_id, v.extra["source"]) for v in voices] == [
            (OWN, "own"),
            (PINNED, "pinned"),
            (LICENSED, "licensed"),
        ]

    async def test_every_page_is_read_and_every_request_takes_an_account_slot(
        self, slots: list[str]
    ) -> None:
        licensed = [entity(f"{index:032x}") for index in range(113)]
        transport, sent = library(own=[], licensed=licensed)
        voices = await list_fish_voices("key", [], transport=transport)
        assert len(voices) == 113
        assert [r.url.params["page_number"] for r in sent if r.url.params.get("licensed")] == [
            "1",
            "2",
        ]
        assert slots == ["fishaudio"] * len(sent)

    async def test_an_unavailable_pin_is_said_and_offered_nowhere(self) -> None:
        transport, _ = library(
            own=[], licensed=[], models={TAKEN_DOWN: entity(TAKEN_DOWN, dmca_taken_down=True)}
        )
        with capture_logs() as logs:
            voices = await list_fish_voices("key", [TAKEN_DOWN, PINNED], transport=transport)
        assert voices == []
        assert [
            e["voice_id"] for e in logs if e["event"] == "fishaudio_pinned_voice_unavailable"
        ] == [
            TAKEN_DOWN,
            PINNED,
        ]

    async def test_a_refusal_reads_as_an_error_with_its_facts(self) -> None:
        def respond(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, headers={"x-fish-error-code": "invalid_api_key"})

        with pytest.raises(FishVoicesError) as caught:
            await list_fish_voices("key", [], transport=httpx.MockTransport(respond))
        assert caught.value.details == {"status_code": 401, "vendor_code": "invalid_api_key"}

    async def test_a_listing_that_outlasts_its_bound_is_an_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The slot wait and the request share one bound: a lease outlives what it covers."""
        monkeypatch.setattr(module, "FISHAUDIO_VOICES_TIMEOUT_SECONDS", 0.05)

        async def respond(request: httpx.Request) -> httpx.Response:
            await asyncio.sleep(1)
            return httpx.Response(200, json={"items": []})

        with pytest.raises(FishVoicesError, match="timed out"):
            await list_fish_voices("key", [], transport=httpx.MockTransport(respond))

    async def test_one_pin_is_fetched_as_a_pin_and_a_missing_one_is_none(self) -> None:
        transport, _ = library(own=[], licensed=[], models={PINNED: entity(PINNED)})
        option = await fetch_fish_voice("key", PINNED, transport=transport)
        assert option is not None and option.extra == {"source": "pinned"}
        assert await fetch_fish_voice("key", "e" * 32, transport=transport) is None


class _Redis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int) -> None:
        self.store[key] = value

    async def scan_iter(self, *, match: str, count: int) -> AsyncIterator[str]:
        for key in list(self.store):
            if fnmatch.fnmatchcase(key, match):
                yield key

    async def delete(self, *keys: str) -> None:
        for key in keys:
            self.store.pop(key, None)


class TestTheCache:
    @pytest.fixture
    def redis(self, monkeypatch: pytest.MonkeyPatch) -> _Redis:
        cache = _Redis()

        async def get_redis() -> _Redis:
            return cache

        # The list is read and kept through the catalogue's one cache, forgotten here.
        monkeypatch.setattr(module, "get_redis_cache", get_redis)
        monkeypatch.setattr(voices_catalog, "get_redis_cache", get_redis)
        return cache

    def listing(self, monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, tuple[str, ...]]]:
        calls: list[tuple[str, tuple[str, ...]]] = []

        async def list_voices(api_key: str, pinned: tuple[str, ...]) -> list[VoiceOption]:
            calls.append((api_key, tuple(pinned)))
            return [VoiceOption(OWN, "Own", "female", "fr", {"source": "own"})]

        monkeypatch.setattr(module, "list_fish_voices", list_voices)
        return calls

    async def test_a_second_read_costs_no_request(
        self, redis: _Redis, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = self.listing(monkeypatch)
        first = await get_fish_voices("key")
        second = await get_fish_voices("key")
        assert first == second == [VoiceOption(OWN, "Own", "female", "fr", {"source": "own"})]
        assert len(calls) == 1
        (key,) = redis.store
        assert "key" not in key.split(":")[2]  # a digest of the account, never the credential

    async def test_a_new_pin_is_a_new_list(
        self, redis: _Redis, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = self.listing(monkeypatch)
        await get_fish_voices("key")
        await get_fish_voices("key", (PINNED,))
        assert calls == [("key", ()), ("key", (PINNED,))]

    async def test_a_late_listing_cannot_repopulate_the_current_cache_after_deletion(
        self, redis: _Redis, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        revision: list[UUID | None] = [None]
        started = asyncio.Event()
        resume = asyncio.Event()
        calls = 0

        async def current_revision() -> UUID | None:
            return revision[0]

        async def list_voices(api_key: str, pinned: tuple[str, ...]) -> list[VoiceOption]:
            nonlocal calls
            calls += 1
            if calls == 1:
                started.set()
                await resume.wait()
                return [VoiceOption(OWN, "Deleted voice", "female", "fr")]
            return []

        monkeypatch.setattr(module, "catalogue_revision", current_revision, raising=False)
        monkeypatch.setattr(module, "list_fish_voices", list_voices)
        listing = asyncio.create_task(get_fish_voices("key"))
        try:
            await asyncio.wait_for(started.wait(), timeout=5)
            revision[0] = uuid4()
            resume.set()
            await asyncio.wait_for(listing, timeout=5)
            assert await peek_fish_voices("key") is None
            assert await get_fish_voices("key") == []
            assert calls == 2
        finally:
            resume.set()
            if not listing.done():
                listing.cancel()
            await asyncio.gather(listing, return_exceptions=True)

    async def test_a_library_change_forgets_every_list_of_that_account_alone(
        self, redis: _Redis, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = self.listing(monkeypatch)
        await get_fish_voices("key")
        await get_fish_voices("key", (PINNED,))
        await get_fish_voices("other-key")

        await invalidate_fish_voices("key")

        assert len(redis.store) == 1  # the other account's list stays
        await get_fish_voices("key", (PINNED,))
        assert calls[-1] == ("key", (PINNED,)) and len(calls) == 4

    async def test_without_redis_the_vendor_is_read(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def broken() -> Any:
            raise OSError("redis down")

        monkeypatch.setattr(module, "get_redis_cache", broken)
        monkeypatch.setattr(voices_catalog, "get_redis_cache", broken)
        calls = self.listing(monkeypatch)
        assert len(await get_fish_voices("key")) == 1
        assert len(calls) == 1

    async def test_a_peek_never_asks_the_vendor(
        self, redis: _Redis, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # What a voice turn reads (ADR-345 amendment): a cold cache answers None.
        calls = self.listing(monkeypatch)
        assert await peek_fish_voices("key", (PINNED,)) is None
        await get_fish_voices("key", (PINNED,))
        assert await peek_fish_voices("key", (PINNED,)) == [
            VoiceOption(OWN, "Own", "female", "fr", {"source": "own"})
        ]
        assert await peek_fish_voices("key") is None  # another pin set is another list
        assert len(calls) == 1
