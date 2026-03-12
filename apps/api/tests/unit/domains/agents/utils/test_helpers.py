"""
Unit tests for agents domain helper utilities.

Phase: Session 11 - Tests Quick Wins (utils/helpers)
Created: 2025-11-20
Enhanced: 2026-02-05 (added round_score and SCORE_PRECISION tests)

Focus: Run ID generation and score formatting
"""

import uuid
from unittest.mock import patch

import pytest

from src.domains.agents.utils.helpers import (
    SCORE_PRECISION,
    generate_run_id,
    round_score,
)


class TestGenerateRunId:
    """Tests for generate_run_id() function."""

    def test_generate_run_id_returns_string(self):
        """Test that generate_run_id() returns a string."""
        run_id = generate_run_id()
        assert isinstance(run_id, str)

    def test_generate_run_id_valid_uuid_format(self):
        """Test that generated run ID is a valid UUID."""
        run_id = generate_run_id()
        # Should be parseable as UUID
        parsed = uuid.UUID(run_id)
        assert str(parsed) == run_id

    def test_generate_run_id_unique(self):
        """Test that generate_run_id() generates unique IDs."""
        run_id1 = generate_run_id()
        run_id2 = generate_run_id()
        assert run_id1 != run_id2

    def test_generate_run_id_uses_uuid4(self):
        """Test that generate_run_id() uses uuid.uuid4()."""
        with patch("src.domains.agents.utils.helpers.uuid.uuid4") as mock_uuid4:
            # Mock uuid4 to return a specific UUID
            mock_uuid = uuid.UUID("12345678-1234-5678-1234-567812345678")
            mock_uuid4.return_value = mock_uuid

            run_id = generate_run_id()

            mock_uuid4.assert_called_once()
            assert run_id == "12345678-1234-5678-1234-567812345678"

    def test_generate_run_id_format(self):
        """Test that generated run ID follows UUID format (8-4-4-4-12)."""
        run_id = generate_run_id()
        parts = run_id.split("-")
        assert len(parts) == 5
        assert len(parts[0]) == 8
        assert len(parts[1]) == 4
        assert len(parts[2]) == 4
        assert len(parts[3]) == 4
        assert len(parts[4]) == 12

    def test_generate_run_id_multiple_calls_all_unique(self):
        """Test that multiple calls generate all unique IDs."""
        run_ids = [generate_run_id() for _ in range(100)]
        assert len(set(run_ids)) == 100

    def test_generate_run_id_is_lowercase(self):
        """Test that generated run ID is lowercase."""
        run_id = generate_run_id()
        assert run_id == run_id.lower()

    def test_generate_run_id_no_whitespace(self):
        """Test that generated run ID contains no whitespace."""
        run_id = generate_run_id()
        assert run_id.strip() == run_id
        assert " " not in run_id
        assert "\t" not in run_id
        assert "\n" not in run_id


# ============================================================================
# Tests for SCORE_PRECISION constant
# ============================================================================


class TestScorePrecision:
    """Tests for SCORE_PRECISION constant."""

    def test_score_precision_is_int(self):
        """Test that SCORE_PRECISION is an integer."""
        assert isinstance(SCORE_PRECISION, int)

    def test_score_precision_value(self):
        """Test that SCORE_PRECISION has expected default value."""
        assert SCORE_PRECISION == 2

    def test_score_precision_is_positive(self):
        """Test that SCORE_PRECISION is positive."""
        assert SCORE_PRECISION > 0

    def test_score_precision_is_reasonable(self):
        """Test that SCORE_PRECISION is within reasonable range."""
        # Typically 1-4 decimal places for scores
        assert 1 <= SCORE_PRECISION <= 4


# ============================================================================
# Tests for round_score() function - basic functionality
# ============================================================================


