"""The chat cards a turn queues for its answer (ADR-226, ADR-279, ADR-327).

One store shape for every card family: queued by whatever produced it, PEEKED
by the archive (the row must carry it across a reload), TAKEN by the done
chunk (which frees it). Conversations never see each other's cards.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

import pytest

from src.domains.shared.pending_cards import PendingCards

pytestmark = pytest.mark.unit


@dataclass(frozen=True)
class _Card:
    name: str


def test_peek_keeps_what_take_then_frees() -> None:
    cards: PendingCards[_Card] = PendingCards("test")
    cards.add("c1", _Card("a"))
    cards.add("c1", _Card("b"))

    assert [c.name for c in cards.peek("c1")] == ["a", "b"]
    assert [c.name for c in cards.take("c1")] == ["a", "b"]
    assert cards.peek("c1") == []
    assert cards.take("c1") == []


def test_conversations_are_isolated() -> None:
    cards: PendingCards[_Card] = PendingCards("test")
    cards.add("c1", _Card("a"))

    assert cards.peek("c2") == []
    assert cards.take("c2") == []
    assert [c.name for c in cards.take("c1")] == ["a"]


def test_a_peeked_list_is_a_copy() -> None:
    cards: PendingCards[_Card] = PendingCards("test")
    cards.add("c1", _Card("a"))

    cards.peek("c1").append(_Card("intruder"))

    assert [c.name for c in cards.peek("c1")] == ["a"]


def test_clear_forgets_every_conversation() -> None:
    cards: PendingCards[_Card] = PendingCards("test")
    cards.add("c1", _Card("a"))
    cards.add("c2", _Card("b"))

    cards.clear()

    assert cards.peek("c1") == [] and cards.peek("c2") == []


def test_concurrent_adds_are_all_kept() -> None:
    cards: PendingCards[_Card] = PendingCards("test")

    def add_many(prefix: str) -> None:
        for index in range(200):
            cards.add("c1", _Card(f"{prefix}{index}"))

    threads = [threading.Thread(target=add_many, args=(p,)) for p in "abcd"]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(cards.take("c1")) == 800
