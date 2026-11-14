"""A slide's chart: native, so the presenter can restyle it (ADR-274 amendment).

PowerPoint draws the chart from data embedded in the deck — the presenter can
open it, change a value, recolour a series — the reason a slide's chart is
never a picture. The marks follow the same doctrine as every format's: the
validated palette in order, hairline gridlines, no axis line, text in ink, a
legend for two series or more, values written only where they are few, the
first category of horizontal bars on top with its value axis kept below.

python-pptx writes the embedded workbook with XlsxWriter, so ``pptx.chart.data``
is imported on first use, like XlsxWriter itself (5.8 MB per process).
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from decimal import Decimal
from typing import Any

from pptx.dml.color import RGBColor
from pptx.enum.chart import (
    XL_CHART_TYPE,
    XL_LABEL_POSITION,
    XL_LEGEND_POSITION,
    XL_MARKER_STYLE,
    XL_TICK_MARK,
)
from pptx.oxml.ns import qn
from pptx.oxml.xmlchemy import OxmlElement
from pptx.util import Inches, Pt

from src.domains.document_generation import typography
from src.domains.document_generation.charts import ChartData, ChartSeries
from src.domains.document_generation.numbers import display, excel_format
from src.domains.document_generation.renderers import pptx_geometry as geometry
from src.domains.document_generation.renderers.chart_scale import text_width, values_fit
from src.domains.document_generation.schemas import CHART_FORMS

_TYPES: dict[str, Any] = {
    "column": XL_CHART_TYPE.COLUMN_CLUSTERED,
    "bar": XL_CHART_TYPE.BAR_CLUSTERED,
    "line": XL_CHART_TYPE.LINE_MARKERS,
    "area": XL_CHART_TYPE.AREA,
    "scatter": XL_CHART_TYPE.XY_SCATTER,
    "segmented": XL_CHART_TYPE.BAR_STACKED_100,
    "pie": XL_CHART_TYPE.PIE,
    "doughnut": XL_CHART_TYPE.DOUGHNUT,
}

# Boot-time completeness (ADR-085): every form a chart can take has its PowerPoint type.
assert set(_TYPES) == set(CHART_FORMS), "_TYPES must cover every chart form"

_TEXT_PT = 12
_LINE_PT = 2.25
_MARKER_SIZE = 7
_MARKERS_MAX = 24
#: An area's wash: its colour at a third of its strength (thousandths of a percent).
_AREA_ALPHA = 35000
#: A segmented bar is a strip across the slide, not a block filling it.
_SEGMENTED_HEIGHT_IN = 2.2
#: Width a label may take inside a segment, in points (the plot spans the frame).
_PLOT_WIDTH_PT = geometry.TABLE_WIDTH_IN * 72 * 0.9


def _rgb(hex_color: str) -> RGBColor:
    color: RGBColor = RGBColor.from_string(hex_color)
    return color


def _color(data: ChartData, index: int) -> RGBColor:
    return _rgb(data.color(index))


def _number_format(series: ChartSeries, language: str) -> str:
    return excel_format(series.kind, series.unit, series.decimals, language)


def _floats(values: tuple[Decimal | None, ...]) -> list[float | None]:
    return [float(value) if value is not None else None for value in values]


def _data(data: ChartData, language: str) -> Any:
    """The data PowerPoint embeds: categories and series, or X/Y points."""
    module = importlib.import_module("pptx.chart.data")
    if data.form == "scatter":
        points = module.XyChartData()
        across = data.series[0]
        for series in data.series[1:]:
            target = points.add_series(series.name, number_format=_number_format(series, language))
            for x, y in zip(across.values, series.values, strict=True):
                if x is not None and y is not None:
                    target.add_data_point(float(x), float(y))
        return points
    table = module.CategoryChartData(number_format=_number_format(data.axis, language))
    if data.form == "segmented":
        table.categories = [data.series[0].name]
        for label, value in zip(data.categories, data.series[0].values, strict=True):
            if value is not None and value > 0:
                table.add_series(label, [float(value)])
        return table
    table.categories = list(data.categories)
    for series in data.series:
        table.add_series(
            series.name, _floats(series.values), number_format=_number_format(series, language)
        )
    return table


def _paint(chart: Any, data: ChartData) -> None:
    """Each series in its slot of the validated palette; a part keeps its row's colour."""
    plot = chart.plots[0]
    if data.form in ("pie", "doughnut"):
        for index, point in enumerate(plot.series[0].points):
            point.format.fill.solid()
            point.format.fill.fore_color.rgb = _color(data, index)
        return
    rows = [
        row for row, value in enumerate(data.series[0].values) if value is not None and value > 0
    ]
    for index, series in enumerate(plot.series):
        color = _color(data, rows[index] if data.form == "segmented" else index)
        if data.form in ("line", "scatter"):
            series.format.line.color.rgb = color
            series.format.line.width = Pt(_LINE_PT)
            if data.form == "scatter":
                series.format.line.fill.background()
            _marker(
                series,
                color,
                visible=len(data.categories) <= _MARKERS_MAX or data.form == "scatter",
            )
        elif data.form == "area":
            _wash(series, color)
        else:
            series.format.fill.solid()
            series.format.fill.fore_color.rgb = color


