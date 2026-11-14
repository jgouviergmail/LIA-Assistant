"""The pieces of a workbook around its data (ADR-274 amendment).

Formats, legal names, the assumptions sheet whose cells the formulas read by
name, the grouped summary whose formulas read the data sheet, and the hidden
lists a drop-down reads. Every value written beside a formula is the one
``computation.py`` computed, so a reader that never recalculates — a preview
pane, a phone, the chat's own excerpt — shows what Excel will show.

XlsxWriter is imported on first use: ~5.8 MB per process, paid by every worker
at boot otherwise (measured 2026-11-13).
"""

from __future__ import annotations

import importlib
import math
import re
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from types import ModuleType
from typing import Any

from src.core.i18n_documents import document_label
from src.domains.document_generation import typography
from src.domains.document_generation.columns import effective_type
from src.domains.document_generation.computation import (
    CellValue,
    Column,
    ComputedTable,
    Summary,
    display_kind,
    display_text,
    serial,
    summary_columns,
    typed_cell,
)
from src.domains.document_generation.fit import display_columns
from src.domains.document_generation.numbers import excel_format
from src.domains.document_generation.sanitize import neutralize_formula
from src.domains.document_generation.schemas import ColumnSpec, SheetInput
from src.domains.document_generation.tables import (
    ColumnKind,
    excel_table_name,
    infer_column_types,
    is_table_name,
)

_XLSX_TITLE_FORBIDDEN = re.compile(r"[\[\]:*?/\\]")  # Excel rejects these in a sheet title
_XLSX_TITLE_MAX = 31  # Excel's hard sheet-title limit
#: Padding added to the longest value when sizing a column.
_WIDTH_PADDING = 2
#: What a defined name may not contain (Excel: letters, digits, ``_`` and ``.``).
_NAME_FORBIDDEN = re.compile(r"[^\w.]")
#: Names Excel reads as a cell (``TAX1``) or an R1C1 reference (``R``, ``C2``, ``R1C1``).
_CELL_LIKE = re.compile(r"^([A-Za-z]{1,3}\d+|[Rr]\d*([Cc]\d*)?|[Cc]\d*)$")
_RESERVED_NAMES = frozenset({"true", "false"})
#: The prefix of the names Excel keeps for itself (``_xlnm.Print_Area``, ``_xlnm._FilterDatabase``).
_BUILT_IN_NAME_PREFIX = "_xlnm."
#: The longest list Excel accepts written inline in a validation rule.
_INLINE_LIST_MAX_CHARS = 255
#: What an inline list cannot hold: a comma separates its items, and the list is
#: ONE quoted text of the rule's formula — XlsxWriter writes a quote inside it bare.
_INLINE_LIST_FORBIDDEN = frozenset(',"')
#: Excel's border style index of a toned header's rule (2 = medium).
_HEADER_RULE = 2


def xlsxwriter() -> ModuleType:
    """XlsxWriter, imported on first use."""
    return importlib.import_module("xlsxwriter")


def utility() -> ModuleType:
    """XlsxWriter's cell-reference helpers, imported on first use."""
    return importlib.import_module("xlsxwriter.utility")


class SheetNames:
    """Legal, unique sheet titles for one workbook."""

    def __init__(self) -> None:
        self._used: set[str] = set()

    def take(self, name: str, fallback: str) -> str:
        """A title Excel accepts, never one already taken (compared without case).

        Args:
            name: The wished title.
            fallback: The title when nothing of ``name`` survives.

        Returns:
            The title, recorded as taken.
        """
        cleaned = _XLSX_TITLE_FORBIDDEN.sub("_", name).strip().strip("'")[:_XLSX_TITLE_MAX]
        base = cleaned or fallback
        candidate, suffix = base, 2
        while candidate.casefold() in self._used:
            tail = f" {suffix}"
            candidate = f"{base[: _XLSX_TITLE_MAX - len(tail)]}{tail}"
            suffix += 1
        self._used.add(candidate.casefold())
        return candidate


class TableNames:
    """``Table1``, ``Table2``… across the whole workbook — never the model's words."""

    def __init__(self) -> None:
        self._count = 0

    def next(self) -> str:
        """The next workbook-unique table name."""
        self._count += 1
        return excel_table_name(self._count)


