"""xlsx: typed cells, live formulas, a named Table, totals, a summary, a chart (ADR-226, ADR-274).

A spreadsheet whose numbers are strings is a picture of data, not data: it
cannot be summed, sorted or filtered. Columns are therefore TYPED (by unanimity
— see ``tables.py`` — or by the kind the writer declared) and carry their
display format; the header row is frozen and the rows sit in a named Table, so
Excel offers its filter and its sort.

A computed column is a LIVE formula: the reader changes a value and the sheet
follows. Each formula is written with the value ``computation.py`` computed,
because many readers never recalculate — a preview pane, a phone, the chat's
own excerpt — and openpyxl, the previous writer, could cache none (measured
2026-11-13: a reader saw ``None``). The totals row is the Table's own, its
cached totals given explicitly: XlsxWriter caches 0 otherwise (measured).

Two rules Excel enforces and we satisfy before writing: a Table's headers are
unique and non-empty, and its name is an identifier — both measured 2026-09-08,
both handled upstream in ``tables.py``.
"""

from __future__ import annotations

import io
from datetime import UTC
from typing import Any

from src.core.i18n_documents import document_label
from src.domains.document_generation import typography
from src.domains.document_generation.computation import (
    Column,
    ComputedTable,
    compute_table,
    input_values,
)
from src.domains.document_generation.context import RenderContext
from src.domains.document_generation.formulas import to_excel
from src.domains.document_generation.renderers.xlsx_charts import ChartSources, insert_chart
from src.domains.document_generation.renderers.xlsx_figures import (
    reserve_figures_sheet,
    write_figures,
)
from src.domains.document_generation.renderers.xlsx_parts import (
    Formats,
    Lists,
    SheetNames,
    TableNames,
    cached,
    column_width,
    print_setup,
    shown_texts,
    utility,
    write_inputs,
    write_summary,
    write_value,
    xlsxwriter,
)
from src.domains.document_generation.schemas import DocumentContent, TabularContent

#: The totals a column declares, as the Table's totals row names them.
_TOTAL_FUNCTIONS: dict[str, str] = {
    "sum": "sum",
    "average": "average",
    "min": "min",
    "max": "max",
    "count": "count",
}


class _Cells:
    """Where a formula's names live, for one data row of one sheet."""

    def __init__(
        self, letters: dict[str, str], excel_row: int, last_row: int, inputs: dict[str, str]
    ) -> None:
        self._letters = letters
        self._row = excel_row
        self._last = last_row
        self._inputs = inputs

    def cell(self, column: str) -> str:
        return f"{self._letters[column]}{self._row}"

    def previous_cell(self, column: str) -> str:
        return f"{self._letters[column]}{self._row - 1}"

    def column_range(self, column: str) -> str:
        letter = self._letters[column]
        return f"{letter}$2:{letter}${self._last}"

    def running_range(self, column: str) -> str:
        letter = self._letters[column]
        return f"{letter}$2:{letter}{self._row}"

    def sheet_range(self, sheet: str, column: str) -> str:
        # A row formula never names another sheet: the grammar refuses it.
        raise ValueError("a row formula reads no other sheet")

    def input_name(self, name: str) -> str:
        return self._inputs[name]


def _table_column(column: Column, total: Any, formats: Formats, first: bool) -> dict[str, Any]:
    """One column of the Table: its header, and its totals-row cell."""
    spec: dict[str, Any] = {"header": column.header, "header_format": formats.header()}
    if column.total:
        spec["total_function"] = _TOTAL_FUNCTIONS[column.total]
        spec["total_value"] = cached(total)
        spec["format"] = formats.cell(column)
    elif first:
        spec["total_string"] = document_label(formats.language, "documents.total_label")
    return spec


def _write_rows(
    worksheet: Any,
    table: ComputedTable,
    formats: Formats,
    inputs: dict[str, str],
    wide: list[bool],
) -> None:
    """Every data cell: a typed value, or a live formula with its value cached."""
    last_row = len(table.cells) + 1
    cell_formats = [
        formats.cell(column, wide=wide[position]) for position, column in enumerate(table.columns)
    ]
    letters = {
        column.header: utility().xl_col_to_name(index) for index, column in enumerate(table.columns)
    }
    for row, cells in enumerate(table.cells):
        excel_row = row + 2
        for position, column in enumerate(table.columns):
            cell_format = cell_formats[position]
            if column.formula is None:
                write_value(worksheet, row + 1, position, cells[position], cell_format)
                continue
            text = to_excel(column.formula, _Cells(letters, excel_row, last_row, inputs))
            if column.may_blank:
                text = f'IFERROR({text},"")'
            worksheet.write_formula(
                row + 1, position, f"={text}", cell_format, cached(cells[position])
            )


