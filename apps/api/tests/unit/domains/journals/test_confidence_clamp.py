"""Epistemic clamp on journal confidence (audit B-06, lot 2).

The ``JournalEntryConfidence`` contract says high = "confirmed by repeated
evidence", transitions "based on the visible evidence_count" — yet prod held
six entries at ``confidence=high`` with ``evidence_count=0`` everywhere: the
LLM promoted without proof and nothing stopped it. The clamp makes the
docstring true in code: an L0/L1 directive cannot hold ``high`` while its
``evidence_count`` is zero (demoted to ``medium``, logged, counted). L2/L3
stay free — their evidence is cross-entry convergence, not a reaction
counter.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.journals.models import (
    JournalEntry,
    JournalEntryConfidence,
    JournalEntryLevel,
)
from src.domains.journals.service import JournalService

pytestmark = pytest.mark.unit


def _make_entry(
    *,
    level: str = JournalEntryLevel.L1.value,
    confidence: str = JournalEntryConfidence.MEDIUM.value,
    evidence_count: int = 0,
) -> JournalEntry:
    entry = JournalEntry(
        user_id=uuid4(),
        theme="user_observations",
        title="Test entry",
        content="Test content body",
        mood="reflective",
        status="active",
        source="conversation",
        char_count=len("Test content body"),
        level=level,
        confidence=confidence,
        evidence_count=evidence_count,
        contradiction_count=0,
    )
    entry.id = uuid4()
    return entry


def _service() -> JournalService:
    service = JournalService(MagicMock())
    service.repo = MagicMock()
    service.repo.update = AsyncMock(side_effect=lambda e: e)
    service.repo.create = AsyncMock(side_effect=lambda e: e)
    return service


class TestUpdateClamp:
    async def test_l1_high_without_evidence_is_demoted(self) -> None:
        entry = _make_entry(evidence_count=0)
        await _service().update_entry(entry, confidence="high")
        assert entry.confidence == JournalEntryConfidence.MEDIUM.value

    async def test_l1_high_with_evidence_is_accepted(self) -> None:
        entry = _make_entry(evidence_count=2)
        await _service().update_entry(entry, confidence="high")
        assert entry.confidence == JournalEntryConfidence.HIGH.value

    async def test_same_update_evidence_signal_counts_toward_the_clamp(self) -> None:
        """A confirming signal in the SAME update legitimises the promotion:
        the increment is applied before the clamp reads the counter."""
        entry = _make_entry(evidence_count=0)
        await _service().update_entry(entry, confidence="high", evidence_outcome="evidence")
        assert entry.evidence_count == 1
        assert entry.confidence == JournalEntryConfidence.HIGH.value

    async def test_l2_high_without_evidence_is_accepted(self) -> None:
        """L2 patterns earn high through cross-entry convergence."""
        entry = _make_entry(level=JournalEntryLevel.L2.value, evidence_count=0)
        await _service().update_entry(entry, confidence="high")
        assert entry.confidence == JournalEntryConfidence.HIGH.value

    async def test_promotion_to_l2_in_same_update_is_accepted(self) -> None:
        """The clamp judges the FINAL level: an L1 merged into an L2 pattern
        by consolidation may carry high on the same action."""
        entry = _make_entry(evidence_count=0)
        await _service().update_entry(entry, confidence="high", level="L2")
        assert entry.confidence == JournalEntryConfidence.HIGH.value

    async def test_low_and_medium_pass_through(self) -> None:
        entry = _make_entry(evidence_count=0)
        await _service().update_entry(entry, confidence="low")
        assert entry.confidence == JournalEntryConfidence.LOW.value


class TestCreateClamp:
    async def test_created_l1_cannot_be_born_high(self) -> None:
        """A fresh directive has zero evidence by definition."""
        with patch(
            "src.domains.journals.service._generate_dual_embeddings",
            AsyncMock(return_value=(None, None)),
        ):
            created = await _service().create_entry(
                user_id=uuid4(),
                theme="learnings",
                title="t",
                content="c",
                confidence="high",
                level="L1",
            )
        assert created.confidence == JournalEntryConfidence.MEDIUM.value

    async def test_created_l2_may_be_born_high(self) -> None:
        with patch(
            "src.domains.journals.service._generate_dual_embeddings",
            AsyncMock(return_value=(None, None)),
        ):
            created = await _service().create_entry(
                user_id=uuid4(),
                theme="learnings",
                title="t",
                content="c",
                confidence="high",
                level="L2",
            )
        assert created.confidence == JournalEntryConfidence.HIGH.value
