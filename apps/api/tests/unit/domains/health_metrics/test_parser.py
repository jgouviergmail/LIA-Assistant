"""Unit tests for the flexible Health Metrics body parser.

Covers the four accepted payload envelope shapes:

1. iOS Shortcuts "Dictionnaire" wrapping (NDJSON blob stored as a single
   dict key with an empty value)
2. Raw NDJSON (newline-delimited JSON objects)
3. JSON array of samples
4. ``{"data": [...]}`` envelope

Plus failure modes: empty body, invalid UTF-8, unsupported shape,
malformed NDJSON.
"""

from __future__ import annotations

import json

import pytest

from src.domains.health_metrics.parser import (
    HealthSamplesBodyParseError,
    parse_samples_body,
)

pytestmark = pytest.mark.unit


# =============================================================================
# Fixtures
# =============================================================================


_SAMPLE_A = {
    "date_start": "2026-04-21T06:00:00+02:00",
    "date_end": "2026-04-21T07:00:00+02:00",
    "steps": 1234,
    "o": "iphone",
}
_SAMPLE_B = {
    "date_start": "2026-04-21T07:00:00+02:00",
    "date_end": "2026-04-21T08:00:00+02:00",
    "steps": 5678,
    "o": "iphone",
}


# =============================================================================
# JSON array
# =============================================================================


class TestJsonArrayShape:
    """Canonical JSON array of sample objects."""

    def test_parses_array(self) -> None:
        """A plain JSON array is returned as-is (non-dict entries filtered)."""
        body = json.dumps([_SAMPLE_A, _SAMPLE_B]).encode("utf-8")
        result = parse_samples_body(body)
        assert result == [_SAMPLE_A, _SAMPLE_B]

    def test_filters_non_dict_entries(self) -> None:
        """Primitives and nested arrays are silently dropped."""
        body = json.dumps([_SAMPLE_A, "oops", 42, [1, 2], _SAMPLE_B]).encode("utf-8")
        result = parse_samples_body(body)
        assert result == [_SAMPLE_A, _SAMPLE_B]

    def test_empty_array(self) -> None:
        """An empty array parses to an empty list (no error)."""
        assert parse_samples_body(b"[]") == []


# =============================================================================
# {"data": [...]} envelope
# =============================================================================


class TestDataEnvelopeShape:
    """``{"data": [...]}`` wrapper is unwrapped transparently."""

    def test_data_envelope(self) -> None:
        """The list inside ``data`` is returned."""
        body = json.dumps({"data": [_SAMPLE_A, _SAMPLE_B]}).encode("utf-8")
        assert parse_samples_body(body) == [_SAMPLE_A, _SAMPLE_B]


# =============================================================================
# NDJSON
# =============================================================================


class TestNdjsonShape:
    """Newline-delimited JSON where each line is a standalone object."""

    def test_ndjson_two_lines(self) -> None:
        """Two NDJSON lines yield two samples."""
        body = (json.dumps(_SAMPLE_A) + "\n" + json.dumps(_SAMPLE_B)).encode("utf-8")
        result = parse_samples_body(body)
        assert result == [_SAMPLE_A, _SAMPLE_B]

    def test_ndjson_skips_blank_lines(self) -> None:
        """Blank lines between NDJSON objects are tolerated."""
        body = (json.dumps(_SAMPLE_A) + "\n\n" + json.dumps(_SAMPLE_B) + "\n").encode("utf-8")
        result = parse_samples_body(body)
        assert result == [_SAMPLE_A, _SAMPLE_B]

    def test_ndjson_malformed_line_raises(self) -> None:
        """A non-JSON line aborts the parse with line number context."""
        body = (json.dumps(_SAMPLE_A) + "\nnot_json_at_all").encode("utf-8")
        with pytest.raises(HealthSamplesBodyParseError, match="line 2"):
            parse_samples_body(body)


# =============================================================================
# iOS Shortcuts "Dictionnaire" wrapping
# =============================================================================


class TestIosShortcutsWrapping:
    """iOS Shortcuts emits the NDJSON blob as a single dict key."""

    def test_ios_wrapping(self) -> None:
        """``{"<ndjson>": {}}`` is unwrapped and parsed as NDJSON."""
        ndjson = json.dumps(_SAMPLE_A) + "\n" + json.dumps(_SAMPLE_B)
        body = json.dumps({ndjson: {}}).encode("utf-8")
        result = parse_samples_body(body)
        assert result == [_SAMPLE_A, _SAMPLE_B]

    def test_ios_wrapping_single_sample(self) -> None:
        """Single-sample iOS wrappings still parse (only newline is required)."""
        ndjson = json.dumps(_SAMPLE_A) + "\n"
        body = json.dumps({ndjson: {}}).encode("utf-8")
        result = parse_samples_body(body)
        assert result == [_SAMPLE_A]


# =============================================================================
# Single sample as root dict
# =============================================================================


class TestSingleSampleShape:
    """A single sample dict (with date_start/date_end) is wrapped into a list."""

    def test_single_sample_root(self) -> None:
        """A root-level sample dict becomes a one-element list."""
        body = json.dumps(_SAMPLE_A).encode("utf-8")
        assert parse_samples_body(body) == [_SAMPLE_A]


# =============================================================================
# Failure modes
# =============================================================================


class TestFailureModes:
    """Inputs that cannot be mapped to any supported shape must raise."""

    def test_empty_body(self) -> None:
        """Empty bodies are rejected explicitly."""
        with pytest.raises(HealthSamplesBodyParseError, match="empty body"):
            parse_samples_body(b"")

    def test_whitespace_only_body(self) -> None:
        """Whitespace-only bodies are also treated as empty."""
        with pytest.raises(HealthSamplesBodyParseError, match="empty body"):
            parse_samples_body(b"   \n\t ")

    def test_unsupported_root_type(self) -> None:
        """A root-level primitive (e.g. bare number) is rejected."""
        with pytest.raises(HealthSamplesBodyParseError, match="unsupported payload shape"):
            parse_samples_body(b"42")

    def test_unknown_dict_shape(self) -> None:
        """Dict without ``data``, iOS wrapping, or ``date_start`` is rejected."""
        with pytest.raises(HealthSamplesBodyParseError, match="unsupported payload shape"):
            parse_samples_body(b'{"foo": "bar"}')
