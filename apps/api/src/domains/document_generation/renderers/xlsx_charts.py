"""A workbook's charts: native, and fed by the sheet's own cells (ADR-274 amendment).

Excel draws the chart from the cells, so a reader who changes a value sees the
chart follow — the reason a spreadsheet's chart is never a picture. It is
placed beside its table, below the frozen header, and the sheet prints in
landscape so the two stay on one page.

A computed cell with no value holds "" (``IFERROR(…,"")``), and Excel plots
text as ZERO: a growth rate's first month would dive to 0 %. A drawn column
that can lack a value is therefore read through a hidden sheet of
``IF(ISNUMBER(x),x,NA())`` cells, each written with its cached value, and the
chart shows #N/A as nothing — a gap, as in every other format.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from src.domains.document_generation import typography
from src.domains.document_generation.charts import ChartData, ChartSeries, chart_data
from src.domains.document_generation.computation import ComputedTable
from src.domains.document_generation.numbers import display, excel_format
from src.domains.document_generation.renderers.chart_scale import text_width, values_fit
from src.domains.document_generation.renderers.xlsx_parts import SheetNames, cached, utility
from src.domains.document_generation.schemas import CHART_FORMS

#: XlsxWriter's name for each form.
_TYPES: dict[str, dict[str, str]] = {
    "column": {"type": "column"},
    "bar": {"type": "bar"},
    "line": {"type": "line"},
    "area": {"type": "area"},
    "scatter": {"type": "scatter"},
    "segmented": {"type": "bar", "subtype": "percent_stacked"},
    "pie": {"type": "pie"},
    "doughnut": {"type": "doughnut"},
}

# Boot-time completeness (ADR-085): every form a chart can take has its Excel type.
assert set(_TYPES) == set(CHART_FORMS), "_TYPES must cover every chart form"

_SHARE_FORMS = frozenset({"segmented", "pie", "doughnut"})
_LINE_WIDTH_PT = 2.25
_MARKER_SIZE = 6
_MARKERS_MAX = 24
#: An area is a wash of its colour, never a saturated block (percent transparent).
_AREA_TRANSPARENCY = 65
_AXIS_FONT = {"size": 9, "color": f"#{typography.MUTED}"}
_LABEL_FONT = {"size": 9, "color": f"#{typography.INK}"}
#: A segment's label is written inside it only where it fits (in points).
_PLOT_WIDTH_PT = typography.XLSX_CHART_WIDTH_PX * 0.75 * 0.9
#: Room per category a horizontal bar chart takes, in pixels.
_BAR_STEP_PX = 22
_CHART_TOP_PX = 70


def _color(data: ChartData, index: int) -> str:
    return f"#{data.color(index)}"


class ChartSources:
    """The hidden sheet a chart reads a computed column through, created on first need."""

    def __init__(self, workbook: Any, sheets: SheetNames) -> None:
        self._workbook = workbook
        self._sheets = sheets
        self._worksheet: Any | None = None
        self._title = ""
        self._columns = 0

    def values(self, title: str, table: ComputedTable, position: int) -> list[Any]:
        """The cells a series reads: its column, or a gap-safe copy of it.

        Args:
            title: The data sheet's title.
            table: The computed table.
            position: The drawn column.

        Returns:
            ``[sheet, first_row, column, last_row, column]``, as XlsxWriter reads a range.
        """
        rows = len(table.cells)
        if not table.columns[position].may_blank:
            return [title, 1, position, rows, position]
        if self._worksheet is None:
            self._title = self._sheets.take("ChartData", "ChartData")
            self._worksheet = self._workbook.add_worksheet(self._title)
        column = self._columns
        self._columns += 1
        sheet = utility().quote_sheetname(title)
        letter = utility().xl_col_to_name(position)
        for row in range(rows):
            source = f"{sheet}!${letter}${row + 2}"
            value = None if (row, position) in table.errors else table.cells[row][position]
            shown = cached(value) if value is not None else "#N/A"
            self._worksheet.write_formula(
                row, column, f"=IF(ISNUMBER({source}),{source},NA())", None, shown
            )
        return [self._title, 0, column, rows - 1, column]

    def hide(self) -> None:
        """Hide the sheet once the workbook's visible sheets exist."""
        if self._worksheet is not None:
            self._worksheet.hide()


def _number_format(series: ChartSeries, language: str) -> str:
    return excel_format(series.kind, series.unit, series.decimals, language)