class Formats:
    """One XlsxWriter format per look, created once: a workbook caps its formats."""

    def __init__(
        self, workbook: Any, language: str, palette: typography.Palette = typography.PALETTES[""]
    ) -> None:
        self._workbook = workbook
        self.language = language
        self.palette = palette
        self._cache: dict[tuple[tuple[str, object], ...], Any] = {}

    def get(self, **properties: object) -> Any:
        """The format with these properties (created on first request)."""
        key = tuple(sorted(properties.items()))
        if key not in self._cache:
            self._cache[key] = self._workbook.add_format(dict(properties))
        return self._cache[key]

    def header(self) -> Any:
        """Bold, wrapped and centred: a header row stays readable at any width.

        A toned workbook lays the header on the tone's wash, over a rule of its
        accent; the text stays in ink, which every wash is light enough to carry.
        """
        if self.palette.accent is None:
            return self.get(bold=True, text_wrap=True, align="center", valign="vcenter")
        return self.get(
            bold=True,
            text_wrap=True,
            align="center",
            valign="vcenter",
            bg_color=f"#{self.palette.wash}",
            font_color=f"#{typography.INK}",
            bottom=_HEADER_RULE,
            bottom_color=f"#{self.palette.marker}",
        )

    def cell(self, column: Column, *, wide: bool = False) -> Any:
        """A column's cells: its number format, numbers right, dates centred."""
        properties: dict[str, object] = {"num_format": number_format(column, self.language)}
        if column.type.numeric:
            properties["align"] = "right"
        elif column.type.kind in (ColumnKind.DATE, ColumnKind.DATETIME):
            properties["align"] = "center"
        elif wide:
            properties.update(text_wrap=True, valign="top")
        return self.get(**properties)


def number_format(column: Column, language: str) -> str:
    """The Excel number format of a column.

    A declared (or computed) kind reads in the reader's conventions; an
    undeclared written column keeps the format its cells agree on (ADR-274).
    """
    kind = display_kind(column)
    if kind in ("text", "code"):
        return "@"
    if kind:
        return excel_format(kind, column.unit, column.type.decimals, language)
    return column.type.number_format


def write_value(worksheet: Any, row: int, column: int, value: CellValue, cell_format: Any) -> None:
    """One typed value; text goes through the formula neutralization (ADR-226)."""
    if value is None:
        worksheet.write_blank(row, column, None, cell_format)
    elif isinstance(value, Decimal):
        worksheet.write_number(row, column, float(value), cell_format)
    elif isinstance(value, date):
        worksheet.write_datetime(row, column, value, cell_format)
    else:
        worksheet.write_string(row, column, neutralize_formula(value), cell_format)


def cached(value: CellValue) -> float | str:
    """The value cached beside a formula: a number, or "" where it has none.

    A total of values Excel each holds can pass what a float holds: written as
    ``inf`` it would make Excel repair the file, so it is cached as nothing and
    the live formula says what Excel makes of it.
    """
    if isinstance(value, Decimal):
        number = float(value)
        return number if math.isfinite(number) else ""
    if isinstance(value, date):
        return float(serial(value))
    return ""


def column_width(header: str, texts: Sequence[str]) -> int:
    """Width in Excel's own unit — the average Latin character, not the code point."""
    longest = max((display_columns(text) for text in [header, *texts]), default=0.0)
    return min(
        max(int(longest) + _WIDTH_PADDING, typography.XLSX_COLUMN_WIDTH_MIN),
        typography.XLSX_COLUMN_WIDTH_MAX,
    )


def shown_texts(table: ComputedTable, position: int, language: str) -> list[str]:
    """What a column shows, for its width: the value as read, or the cell as written."""
    column = table.columns[position]
    if column.computed or column.kind:
        return [display_text(column, row[position], language) for row in table.cells]
    return [row[position] for row in table.raw]


def page_footer(language: str) -> str:
    """« Page 2 / 7 », centred, in the reader's words, with Excel's own fields."""
    template = document_label(language, "documents.page_of", page="\x00", total="\x01")
    escaped = template.replace("&", "&&")
    return "&C" + escaped.replace("\x00", "&P").replace("\x01", "&N")


def print_setup(worksheet: Any, columns: int, page_size: str, language: str) -> None:
    """A sheet that prints as a document: one page wide, its header on every page."""
    if columns > typography.XLSX_PORTRAIT_MAX_COLUMNS:
        worksheet.set_landscape()
    worksheet.set_paper(typography.XLSX_PAPER[page_size])
    worksheet.fit_to_pages(1, 0)
    worksheet.repeat_rows(0)
    worksheet.set_footer(page_footer(language))


