"""A boolean the writer writes, in any of the six languages, reads back as itself.

The writer writes the yes/no words of the labels it is handed; the reader
compared cells with a hand-typed list that lacked WAHR/FALSCH, VERDADERO/FALSO
and VERO. A German, Spanish or Italian export re-imported untouched was refused
on every boolean cell (``NOT_A_BOOLEAN``). The reader now derives its words from
the writer's own ``boolean_word`` over every language's labels — one declaration,
the workbook translations — and this round trip holds the two together.
"""

from __future__ import annotations

import io
from typing import get_args

import openpyxl
import pytest

from src.core.i18n_pricing_sheet import build_sheet_labels
from src.core.i18n_types import Language
from src.infrastructure.tabular_io.reader import parse_workbook
from src.infrastructure.tabular_io.report import IssueCode
from src.infrastructure.tabular_io.spec import ColumnSpec, SheetSpec, WorkbookSpec
from src.infrastructure.tabular_io.writer import DATA_TOP_ROW, build_workbook

pytestmark = pytest.mark.unit

_SHEET = SheetSpec(
    name="Models",
    title_key="t",
    key_column="model_name",
    columns=(
        ColumnSpec(key="model_name", label_key="l", kind="text", required=True),
        ColumnSpec(key="active", label_key="l", kind="boolean"),
    ),
)
_SPEC = WorkbookSpec(sheets=(_SHEET,), referentials={}, schema_version=1)
_ROWS: list[dict[str, object]] = [
    {"model_name": "on", "active": True},
    {"model_name": "off", "active": False},
]
_LIMITS = {"max_rows": 50, "max_files": 200, "max_decompressed_bytes": 20_000_000}


def _written(labels: dict[str, str]) -> bytes:
    return build_workbook(_SPEC, {_SHEET.name: _ROWS}, notice=(), labels=labels, metadata={})


def _cells(content: bytes) -> list[object]:
    """What the boolean cells of the file hold, as Excel would show them."""
    workbook = openpyxl.load_workbook(io.BytesIO(content))
    try:
        sheet = workbook[_SHEET.name]
        return [sheet.cell(row=DATA_TOP_ROW + offset, column=2).value for offset in range(2)]
    finally:
        workbook.close()


@pytest.mark.parametrize("language", get_args(Language))
def test_a_boolean_written_in_a_language_reads_back_as_itself(language: str) -> None:
    labels = build_sheet_labels(language)
    content = _written(labels)

    # The file carries the translated words, not Excel booleans: the round trip
    # goes through the words themselves.
    assert _cells(content) == [labels["boolean.true"], labels["boolean.false"]]

    parsed = parse_workbook(_SPEC, content, **_LIMITS)

    assert IssueCode.NOT_A_BOOLEAN not in {issue.code for issue in parsed.issues}
    assert [row.values["active"] for row in parsed.rows(_SHEET.name)] == [True, False]


def test_the_writer_s_fallback_words_read_back_too() -> None:
    content = _written({})

    assert _cells(content) == ["TRUE", "FALSE"]
    parsed = parse_workbook(_SPEC, content, **_LIMITS)
    assert [row.values["active"] for row in parsed.rows(_SHEET.name)] == [True, False]