def _wash(series: Any, color: RGBColor) -> None:
    """An area as a translucent wash of its colour, never a saturated block.

    python-pptx exposes no transparency: the alpha is written on the colour
    element itself (``a:alpha``, in thousandths of a percent).
    """
    series.format.fill.solid()
    series.format.fill.fore_color.rgb = color
    series.format.line.fill.background()
    solid = series._element.spPr.find(qn("a:solidFill"))
    alpha = OxmlElement("a:alpha")
    alpha.set("val", str(_AREA_ALPHA))
    solid.find(qn("a:srgbClr")).append(alpha)


def _marker(series: Any, color: RGBColor, *, visible: bool) -> None:
    """A dot ringed in white, legible where it crosses a line."""
    if not visible:
        series.marker.style = XL_MARKER_STYLE.NONE
        return
    series.marker.style = XL_MARKER_STYLE.CIRCLE
    series.marker.size = _MARKER_SIZE
    series.marker.format.fill.solid()
    series.marker.format.fill.fore_color.rgb = color
    series.marker.format.line.color.rgb = _rgb("FFFFFF")


def _label(point: Any, text: str, position: Any | None, color: str = typography.INK) -> None:
    """One point's label, written as text: only where the reader needs it.

    An area admits no label position (OOXML): ``None`` leaves PowerPoint's own.
    """
    label = point.data_label
    label.has_text_frame = True
    label.text_frame.text = text
    if position is not None:
        label.position = position
    for paragraph in label.text_frame.paragraphs:
        for run in paragraph.runs:
            run.font.size = Pt(_TEXT_PT)
            run.font.color.rgb = _rgb(color)


def _values(chart: Any, data: ChartData, language: str) -> None:
    """Values written beside single-series marks, only a few; a part's inside it when it fits."""
    plot = chart.plots[0]
    if data.form in ("pie", "doughnut"):
        plot.has_data_labels = True
        plot.data_labels.show_percentage = True
        plot.data_labels.show_value = False
        plot.data_labels.number_format = "0%"
        plot.data_labels.number_format_is_linked = False
        plot.data_labels.font.size = Pt(_TEXT_PT)
        return
    if data.form == "segmented":
        _part_values(plot, data, language)
        return
    if len(data.series) != 1 or data.form == "scatter":
        return
    series = data.series[0]
    if data.form in ("column", "bar"):
        band = _PLOT_WIDTH_PT / len(data.categories)
        crowded = data.form == "column" and not values_fit(series, _TEXT_PT, band - 2, language)
        if len(data.categories) <= typography.CHART_VALUE_LABELS_MAX and not crowded:
            plot.has_data_labels = True
            plot.data_labels.number_format = _number_format(series, language)
            plot.data_labels.number_format_is_linked = False
            plot.data_labels.position = XL_LABEL_POSITION.OUTSIDE_END
            plot.data_labels.font.size = Pt(_TEXT_PT)
        return
    present = [(index, value) for index, value in enumerate(series.values) if value is not None]
    if present:
        last, value = present[-1]
        text = display(value, series.kind, series.unit, series.decimals, language)
        position = XL_LABEL_POSITION.RIGHT if data.form == "line" else None
        _label(plot.series[0].points[last], text, position)


def _part_values(plot: Any, data: ChartData, language: str) -> None:
    series = data.series[0]
    rows = [row for row, value in enumerate(series.values) if value is not None and value > 0]
    present = [value for value in series.values if value is not None and value > 0]
    total = sum(present, Decimal(0))
    for index, (drawn, value) in enumerate(zip(plot.series, present, strict=True)):
        text = display(value, series.kind, series.unit, series.decimals, language)
        if text_width(text, _TEXT_PT) + 8 <= _PLOT_WIDTH_PT * float(value / total):
            fill = data.color(rows[index])
            _label(drawn.points[0], text, XL_LABEL_POSITION.CENTER, typography.label_on(fill))


