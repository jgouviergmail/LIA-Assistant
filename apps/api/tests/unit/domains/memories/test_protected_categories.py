"""A directive is corrected, never deleted (owner arbitration, 2026-09-10).

``procedural`` memories are the standing instructions a person gave about HOW
LIA should work for them (ADR-236). Every other category is a FACT LIA inferred
and may re-infer; a directive was DICTATED, and nothing automated may take it
back — not the retention sweep, not the extractor's delete action, not the
consolidation that merges near-duplicates by destroying one of them.

What stays allowed, deliberately: correcting one (``supersede_with_update``
files a successor and retires the old row — the fact leaves the active set WITH
a replacement), editing one in place, and the person deleting their own. The
rule is therefore not "this row is frozen" but **"it never leaves the active
set without a successor"**.

Pinning was considered and rejected by the owner: pinned means user-LOCKED,
which would also block the corrections that keep a directive true.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from src.domains.memories.models import MemoryCategory, PurgeRiskLevel
from src.domains.memories.protection import (
    PROTECTED_CATEGORIES,
    is_protected_from_deletion,
)
from src.domains.memories.retention import (
    RetentionConfig,
    classify_purge_risk,
    should_purge,
)

pytestmark = pytest.mark.unit

_OLD = datetime.now(UTC) - timedelta(days=400)

_PURGE_ARGS: dict[str, Any] = {
    "min_age_for_cleanup_days": 30,
    "recency_decay_days": 90,
    "usage_penalty_age_days": 60,
    "usage_penalty_factor": 0.5,
    "purge_threshold": 0.9,
    "weight_importance": 0.5,
    "weight_recency": 0.5,
}

_CONFIG = RetentionConfig(at_risk_margin=0.05, **_PURGE_ARGS)


def _memory(category: str, *, pinned: bool = False) -> Any:
    """A memory old enough and dull enough to be purged, but for its category."""
    return SimpleNamespace(
        category=category,
        pinned=pinned,
        importance=0.0,
        created_at=_OLD,
        last_accessed_at=None,
        usage_count=0,
        invalidated_at=None,
    )


class TestTheVocabularyOfProtection:
    def test_only_the_dictated_category_is_protected(self) -> None:
        assert PROTECTED_CATEGORIES == frozenset({MemoryCategory.PROCEDURAL.value})

    def test_the_predicate_answers_for_a_raw_string(self) -> None:
        """The column stores a string; the predicate must not demand an enum."""
        assert is_protected_from_deletion("procedural") is True
        assert is_protected_from_deletion("preference") is False

    def test_an_unknown_category_is_not_protected(self) -> None:
        """A category nobody declared is a fact like any other, never a
        directive by default — a permissive fallback here would silently
        freeze rows."""
        assert is_protected_from_deletion("who_knows") is False

    def test_none_is_not_protected(self) -> None:
        assert is_protected_from_deletion(None) is False

    def test_every_protected_value_is_a_real_category(self) -> None:
        assert PROTECTED_CATEGORIES <= {member.value for member in MemoryCategory}


class TestTheRetentionSweepNeverPurgesADirective:
    def test_a_stale_directive_survives_the_sweep(self) -> None:
        purge, score = should_purge(_memory("procedural"), datetime.now(UTC), **_PURGE_ARGS)

        assert purge is False
        assert score == 1.0

    def test_the_same_row_in_any_other_category_is_purged(self) -> None:
        """Falsifies the test above: the fixture really is purge-eligible."""
        purge, _score = should_purge(_memory("preference"), datetime.now(UTC), **_PURGE_ARGS)

        assert purge is True

    def test_the_badge_says_protected_rather_than_a_score(self) -> None:
        risk, score = classify_purge_risk(_memory("procedural"), datetime.now(UTC), _CONFIG)

        assert risk is PurgeRiskLevel.PROTECTED
        assert score is None

    def test_a_pinned_directive_is_still_protected(self) -> None:
        """Two reasons to protect are not a contradiction."""
        risk, _score = classify_purge_risk(
            _memory("procedural", pinned=True), datetime.now(UTC), _CONFIG
        )

        assert risk is PurgeRiskLevel.PROTECTED


class TestTheBadgeStaysHonestForEveryOtherCategory:
    def test_a_stale_fact_is_announced_as_imminent(self) -> None:
        """Falsifies the protected assertions: the fixture really is at risk."""
        risk, score = classify_purge_risk(_memory("preference"), datetime.now(UTC), _CONFIG)

        assert risk is PurgeRiskLevel.IMMINENT
        assert score is not None


class TestTheServiceRefusesToRetireADirectiveAlone:
    """``invalidate_memory`` retires a row with NO successor — a deletion."""

    @staticmethod
    def _service() -> Any:
        from unittest.mock import AsyncMock, MagicMock

        from src.domains.memories.service import MemoryService

        service = MemoryService(MagicMock())
        service.repo = MagicMock()
        service.repo.update = AsyncMock()
        return service

    @pytest.mark.asyncio
    async def test_a_directive_cannot_be_invalidated(self) -> None:
        service = self._service()
        memory = _memory("procedural")
        memory.id = "m1"

        with pytest.raises(ValueError, match="directive"):
            await service.invalidate_memory(memory)

        service.repo.update.assert_not_awaited()
        assert memory.invalidated_at is None

    @pytest.mark.asyncio
    async def test_any_other_category_is_invalidated_as_before(self) -> None:
        """Falsifies the refusal above."""
        service = self._service()
        memory = _memory("preference")
        memory.id = "m2"
        memory.user_id = "u1"

        await service.invalidate_memory(memory)

        assert memory.invalidated_at is not None

    @pytest.mark.asyncio
    async def test_a_directive_is_still_CORRECTABLE_by_supersession(self) -> None:
        """The whole point: a directive is corrected, not frozen."""
        from unittest.mock import AsyncMock

        service = self._service()
        successor = _memory("procedural")
        successor.id = "m4"
        service.create_memory = AsyncMock(return_value=successor)
        memory = _memory("procedural")
        memory.id = "m3"
        memory.user_id = "u1"
        memory.content = "Answer me in French"
        memory.emotional_weight = 0
        memory.trigger_topic = ""
        memory.usage_nuance = ""

        result = await service.supersede_with_update(memory, content="Answer me in English")

        assert result is successor
        assert memory.superseded_by_id == "m4"
        assert memory.invalidated_at is not None


class TestConsolidationNeverPairsADirective:
    def test_the_pair_query_excludes_every_protected_category(self) -> None:
        """Consolidation DESTROYS the loser of a pair; a directive is never a
        candidate, so the exclusion lives in SQL rather than in a Python
        post-filter a future caller could forget."""
        import inspect

        from src.domains.memories.repository import MemoryRepository

        source = inspect.getsource(MemoryRepository.find_consolidation_pairs)
        assert source.count("category.not_in(PROTECTED_CATEGORIES)") == 2
