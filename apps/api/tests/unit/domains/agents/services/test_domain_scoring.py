"""
Unit tests for domain softmax calibration (CORRECTION 3).

Tests coverage:
- Primary domain has higher calibrated score than secondary
- Calibrated scores sum to ~1.0
- Single domain returns score 1.0
- Empty domains returns empty dict
- Edge case: confidence=0.0

Target: _apply_domain_softmax_calibration in
    domains/agents/services/query_analyzer_service.py
"""

from __future__ import annotations

from src.domains.agents.services.query_analyzer_service import (
    _apply_domain_softmax_calibration,
)


class TestDomainSoftmaxCalibration:
    """CORRECTION 3: Softmax calibration for discriminated domain scores."""

    def test_primary_higher_than_secondary(self) -> None:
        """Primary domain should have higher calibrated score than secondary."""
        scores = _apply_domain_softmax_calibration(
            primary_domain="contact",
            secondary_domains=["event"],
            confidence=0.85,
        )

        assert scores["contact"] > scores["event"]

    def test_calibrated_scores_sum_to_one(self) -> None:
        """Softmax calibration should produce scores summing to ~1.0."""
        scores = _apply_domain_softmax_calibration(
            primary_domain="contact",
            secondary_domains=["event", "email"],
            confidence=0.85,
        )

        total = sum(scores.values())
        assert abs(total - 1.0) < 1e-6

    def test_single_domain_returns_one(self) -> None:
        """Single domain should get score of exactly 1.0."""
        scores = _apply_domain_softmax_calibration(
            primary_domain="contact",
            secondary_domains=[],
            confidence=0.85,
        )

        assert len(scores) == 1
        assert scores["contact"] == 1.0

    def test_empty_domains_returns_empty(self) -> None:
        """No domains should return empty dict."""
        scores = _apply_domain_softmax_calibration(
            primary_domain=None,
            secondary_domains=[],
            confidence=0.85,
        )

        assert scores == {}

    def test_three_secondary_domains_decreasing(self) -> None:
        """Multiple secondary domains should have decreasing weights."""
        scores = _apply_domain_softmax_calibration(
            primary_domain="contact",
            secondary_domains=["event", "email", "task"],
            confidence=0.90,
        )

        assert scores["contact"] > scores["event"]
        assert scores["event"] > scores["email"]
        assert scores["email"] > scores["task"]

    def test_confidence_zero_uniform_distribution(self) -> None:
        """Confidence=0.0 should produce uniform distribution (all scores equal)."""
        scores = _apply_domain_softmax_calibration(
            primary_domain="contact",
            secondary_domains=["event"],
            confidence=0.0,
        )

        # All raw scores are 0.0 → score_range < 1e-6 → uniform
        assert len(scores) == 2
        assert abs(scores["contact"] - scores["event"]) < 1e-6
        assert abs(sum(scores.values()) - 1.0) < 1e-6

    def test_high_confidence_strong_discrimination(self) -> None:
        """High confidence should produce strong discrimination (primary >> secondary)."""
        scores = _apply_domain_softmax_calibration(
            primary_domain="contact",
            secondary_domains=["event"],
            confidence=0.95,
        )

        # With default temperature=0.1, primary should strongly dominate
        assert scores["contact"] > 0.7

    def test_secondary_only_no_primary(self) -> None:
        """Secondary domains without primary should still work."""
        scores = _apply_domain_softmax_calibration(
            primary_domain=None,
            secondary_domains=["event", "email"],
            confidence=0.80,
        )

        # Both are "secondary" with decreasing weights
        assert len(scores) == 2
        assert scores["event"] > scores["email"]
        assert abs(sum(scores.values()) - 1.0) < 1e-6
