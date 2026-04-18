"""
Unit tests for the memory consolidation pure helpers.

Covers:
- _pick_survivor: deterministic cascade (importance > completeness > recency)
- _should_skip: category/emotional divergence rules

SQL-level filters (pinned exclusion, similarity threshold) live in the
repository and are exercised at integration level elsewhere.
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from src.infrastructure.scheduler.memory_consolidation import (
    _pick_survivor,
    _should_skip,
)


def _make_memory(
    *,
    id_: str = "uuid",
    importance: float = 0.7,
    content: str = "content",
    category: str = "preference",
    emotional_weight: int = 0,
    age_days: int = 0,
):
    return SimpleNamespace(
        id=id_,
        importance=importance,
        content=content,
        category=category,
        emotional_weight=emotional_weight,
        created_at=datetime.now(UTC) - timedelta(days=age_days),
    )


@pytest.mark.unit
class TestPickSurvivor:
    """Deterministic cascade: importance > completeness > recency."""

    def test_higher_importance_wins(self):
        mem_a = _make_memory(id_="a", importance=0.9, content="short")
        mem_b = _make_memory(id_="b", importance=0.5, content="a much longer content")

        survivor, loser = _pick_survivor(mem_a, mem_b)

        assert survivor.id == "a"
        assert loser.id == "b"

    def test_higher_importance_wins_regardless_of_order(self):
        """Symmetry check: reversing the argument order should flip nothing."""
        mem_low = _make_memory(id_="low", importance=0.5)
        mem_high = _make_memory(id_="high", importance=0.9)

        survivor_ab, _ = _pick_survivor(mem_low, mem_high)
        survivor_ba, _ = _pick_survivor(mem_high, mem_low)

        assert survivor_ab.id == "high"
        assert survivor_ba.id == "high"

    def test_longer_content_wins_when_importance_equal(self):
        mem_short = _make_memory(id_="short", importance=0.7, content="short")
        mem_long = _make_memory(id_="long", importance=0.7, content="a much longer content string")

        survivor, loser = _pick_survivor(mem_short, mem_long)

        assert survivor.id == "long"
        assert loser.id == "short"

    def test_recency_wins_when_importance_and_length_equal(self):
        mem_old = _make_memory(id_="old", importance=0.7, content="same", age_days=30)
        mem_new = _make_memory(id_="new", importance=0.7, content="same", age_days=5)

        survivor, loser = _pick_survivor(mem_old, mem_new)

        assert survivor.id == "new"
        assert loser.id == "old"

    def test_none_created_at_loses_to_dated_memory(self):
        """Defensive: a memory with no created_at shouldn't win the recency tiebreaker."""
        mem_dated = _make_memory(id_="dated", importance=0.7, content="same", age_days=10)
        mem_undated = _make_memory(id_="undated", importance=0.7, content="same")
        mem_undated.created_at = None

        survivor, _ = _pick_survivor(mem_dated, mem_undated)

        assert survivor.id == "dated"


@pytest.mark.unit
class TestShouldSkip:
    """Skip rules: category divergence and emotional weight gap."""

    EMOTIONAL_DIFF_SKIP = 5

    def test_same_category_similar_weights_not_skipped(self):
        mem_a = _make_memory(category="preference", emotional_weight=3)
        mem_b = _make_memory(category="preference", emotional_weight=5)

        result = _should_skip(mem_a, mem_b, self.EMOTIONAL_DIFF_SKIP)

        assert result is None

    def test_different_categories_skipped(self):
        mem_a = _make_memory(category="preference", emotional_weight=3)
        mem_b = _make_memory(category="event", emotional_weight=3)

        result = _should_skip(mem_a, mem_b, self.EMOTIONAL_DIFF_SKIP)

        assert result == "categories_differ"

    def test_emotional_diff_exceeding_threshold_skipped(self):
        mem_a = _make_memory(category="sensitivity", emotional_weight=-7)
        mem_b = _make_memory(category="sensitivity", emotional_weight=2)

        result = _should_skip(mem_a, mem_b, self.EMOTIONAL_DIFF_SKIP)

        assert result == "emotional_diff"

    def test_emotional_diff_at_threshold_not_skipped(self):
        """Boundary: |weight_a - weight_b| == threshold → not skipped (> only)."""
        mem_a = _make_memory(category="preference", emotional_weight=0)
        mem_b = _make_memory(category="preference", emotional_weight=5)

        result = _should_skip(mem_a, mem_b, self.EMOTIONAL_DIFF_SKIP)

        assert result is None

    def test_category_check_precedes_emotional_check(self):
        """When both fail, category reason takes priority."""
        mem_a = _make_memory(category="preference", emotional_weight=-7)
        mem_b = _make_memory(category="event", emotional_weight=5)

        result = _should_skip(mem_a, mem_b, self.EMOTIONAL_DIFF_SKIP)

        assert result == "categories_differ"
