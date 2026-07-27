"""Tests for dedup hardening and retro-merge pairing (ADR-131)."""

import uuid
from datetime import UTC, datetime

import pytest

from src.infrastructure.scheduler.interest_cleanup import find_duplicate_pairs


class FakeInterest:
    def __init__(self, topic: str, embedding: list[float] | None, positive: int = 1) -> None:
        self.id = uuid.uuid4()
        self.topic = topic
        self.embedding = embedding
        self.positive_signals = positive
        self.created_at = datetime.now(UTC)


@pytest.mark.unit
class TestFindDuplicatePairs:
    def test_case_variant_is_duplicate_even_without_embeddings(self) -> None:
        a = FakeInterest("Anthropic", None, positive=10)
        b = FakeInterest("anthropic", None, positive=3)
        pairs = find_duplicate_pairs([a, b], threshold=0.95)
        assert pairs == [(a, b)]  # higher positive_signals wins

    def test_high_cosine_is_duplicate(self) -> None:
        a = FakeInterest("Anthropic", [1.0, 0.0, 0.0], positive=5)
        b = FakeInterest("anthropic AI", [0.999, 0.04, 0.0], positive=2)
        assert find_duplicate_pairs([a, b], threshold=0.95) == [(a, b)]

    def test_below_threshold_not_duplicate(self) -> None:
        a = FakeInterest("Bitcoin", [1.0, 0.0], positive=5)
        b = FakeInterest("Cryptomonnaies", [0.89, 0.454], positive=2)  # cos ~0.89
        assert find_duplicate_pairs([a, b], threshold=0.95) == []

    def test_transitive_chain_keeps_single_winner(self) -> None:
        a = FakeInterest("X", None, positive=9)
        b = FakeInterest("x", None, positive=5)
        c = FakeInterest("X ", None, positive=1)  # strip-equal
        pairs = find_duplicate_pairs([a, b, c], threshold=0.95)
        keeps = {id(k) for k, _ in pairs}
        assert keeps == {id(a)}
        assert len(pairs) == 2

    def test_distinct_topics_without_embeddings_untouched(self) -> None:
        a = FakeInterest("Bitcoin", None, positive=5)
        b = FakeInterest("Patagonie", None, positive=2)
        assert find_duplicate_pairs([a, b], threshold=0.95) == []