def defined_name(raw: str, taken: set[str], index: int, *, fallback: str = "Input") -> str:
    """A legal, unique defined name for an input or a key figure — readable when its label allows.

    Args:
        raw: The input's label.
        taken: Names already defined, casefolded (mutated).
        index: The input's position, for the generated fallback.
        fallback: The generated name's stem (``Input_3``, ``Figure_2``).

    Returns:
        The name the formulas read.
    """
    # Truncated BEFORE the checks: a long label cut to the bound can become a cell
    # reference (« AB111…1x » cut to « AB111…1 »).
    name = _NAME_FORBIDDEN.sub("_", " ".join(raw.split()).replace(" ", "_"))[
        : typography.XLSX_NAME_MAX_CHARS
    ]
    illegal = (
        not name
        or not (name[0].isalpha() or name[0] == "_")
        or bool(_CELL_LIKE.match(name))
        or name.casefold() in _RESERVED_NAMES
        or name.casefold().startswith(_BUILT_IN_NAME_PREFIX)
        or is_table_name(name)
    )
    base = f"{fallback}_{index}" if illegal else name
    candidate, suffix = base, 2
    while candidate.casefold() in taken:
        candidate = f"{base}_{suffix}"
        suffix += 1
    taken.add(candidate.casefold())
    return candidate


def _input_column(item: SheetInput) -> Column:
    inferred = infer_column_types(["value"], [[item.value]])[0]
    spec = ColumnSpec(header=item.name, kind=item.kind, unit=item.unit)
    return Column(
        header=item.name,
        kind=item.kind,
        unit=item.unit,
        type=effective_type(spec, inferred, empty=False),
        formula=None,
        total="",
        better="",
        choices=(),
    )


def write_inputs(
    workbook: Any,
    formats: Formats,
    sheets: SheetNames,
    tables: TableNames,
    inputs: Sequence[SheetInput],
) -> dict[str, str]:
    """The assumptions sheet: one named cell per input, the first sheet a reader sees.

    Args:
        workbook: The XlsxWriter workbook.
        formats: Its formats.
        sheets: Its sheet titles.
        tables: Its table names.
        inputs: The canonical inputs.

    Returns:
        ``input name -> defined name``, for the formulas.
    """
    language = formats.language
    title = sheets.take(document_label(language, "documents.inputs_sheet"), "Inputs")
    worksheet = workbook.add_worksheet(title)
    headers = [
        document_label(language, key)
        for key in ("documents.input_name", "documents.input_value", "documents.input_note")
    ]
    worksheet.add_table(
        0,
        0,
        len(inputs),
        len(headers) - 1,
        {
            "name": tables.next(),
            "style": typography.XLSX_TABLE_STYLE,
            "columns": [
                {"header": header, "header_format": formats.header()} for header in headers
            ],
        },
    )
    names: dict[str, str] = {}
    taken: set[str] = set()
    sheet_reference = utility().quote_sheetname(title)
    for index, item in enumerate(inputs, start=1):
        column = _input_column(item)
        worksheet.write_string(index, 0, neutralize_formula(item.name))
        value = typed_cell(item.value, column.type)
        write_value(worksheet, index, 1, value, formats.cell(column))
        worksheet.write_string(index, 2, neutralize_formula(item.note))
        names[item.name] = defined_name(item.name, taken, index)
        workbook.define_name(names[item.name], f"={sheet_reference}!$B${index + 1}")
    widths = (
        [item.name for item in inputs],
        [item.value for item in inputs],
        [item.note for item in inputs],
    )
    for position, (header, texts) in enumerate(zip(headers, widths, strict=True)):
        worksheet.set_column(position, position, column_width(header, texts))
    worksheet.freeze_panes(1, 0)
    return names


def _criterion(cell: str) -> str:
    """An exact-match criterion: a label's ``*``, ``?`` and ``~`` are not wildcards,
    and a leading ``>`` is a character, not a comparison."""
    escaped = f'SUBSTITUTE(SUBSTITUTE(SUBSTITUTE({cell},"~","~~"),"*","~*"),"?","~?")'
    return f'"="&{escaped}'


def _summary_formula(function: str, measure: str, by: str, label_cell: str) -> str:
    criterion = _criterion(label_cell)
    if function == "count":
        return f"COUNTIFS({by},{criterion})"
    if function == "average":
        return f'IFERROR(AVERAGEIFS({measure},{by},{criterion}),"")'
    return f"SUMIFS({measure},{by},{criterion})"


