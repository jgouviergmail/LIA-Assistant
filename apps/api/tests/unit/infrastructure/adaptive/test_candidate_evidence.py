"""Calibration evidence for CANDIDATE adaptive perimeters (Lot 7-B4).

Registering a perimeter is an owner arbitration (bounds = design). What can
ship without it is the EVIDENCE: an aggregate score distribution per
candidate perimeter, so the arbitration reads data instead of guesses
(lot-0 doctrine: instrument before tuning).
"""

import pytest

from src.infrastructure.adaptive.threshold_controller import record_candidate_score


@pytest.mark.unit
class TestCandidateEvidence:
    def test_records_a_labeled_observation(self):
        from src.infrastructure.observability.metrics_registry import (
            adaptive_candidate_top_score,
        )

        before = adaptive_candidate_top_score.labels(perimeter="memory_injection")

        record_candidate_score("memory_injection", 0.72)

        # Histogram observation is visible through the internal sum.
        assert before._sum.get() >= 0.72

    def test_never_raises_even_on_junk(self):
        record_candidate_score("memory_injection", float("nan"))
        record_candidate_score("", 0.5)