def _marks(form: str, color: str, points: int) -> dict[str, Any]:
    """How one series is drawn: a fill for bars, a line with ringed markers, a wash."""
    if form in ("column", "bar"):
        return {"fill": {"color": color}, "border": {"none": True}}
    marker: dict[str, Any] = {
        "type": "circle",
        "size": _MARKER_SIZE,
        "fill": {"color": color},
        "border": {"color": "#FFFFFF"},
    }
    if form == "scatter":
        return {"marker": marker}
    if form == "area":
        # An area's border would run along its baseline and up its sides: a wash alone.
        return {
            "fill": {"color": color, "transparency": _AREA_TRANSPARENCY},
            "line": {"none": True},
        }
    return {
        "line": {"color": color, "width": _LINE_WIDTH_PT},
        "marker": marker if points <= _MARKERS_MAX else {"type": "none"},
    }


def _value_labels(data: ChartData, language: str) -> dict[str, Any] | None:
    """Values written beside single-series marks, and only a few of them."""
    if len(data.series) != 1:
        return None
    labels: dict[str, Any] = {
        "value": True,
        "num_format": _number_format(data.series[0], language),
        "font": _LABEL_FONT,
    }
    if data.form in ("column", "bar"):
        band = _PLOT_WIDTH_PT / len(data.categories)
        crowded = data.form == "column" and not values_fit(data.series[0], 9, band - 2, language)
        if len(data.categories) > typography.CHART_VALUE_LABELS_MAX or crowded:
            return None
        return {**labels, "position": "outside_end"}
    if data.form in ("line", "area"):
        # The last value only: where the line ends, the reader looks.
        last = max(
            (index for index, value in enumerate(data.series[0].values) if value is not None),
            default=None,
        )
        if last is None:
            return None
        custom = [{"delete": True} if index != last else None for index in range(last + 1)]
        # An area admits no label position (OOXML): Office would « repair » the file.
        placed = {"position": "right"} if data.form == "line" else {}
        return {**labels, **placed, "custom": custom}
    return None


def _category_series(
    chart: Any,
    data: ChartData,
    title: str,
    table: ComputedTable,
    sources: ChartSources,
    language: str,
) -> None:
    rows = len(table.cells)
    categories = [title, 1, data.category_position, rows, data.category_position]
    labels = _value_labels(data, language)
    for index, position in enumerate(data.value_positions):
        options: dict[str, Any] = {
            "name": [title, 0, position],
            "categories": categories,
            "values": sources.values(title, table, position),
            **_marks(data.form, _color(data, index), rows),
        }
        if labels is not None:
            options["data_labels"] = labels
        chart.add_series(options)


def _scatter_series(
    chart: Any, data: ChartData, title: str, table: ComputedTable, sources: ChartSources
) -> None:
    across = sources.values(title, table, data.value_positions[0])
    for index, position in enumerate(data.value_positions[1:]):
        chart.add_series(
            {
                "name": [title, 0, position],
                "categories": across,
                "values": sources.values(title, table, position),
                **_marks("scatter", _color(data, index), len(table.cells)),
            }
        )


def _fits(text: str, share: float) -> bool:
    return text_width(text, 9) + 8 <= _PLOT_WIDTH_PT * share


def _part_series(
    chart: Any, data: ChartData, title: str, table: ComputedTable, language: str
) -> None:
    """A segmented bar: one series per part, named by its row, colour by its row."""
    series = data.series[0]
    total = sum(series.present(), Decimal(0))
    position = data.value_positions[0]
    for row, value in enumerate(series.values):
        if value is None or value <= 0:
            continue
        options: dict[str, Any] = {
            "name": [title, row + 1, data.category_position],
            "values": [title, row + 1, position, row + 1, position],
            "fill": {"color": _color(data, row)},
            "border": {"color": "#FFFFFF", "width": 1.5},
        }
        written = display(value, series.kind, series.unit, series.decimals, language)
        if _fits(written, float(value / total)):
            options["data_labels"] = {
                "value": True,
                "position": "center",
                "num_format": _number_format(series, language),
                "font": {"size": 9, "color": f"#{typography.label_on(data.color(row))}"},
            }
        chart.add_series(options)


def _round_series(chart: Any, data: ChartData, title: str, rows: int) -> None:
    position = data.value_positions[0]
    chart.add_series(
        {
            "name": [title, 0, position],
            "categories": [title, 1, data.category_position, rows, data.category_position],
            "values": [title, 1, position, rows, position],
            "points": [
                {"fill": {"color": _color(data, row)}, "border": {"color": "#FFFFFF", "width": 1.5}}
                for row in range(rows)
            ],
            "data_labels": {"percentage": True, "font": _LABEL_FONT},
        }
    )


