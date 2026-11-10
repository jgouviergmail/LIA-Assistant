"""Blind substring candidates must never discard a literal display match."""

import asyncio
import threading
from uuid import UUID

import pytest

from src.domains.shared.text_normalization import normalize_search_text
from src.domains.sms import index_projection
from src.domains.sms.display_index import display_hashes

pytestmark = pytest.mark.unit
OWNER = UUID(int=1)
KEY = b"d" * 32


async def test_index_preparation_keeps_the_event_loop_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = index_projection.build_index_projection(OWNER, "sender", "Café", key=KEY)
    release = threading.Event()

    def cpu_work(
        owner: UUID, sender: str, body: str, *, key: bytes
    ) -> index_projection.SmsIndexProjection:
        assert release.wait(timeout=1), "CPU preparation blocked the event loop"
        return expected

    monkeypatch.setattr(index_projection, "build_index_projection", cpu_work)
    preparation = asyncio.create_task(
        index_projection.prepare_index_projection(OWNER, "sender", "Café", key=KEY)
    )
    asyncio.get_running_loop().call_soon(release.set)
    assert await preparation == expected


def test_every_matching_fragment_is_admitted_by_the_blind_projection() -> None:
    for text in (
        "Été l’été 100%_ Café",
        "東京のニュース中文",
        "emoji 🥳 abcd",
        "İΣΟΣ Straße",
        "a\u202fb a\u00a0b",
    ):
        body = normalize_search_text(text)
        indexed = set(display_hashes(OWNER, text, key=KEY))
        for start in range(len(body)):
            for end in range(start + 1, len(body) + 1):
                needle = body[start:end]
                assert set(display_hashes(OWNER, needle, key=KEY)) <= indexed


def test_short_queries_have_no_narrowing_hash_and_trigrams_are_only_candidates() -> None:
    assert display_hashes(OWNER, "a", key=KEY) == ()
    assert display_hashes(OWNER, "ab", key=KEY) == ()
    assert set(display_hashes(OWNER, "abcd", key=KEY)) <= set(
        display_hashes(OWNER, "abc---bcd", key=KEY)
    )
    assert "abcd" not in "abc---bcd"
    assert display_hashes(OWNER, "abcd", key=KEY) != display_hashes(UUID(int=2), "abcd", key=KEY)
