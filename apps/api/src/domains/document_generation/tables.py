"""Tables: typed columns, legal headers, generated names, chunks (ADR-274).

Typing is by **unanimity**: a column becomes a number, a percentage or a date
only when every non-empty cell obeys the same rule, so one stray value keeps
the whole column text rather than corrupting it. Integers carry no thousands
separator (a year and a postal code are integers too) and a leading zero
protects a column of codes.

Excel REFUSES to open a workbook whose Table has a duplicate or empty header,
or a name with a space or shaped like a cell reference (measured 2026-09-08).
Headers are therefore made unique here, for every format, and the Table name is
never taken from the model's words.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum

from src.core.i18n_documents import document_label
from src.domains.document_generation.sanitize import (
    neutralize_formula,
    strip_control_characters,
)
from src.domains.document_generation.schemas import TableSheet

_INT = re.compile(r"^[+-]?\d{1,15}$")
_LEADING_ZERO = re.compile(r"^[+-]?0\d")
_DECIMAL = re.compile(r"^[+-]?\d{1,15}\.\d{1,6}$")
_PERCENT = re.compile(r"^[+-]?\d{1,15}(\.\d{1,6})?\s?%$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?$")
_EXCEL_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")
_CELL_REFERENCE = re.compile(r"^([A-Za-z]{1,3}\d{1,7}|[Rr]\d+[Cc]\d+)$")

#: Excel's own header limit; beyond it the workbook is rejected.
MAX_HEADER_LENGTH = 255
#: Displaying more decimals than this reads as noise, not precision.
MAX_DECIMALS = 4


class ColumnKind(str, Enum):
    """What every non-empty cell of a column obeys."""

    TEXT = "text"
    INT = "int"
    DECIMAL = "decimal"
    PERCENT = "percent"
    DATE = "date"
    DATETIME = "datetime"


@dataclass(frozen=True, slots=True)
class ColumnType:
    """A column's kind and, for decimals and percentages, its widest scale."""

    kind: ColumnKind
    decimals: int = 0

    @property
    def numeric(self) -> bool:
        """Right-aligned in every format."""
        return self.kind in (ColumnKind.INT, ColumnKind.DECIMAL, ColumnKind.PERCENT)

    @property
    def number_format(self) -> str:
        """The Excel number format of the column."""
        scale = "0" * self.decimals
        if self.kind is ColumnKind.INT:
            return "0"
        if self.kind is ColumnKind.DECIMAL:
            return f"0.{scale}" if scale else "0"
        if self.kind is ColumnKind.PERCENT:
            return f"0.{scale}%" if scale else "0%"
        if self.kind is ColumnKind.DATE:
            return "yyyy-mm-dd"
        if self.kind is ColumnKind.DATETIME:
            return "yyyy-mm-dd hh:mm"
        return "@"


def _decimals_of(number: str) -> int:
    return len(number.split(".")[1]) if "." in number else 0


def _parses_date(value: str) -> bool:
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _parses_datetime(value: str) -> bool:
    try:
        datetime.fromisoformat(value.replace(" ", "T"))
    except ValueError:
        return False
    return True


def _cell_kind(cell: str) -> tuple[ColumnKind, int] | None:
    """The rule one non-empty cell obeys, with its scale; ``None`` for text."""
    value = cell.strip()
    if _LEADING_ZERO.match(value):
        # "01000" is a code, not a thousand: typing it would eat the zero.
        return None
    if _INT.match(value):
        return ColumnKind.INT, 0
    if _DECIMAL.match(value):
        return ColumnKind.DECIMAL, _decimals_of(value)
    if _PERCENT.match(value):
        return ColumnKind.PERCENT, _decimals_of(value.rstrip("%").strip())
    if _DATE.match(value) and _parses_date(value):
        return ColumnKind.DATE, 0
    if _DATETIME.match(value) and _parses_datetime(value):
        return ColumnKind.DATETIME, 0
    return None


def _resolve(kinds: set[ColumnKind], decimals: int) -> ColumnType:
    """The column type a set of per-cell verdicts agrees on."""
    if kinds == {ColumnKind.INT}:
        return ColumnType(ColumnKind.INT)
    if kinds and kinds <= {ColumnKind.INT, ColumnKind.DECIMAL}:
        # Integers and decimals are ONE numeric rule: a column of prices whose
        # round values lost their ".00" is still a column of prices.
        return ColumnType(ColumnKind.DECIMAL, min(decimals, MAX_DECIMALS))
    if len(kinds) == 1:
        kind = next(iter(kinds))
        scale = min(decimals, MAX_DECIMALS) if kind is ColumnKind.PERCENT else 0
        return ColumnType(kind, scale)
    return ColumnType(ColumnKind.TEXT)


