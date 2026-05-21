"""Unit tests for the pure memory retention logic.

Moved from tests/unit/infrastructure/scheduler/test_memory_cleanup.py when the
scoring functions were extracted to src/domains/memories/retention.py.

Covers the pure scoring functions:
- calculate_retention_score: importance + recency + usage penalty
- should_purge: grace period, pinned protection, threshold decision
- classify_purge_risk: 4-state read-only purge-risk classification

Critical calibration points verified:
- importance=0.5 at 30 days is purged (product requirement)
- importance=0.9 old memories stay as long as they are activated
- Never-activated memories past grace period are penalized
- Pinned memories are always protected
- Memories within grace period are never purged
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import cast

import pytest

from src.domains.memories.models import Memory, PurgeRiskLevel
from src.domains.memories.retention import (
    RetentionConfig,
    calculate_retention_score,
    classify_purge_risk,
    should_purge,
)

# Calibrated defaults matching .env.example (Lot 2bis)
RECENCY_DECAY_DAYS = 45
USAGE_PENALTY_AGE_DAYS = 30
USAGE_PENALTY_FACTOR = 0.5
MIN_AGE_FOR_CLEANUP_DAYS = 7
WEIGHT_IMPORTANCE = 0.7
WEIGHT_RECENCY = 0.3
PURGE_THRESHOLD = 0.5
AT_RISK_MARGIN = 0.1


def _make_memory(
    *,
    importance: float = 0.7,
    age_days: int = 0,
    usage_count: int = 0,
    pinned: bool = False,
) -> Memory:
    """Build a minimal Memory-like object for scoring tests.

    The retention functions only read importance/created_at/usage_count/pinned,
    so a typed SimpleNamespace stand-in is sufficient (cast to Memory).
    """
    return cast(
        Memory,
        SimpleNamespace(
            importance=importance,
            usage_count=usage_count,
            pinned=pinned,
            created_at=datetime.now(UTC) - timedelta(days=age_days),
        ),
    )


def _config() -> RetentionConfig:
    """Build a RetentionConfig with the calibrated test defaults."""
    return RetentionConfig(
        min_age_for_cleanup_days=MIN_AGE_FOR_CLEANUP_DAYS,
        recency_decay_days=RECENCY_DECAY_DAYS,
        usage_penalty_age_days=USAGE_PENALTY_AGE_DAYS,
        usage_penalty_factor=USAGE_PENALTY_FACTOR,
        purge_threshold=PURGE_THRESHOLD,
        at_risk_margin=AT_RISK_MARGIN,
        weight_importance=WEIGHT_IMPORTANCE,
        weight_recency=WEIGHT_RECENCY,
    )


@pytest.mark.unit
class TestCalculateRetentionScore:
    """Tests the pure scoring formula."""

    def test_new_high_importance_memory_scores_high(self) -> None:
        mem = _make_memory(importance=0.9, age_days=10, usage_count=2)
        score = calculate_retention_score(
            mem,
            datetime.now(UTC),
            RECENCY_DECAY_DAYS,
            USAGE_PENALTY_AGE_DAYS,
            USAGE_PENALTY_FACTOR,
            WEIGHT_IMPORTANCE,
            WEIGHT_RECENCY,
        )
        # 0.7 * 0.9 + 0.3 * (1 - 10/45) = 0.63 + 0.233 = 0.863
        assert score == pytest.approx(0.863, abs=0.01)

    def test_medium_importance_at_30_days_falls_below_threshold(self) -> None:
        """Product requirement: importance=0.5 purged around 30 days."""
        mem = _make_memory(importance=0.5, age_days=30, usage_count=1)
        score = calculate_retention_score(
            mem,
            datetime.now(UTC),
            RECENCY_DECAY_DAYS,
            USAGE_PENALTY_AGE_DAYS,
            USAGE_PENALTY_FACTOR,
            WEIGHT_IMPORTANCE,
            WEIGHT_RECENCY,
        )
        # 0.7 * 0.5 + 0.3 * (1 - 30/45) = 0.35 + 0.10 = 0.45 < 0.5
        assert score < PURGE_THRESHOLD

    def test_high_importance_old_memory_stays_above_threshold(self) -> None:
        mem = _make_memory(importance=0.9, age_days=60, usage_count=2)
        score = calculate_retention_score(
            mem,
            datetime.now(UTC),
            RECENCY_DECAY_DAYS,
            USAGE_PENALTY_AGE_DAYS,
            USAGE_PENALTY_FACTOR,
            WEIGHT_IMPORTANCE,
            WEIGHT_RECENCY,
        )
        # 0.7 * 0.9 + 0.3 * 0 = 0.63 (recency_factor clamped at 0)
        assert score > PURGE_THRESHOLD
        assert score == pytest.approx(0.63, abs=0.01)

    def test_zero_usage_penalty_applied_past_threshold(self) -> None:
        """Memory past 30 days with usage_count=0 has its score halved."""
        mem = _make_memory(importance=0.9, age_days=35, usage_count=0)
        score = calculate_retention_score(
            mem,
            datetime.now(UTC),
            RECENCY_DECAY_DAYS,
            USAGE_PENALTY_AGE_DAYS,
            USAGE_PENALTY_FACTOR,
            WEIGHT_IMPORTANCE,
            WEIGHT_RECENCY,
        )
        # Base: 0.7*0.9 + 0.3*(1-35/45) = 0.63 + 0.067 = 0.697
        # After penalty: 0.697 * 0.5 = 0.348
        assert score == pytest.approx(0.348, abs=0.01)
        assert score < PURGE_THRESHOLD

    def test_zero_usage_penalty_not_applied_within_grace(self) -> None:
        """Same score, but age < penalty threshold → no penalty."""
        mem = _make_memory(importance=0.9, age_days=20, usage_count=0)
        score = calculate_retention_score(
            mem,
            datetime.now(UTC),
            RECENCY_DECAY_DAYS,
            USAGE_PENALTY_AGE_DAYS,
            USAGE_PENALTY_FACTOR,
            WEIGHT_IMPORTANCE,
            WEIGHT_RECENCY,
        )
        # 0.7 * 0.9 + 0.3 * (1 - 20/45) = 0.63 + 0.167 = 0.797 (no penalty)
        assert score == pytest.approx(0.797, abs=0.01)

    def test_positive_usage_count_suppresses_penalty(self) -> None:
        """Usage_count >= 1 past threshold: penalty does NOT apply."""
        mem = _make_memory(importance=0.9, age_days=35, usage_count=1)
        score = calculate_retention_score(
            mem,
            datetime.now(UTC),
            RECENCY_DECAY_DAYS,
            USAGE_PENALTY_AGE_DAYS,
            USAGE_PENALTY_FACTOR,
            WEIGHT_IMPORTANCE,
            WEIGHT_RECENCY,
        )
        # Same as above, but no penalty
        assert score == pytest.approx(0.697, abs=0.01)
        assert score > PURGE_THRESHOLD


@pytest.mark.unit
class TestShouldPurge:
    """Tests the purge decision function (protections + threshold)."""

    def _call(self, mem: Memory, threshold: float = PURGE_THRESHOLD) -> tuple[bool, float]:
        return should_purge(
            mem,
            datetime.now(UTC),
            MIN_AGE_FOR_CLEANUP_DAYS,
            RECENCY_DECAY_DAYS,
            USAGE_PENALTY_AGE_DAYS,
            USAGE_PENALTY_FACTOR,
            threshold,
            WEIGHT_IMPORTANCE,
            WEIGHT_RECENCY,
        )

    def test_pinned_memory_never_purged(self) -> None:
        """Even with terrible score, pinned=True forces no purge."""
        mem = _make_memory(importance=0.1, age_days=365, usage_count=0, pinned=True)
        should_delete, score = self._call(mem)

        assert should_delete is False
        assert score == 1.0  # protection short-circuits scoring

    def test_grace_period_protects_new_memory(self) -> None:
        """Age < MIN_AGE_FOR_CLEANUP_DAYS → not eligible."""
        mem = _make_memory(importance=0.1, age_days=3, usage_count=0, pinned=False)
        should_delete, score = self._call(mem)

        assert should_delete is False
        assert score == 1.0

    def test_eligible_low_score_purged(self) -> None:
        """importance=0.5 at 30 days (our calibration benchmark)."""
        mem = _make_memory(importance=0.5, age_days=30, usage_count=1, pinned=False)
        should_delete, _score = self._call(mem)

        assert should_delete is True

    def test_eligible_high_score_kept(self) -> None:
        mem = _make_memory(importance=0.9, age_days=20, usage_count=2, pinned=False)
        should_delete, score = self._call(mem)

        assert should_delete is False
        assert score > PURGE_THRESHOLD

    def test_never_activated_old_memory_purged_via_penalty(self) -> None:
        """Usage penalty brings high-importance old memory below threshold."""
        mem = _make_memory(importance=0.9, age_days=40, usage_count=0, pinned=False)
        should_delete, _score = self._call(mem)

        assert should_delete is True


@pytest.mark.unit
class TestClassifyPurgeRisk:
    """Tests the 4-state read-only purge-risk classification."""

    def test_pinned_is_protected(self) -> None:
        mem = _make_memory(importance=0.1, age_days=365, usage_count=0, pinned=True)
        risk, score = classify_purge_risk(mem, datetime.now(UTC), _config())
        assert risk == PurgeRiskLevel.PROTECTED
        assert score is None

    def test_within_grace_is_safe(self) -> None:
        mem = _make_memory(importance=0.1, age_days=3, usage_count=0)
        risk, score = classify_purge_risk(mem, datetime.now(UTC), _config())
        assert risk == PurgeRiskLevel.SAFE
        assert score is None

    def test_low_score_is_imminent(self) -> None:
        # 0.7*0.5 + 0.3*(1-30/45) = 0.45 < 0.5
        mem = _make_memory(importance=0.5, age_days=30, usage_count=1)
        risk, score = classify_purge_risk(mem, datetime.now(UTC), _config())
        assert risk == PurgeRiskLevel.IMMINENT
        assert score is not None and score < PURGE_THRESHOLD

    def test_near_threshold_is_at_risk(self) -> None:
        # 0.7*0.6 + 0.3*(1-25/45) = 0.42 + 0.133 = 0.553 -> [0.5, 0.6)
        mem = _make_memory(importance=0.6, age_days=25, usage_count=1)
        risk, score = classify_purge_risk(mem, datetime.now(UTC), _config())
        assert risk == PurgeRiskLevel.AT_RISK
        assert score is not None and PURGE_THRESHOLD <= score < PURGE_THRESHOLD + AT_RISK_MARGIN

    def test_high_score_is_safe(self) -> None:
        # 0.7*0.9 + 0.3*(1-20/45) = 0.63 + 0.167 = 0.797 >= 0.6
        mem = _make_memory(importance=0.9, age_days=20, usage_count=2)
        risk, score = classify_purge_risk(mem, datetime.now(UTC), _config())
        assert risk == PurgeRiskLevel.SAFE
        assert score is not None and score >= PURGE_THRESHOLD + AT_RISK_MARGIN