def _rules(worksheet: Any, table: ComputedTable, lists: Lists) -> None:
    """Drop-downs for closed lists, a colour scale for a measure with a good direction."""
    last = len(table.cells)
    for position, column in enumerate(table.columns):
        if column.choices and not column.computed:
            worksheet.data_validation(
                1,
                position,
                last,
                position,
                {"validate": "list", "source": lists.source(column.choices)},
            )
        if column.better:
            low, high = (
                (typography.XLSX_SCALE_NEUTRAL, typography.XLSX_SCALE_GOOD)
                if column.better == "higher"
                else (typography.XLSX_SCALE_GOOD, typography.XLSX_SCALE_NEUTRAL)
            )
            worksheet.conditional_format(
                1,
                position,
                last,
                position,
                {"type": "2_color_scale", "min_color": low, "max_color": high},
            )


def _write_sheet(book: _Book, table: ComputedTable, title: str, inputs: dict[str, str]) -> None:
    """One data sheet: Table, cells, widths, frozen header, rules, print setup."""
    worksheet = book.workbook.add_worksheet(title)
    columns = len(table.columns)
    widths = [
        column_width(column.header, shown_texts(table, position, book.formats.language))
        for position, column in enumerate(table.columns)
    ]
    if table.cells:
        totals = table.has_totals
        worksheet.add_table(
            0,
            0,
            len(table.cells) + (1 if totals else 0),
            columns - 1,
            {
                "name": book.tables.next(),
                "style": typography.XLSX_TABLE_STYLE,
                "total_row": totals,
                "columns": [
                    _table_column(column, total, book.formats, index == 0)
                    for index, (column, total) in enumerate(
                        zip(table.columns, table.totals, strict=True)
                    )
                ],
            },
        )
        wide = [width >= typography.XLSX_COLUMN_WIDTH_MAX for width in widths]
        _write_rows(worksheet, table, book.formats, inputs, wide)
        _rules(worksheet, table, book.lists)
        insert_chart(
            book.workbook,
            worksheet,
            table,
            title,
            book.charts,
            book.formats.language,
            book.palette.series,
        )
    else:
        # A Table over a header-only range is what Excel refuses to open.
        worksheet.write_row(
            0, 0, [column.header for column in table.columns], book.formats.header()
        )
    for position, width in enumerate(widths):
        worksheet.set_column(position, position, width)
    worksheet.freeze_panes(1, 0)
    print_setup(worksheet, columns, book.page_size, book.formats.language)


class _Book:
    """Per-workbook state: the writer, its formats, names, hidden lists and chart sources."""

    def __init__(self, workbook: Any, context: RenderContext, tone: str) -> None:
        self.workbook = workbook
        self.palette = typography.palette_for(tone)
        self.formats = Formats(workbook, context.language, self.palette)
        self.sheets = SheetNames()
        self.tables = TableNames()
        self.lists = Lists(workbook, self.sheets)
        self.charts = ChartSources(workbook, self.sheets)
        self.page_size = context.page_size


def render_xlsx(content: DocumentContent, context: RenderContext) -> bytes:
    """A workbook whose columns are data, whose computations stay alive."""
    if not isinstance(content, TabularContent):
        raise ValueError("xlsx rendering requires TabularContent")
    buffer = io.BytesIO()
    workbook = xlsxwriter().Workbook(
        buffer,
        {
            "in_memory": True,
            "strings_to_formulas": False,
            "strings_to_urls": False,
            "strings_to_numbers": False,
        },
    )
    book = _Book(workbook, context, content.tone)
    names = (
        write_inputs(workbook, book.formats, book.sheets, book.tables, content.inputs)
        if content.inputs
        else {}
    )
    figures = reserve_figures_sheet(workbook, book.sheets, book.formats.language, content.figures)
    values = input_values(content.inputs)
    written: dict[str, tuple[str, ComputedTable]] = {}
    for index, sheet in enumerate(content.sheets):
        table = compute_table(sheet, values)
        title = book.sheets.take(sheet.name, f"Sheet{index + 1}")
        _write_sheet(book, table, title, names)
        write_summary(workbook, book.formats, book.sheets, book.tables, table, title)
        written[sheet.name] = (title, table)
    if figures is not None:
        write_figures(
            figures, workbook, book.formats, book.tables, content.figures, values, names, written
        )
    book.lists.hide()
    book.charts.hide()
    properties: dict[str, Any] = {"title": content.title}
    if context.generated_at is not None:
        properties["created"] = context.generated_at.astimezone(UTC).replace(tzinfo=None)
    workbook.set_properties(properties)
    workbook.close()
    return buffer.getvalue()