def infer_column_types(headers: list[str], rows: list[list[str]]) -> list[ColumnType]:
    """One type per header column, by unanimity of the non-empty cells.

    Args:
        headers: Column headers (their count decides the width).
        rows: Data rows; shorter rows simply contribute nothing.

    Returns:
        One ``ColumnType`` per header, ``TEXT`` when nothing agreed.
    """
    types: list[ColumnType] = []
    for index in range(len(headers)):
        kinds: set[ColumnKind] = set()
        decimals = 0
        for row in rows:
            cell = row[index] if index < len(row) else ""
            if not cell.strip():
                continue
            matched = _cell_kind(cell)
            if matched is None:
                kinds = {ColumnKind.TEXT}
                break
            kinds.add(matched[0])
            decimals = max(decimals, matched[1])
        types.append(_resolve(kinds, decimals))
    return types


def typed_value(cell: str, column: ColumnType) -> str | int | float | date | datetime | None:
    """The spreadsheet value of one cell under its column's type.

    Args:
        cell: Raw cell text.
        column: The column's inferred type.

    Returns:
        A typed value, ``None`` for an empty cell, or the neutralized string.
    """
    value = cell.strip()
    if not value:
        return None
    if column.kind is ColumnKind.INT:
        return int(value)
    if column.kind is ColumnKind.DECIMAL:
        return float(value)
    if column.kind is ColumnKind.PERCENT:
        return float(value.rstrip("%").strip()) / 100
    if column.kind is ColumnKind.DATE:
        return date.fromisoformat(value)
    if column.kind is ColumnKind.DATETIME:
        return datetime.fromisoformat(value.replace(" ", "T"))
    return neutralize_formula(value)


def sanitize_headers(headers: list[str], language: str) -> list[str]:
    """Unique, non-empty, bounded headers — Excel refuses a Table otherwise.

    Args:
        headers: Raw headers, possibly empty or duplicated.
        language: Reader's language, for the generated column names.

    Returns:
        One header per input, unique case-insensitively.
    """
    result: list[str] = []
    taken: set[str] = set()
    for index, raw in enumerate(headers, start=1):
        base = strip_control_characters(" ".join(raw.split()))[
            :MAX_HEADER_LENGTH
        ] or document_label(language, "documents.column_label", n=index)
        name, suffix = base, 2
        while name.casefold() in taken:
            name = f"{base} ({suffix})"
            suffix += 1
        taken.add(name.casefold())
        result.append(name)
    return result


def normalize_sheet(sheet: TableSheet, language: str) -> TableSheet | None:
    """Widen ragged rows, generate missing headers, drop blank rows.

    Rows are WIDENED to the longest one rather than truncated: a cell beyond
    the headers gets a generated header, which is visible and repairable, where
    truncation would silently lose what the model wrote.

    Args:
        sheet: The model's table.
        language: Reader's language, for generated headers.

    Returns:
        A rectangular table, or ``None`` when there is nothing to render.
    """
    width = max(len(sheet.headers), max((len(row) for row in sheet.rows), default=0))
    if width == 0:
        return None
    padded_headers = list(sheet.headers) + [""] * (width - len(sheet.headers))
    rows = [
        [strip_control_characters(cell) for cell in (list(row) + [""] * (width - len(row)))[:width]]
        for row in sheet.rows
    ]
    rows = [row for row in rows if any(cell.strip() for cell in row)]
    return TableSheet(
        name=strip_control_characters(sheet.name),
        headers=sanitize_headers(padded_headers, language),
        rows=rows,
    )


def excel_table_name(index: int) -> str:
    """A workbook-unique, Excel-legal Table name — never the model's words."""
    return f"Table{index}"


def is_excel_legal_name(name: str) -> bool:
    """Excel's rules for a Table name: identifier-shaped, not a cell reference."""
    return bool(_EXCEL_NAME.match(name)) and not _CELL_REFERENCE.match(name)


def chunk_rows(rows: list[list[str]], size: int) -> list[list[list[str]]]:
    """Rows in slices of ``size`` (the last one shorter), for slide tables."""
    step = max(1, size)
    return [rows[start : start + step] for start in range(0, len(rows), step)]