class TestRoundScoreBasic:
    """Tests for round_score() basic functionality."""

    def test_round_score_returns_float(self):
        """Test that round_score returns a float."""
        result = round_score(0.5)
        assert isinstance(result, float)

    def test_round_score_with_default_precision(self):
        """Test round_score with default precision."""
        result = round_score(0.87654321)
        assert result == 0.88

    def test_round_score_with_custom_precision_3(self):
        """Test round_score with precision=3."""
        result = round_score(0.123456, precision=3)
        assert result == 0.123

    def test_round_score_with_custom_precision_1(self):
        """Test round_score with precision=1."""
        result = round_score(0.567, precision=1)
        assert result == 0.6

    def test_round_score_with_custom_precision_4(self):
        """Test round_score with precision=4."""
        result = round_score(0.12345678, precision=4)
        assert result == 0.1235

    def test_round_score_zero(self):
        """Test round_score with zero."""
        result = round_score(0.0)
        assert result == 0.0

    def test_round_score_one(self):
        """Test round_score with one."""
        result = round_score(1.0)
        assert result == 1.0


# ============================================================================
# Tests for round_score() - rounding behavior
# ============================================================================


class TestRoundScoreRounding:
    """Tests for round_score() rounding behavior."""

    def test_round_score_rounds_up_at_midpoint(self):
        """Test that round_score rounds up at midpoint (banker's rounding in Python)."""
        # Python uses banker's rounding (round half to even)
        result = round_score(0.125, precision=2)
        # 0.125 rounds to 0.12 (banker's rounding to even)
        assert result == 0.12

    def test_round_score_rounds_up_when_above_midpoint(self):
        """Test that round_score rounds up when above midpoint."""
        result = round_score(0.126, precision=2)
        assert result == 0.13

    def test_round_score_rounds_down_when_below_midpoint(self):
        """Test that round_score rounds down when below midpoint."""
        result = round_score(0.124, precision=2)
        assert result == 0.12

    def test_round_score_precision_zero(self):
        """Test round_score with precision=0."""
        result = round_score(0.567, precision=0)
        assert result == 1.0

    def test_round_score_precision_zero_rounds_down(self):
        """Test round_score with precision=0 rounds down."""
        result = round_score(0.499, precision=0)
        assert result == 0.0

    def test_round_score_long_decimal(self):
        """Test round_score with very long decimal."""
        result = round_score(0.123456789012345, precision=2)
        assert result == 0.12

    def test_round_score_preserves_exact_values(self):
        """Test round_score preserves exact values at precision."""
        result = round_score(0.42, precision=2)
        assert result == 0.42


# ============================================================================
# Tests for round_score() - edge cases
# ============================================================================


class TestRoundScoreEdgeCases:
    """Tests for round_score() edge cases."""

    def test_round_score_negative_value(self):
        """Test round_score with negative value."""
        result = round_score(-0.567, precision=2)
        assert result == -0.57

    def test_round_score_value_greater_than_one(self):
        """Test round_score with value greater than 1."""
        result = round_score(1.5678, precision=2)
        assert result == 1.57

    def test_round_score_integer_input(self):
        """Test round_score with integer input.

        Note: Python's round() preserves int type when input is int.
        """
        result = round_score(1, precision=2)
        assert result == 1
        # round() preserves int type for int input
        assert isinstance(result, int)

    def test_round_score_very_small_value(self):
        """Test round_score with very small value."""
        result = round_score(0.001, precision=2)
        assert result == 0.0

    def test_round_score_very_small_value_high_precision(self):
        """Test round_score with very small value and high precision."""
        result = round_score(0.0001, precision=4)
        assert result == 0.0001

    def test_round_score_negative_precision(self):
        """Test round_score with negative precision (rounds to tens, etc.)."""
        result = round_score(123.456, precision=-1)
        assert result == 120.0

    def test_round_score_large_value(self):
        """Test round_score with large value."""
        result = round_score(99.999, precision=2)
        assert result == 100.0


# ============================================================================
# Tests for round_score() - typical score values
# ============================================================================


