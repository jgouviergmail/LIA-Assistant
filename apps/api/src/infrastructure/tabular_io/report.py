"""Structured outcome of parsing a workbook.

Issues carry a **code and parameters**, never a sentence: the frontend resolves
them in the administrator's language, so the API never ships pre-translated
strings. Every issue also carries where it happened — sheet and cell — because
"row 42, column C" is the difference between a report an administrator can act
on and one they can only stare at.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class IssueCode(str, Enum):
    """Everything that can go wrong, as a closed vocabulary."""

    NOT_A_WORKBOOK = "not_a_workbook"
    ARCHIVE_TOO_LARGE = "archive_too_large"
    SCHEMA_VERSION_MISMATCH = "schema_version_mismatch"
    SHEET_MISSING = "sheet_missing"
    COLUMN_MISSING = "column_missing"
    TOO_MANY_ROWS = "too_many_rows"
    FORMULA_REJECTED = "formula_rejected"
    NOT_A_NUMBER = "not_a_number"
    NOT_A_BOOLEAN = "not_a_boolean"
    NOT_A_TIME = "not_a_time"
    TOO_MANY_DECIMALS = "too_many_decimals"
    OUT_OF_RANGE = "out_of_range"
    VALUE_NOT_IN_REFERENTIAL = "value_not_in_referential"
    KEY_MISSING = "key_missing"
    DUPLICATE_KEY = "duplicate_key"
    # Raised by a domain diff rather than by the parser: the value is readable,
    # it is the write path that cannot express it, or the world that moved.
    PROVIDER_IMMUTABLE = "provider_immutable"
    ROW_CHANGED_SINCE_EXPORT = "row_changed_since_export"
    REASONING_LEVEL_UNKNOWN = "reasoning_level_unknown"
    CREATION_FIELD_MISSING = "creation_field_missing"


#: Issues that make the whole file unusable rather than one cell wrong.
_STRUCTURAL: frozenset[IssueCode] = frozenset(
    {
        IssueCode.NOT_A_WORKBOOK,
        IssueCode.ARCHIVE_TOO_LARGE,
        IssueCode.SCHEMA_VERSION_MISMATCH,
        IssueCode.SHEET_MISSING,
        IssueCode.COLUMN_MISSING,
        IssueCode.TOO_MANY_ROWS,
    }
)


@dataclass(frozen=True)
class CellIssue:
    """One problem, located as precisely as it can be.

    Attributes:
        code: What went wrong.
        sheet: Worksheet name, when the problem has one.
        cell: Excel coordinate (``"C42"``), when the problem has one.
        column: Technical column key, when the problem has one.
        params: Values the translated message interpolates (limits, the
            offending text, the accepted values...).
    """

    code: IssueCode
    sheet: str | None = None
    cell: str | None = None
    column: str | None = None
    params: Mapping[str, str] = field(default_factory=dict)

    @property
    def is_structural(self) -> bool:
        """True when the file as a whole cannot be used."""
        return self.code in _STRUCTURAL


@dataclass(frozen=True)
class ParsedRow:
    """One data row, typed and located.

    Attributes:
        row_number: 1-based worksheet row, so a report can point at it.
        key: Value of the sheet's key column, when readable.
        values: Editable columns only, coerced to their declared kind — the
            administrator's input, and the only thing a diff may act on.
        derived: Read-only columns, coerced the same way. Carried because some
            of them are contracts rather than decoration (a row fingerprint),
            never because a caller should treat them as input.
    """

    row_number: int
    key: str | None
    values: Mapping[str, Any]
    derived: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ParsedWorkbook:
    """What a workbook yielded: typed rows per sheet, plus every issue found."""

    sheets: Mapping[str, Sequence[ParsedRow]]
    issues: Sequence[CellIssue]

    def rows(self, sheet_name: str) -> Sequence[ParsedRow]:
        """Rows parsed for a sheet; empty when the sheet was unusable."""
        return self.sheets.get(sheet_name, ())

    @property
    def has_blocking_issues(self) -> bool:
        """True when nothing may be applied from this file.

        Any issue blocks application — an import is all-or-nothing — but a
        structural one also means no row could be read at all.
        """
        return bool(self.issues)
