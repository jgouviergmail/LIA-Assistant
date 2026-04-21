"""Unit tests for Health Metrics service helpers.

Covers the pure helpers that do not require a DB session:
- Token hashing (stable SHA-256)
- Token generation (prefix + raw value)
- Source slugification (accents, case, invalid chars)
- Field validators (mixed validation, out-of-range → NULL)
"""

from __future__ import annotations

import pytest

from src.core.constants import (
    HEALTH_METRICS_SOURCE_DEFAULT,
    HEALTH_METRICS_TOKEN_DISPLAY_PREFIX_CHARS,
    HEALTH_METRICS_TOKEN_PREFIX,
)
from src.domains.health_metrics.service import (
    _generate_raw_token,
    _hash_token,
    _normalize_source,
    _validate_heart_rate,
    _validate_steps,
)

pytestmark = pytest.mark.unit


# =============================================================================
# Token helpers
# =============================================================================


class TestTokenHashing:
    """SHA-256 hashing must be stable and produce 64 hex chars."""

    def test_hash_is_stable(self) -> None:
        """The same input always produces the same hash."""
        h1 = _hash_token("hm_abc123")
        h2 = _hash_token("hm_abc123")
        assert h1 == h2
        assert len(h1) == 64

    def test_hash_changes_with_input(self) -> None:
        """Different inputs produce different hashes."""
        assert _hash_token("hm_a") != _hash_token("hm_b")


class TestTokenGeneration:
    """Generated tokens honor the advertised prefix and prefix-length."""

    def test_prefix_and_length(self) -> None:
        """The raw token starts with ``hm_`` and the display prefix is the first N chars."""
        raw, prefix = _generate_raw_token()
        assert raw.startswith(HEALTH_METRICS_TOKEN_PREFIX)
        assert prefix == raw[:HEALTH_METRICS_TOKEN_DISPLAY_PREFIX_CHARS]
        assert len(raw) > HEALTH_METRICS_TOKEN_DISPLAY_PREFIX_CHARS

    def test_entropy(self) -> None:
        """Two consecutive generations yield distinct values (sanity on randomness)."""
        first, _ = _generate_raw_token()
        second, _ = _generate_raw_token()
        assert first != second


# =============================================================================
# Source slugification
# =============================================================================


class TestSourceNormalization:
    """The ``o`` field must collapse to a low-cardinality slug."""

    def test_none_returns_default(self) -> None:
        """Absent source falls back to the default label."""
        assert _normalize_source(None) == HEALTH_METRICS_SOURCE_DEFAULT

    def test_empty_string_returns_default(self) -> None:
        """Whitespace-only source falls back to the default label."""
        assert _normalize_source("   ") == HEALTH_METRICS_SOURCE_DEFAULT

    def test_lowercases_and_strips_accents(self) -> None:
        """Diacritics are stripped, uppercase is lowered."""
        assert _normalize_source("iPhöne") == "iphone"

    def test_drops_invalid_chars(self) -> None:
        """Only [a-z0-9_-] characters survive."""
        assert _normalize_source("iphone 15!") == "iphone15"

    def test_truncates_long_source(self) -> None:
        """Values exceeding the max length are truncated to the configured bound."""
        long_value = "x" * 200
        normalized = _normalize_source(long_value)
        assert len(normalized) <= 32


# =============================================================================
# Mixed per-field validation
# =============================================================================


class TestHeartRateValidation:
    """Out-of-range heart rates nullify the field without blocking siblings."""

    def test_valid_value_stored(self) -> None:
        """A plausible heart rate passes through unchanged."""
        outcome = _validate_heart_rate(72)
        assert outcome.stored_value == 72
        assert outcome.was_stored is True
        assert outcome.was_nullified is False

    def test_none_is_noop(self) -> None:
        """Absent heart rate is neither stored nor nullified."""
        outcome = _validate_heart_rate(None)
        assert outcome.stored_value is None
        assert outcome.was_stored is False
        assert outcome.was_nullified is False

    @pytest.mark.parametrize("bad_value", [-10, 0, 5, 251, 999])
    def test_out_of_range_nullifies(self, bad_value: int) -> None:
        """Extreme values are converted to NULL with the nullified flag raised."""
        outcome = _validate_heart_rate(bad_value)
        assert outcome.stored_value is None
        assert outcome.was_stored is False
        assert outcome.was_nullified is True


class TestStepsValidation:
    """Out-of-range per-sample step counts nullify the field."""

    def test_valid_value_stored(self) -> None:
        """A normal per-sample count passes through unchanged."""
        outcome = _validate_steps(4521)
        assert outcome.stored_value == 4521
        assert outcome.was_stored is True

    @pytest.mark.parametrize("bad_value", [-1, 15_001])
    def test_out_of_range_nullifies(self, bad_value: int) -> None:
        """Negative and implausibly large per-sample step counts are nullified."""
        outcome = _validate_steps(bad_value)
        assert outcome.stored_value is None
        assert outcome.was_nullified is True
