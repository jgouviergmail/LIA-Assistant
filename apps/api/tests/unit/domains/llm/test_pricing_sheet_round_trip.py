"""A real workbook, written and read back: the reasoning identity survives.

Every other test in this area exercises one half — the row builder, the change
plan, the import payload. This one writes an actual ``.xlsx`` through the
declared spec and parses it again, which is the only way to catch a column that
the writer emits and the reader cannot find, or a cell whose type changes in
transit.

It matters more than usual right now: the reasoning columns were REPLACED. A
``reasoning_template`` dropdown became a boolean plus a free-text ladder, and
the two halves are declared in one place but consumed by two.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.domains.llm.pricing_sheet import (
    MODELS_SHEET,
    SCHEMA_VERSION,
    SLOTS_SHEET,
    build_pricing_workbook_spec,
)
from src.infrastructure.tabular_io.reader import parse_workbook
from src.infrastructure.tabular_io.writer import build_workbook

pytestmark = pytest.mark.unit

_LIMITS = {"max_rows": 500, "max_files": 64, "max_decompressed_bytes": 32 * 1024 * 1024}


def _row(**overrides: Any) -> dict[str, Any]:
    """One complete models-sheet row, as the export builds it."""
    base: dict[str, Any] = {
        "model_name": "claude-opus-4-6",
        "provider": "anthropic",
        "kind": "chat",
        "is_active": True,
        "max_input_tokens": 200000,
        "max_output_tokens": 64000,
        "supports_tools": True,
        "supports_structured_output": True,
        "supports_strict_mode": False,
        "supports_streaming": True,
        "supports_vision": True,
        "supports_temperature": True,
        "supports_top_p": False,
        "supports_frequency_penalty": False,
        "supports_presence_penalty": False,
        "is_reasoning_model": True,
        "reasoning_enum_values": "low, high",
        "reasoning_shape": "anthropic_adaptive [none/low/medium/high/max]",
        # An i18n key name, not a credential: the generic-api-key rule fires on
        # any field whose name ends in `_key` when the value carries entropy.
        # The annotation must sit on the FLAGGED line, not above it.
        "reasoning_doc_i18n_key": "anthropic_4_6",  # gitleaks:allow
        "pricing_unit": "per_1m_tokens",
        "input_unit_price": "3.0",
        "cached_input_unit_price": None,
        "output_unit_price": "15.0",
        "effective_from": "2026-01-01",
        "time_slots_mode": "flat",
        "time_slots_summary": "",
        "statut": "ok",
        "row_fingerprint": "abc123",
    }
    base.update(overrides)
    return base


def _round_trip(row: dict[str, Any]) -> dict[str, Any]:
    """Write one row to a real workbook and read it back."""
    spec = build_pricing_workbook_spec()
    content = build_workbook(
        spec,
        {MODELS_SHEET.name: [row], SLOTS_SHEET.name: []},
        notice=["notice"],
        labels={},
        metadata={},
    )
    parsed = parse_workbook(spec, content, **_LIMITS)
    assert not [
        issue for issue in parsed.issues if issue.code.name.startswith("SCHEMA")
    ], parsed.issues
    rows = parsed.sheets[MODELS_SHEET.name]
    assert len(rows) == 1, parsed.issues
    return dict(rows[0].values)


def test_the_ladder_survives_a_real_write_and_read() -> None:
    values = _round_trip(_row())

    assert values["is_reasoning_model"] is True
    assert values["reasoning_enum_values"] == "low, high"


def test_an_empty_ladder_comes_back_empty_not_as_a_string() -> None:
    """Empty means "no narrowing", and it must not become the text "None"."""
    values = _round_trip(_row(reasoning_enum_values=None))

    assert values["reasoning_enum_values"] in (None, "")


def test_a_non_reasoning_row_survives_too() -> None:
    values = _round_trip(_row(is_reasoning_model=False, reasoning_enum_values=None))

    assert values["is_reasoning_model"] is False


def test_the_template_column_is_no_longer_written() -> None:
    """The file must not carry a column the reader has no meaning for."""
    assert "reasoning_template" not in {column.key for column in MODELS_SHEET.columns}


def test_the_schema_version_travels_and_matches() -> None:
    """A file written before the columns changed must be refusable by version."""
    spec = build_pricing_workbook_spec()

    assert spec.schema_version == SCHEMA_VERSION == 2
