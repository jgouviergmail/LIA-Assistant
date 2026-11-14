"""A workbook's key figures, on a sheet of their own: one live formula each (ADR-388).

The sheet comes after the assumptions and before the data: a reader sees what was
assumed, what it amounts to, then the detail. Each figure's value cell is a live
formula reading the inputs and the other figures by their defined names, and a
sheet's whole column by its absolute range, with the value the same grammar
computed cached beside it — a reader that never recalculates still sees it. A
figure that may have no value is wrapped in ``IFERROR(…, "")``, as a computed
column is, and each figure is a defined name itself: another figure reads a name.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

from src.core.i18n_documents import document_label
from src.domains.document_generation import typography
from src.domains.document_generation.columns import column_key
from src.domains.document_generation.computation import (
    ComputedTable,
    computed_column,
    display_text,
)
from src.domains.document_generation.formulas import to_excel
from src.domains.document_generation.renderers.xlsx_parts import (
    Formats,
    SheetNames,
    TableNames,
    cached,
    column_width,
    defined_name,
    utility,
)
from src.domains.document_generation.sanitize import neutralize_formula
from src.domains.document_generation.schemas import WorkbookFigure
from src.domains.document_generation.workbook_figures import (
    blank_figures,
    compute_figures,
    parsed_figures,
)


def reserve_figures_sheet(
    workbook: Any, sheets: SheetNames, language: str, figures: Sequence[WorkbookFigure]
) -> Any | None:
    """The key figures' sheet, created now so it comes before the data.

    Args:
        workbook: The XlsxWriter workbook.
        sheets: Its sheet titles.
        language: The reader's language (the sheet's title).
        figures: The canonical figures.

    Returns:
        The worksheet, filled by ``write_figures`` once the data sheets exist;
        ``None`` when the workbook has no figure.
    """
    if not figures:
        return None
    title = sheets.take(document_label(language, "documents.figures_sheet"), "Figures")
    return workbook.add_worksheet(title)


class _FigureCells:
    """Where a key figure's names live: defined names, and the data sheets' columns."""

    def __init__(
        self, names: Mapping[str, str], sheets: Mapping[str, tuple[str, ComputedTable]]
    ) -> None:
        self._names = names
        self._sheets = sheets

    def cell(self, column: str) -> str:
        raise ValueError("a key figure reads no row")

    def previous_cell(self, column: str) -> str:
        raise ValueError("a key figure reads no row")

    def column_range(self, column: str) -> str:
        raise ValueError("a key figure reads no row")

    def running_range(self, column: str) -> str:
        raise ValueError("a key figure reads no row")

    def sheet_range(self, sheet: str, column: str) -> str:
        title, table = self._sheets[sheet]
        letter = utility().xl_col_to_name(table.position(column))
        reference = utility().quote_sheetname(title)
        return f"{reference}!${letter}$2:${letter}${len(table.cells) + 1}"

    def input_name(self, name: str) -> str:
        return self._names[name]


def write_figures(
    worksheet: Any,
    workbook: Any,
    formats: Formats,
    tables: TableNames,
    figures: Sequence[WorkbookFigure],
    inputs: Mapping[str, Decimal],
    names: Mapping[str, str],
    sheets: Mapping[str, tuple[str, ComputedTable]],
) -> None:
    """Fill the key figures' sheet: one named, live, cached value per figure.

    Args:
        worksheet: The sheet ``reserve_figures_sheet`` created.
        workbook: The XlsxWriter workbook.
        formats: Its formats.
        tables: Its table names.
        figures: The canonical figures.
        inputs: The workbook's input values, by name.
        names: ``input name -> defined name``.
        sheets: Each data sheet's title and computed table, by the sheet's name.
    """
    computed = {name: table for name, (_title, table) in sheets.items()}
    parsed = parsed_figures(figures, list(inputs), computed)
    values = compute_figures(figures, inputs, computed)
    blank = blank_figures(parsed, list(inputs))
    shown = [figure for figure in figures if figure.label in parsed]
    language = formats.language
    headers = [
        document_label(language, "documents.figure_name"),
        document_label(language, "documents.input_value"),
    ]
    if not shown:
        # A Table over a header-only range is what Excel refuses to open.
        worksheet.write_row(0, 0, headers, formats.header())
        return
    worksheet.add_table(
        0,
        0,
        len(shown),
        len(headers) - 1,
        {
            "name": tables.next(),
            "style": typography.XLSX_TABLE_STYLE,
            "columns": [
                {"header": header, "header_format": formats.header()} for header in headers
            ],
        },
    )
    readable = dict(names)
    taken = {name.casefold() for name in names.values()}
    inputs_read = {column_key(name) for name in names}
    reference = utility().quote_sheetname(worksheet.get_name())
    for row, figure in enumerate(shown, start=1):
        name = defined_name(figure.label, taken, row, fallback="Figure")
        workbook.define_name(name, f"={reference}!$B${row + 1}")
        # An input wins over a figure of its name, as the computation reads it:
        # the figure keeps a name of its own, and its formula reads the input.
        if column_key(figure.label) not in inputs_read:
            readable[figure.label] = name
    cells = _FigureCells(readable, sheets)
    shown_values: list[str] = []
    for row, figure in enumerate(shown, start=1):
        value = values.get(figure.label)
        formula = parsed[figure.label]
        column = computed_column(figure.label, figure.kind, figure.unit, formula, [value])
        text = to_excel(formula, cells)
        if figure.label in blank:
            text = f'IFERROR({text},"")'
        worksheet.write_string(row, 0, neutralize_formula(figure.label))
        worksheet.write_formula(row, 1, f"={text}", formats.cell(column), cached(value))
        shown_values.append(display_text(column, value, language))
    worksheet.set_column(0, 0, column_width(headers[0], [figure.label for figure in shown]))
    worksheet.set_column(1, 1, column_width(headers[1], shown_values))
    worksheet.freeze_panes(1, 0)
