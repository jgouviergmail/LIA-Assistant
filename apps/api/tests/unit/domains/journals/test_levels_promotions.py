"""Unit tests for level promotions and atomic counter increments (ADR-079).

Validates the contract of ``JournalService.update_entry`` for the three
new fields it introduces:

- ``level``: any change emits ``journal_consolidation_promotions_total``.
- ``confidence``: passes through transparently.
- ``evidence_outcome``: never accepts an absolute count — the service
  atomically increments the right counter and emits ``journal_evidence_total``.

These guards back the fourth anti-hallucination layer described in
ADR-079: the LLM signals an outcome, the service owns the integers.
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


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------


def _make_entry(
    *,
    level: str = JournalEntryLevel.L1.value,
    confidence: str = JournalEntryConfidence.MEDIUM.value,
    evidence_count: int = 0,
    contradiction_count: int = 0,
) -> JournalEntry:
    """Build an in-memory JournalEntry with sane defaults — no DB round-trip."""
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
        contradiction_count=contradiction_count,
    )
    entry.id = uuid4()
    return entry


def _make_service() -> tuple[JournalService, AsyncMock]:
    """Return a service whose repo + embeddings are stubbed.

    The stubbed repo simply echoes back the entry passed to ``update``.
    Embeddings are stubbed to skip the network call entirely.
    """
    session = MagicMock(name="AsyncSession")
    service = JournalService(session)

    repo_mock = MagicMock(name="JournalEntryRepository")
    repo_mock.update = AsyncMock(side_effect=lambda e: e)
    service.repo = repo_mock
    return service, repo_mock


# -----------------------------------------------------------------------------
# Level promotion path
# -----------------------------------------------------------------------------


class TestLevelPromotion:
    """``level`` updates must mutate the entry and emit the promotion metric."""

    @pytest.mark.asyncio
    async def test_level_change_l1_to_l2_emits_promotion_metric(self) -> None:
        service, _ = _make_service()
        entry = _make_entry(level=JournalEntryLevel.L1.value)

        counter = MagicMock(name="PromotionsCounter")
        counter.labels.return_value = counter

        with (
            patch(
                "src.domains.journals.service.journal_consolidation_promotions_total",
                counter,
            ),
            patch(
                "src.domains.journals.service._generate_dual_embeddings",
                AsyncMock(return_value=(None, None)),
            ),
        ):
            await service.update_entry(entry, level=JournalEntryLevel.L2.value)

        assert entry.level == JournalEntryLevel.L2.value
        counter.labels.assert_called_once_with(from_level="L1", to_level="L2")
        counter.inc.assert_called_once()

    @pytest.mark.asyncio
    async def test_level_unchanged_does_not_emit_metric(self) -> None:
        service, _ = _make_service()
        entry = _make_entry(level=JournalEntryLevel.L1.value)

        counter = MagicMock(name="PromotionsCounter")

        with (
            patch(
                "src.domains.journals.service.journal_consolidation_promotions_total",
                counter,
            ),
            patch(
                "src.domains.journals.service._generate_dual_embeddings",
                AsyncMock(return_value=(None, None)),
            ),
        ):
            await service.update_entry(entry, level=JournalEntryLevel.L1.value)

        # Same level → no promotion event.
        counter.labels.assert_not_called()
        counter.inc.assert_not_called()

    @pytest.mark.asyncio
    async def test_level_demotion_l2_to_l1_also_emits(self) -> None:
        """Demotions are tracked too — `from_level` / `to_level` not directional."""
        service, _ = _make_service()
        entry = _make_entry(level=JournalEntryLevel.L2.value)

        counter = MagicMock(name="PromotionsCounter")
        counter.labels.return_value = counter

        with (
            patch(
                "src.domains.journals.service.journal_consolidation_promotions_total",
                counter,
            ),
            patch(
                "src.domains.journals.service._generate_dual_embeddings",
                AsyncMock(return_value=(None, None)),
            ),
        ):
            await service.update_entry(entry, level=JournalEntryLevel.L1.value)

        counter.labels.assert_called_once_with(from_level="L2", to_level="L1")


# -----------------------------------------------------------------------------
# Atomic counter increments via evidence_outcome
# -----------------------------------------------------------------------------


class TestEvidenceOutcomeIncrements:
    """The LLM signals an outcome; the service owns the integer."""

    @pytest.mark.asyncio
    async def test_evidence_outcome_increments_evidence_count(self) -> None:
        service, _ = _make_service()
        entry = _make_entry(evidence_count=3, contradiction_count=1)

        counter = MagicMock(name="EvidenceCounter")
        counter.labels.return_value = counter

        with (
            patch("src.domains.journals.service.journal_evidence_total", counter),
            patch(
                "src.domains.journals.service._generate_dual_embeddings",
                AsyncMock(return_value=(None, None)),
            ),
        ):
            await service.update_entry(entry, evidence_outcome="evidence")

        # Atomic +1 — never an absolute write.
        assert entry.evidence_count == 4
        assert entry.contradiction_count == 1  # untouched
        counter.labels.assert_called_once_with(outcome="evidence")
        counter.inc.assert_called_once()

    @pytest.mark.asyncio
    async def test_contradiction_outcome_increments_contradiction_count(self) -> None:
        service, _ = _make_service()
        entry = _make_entry(evidence_count=2, contradiction_count=0)

        counter = MagicMock(name="EvidenceCounter")
        counter.labels.return_value = counter

        with (
            patch("src.domains.journals.service.journal_evidence_total", counter),
            patch(
                "src.domains.journals.service._generate_dual_embeddings",
                AsyncMock(return_value=(None, None)),
            ),
        ):
            await service.update_entry(entry, evidence_outcome="contradiction")

        assert entry.contradiction_count == 1
        assert entry.evidence_count == 2  # untouched
        counter.labels.assert_called_once_with(outcome="contradiction")

    @pytest.mark.asyncio
    async def test_unknown_outcome_increments_nothing(self) -> None:
        """Defensive: an unknown outcome string is ignored — never crash, never increment."""
        service, _ = _make_service()
        entry = _make_entry(evidence_count=5, contradiction_count=2)

        counter = MagicMock(name="EvidenceCounter")

        with (
            patch("src.domains.journals.service.journal_evidence_total", counter),
            patch(
                "src.domains.journals.service._generate_dual_embeddings",
                AsyncMock(return_value=(None, None)),
            ),
        ):
            await service.update_entry(entry, evidence_outcome="garbage_value")

        assert entry.evidence_count == 5
        assert entry.contradiction_count == 2
        counter.labels.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_outcome_leaves_counters_unchanged(self) -> None:
        service, _ = _make_service()
        entry = _make_entry(evidence_count=7, contradiction_count=3)

        with patch(
            "src.domains.journals.service._generate_dual_embeddings",
            AsyncMock(return_value=(None, None)),
        ):
            await service.update_entry(entry, confidence=JournalEntryConfidence.HIGH.value)

        assert entry.confidence == JournalEntryConfidence.HIGH.value
        assert entry.evidence_count == 7
        assert entry.contradiction_count == 3


# -----------------------------------------------------------------------------
# Confidence pass-through
# -----------------------------------------------------------------------------


class TestConfidencePassthrough:
    """Confidence writes pass through EXCEPT the epistemic clamp (B-06):
    an L0/L1 cannot reach `high` with evidence_count=0 — the exact prod
    defect this suite used to pin as correct behavior (2026-08-19)."""

    @pytest.mark.asyncio
    async def test_confidence_low_to_high_requires_evidence_on_l1(self) -> None:
        service, _ = _make_service()
        entry = _make_entry(confidence=JournalEntryConfidence.LOW.value, evidence_count=1)

        with patch(
            "src.domains.journals.service._generate_dual_embeddings",
            AsyncMock(return_value=(None, None)),
        ):
            await service.update_entry(entry, confidence=JournalEntryConfidence.HIGH.value)

        assert entry.confidence == JournalEntryConfidence.HIGH.value

    @pytest.mark.asyncio
    async def test_confidence_high_without_evidence_is_clamped_on_l1(self) -> None:
        service, _ = _make_service()
        entry = _make_entry(confidence=JournalEntryConfidence.LOW.value, evidence_count=0)

        with patch(
            "src.domains.journals.service._generate_dual_embeddings",
            AsyncMock(return_value=(None, None)),
        ):
            await service.update_entry(entry, confidence=JournalEntryConfidence.HIGH.value)

        assert entry.confidence == JournalEntryConfidence.MEDIUM.value


# -----------------------------------------------------------------------------
# Combined: realistic consolidation scenario
# -----------------------------------------------------------------------------


class TestCombinedUpdate:
    """The service handles level + confidence + outcome in one call (consolidation pattern)."""

    @pytest.mark.asyncio
    async def test_promotion_with_evidence_and_confidence_upgrade(self) -> None:
        service, _ = _make_service()
        entry = _make_entry(
            level=JournalEntryLevel.L1.value,
            confidence=JournalEntryConfidence.MEDIUM.value,
            evidence_count=4,
        )

        promotion_counter = MagicMock(name="PromotionsCounter")
        promotion_counter.labels.return_value = promotion_counter
        evidence_counter = MagicMock(name="EvidenceCounter")
        evidence_counter.labels.return_value = evidence_counter

        with (
            patch(
                "src.domains.journals.service.journal_consolidation_promotions_total",
                promotion_counter,
            ),
            patch(
                "src.domains.journals.service.journal_evidence_total",
                evidence_counter,
            ),
            patch(
                "src.domains.journals.service._generate_dual_embeddings",
                AsyncMock(return_value=(None, None)),
            ),
        ):
            await service.update_entry(
                entry,
                level=JournalEntryLevel.L2.value,
                confidence=JournalEntryConfidence.HIGH.value,
                evidence_outcome="evidence",
            )

        assert entry.level == JournalEntryLevel.L2.value
        assert entry.confidence == JournalEntryConfidence.HIGH.value
        assert entry.evidence_count == 5
        promotion_counter.labels.assert_called_once_with(from_level="L1", to_level="L2")
        evidence_counter.labels.assert_called_once_with(outcome="evidence")