def _value_axis(series: ChartSeries, language: str, *, name: str = "") -> dict[str, Any]:
    axis: dict[str, Any] = {
        "num_format": _number_format(series, language),
        "num_font": _AXIS_FONT,
        "major_gridlines": {
            "visible": True,
            "line": {"color": f"#{typography.RULE_LIGHT}", "width": 0.75},
        },
        "line": {"none": True},
    }
    if name:
        axis["name"] = name
        axis["name_font"] = {"size": 9, "bold": False, "color": f"#{typography.INK}"}
    return axis


def _category_axis(*, reverse: bool = False) -> dict[str, Any]:
    axis: dict[str, Any] = {
        "num_font": _AXIS_FONT,
        "line": {"color": f"#{typography.RULE}"},
        "major_tick_mark": "none",
    }
    if reverse:
        # The first category on top, and the value axis kept at the bottom.
        axis.update(reverse=True, crossing="max")
    return axis


def _axes(chart: Any, data: ChartData, language: str) -> None:
    """Value axis with hairline gridlines; categories plain; a bar's first category on top."""
    if data.form in ("pie", "doughnut"):
        return
    if data.form == "segmented":
        chart.set_x_axis({"num_font": _AXIS_FONT, "line": {"none": True}})
        chart.set_y_axis({"visible": False})
        return
    if data.form == "scatter":
        ups = data.series[1:]
        chart.set_x_axis(_value_axis(data.series[0], language, name=data.series[0].name))
        chart.set_y_axis(_value_axis(ups[0], language, name=ups[0].name if len(ups) == 1 else ""))
        return
    if data.form == "bar":
        chart.set_x_axis(_value_axis(data.axis, language))
        chart.set_y_axis(_category_axis(reverse=True))
        return
    chart.set_x_axis(_category_axis())
    chart.set_y_axis(_value_axis(data.axis, language))


def _legend(data: ChartData) -> dict[str, Any]:
    if data.form in ("pie", "doughnut"):
        return {"position": "right", "font": _LABEL_FONT}
    drawn = len(data.series) - (1 if data.form == "scatter" else 0)
    if data.form == "segmented" or drawn >= 2:
        return {"position": "bottom", "font": _LABEL_FONT}
    return {"none": True}


def _height(data: ChartData) -> int:
    if data.form == "segmented":
        return typography.XLSX_CHART_SEGMENTED_HEIGHT_PX
    if data.form == "bar":
        return max(
            typography.XLSX_CHART_HEIGHT_PX, _CHART_TOP_PX + _BAR_STEP_PX * len(data.categories)
        )
    return typography.XLSX_CHART_HEIGHT_PX


def insert_chart(
    workbook: Any,
    worksheet: Any,
    table: ComputedTable,
    title: str,
    sources: ChartSources,
    language: str,
    colors: tuple[str, ...],
) -> None:
    """Draw the table's chart beside it, when it declares one.

    Args:
        workbook: The XlsxWriter workbook.
        worksheet: The data sheet.
        table: The computed table (its chart settled).
        title: The data sheet's title, which every series reads.
        sources: The workbook's hidden gap-safe columns.
        language: The reader's backend-canonical language.
        colors: The workbook's tone's series colours.
    """
    data = chart_data(table, language, colors)
    if data is None:
        return
    chart = workbook.add_chart(dict(_TYPES[data.form]))
    if data.form == "segmented":
        _part_series(chart, data, title, table, language)
    elif data.form == "scatter":
        _scatter_series(chart, data, title, table, sources)
    elif data.form in _SHARE_FORMS:
        _round_series(chart, data, title, len(table.cells))
    else:
        _category_series(chart, data, title, table, sources, language)
    _axes(chart, data, language)
    chart.set_title(
        {"name": data.title, "name_font": {"size": 12, "bold": True, "color": f"#{typography.INK}"}}
        if data.title
        else {"none": True}
    )
    chart.set_legend(_legend(data))
    chart.set_chartarea({"border": {"none": True}})
    chart.show_blanks_as("gap")
    chart.show_na_as_empty_cell()
    chart.set_size({"width": typography.XLSX_CHART_WIDTH_PX, "height": _height(data)})
    worksheet.insert_chart(
        1, len(table.columns) + 1, chart, {"x_offset": 16, "y_offset": 4, "object_position": 1}
    )
    worksheet.set_landscape()
