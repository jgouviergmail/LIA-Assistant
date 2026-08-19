"""Declarative description of an administration workbook.

One declaration drives both directions. The writer reads it to lay out sheets,
freeze the key column, attach dropdowns and lock the read-only cells; the reader
reads the same object to resolve columns **by technical key** and coerce each
cell to its declared kind. A domain that wants a workbook writes a
:class:`WorkbookSpec` and gets export and import from it — no format code.

Everything is validated at construction. A spec that cannot produce a readable
workbook must fail here rather than emit a file whose columns come back
unparseable: the round trip is the contract, and half of it is written days
before the other half runs.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

#: How a cell is written and, symmetrically, how it is parsed back.
#:
#: - ``text``: free string; empty string and absent are the same value.
#: - ``integer`` / ``decimal``: numbers, the latter with a declared scale.
#: - ``boolean``: written as the locale's yes/no words, parsed leniently.
#: - ``enum``: one value from a referential, rendered as a dropdown.
#: - ``enum_list``: several referential values, comma-separated in one cell.
#: - ``time_hhmm``: a ``HH:MM`` clock time (UTC time-slot boundaries).
ColumnKind = Literal[
    "text",
    "integer",
    "decimal",
    "boolean",
    "enum",
    "enum_list",
    "time_hhmm",
]

_REFERENTIAL_KINDS: frozenset[str] = frozenset({"enum", "enum_list"})

# openpyxl rejects these in a worksheet title, and Excel caps titles at 31 chars.
_SHEET_NAME_FORBIDDEN = re.compile(r"[\[\]:*?/\\]")
_SHEET_NAME_MAX_LENGTH = 31


class SpecError(ValueError):
    """A workbook specification could not produce a readable workbook."""


@dataclass(frozen=True)
class ColumnSpec:
    """One column of one sheet.

    Attributes:
        key: Technical identifier written to the (hidden) first row. Invariant
            across locales and column order — it is what the reader matches on.
        label_key: i18n key of the human label written to the second row.
        kind: How the cell is written and parsed.
        editable: False marks a derived or informational column: the writer
            locks it and the reader ignores whatever it contains.
        required: A row missing this value is reported as an issue.
        referential: Name of the value list backing a dropdown. Mandatory for
            ``enum``/``enum_list``, forbidden otherwise.
        decimals: Accepted scale for ``decimal``, forbidden otherwise. A value
            with more decimals is refused rather than silently rounded.
        minimum: Lower bound enforced on numeric kinds.
        block: Visual grouping; the writer colours the label row by block.
        width: Column width in characters.
        hidden: True hides the column in Excel. Reserved for values that travel
            both ways without concerning the reader — a per-row fingerprint is
            written by the export and read back by the import, and showing it
            would only invite someone to tidy it away.
    """

    key: str
    label_key: str
    kind: ColumnKind
    editable: bool = True
    required: bool = False
    referential: str | None = None
    decimals: int | None = None
    minimum: Decimal | None = None
    block: str = "default"
    width: int = 18
    hidden: bool = False

    def __post_init__(self) -> None:
        if not self.key.strip():
            raise SpecError("a column key must not be empty")

        needs_referential = self.kind in _REFERENTIAL_KINDS
        if needs_referential and not self.referential:
            raise SpecError(f"column {self.key!r} is {self.kind!r} and must name a referential")
        if not needs_referential and self.referential:
            raise SpecError(
                f"column {self.key!r} is {self.kind!r} and must not name a referential: "
                "a dropdown on a column parsed as free text would promise a constraint "
                "the reader does not enforce"
            )

        if self.kind == "decimal" and self.decimals is None:
            raise SpecError(f"decimal column {self.key!r} must declare its decimals")
        if self.kind != "decimal" and self.decimals is not None:
            raise SpecError(f"column {self.key!r} is not decimal and must not declare decimals")

        if self.required and not self.editable:
            raise SpecError(
                f"column {self.key!r} is read-only and cannot be required: "
                "the administrator has no way to provide the value"
            )


@dataclass(frozen=True)
class SheetSpec:
    """One worksheet: an ordered set of columns keyed by one of them.

    Attributes:
        name: Worksheet title, as Excel shows it.
        title_key: i18n key used by the notice to name the sheet.
        columns: Ordered columns; the order is the layout, never the contract.
        key_column: Key of the column identifying — or grouping — a row.
        key_is_unique: True when the key identifies one row. False marks a
            DETAIL sheet whose rows are grouped under a parent key and legitimately
            repeat it: a model with two tariff windows owns two rows. Found by
            simulating a real export, where every windowed model was refused as a
            duplicate.
    """

    name: str
    title_key: str
    columns: tuple[ColumnSpec, ...]
    key_column: str
    key_is_unique: bool = True
    _by_key: dict[str, ColumnSpec] = field(
        init=False, repr=False, compare=False, default_factory=dict
    )

    def __post_init__(self) -> None:
        if not self.columns:
            raise SpecError(f"sheet {self.name!r} declares no column")

        keys = [column.key for column in self.columns]
        duplicates = {key for key in keys if keys.count(key) > 1}
        if duplicates:
            raise SpecError(f"sheet {self.name!r} has duplicate column keys: {sorted(duplicates)}")

        if self.key_column not in keys:
            raise SpecError(
                f"sheet {self.name!r} declares key_column {self.key_column!r}, "
                f"which is not one of its columns"
            )

        if not self.name.strip():
            raise SpecError("a sheet name must not be empty")
        if len(self.name) > _SHEET_NAME_MAX_LENGTH:
            raise SpecError(
                f"sheet name {self.name!r} exceeds Excel's {_SHEET_NAME_MAX_LENGTH}-character limit"
            )
        if _SHEET_NAME_FORBIDDEN.search(self.name):
            raise SpecError(f"sheet name {self.name!r} contains a character Excel rejects")

        object.__setattr__(self, "_by_key", {column.key: column for column in self.columns})

    def column(self, key: str) -> ColumnSpec:
        """Return the column declared under ``key``.

        Raises:
            KeyError: when no column carries that key.
        """
        return self._by_key[key]

    @property
    def keys(self) -> tuple[str, ...]:
        """Every column key, in layout order."""
        return tuple(column.key for column in self.columns)

    @property
    def editable_keys(self) -> tuple[str, ...]:
        """Keys the administrator may change; the rest are read-only."""
        return tuple(column.key for column in self.columns if column.editable)


@dataclass(frozen=True)
class WorkbookSpec:
    """A whole workbook: its sheets and the value lists backing its dropdowns.

    Attributes:
        sheets: Ordered worksheets.
        referentials: Value lists by name. Built from the domain's enums, never
            from the values present in the data — otherwise a value never used
            yet would be missing from its dropdown.
        schema_version: Written to the metadata sheet and checked on import; a
            mismatch is refused rather than interpreted.
    """

    sheets: tuple[SheetSpec, ...]
    referentials: Mapping[str, Sequence[str]]
    schema_version: int
    _by_name: dict[str, SheetSpec] = field(
        init=False, repr=False, compare=False, default_factory=dict
    )

    def __post_init__(self) -> None:
        if not self.sheets:
            raise SpecError("a workbook declares no sheet")

        names = [sheet.name for sheet in self.sheets]
        duplicates = {name for name in names if names.count(name) > 1}
        if duplicates:
            raise SpecError(f"workbook has duplicate sheet names: {sorted(duplicates)}")

        for name, values in self.referentials.items():
            if not values:
                raise SpecError(
                    f"referential {name!r} is empty: its dropdown would be impossible to fill"
                )

        for sheet in self.sheets:
            for column in sheet.columns:
                if column.referential and column.referential not in self.referentials:
                    raise SpecError(
                        f"column {sheet.name}.{column.key} uses referential "
                        f"{column.referential!r}, which the workbook does not declare"
                    )

        object.__setattr__(self, "_by_name", {sheet.name: sheet for sheet in self.sheets})

    def sheet(self, name: str) -> SheetSpec:
        """Return the sheet declared under ``name``.

        Raises:
            KeyError: when no sheet carries that name.
        """
        return self._by_name[name]
