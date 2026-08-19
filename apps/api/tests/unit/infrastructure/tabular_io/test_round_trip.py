"""The property that makes the foundation trustworthy: writing then reading
returns exactly what was written.

Everything else in the layer is machinery; this is the contract. If it does not
hold, an export re-imported unchanged would report edits nobody made, and every
diff built on top would be noise. Measured on the real catalogue before this
code existed: treating an empty string and an absent cell apart produced 122
phantom differences on 124 rows.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.infrastructure.tabular_io.reader import parse_workbook
from src.infrastructure.tabular_io.spec import ColumnSpec, SheetSpec, WorkbookSpec
from src.infrastructure.tabular_io.writer import build_workbook

SHEET = SheetSpec(
    name="Models",
    title_key="t",
    key_column="model_name",
    columns=(
        ColumnSpec(key="model_name", label_key="l", kind="text", required=True),
        ColumnSpec(key="provider", label_key="l", kind="enum", referential="PROVIDER"),
        ColumnSpec(key="active", label_key="l", kind="boolean"),
        ColumnSpec(key="max_tokens", label_key="l", kind="integer", minimum=Decimal("0")),
        ColumnSpec(key="price", label_key="l", kind="decimal", decimals=6, minimum=Decimal("0")),
        ColumnSpec(key="window", label_key="l", kind="time_hhmm"),
        ColumnSpec(key="note", label_key="l", kind="text"),
        ColumnSpec(key="derived", label_key="l", kind="text", editable=False),
    ),
)
SPEC = WorkbookSpec(
    sheets=(SHEET,),
    referentials={"PROVIDER": ("openai", "anthropic")},
    schema_version=1,
)
LABELS = {"boolean.true": "VRAI", "boolean.false": "FAUX"}
LIMITS = {"max_rows": 500, "max_files": 200, "max_decompressed_bytes": 20_000_000}

ROWS: list[dict[str, object]] = [
    {
        "model_name": "gpt-4.1-mini",
        "provider": "openai",
        "active": True,
        "max_tokens": 1_047_576,
        "price": Decimal("0.400000"),
        "window": "01:00",
        "note": "tarif standard",
        "derived": "ok",
    },
    {
        "model_name": "claude-x",
        "provider": "anthropic",
        "active": False,
        "max_tokens": 0,
        "price": Decimal("9999.999999"),
        "window": None,
        "note": "",
        "derived": "",
    },
    {
        "model_name": "sans-tarif",
        "provider": "openai",
        "active": True,
        "max_tokens": 8192,
        "price": None,
        "window": "23:59",
        "note": "accents: éàü — tiret cadratin",
        "derived": "aucun tarif actif",
    },
]


def _round_trip(rows: list[dict[str, object]]):
    blob = build_workbook(SPEC, {"Models": rows}, notice=[], labels=LABELS, metadata={})
    return parse_workbook(SPEC, blob, **LIMITS)  # type: ignore[arg-type]


@pytest.mark.unit
class TestRoundTrip:
    def test_no_issue_is_raised_on_a_freshly_written_workbook(self) -> None:
        assert _round_trip(ROWS).issues == ()

    def test_every_row_comes_back(self) -> None:
        assert len(_round_trip(ROWS).rows("Models")) == len(ROWS)

    def test_every_editable_value_survives_unchanged(self) -> None:
        parsed = _round_trip(ROWS).rows("Models")
        for original, got in zip(ROWS, parsed, strict=True):
            for column in SHEET.columns:
                if not column.editable:
                    continue
                expected = original[column.key]
                # An empty string and an absent value are the same thing.
                if expected == "":
                    expected = None
                assert (
                    got.values[column.key] == expected
                ), f"{original['model_name']} / {column.key}"

    def test_read_only_columns_are_not_returned(self) -> None:
        assert "derived" not in _round_trip(ROWS).rows("Models")[0].values

    def test_decimal_precision_is_exact_at_the_domain_bounds(self) -> None:
        rows = [
            {"model_name": "tiny", "price": Decimal("0.000001")},
            {"model_name": "huge", "price": Decimal("9999.999999")},
        ]
        parsed = _round_trip(rows).rows("Models")
        assert parsed[0].values["price"] == Decimal("0.000001")
        assert parsed[1].values["price"] == Decimal("9999.999999")

    def test_an_empty_sheet_round_trips_to_no_row(self) -> None:
        assert _round_trip([]).rows("Models") == ()

    def test_the_key_of_each_row_is_reported(self) -> None:
        parsed = _round_trip(ROWS).rows("Models")
        assert [row.key for row in parsed] == [str(r["model_name"]) for r in ROWS]

    def test_a_value_that_looks_like_a_formula_survives_as_text(self) -> None:
        """Neutralised on write, it must come back readable — not rejected."""
        parsed = _round_trip([{"model_name": "weird", "note": "=1+2"}]).rows("Models")
        assert parsed[0].values["note"] is not None
        assert "1+2" in str(parsed[0].values["note"])

    def test_writing_twice_produces_the_same_parsed_content(self) -> None:
        """Idempotence at the format layer: re-exporting what was read changes
        nothing, which is what lets the diff above it mean something."""
        first = _round_trip(ROWS).rows("Models")
        rebuilt = [dict(row.values) for row in first]
        second = _round_trip(rebuilt).rows("Models")
        assert [dict(r.values) for r in first] == [dict(r.values) for r in second]
