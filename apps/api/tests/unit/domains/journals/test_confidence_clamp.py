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
    JournalEntryConfidence,
)
from src.domains.journals.service import JournalService, _clamp_confidence

pytestmark = pytest.mark.unit


def _service() -> JournalService:
    service = JournalService(MagicMock())
    service.repo = MagicMock()
    service.repo.create = AsyncMock(side_effect=lambda e: e)
    return service


class TestUpdateClamp:
    def test_l1_high_without_evidence_is_demoted(self) -> None:
        assert _clamp_confidence("high", "L1", 0, "update") == "medium"

    def test_l1_high_with_repeated_evidence_is_accepted(self) -> None:
        assert _clamp_confidence("high", "L1", 2, "update") == "high"

    def test_first_reaction_cannot_certify_repeated_evidence(self) -> None:
        assert _clamp_confidence("high", "L1", 1, "update") == "medium"

    def test_contradicted_rule_is_low_even_after_positive_evidence(self) -> None:
        assert _clamp_confidence("high", "L1", 10, "update", contradiction_count=1) == "low"

    def test_l2_high_without_reactions_is_accepted(self) -> None:
        assert _clamp_confidence("high", "L2", 0, "update") == "high"

    def test_low_and_medium_pass_through_without_contradictions(self) -> None:
        assert _clamp_confidence("low", "L1", 0, "update") == "low"
        assert _clamp_confidence("medium", "L1", 0, "update") == "medium"


@pytest.fixture(autouse=True)
def stub_persistence_lifecycle(monkeypatch):
    monkeypatch.setattr("src.domains.journals.service.lock_journal_owner", AsyncMock())
    monkeypatch.setattr("src.domains.journals.service.mark_journal_changed", AsyncMock())


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