class TestRoundScoreTypicalValues:
    """Tests for round_score() with typical confidence/similarity scores."""

    def test_round_score_high_confidence(self):
        """Test round_score with high confidence score."""
        result = round_score(0.95678)
        assert result == 0.96

    def test_round_score_medium_confidence(self):
        """Test round_score with medium confidence score."""
        result = round_score(0.52341)
        assert result == 0.52

    def test_round_score_low_confidence(self):
        """Test round_score with low confidence score."""
        result = round_score(0.12789)
        assert result == 0.13

    def test_round_score_threshold_value_0_4(self):
        """Test round_score with typical threshold value 0.4."""
        result = round_score(0.4)
        assert result == 0.4

    def test_round_score_threshold_value_0_7(self):
        """Test round_score with typical threshold value 0.7."""
        result = round_score(0.7)
        assert result == 0.7

    def test_round_score_similarity_near_threshold(self):
        """Test round_score with similarity near threshold."""
        result = round_score(0.6999)
        assert result == 0.7

    def test_round_score_semantic_score(self):
        """Test round_score with typical semantic score."""
        result = round_score(0.384521)
        assert result == 0.38

    @pytest.mark.parametrize(
        "score,expected",
        [
            (0.0, 0.0),
            (0.1, 0.1),
            (0.2, 0.2),
            (0.3, 0.3),
            (0.4, 0.4),
            (0.5, 0.5),
            (0.6, 0.6),
            (0.7, 0.7),
            (0.8, 0.8),
            (0.9, 0.9),
            (1.0, 1.0),
        ],
    )
    def test_round_score_boundary_values(self, score: float, expected: float):
        """Test round_score with boundary values from 0 to 1."""
        result = round_score(score)
        assert result == expected


# ============================================================================
# Tests for round_score() - consistency
# ============================================================================


class TestRoundScoreConsistency:
    """Tests for round_score() consistency."""

    def test_round_score_idempotent(self):
        """Test that round_score is idempotent."""
        value = 0.87654321
        result1 = round_score(value)
        result2 = round_score(result1)
        assert result1 == result2

    def test_round_score_consistent_with_builtin_round(self):
        """Test that round_score is consistent with built-in round."""
        value = 0.567
        result = round_score(value, precision=2)
        expected = round(value, 2)
        assert result == expected

    def test_round_score_multiple_calls_same_result(self):
        """Test that multiple calls with same args return same result."""
        value = 0.123456
        results = [round_score(value, precision=3) for _ in range(10)]
        assert all(r == results[0] for r in results)

    def test_round_score_uses_score_precision_constant(self):
        """Test that default precision matches SCORE_PRECISION constant."""
        value = 0.123456789
        result_default = round_score(value)
        result_explicit = round_score(value, precision=SCORE_PRECISION)
        assert result_default == result_explicit


# ============================================================================
# Integration tests
# ============================================================================


class TestHelpersIntegration:
    """Integration tests for helper utilities."""

    def test_generate_run_id_and_round_score_together(self):
        """Test that generate_run_id and round_score work together."""
        # Simulate a typical usage pattern
        run_id = generate_run_id()
        confidence_score = 0.87654321

        # Both should work without issues
        assert len(run_id) == 36
        assert round_score(confidence_score) == 0.88

    def test_round_score_for_logging(self):
        """Test round_score for logging purposes."""
        # Typical pattern: round score for cleaner logs
        raw_score = 0.87654321
        rounded = round_score(raw_score)

        # Verify it produces clean output for logs
        log_output = f"confidence={rounded}"
        assert log_output == "confidence=0.88"

    def test_round_score_multiple_scores(self):
        """Test round_score with multiple scores in a workflow."""
        scores = {
            "semantic_similarity": 0.87654,
            "confidence": 0.92341,
            "threshold": 0.7,
        }

        rounded_scores = {k: round_score(v) for k, v in scores.items()}

        assert rounded_scores["semantic_similarity"] == 0.88
        assert rounded_scores["confidence"] == 0.92
        assert rounded_scores["threshold"] == 0.7
