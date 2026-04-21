"""Unit tests for ``_merge_duplicate_samples``.

Covers the per-kind arbitrage strategy used to collapse intra-batch
duplicates on ``(date_start, date_end)`` before the PostgreSQL UPSERT.

- ``steps`` → MAX (Watch + iPhone complementary counts)
- ``heart_rate`` → AVG (two sensors targeting the same signal)
- unknown kind → last-wins fallback
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from src.core.constants import (
    HEALTH_METRICS_KIND_HEART_RATE,
    HEALTH_METRICS_KIND_STEPS,
)
from src.domains.health_metrics.repository import _merge_duplicate_samples

pytestmark = pytest.mark.unit


# =============================================================================
# Helpers
# =============================================================================


def _sample(
    value: int,
    date_start: datetime,
    date_end: datetime,
    source: str = "iphone",
) -> dict[str, Any]:
    return {
        "date_start": date_start,
        "date_end": date_end,
        "value": value,
        "source": source,
    }


_SLOT_A_START = datetime(2026, 4, 21, 12, 0, tzinfo=UTC)
_SLOT_A_END = _SLOT_A_START + timedelta(minutes=5)
_SLOT_B_START = datetime(2026, 4, 21, 13, 0, tzinfo=UTC)
_SLOT_B_END = _SLOT_B_START + timedelta(minutes=5)


# =============================================================================
# Steps → MAX
# =============================================================================


class TestStepsMax:
    """Steps duplicates collapse to MAX."""

    def test_keeps_highest_in_group(self) -> None:
        """Three samples on the same slot → kept entry has the max value."""
        samples = [
            _sample(500, _SLOT_A_START, _SLOT_A_END, source="watch"),
            _sample(1200, _SLOT_A_START, _SLOT_A_END, source="iphone"),
            _sample(800, _SLOT_A_START, _SLOT_A_END, source="iphone"),
        ]
        result = _merge_duplicate_samples(samples, HEALTH_METRICS_KIND_STEPS)
        assert len(result) == 1
        assert result[0]["value"] == 1200
        # Source of the MAX winner is preserved.
        assert result[0]["source"] == "iphone"

    def test_preserves_singleton_and_merges_dupes(self) -> None:
        """Distinct slots pass through; duplicate slots reduce to MAX."""
        samples = [
            _sample(500, _SLOT_A_START, _SLOT_A_END),
            _sample(1200, _SLOT_A_START, _SLOT_A_END),
            _sample(300, _SLOT_B_START, _SLOT_B_END),
        ]
        result = _merge_duplicate_samples(samples, HEALTH_METRICS_KIND_STEPS)
        by_start = {s["date_start"]: s["value"] for s in result}
        assert by_start == {_SLOT_A_START: 1200, _SLOT_B_START: 300}

    def test_preserves_insertion_order(self) -> None:
        """First-seen slot remains first in the returned list."""
        samples = [
            _sample(300, _SLOT_B_START, _SLOT_B_END),
            _sample(500, _SLOT_A_START, _SLOT_A_END),
            _sample(1200, _SLOT_A_START, _SLOT_A_END),
        ]
        result = _merge_duplicate_samples(samples, HEALTH_METRICS_KIND_STEPS)
        assert [s["date_start"] for s in result] == [_SLOT_B_START, _SLOT_A_START]


# =============================================================================
# Heart rate → AVG (rounded to int)
# =============================================================================


class TestHeartRateAverage:
    """Heart-rate duplicates collapse to the arithmetic mean (rounded)."""

    def test_averages_three_values(self) -> None:
        """AVG(70, 80, 85) = round(78.33) = 78."""
        samples = [
            _sample(70, _SLOT_A_START, _SLOT_A_END),
            _sample(80, _SLOT_A_START, _SLOT_A_END),
            _sample(85, _SLOT_A_START, _SLOT_A_END),
        ]
        result = _merge_duplicate_samples(samples, HEALTH_METRICS_KIND_HEART_RATE)
        assert len(result) == 1
        assert result[0]["value"] == 78

    def test_rounds_to_nearest_int_banker_sensitive(self) -> None:
        """AVG(70, 71) = 70.5 → Python's banker's rounding yields 70."""
        # Documented behavior: Python's round() uses banker's rounding at .5.
        samples = [
            _sample(70, _SLOT_A_START, _SLOT_A_END),
            _sample(71, _SLOT_A_START, _SLOT_A_END),
        ]
        result = _merge_duplicate_samples(samples, HEALTH_METRICS_KIND_HEART_RATE)
        assert result[0]["value"] == 70

    def test_singleton_unchanged(self) -> None:
        """A single sample passes through without any averaging."""
        samples = [_sample(72, _SLOT_A_START, _SLOT_A_END)]
        result = _merge_duplicate_samples(samples, HEALTH_METRICS_KIND_HEART_RATE)
        assert result[0]["value"] == 72
        assert result[0] is samples[0]  # identity preserved


# =============================================================================
# Edge cases
# =============================================================================


class TestEdgeCases:
    """Boundary conditions and forward-compat behavior."""

    def test_empty_list(self) -> None:
        """An empty input yields an empty output (no exception)."""
        assert _merge_duplicate_samples([], HEALTH_METRICS_KIND_STEPS) == []

    def test_no_duplicates_passthrough(self) -> None:
        """When every slot is distinct, the list is returned unchanged in order."""
        samples = [
            _sample(100, _SLOT_A_START, _SLOT_A_END),
            _sample(200, _SLOT_B_START, _SLOT_B_END),
        ]
        result = _merge_duplicate_samples(samples, HEALTH_METRICS_KIND_STEPS)
        assert result == samples

    def test_unknown_kind_falls_back_to_last_wins(self) -> None:
        """Defensive: an unknown kind yields the last sample of each group."""
        samples = [
            _sample(100, _SLOT_A_START, _SLOT_A_END, source="a"),
            _sample(200, _SLOT_A_START, _SLOT_A_END, source="b"),
        ]
        result = _merge_duplicate_samples(samples, "some_future_kind")
        assert len(result) == 1
        assert result[0]["value"] == 200
        assert result[0]["source"] == "b"


# =============================================================================
# Ignored: distinct date_end but same date_start
# =============================================================================


class TestKeyGranularity:
    """The merge key is the full ``(date_start, date_end)`` tuple."""

    def test_different_date_end_is_a_different_slot(self) -> None:
        """Samples with the same start but different end are NOT duplicates."""
        end_plus_one = _SLOT_A_END + timedelta(minutes=1)
        samples = [
            _sample(100, _SLOT_A_START, _SLOT_A_END),
            _sample(200, _SLOT_A_START, end_plus_one),
        ]
        result = _merge_duplicate_samples(samples, HEALTH_METRICS_KIND_STEPS)
        assert len(result) == 2
