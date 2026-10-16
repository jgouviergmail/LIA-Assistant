"""Designed voices wait server-side until one is saved or they expire (ADR-345)."""

from __future__ import annotations

from typing import Any

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from src.core.constants import FISHAUDIO_DESIGN_CANDIDATE_TTL_SECONDS
from src.domains.voice.fishaudio import design_store
from src.domains.voice.fishaudio.design_store import (
    DesignStoreUnavailable,
    keep_candidates,
    stored_candidate,
)
from src.domains.voice.fishaudio.library import DesignCandidate

pytestmark = pytest.mark.unit


class _Redis:
    def __init__(self, *, down: bool = False) -> None:
        self.store: dict[str, str] = {}
        self.expiries: dict[str, int] = {}
        self.down = down

    def _check(self) -> None:
        if self.down:
            raise RedisConnectionError("unreachable")

    async def set(self, key: str, value: str, ex: int) -> None:
        self._check()
        self.store[key], self.expiries[key] = value, ex

    async def get(self, key: str) -> str | None:
        self._check()
        return self.store.get(key)


@pytest.fixture
def redis(monkeypatch: pytest.MonkeyPatch) -> _Redis:
    fake = _Redis()

    async def _get() -> Any:
        return fake

    monkeypatch.setattr(design_store, "get_redis_cache", _get)
    return fake


def candidate(audio: bytes = b"RIFF-wav", text: str | None = "Hello.") -> DesignCandidate:
    return DesignCandidate(audio=audio, duration_ms=3100, text=text, language="en")


class TestTheCandidates:
    async def test_each_is_kept_under_a_fresh_id_until_it_expires(self, redis: _Redis) -> None:
        kept = await keep_candidates(
            [candidate(b"one"), candidate(b"two", text=None)],
            credential_fingerprint="test-credential",
        )

        assert len({item.candidate_id for item in kept}) == 2
        assert set(redis.expiries.values()) == {FISHAUDIO_DESIGN_CANDIDATE_TTL_SECONDS}
        assert await stored_candidate(kept[1].candidate_id) == candidate(b"two", text=None)

    @pytest.mark.parametrize("candidate_id", ["../../x", "A" * 32, ""])
    async def test_an_id_lia_never_minted_reads_nothing(
        self, redis: _Redis, candidate_id: str
    ) -> None:
        assert await stored_candidate(candidate_id) is None

    async def test_an_unreadable_record_reads_nothing(self, redis: _Redis) -> None:
        redis.store[f"fishaudio:design:{'a' * 32}"] = "{not json"

        assert await stored_candidate("a" * 32) is None


class TestWithoutRedis:
    async def test_keeping_or_reading_says_so(self, redis: _Redis) -> None:
        redis.down = True

        with pytest.raises(DesignStoreUnavailable):
            await keep_candidates([candidate()], credential_fingerprint="test-credential")
        with pytest.raises(DesignStoreUnavailable):
            await stored_candidate("a" * 32)