def _value_axis(axis: Any, series: ChartSeries, language: str, title: str = "") -> None:
    axis.has_major_gridlines = True
    axis.major_gridlines.format.line.color.rgb = _rgb(typography.RULE_LIGHT)
    axis.major_gridlines.format.line.width = Pt(0.75)
    axis.format.line.fill.background()
    axis.major_tick_mark = XL_TICK_MARK.NONE
    axis.tick_labels.number_format = _number_format(series, language)
    axis.tick_labels.number_format_is_linked = False
    axis.tick_labels.font.size = Pt(_TEXT_PT)
    axis.tick_labels.font.color.rgb = _rgb(typography.MUTED)
    if title:
        axis.has_title = True
        axis.axis_title.text_frame.text = title


def _category_axis(axis: Any) -> None:
    axis.format.line.color.rgb = _rgb(typography.RULE)
    axis.major_tick_mark = XL_TICK_MARK.NONE
    axis.tick_labels.font.size = Pt(_TEXT_PT)


def _axes(chart: Any, data: ChartData, language: str) -> None:
    if data.form in ("pie", "doughnut"):
        return
    if data.form == "segmented":
        chart.category_axis.visible = False
        chart.value_axis.has_major_gridlines = False
        chart.value_axis.tick_labels.font.size = Pt(_TEXT_PT)
        return
    if data.form == "scatter":
        ups = data.series[1:]
        _value_axis(chart.category_axis, data.series[0], language, data.series[0].name)
        _value_axis(chart.value_axis, ups[0], language, ups[0].name if len(ups) == 1 else "")
        return
    _value_axis(chart.value_axis, data.axis, language)
    _category_axis(chart.category_axis)
    if data.form == "bar":
        # The first category on top, and the value axis kept at the bottom.
        chart.category_axis.reverse_order = True
        crosses = chart.value_axis._element.find(qn("c:crosses"))
        if crosses is not None:
            crosses.set("val", "max")


def _legend(chart: Any, data: ChartData) -> None:
    drawn = len(data.series) - (1 if data.form == "scatter" else 0)
    round_form = data.form in ("pie", "doughnut")
    chart.has_legend = round_form or data.form == "segmented" or drawn >= 2
    if chart.has_legend:
        chart.legend.position = (
            XL_LEGEND_POSITION.RIGHT if round_form else XL_LEGEND_POSITION.BOTTOM
        )
        chart.legend.include_in_layout = False
        chart.legend.font.size = Pt(_TEXT_PT)


def _frame(form: str) -> tuple[Any, Any, Any, Any]:
    """Where the chart sits on a Title Only slide: the data area, a strip for a share."""
    left, top = Inches(geometry.TABLE_LEFT_IN), Inches(geometry.TABLE_TOP_IN)
    width, height = Inches(geometry.TABLE_WIDTH_IN), Inches(geometry.TABLE_AREA_HEIGHT_IN)
    if form == "segmented":
        top = Inches(
            geometry.TABLE_TOP_IN + (geometry.TABLE_AREA_HEIGHT_IN - _SEGMENTED_HEIGHT_IN) / 2
        )
        height = Inches(_SEGMENTED_HEIGHT_IN)
    return left, top, width, height


_STEPS: tuple[Callable[[Any, ChartData, str], None], ...] = (
    lambda chart, data, _language: _paint(chart, data),
    _values,
    _axes,
    lambda chart, data, _language: _legend(chart, data),
)


def add_chart(slide: Any, data: ChartData, language: str) -> Any:
    """A native chart in the slide's data area.

    Args:
        slide: A Title Only slide.
        data: What to draw (``charts.chart_data``).
        language: The reader's backend-canonical language.

    Returns:
        The chart python-pptx created.
    """
    left, top, width, height = _frame(data.form)
    frame = slide.shapes.add_chart(
        _TYPES[data.form], left, top, width, height, _data(data, language)
    )
    chart = frame.chart
    chart.has_title = False
    chart.font.size = Pt(_TEXT_PT)
    chart.font.color.rgb = _rgb(typography.INK)
    for step in _STEPS:
        step(chart, data, language)
    return chart
