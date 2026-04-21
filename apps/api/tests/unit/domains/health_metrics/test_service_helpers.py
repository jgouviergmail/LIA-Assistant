"""Unit tests for Health Metrics service helpers.

Covers the pure helpers that do not require a DB session:
- Token hashing (stable SHA-256)
- Token generation (prefix + raw value)
- Source slugification (accents, case, invalid chars, length cap)
- Datetime normalization (ISO 8601 parsing, UTC conversion, second truncation,
  naive-rejection)
- Polymorphic sample validation (``_validate_sample`` for heart_rate + steps)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from src.core.constants import (
    HEALTH_METRICS_KIND_HEART_RATE,
    HEALTH_METRICS_KIND_STEPS,
    HEALTH_METRICS_SOURCE_DEFAULT,
    HEALTH_METRICS_TOKEN_DISPLAY_PREFIX_CHARS,
    HEALTH_METRICS_TOKEN_PREFIX,
)
from src.domains.health_metrics.constants import (
    REJECTION_REASON_INVALID_DATE,
    REJECTION_REASON_MALFORMED,
    REJECTION_REASON_MISSING_FIELD,
    REJECTION_REASON_OUT_OF_RANGE,
)
from src.domains.health_metrics.service import (
    _generate_raw_token,
    _hash_token,
    _normalize_datetime,
    _normalize_source,
    _validate_sample,
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
        """Two consecutive generations yield distinct values."""
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
# Datetime normalization
# =============================================================================


class TestDatetimeNormalization:
    """Incoming timestamps must be aware, UTC-converted, and second-truncated."""

    def test_parses_iso_with_offset(self) -> None:
        """An ISO 8601 string with ``+02:00`` is shifted to UTC."""
        parsed = _normalize_datetime("2026-04-21T14:30:00+02:00")
        assert parsed == datetime(2026, 4, 21, 12, 30, 0, tzinfo=UTC)

    def test_parses_iso_with_z_suffix(self) -> None:
        """The shorthand ``Z`` suffix is treated as UTC."""
        parsed = _normalize_datetime("2026-04-21T12:30:00Z")
        assert parsed == datetime(2026, 4, 21, 12, 30, 0, tzinfo=UTC)

    def test_accepts_aware_datetime_object(self) -> None:
        """An existing aware datetime is normalized to UTC."""
        aware = datetime(2026, 4, 21, 14, 30, 0, tzinfo=timezone(timedelta(hours=2)))
        parsed = _normalize_datetime(aware)
        assert parsed.tzinfo is UTC
        assert parsed.hour == 12

    def test_truncates_microseconds(self) -> None:
        """Sub-second precision is dropped for stable unique-key matching."""
        parsed = _normalize_datetime("2026-04-21T12:30:00.123456+00:00")
        assert parsed.microsecond == 0

    def test_rejects_naive_datetime_string(self) -> None:
        """An ISO string without timezone is rejected."""
        with pytest.raises(ValueError, match="Timezone-naive"):
            _normalize_datetime("2026-04-21T12:30:00")

    def test_rejects_naive_datetime_object(self) -> None:
        """A naive datetime object is also rejected."""
        naive = datetime(2026, 4, 21, 12, 30, 0)
        with pytest.raises(ValueError, match="Timezone-naive"):
            _normalize_datetime(naive)

    def test_rejects_unsupported_type(self) -> None:
        """Non-string / non-datetime inputs raise explicitly."""
        with pytest.raises(ValueError, match="Unsupported datetime type"):
            _normalize_datetime(12345)  # type: ignore[arg-type]


# =============================================================================
# Polymorphic sample validation
# =============================================================================


_BASE_DATES = {
    "date_start": "2026-04-21T12:00:00+00:00",
    "date_end": "2026-04-21T12:30:00+00:00",
}


class TestValidateSampleHeartRate:
    """Heart-rate samples must carry a plausible bpm value."""

    def test_valid_hr_sample(self) -> None:
        """A valid HR sample yields a normalized payload."""
        raw = {**_BASE_DATES, "heart_rate": 72, "o": "iPhone"}
        outcome = _validate_sample(raw, HEALTH_METRICS_KIND_HEART_RATE)
        assert outcome.valid is True
        assert outcome.payload is not None
        assert outcome.payload["value"] == 72
        assert outcome.payload["source"] == "iphone"
        assert outcome.payload["date_start"].tzinfo is UTC

    def test_missing_hr_field_rejected(self) -> None:
        """Missing the measurement field yields a missing_field rejection."""
        raw = {**_BASE_DATES, "o": "iphone"}
        outcome = _validate_sample(raw, HEALTH_METRICS_KIND_HEART_RATE)
        assert outcome.valid is False
        assert outcome.reason is not None
        assert outcome.reason.startswith(REJECTION_REASON_MISSING_FIELD)

    @pytest.mark.parametrize("bad_value", [-10, 0, 5, 251, 999])
    def test_out_of_range_hr_rejected(self, bad_value: int) -> None:
        """Extreme HR values are rejected, not clamped."""
        raw = {**_BASE_DATES, "heart_rate": bad_value}
        outcome = _validate_sample(raw, HEALTH_METRICS_KIND_HEART_RATE)
        assert outcome.valid is False
        assert outcome.reason is not None
        assert outcome.reason.startswith(REJECTION_REASON_OUT_OF_RANGE)


class TestValidateSampleSteps:
    """Steps samples must carry a non-negative int."""

    def test_valid_steps_sample(self) -> None:
        """A valid steps sample yields a normalized payload."""
        raw = {**_BASE_DATES, "steps": 4521, "o": "iphone"}
        outcome = _validate_sample(raw, HEALTH_METRICS_KIND_STEPS)
        assert outcome.valid is True
        assert outcome.payload is not None
        assert outcome.payload["value"] == 4521

    def test_zero_steps_accepted(self) -> None:
        """``steps=0`` is explicitly supported (inactive interval)."""
        raw = {**_BASE_DATES, "steps": 0}
        outcome = _validate_sample(raw, HEALTH_METRICS_KIND_STEPS)
        assert outcome.valid is True
        assert outcome.payload is not None
        assert outcome.payload["value"] == 0

    def test_missing_source_falls_back_to_default(self) -> None:
        """Omitting ``o`` substitutes the default source label."""
        raw = {**_BASE_DATES, "steps": 100}
        outcome = _validate_sample(raw, HEALTH_METRICS_KIND_STEPS)
        assert outcome.valid is True
        assert outcome.payload is not None
        assert outcome.payload["source"] == HEALTH_METRICS_SOURCE_DEFAULT


class TestValidateSampleCommon:
    """Common rejection paths regardless of kind."""

    def test_invalid_date_rejected(self) -> None:
        """A malformed date string yields an invalid_date rejection."""
        raw = {
            "date_start": "not-a-date",
            "date_end": "2026-04-21T12:30:00+00:00",
            "steps": 100,
        }
        outcome = _validate_sample(raw, HEALTH_METRICS_KIND_STEPS)
        assert outcome.valid is False
        assert outcome.reason is not None
        assert outcome.reason.startswith(REJECTION_REASON_INVALID_DATE)

    def test_naive_date_rejected(self) -> None:
        """An ISO date without TZ is rejected as invalid_date."""
        raw = {
            "date_start": "2026-04-21T12:00:00",
            "date_end": "2026-04-21T12:30:00",
            "steps": 100,
        }
        outcome = _validate_sample(raw, HEALTH_METRICS_KIND_STEPS)
        assert outcome.valid is False
        assert outcome.reason is not None
        assert outcome.reason.startswith(REJECTION_REASON_INVALID_DATE)

    def test_non_integer_value_rejected(self) -> None:
        """A non-coercible value yields a malformed rejection."""
        raw = {**_BASE_DATES, "steps": "not-a-number"}
        outcome = _validate_sample(raw, HEALTH_METRICS_KIND_STEPS)
        assert outcome.valid is False
        assert outcome.reason is not None
        assert outcome.reason.startswith(REJECTION_REASON_MALFORMED)