def _summary_table(
    formats: Formats, summary: Summary, measures: list[Column], name: str
) -> dict[str, Any]:
    """The summary's Table: its headers, and a totals row when its measures add up."""
    totals = summary.function in ("sum", "count")
    columns: list[dict[str, Any]] = [
        {
            "header": summary.by,
            "header_format": formats.header(),
            "total_string": document_label(formats.language, "documents.total_label"),
        }
    ]
    for index, column in enumerate(measures):
        spec: dict[str, Any] = {
            "header": column.header,
            "header_format": formats.header(),
            "format": formats.cell(column),
        }
        if totals:
            spec["total_function"] = "sum"
            spec["total_value"] = cached(
                sum((values[index] or Decimal(0) for _label, values in summary.groups), Decimal(0))
            )
        columns.append(spec)
    return {
        "name": name,
        "style": typography.XLSX_TABLE_STYLE,
        "total_row": totals,
        "columns": columns,
    }


def write_summary(
    workbook: Any,
    formats: Formats,
    sheets: SheetNames,
    tables: TableNames,
    table: ComputedTable,
    data_title: str,
) -> None:
    """A data sheet's grouped summary, on a sheet of its own, read from the data.

    Args:
        workbook: The XlsxWriter workbook.
        formats: Its formats.
        sheets: Its sheet titles.
        tables: Its table names.
        table: The computed data sheet (its summary is written).
        data_title: The data sheet's title, which the formulas read.
    """
    summary = table.summary
    if summary is None:
        return
    language = formats.language
    title = sheets.take(
        summary.title or document_label(language, "documents.summary_title", column=summary.by),
        "Summary",
    )
    worksheet = workbook.add_worksheet(title)
    measures = summary_columns(table, language)
    reference = _DataReference(data_title, len(table.cells) + 1)
    by_range = reference.column(table.position(summary.by))
    worksheet.add_table(
        0,
        0,
        len(summary.groups) + (1 if summary.function in ("sum", "count") else 0),
        len(measures),
        _summary_table(formats, summary, measures, tables.next()),
    )
    for row, (label, values) in enumerate(summary.groups, start=1):
        worksheet.write_string(row, 0, neutralize_formula(label))
        for index, column in enumerate(measures):
            measure_range = (
                by_range
                if summary.function == "count"
                else reference.column(table.position(summary.measures[index]))
            )
            formula = _summary_formula(summary.function, measure_range, by_range, f"$A{row + 1}")
            worksheet.write_formula(
                row, index + 1, f"={formula}", formats.cell(column), cached(values[index])
            )
    _summary_widths(worksheet, summary, measures, language)
    worksheet.freeze_panes(1, 0)


class _DataReference:
    """Absolute references to a data sheet's data rows."""

    def __init__(self, title: str, last_row: int) -> None:
        self._sheet = utility().quote_sheetname(title)
        self._last = last_row

    def column(self, position: int) -> str:
        letter = utility().xl_col_to_name(position)
        return f"{self._sheet}!${letter}$2:${letter}${self._last}"


def _summary_widths(
    worksheet: Any, summary: Summary, measures: list[Column], language: str
) -> None:
    worksheet.set_column(0, 0, column_width(summary.by, [label for label, _ in summary.groups]))
    for index, column in enumerate(measures, start=1):
        texts = [display_text(column, values[index - 1], language) for _, values in summary.groups]
        worksheet.set_column(index, index, column_width(column.header, texts))


class Lists:
    """The hidden sheet a drop-down list reads when it cannot be written inline:
    too long for the rule, or holding a comma or a quote."""

    def __init__(self, workbook: Any, sheets: SheetNames) -> None:
        self._workbook = workbook
        self._sheets = sheets
        self._worksheet: Any | None = None
        self._title = ""
        self._columns = 0

    def source(self, choices: Sequence[str]) -> list[str] | str:
        """What a validation rule reads: the list itself, or a range of the lists sheet."""
        inline = sum(len(choice) for choice in choices) + len(choices) - 1
        writable = not any(_INLINE_LIST_FORBIDDEN & set(choice) for choice in choices)
        if inline <= _INLINE_LIST_MAX_CHARS and writable:
            return list(choices)
        if self._worksheet is None:
            self._title = self._sheets.take("Lists", "Lists")
            self._worksheet = self._workbook.add_worksheet(self._title)
        column = self._columns
        self._columns += 1
        for row, choice in enumerate(choices):
            self._worksheet.write_string(row, column, neutralize_formula(choice))
        letter = utility().xl_col_to_name(column)
        return f"={utility().quote_sheetname(self._title)}!${letter}$1:${letter}${len(choices)}"

    def hide(self) -> None:
        """Hide the lists sheet once the workbook's visible sheets exist."""
        if self._worksheet is not None:
            self._worksheet.hide()
