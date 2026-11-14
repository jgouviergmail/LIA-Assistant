"""A chart drawn as SVG: the figure a report prints (ADR-274 amendment).

ONE drawing serves two formats. The PDF lays the SVG out as a vector image whose
text stays text, searchable and selectable (measured 2026-11-13: MuPDF draws
Latin in Helvetica and CJK in Droid Sans Fallback, honours ``text-anchor`` and
rotations); Word receives the same drawing rasterized by MuPDF, because
python-docx writes no chart part.

The marks follow the dataviz doctrine: bars thin and capped, rounded at their
data end only, two points of paper between touching bars; 2 pt lines with round
joins; markers ringed in the paper colour; a 10 % wash under an area; solid
hairline gridlines; every word in ink, never in a series colour; a legend for
two series or more, none for one (the caption names it); values written beside
the marks only where they are few. A word never overflows: it is measured, then
thinned, turned or shortened — the whole label stays in the table and in the
figure's description.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from html import escape

from src.domains.document_generation import typography
from src.domains.document_generation.charts import ChartData, ChartSeries
from src.domains.document_generation.numbers import display
from src.domains.document_generation.renderers.chart_scale import (
    Scale,
    nice_scale,
    shortened,
    text_width,
    tick_text,
    values_fit,
    widest_value,
)
from src.domains.document_generation.schemas import CHART_FORMS

_FONT = "Helvetica, Arial, sans-serif"
_PAPER = "FFFFFF"
_TEXT_PT = 8.0
_LEGEND_PT = 8.5
_LINE_SPACING = 1.6
_GAP = 4.0
#: From a plot's bottom edge to the top of a row of words under it.
_UNDER = 6.0
_PAD = 4.0
#: A bar never fills its slot: capped, with air around it.
_BAR_MAX_PT = 16.0
_BAR_FILL = 0.72
_BAR_SPACE_PT = 2.0
_CORNER_PT = 2.0
_LINE_PT = 2.0
_MARKER_R = 3.0
_RING_PT = 1.5
_AREA_OPACITY = 0.1
_SWATCH_PT = 7.0
_LEGEND_ITEM_GAP = 12.0
#: A bar chart's labels take at most this share of the figure's width.
_BAR_LABEL_SHARE = 0.35
#: A turned category label is cut at this length.
_TURNED_LABEL_MAX_PT = 90.0
#: Turned labels stand this many font sizes apart, or every k-th is shown.
_TURNED_STEP = 2.4
#: Markers drawn on a line up to this many points.
_MARKERS_MAX = 24
_SEGMENT_PT = 22.0
#: Each block of a segmented bar is its own rounded block.
_SEGMENT_CORNER_PT = 3.0
_PIE_HEIGHT_PT = 200.0
#: A tiny part's share is written with up to this many decimals rather than « 0 % ».
_SHARE_MAX_DECIMALS = 2
_DOUGHNUT_HOLE = 0.55
_COS45 = math.cos(math.pi / 4)


@dataclass(frozen=True, slots=True)
class Figure:
    """A drawn chart: the SVG, its size in points, and its words for a screen reader."""

    svg: str
    width_pt: float
    height_pt: float
    description: str


@dataclass(slots=True)
class _Plot:
    """The rectangle the marks are drawn in."""

    left: float
    top: float
    right: float
    bottom: float

    @property
    def width(self) -> float:
        return self.right - self.left


def _n(value: float) -> str:
    """A coordinate: two decimals at most, never « -0 »."""
    return f"{(round(value, 2) or 0.0):.2f}".rstrip("0").rstrip(".")


class _Svg:
    """The figure's elements, in drawing order."""

    def __init__(self, width: float, height: float) -> None:
        self.width = width
        self.height = height
        self.parts: list[str] = []

    def rect(self, x: float, y: float, w: float, h: float, color: str, radius: float = 0) -> None:
        corner = f' rx="{_n(radius)}"' if radius else ""
        self.parts.append(
            f'<rect x="{_n(x)}" y="{_n(y)}" width="{_n(w)}" height="{_n(h)}"{corner} '
            f'fill="#{color}"/>'
        )

    def path(self, d: str, color: str, *, opacity: float = 1.0, stroke: str = "") -> None:
        alpha = f' fill-opacity="{opacity}"' if opacity < 1 else ""
        outline = f' stroke="#{stroke}" stroke-width="{_RING_PT}"' if stroke else ""
        self.parts.append(f'<path d="{d}" fill="#{color}"{alpha}{outline}/>')

    def line(self, x1: float, y1: float, x2: float, y2: float, color: str, width: float) -> None:
        self.parts.append(
            f'<line x1="{_n(x1)}" y1="{_n(y1)}" x2="{_n(x2)}" y2="{_n(y2)}" '
            f'stroke="#{color}" stroke-width="{_n(width)}"/>'
        )

    def polyline(self, points: Sequence[tuple[float, float]], color: str) -> None:
        coordinates = " ".join(f"{_n(x)},{_n(y)}" for x, y in points)
        self.parts.append(
            f'<polyline points="{coordinates}" fill="none" stroke="#{color}" '
            f'stroke-width="{_LINE_PT}" stroke-linejoin="round" stroke-linecap="round"/>'
        )

    def marker(self, x: float, y: float, color: str) -> None:
        """A dot ringed in the paper colour, legible where it crosses a line."""
        self.parts.append(
            f'<circle cx="{_n(x)}" cy="{_n(y)}" r="{_MARKER_R}" fill="#{color}" '
            f'stroke="#{_PAPER}" stroke-width="{_RING_PT}"/>'
        )

    def text(
        self,
        x: float,
        y: float,
        content: str,
        *,
        size: float = _TEXT_PT,
        anchor: str = "start",
        turned: bool = False,
        color: str = typography.INK,
    ) -> None:
        if not content:
            return
        rotation = f' transform="rotate(-45 {_n(x)} {_n(y)})"' if turned else ""
        self.parts.append(
            f'<text x="{_n(x)}" y="{_n(y)}" font-family="{_FONT}" font-size="{_n(size)}" '
            f'fill="#{color}" text-anchor="{anchor}"{rotation}>{escape(content)}</text>'
        )

    def render(self, title: str, description: str) -> str:
        heading = f"<title>{escape(title)}</title>" if title else ""
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{_n(self.width)}" '
            f'height="{_n(self.height)}" viewBox="0 0 {_n(self.width)} {_n(self.height)}">'
            f"{heading}<desc>{escape(description)}</desc>"
            f'<rect x="0" y="0" width="{_n(self.width)}" height="{_n(self.height)}" '
            f'fill="#{_PAPER}"/>' + "".join(self.parts) + "</svg>"
        )


# ---------------------------------------------------------------------------
# Words around the marks
# ---------------------------------------------------------------------------
def _legend(
    svg: _Svg, entries: Sequence[tuple[str, str]], top: float, *, stacked: bool = False
) -> float:
    """Swatch-and-name pairs from ``top``, in rows (or one per row); returns their height."""
    if not entries:
        return 0.0
    row_height = _LEGEND_PT * _LINE_SPACING
    x, baseline = _PAD, top + _LEGEND_PT
    for index, (color, name) in enumerate(entries):
        label = shortened(name, _LEGEND_PT, svg.width - _PAD * 2 - _SWATCH_PT - _GAP)
        item = _SWATCH_PT + _GAP + text_width(label, _LEGEND_PT)
        if index and (stacked or x + item > svg.width - _PAD):
            x, baseline = _PAD, baseline + row_height
        svg.rect(x, baseline - _SWATCH_PT + 0.5, _SWATCH_PT, _SWATCH_PT, color, radius=1.5)
        svg.text(x + _SWATCH_PT + _GAP, baseline, label, size=_LEGEND_PT)
        x += item + _LEGEND_ITEM_GAP
    return baseline - top + row_height - _LEGEND_PT + _GAP


def _series_legend(svg: _Svg, series: Sequence[ChartSeries], top: float, data: ChartData) -> float:
    """A legend only where colour must say WHICH series: two or more."""
    if len(series) < 2:
        return 0.0
    return _legend(svg, [(data.color(k), one.name) for k, one in enumerate(series)], top)


def _value_text(series: ChartSeries, value: Decimal, language: str) -> str:
    return display(value, series.kind, series.unit, series.decimals, language)


def _ticks_width(scale: Scale, series: ChartSeries, language: str) -> float:
    return max(
        text_width(tick_text(tick, scale, series.kind, series.unit, language), _TEXT_PT)
        for tick in scale.ticks
    )


def _value_grid(svg: _Svg, scale: Scale, plot: _Plot, series: ChartSeries, language: str) -> None:
    """Hairline gridlines at the round ticks, the zero line a step darker, ticks in muted ink."""
    for tick in scale.ticks:
        y = scale.at(tick, plot.bottom, plot.top)
        color, width = (typography.RULE, 0.8) if tick == 0 else (typography.RULE_LIGHT, 0.5)
        svg.line(plot.left, y, plot.right, y, color, width)
        svg.text(
            plot.left - _GAP,
            y + _TEXT_PT * 0.35,
            tick_text(tick, scale, series.kind, series.unit, language),
            anchor="end",
            color=typography.MUTED,
        )


@dataclass(frozen=True, slots=True)
class _CategoryLabels:
    """Category labels under a plot: flat, or turned and thinned when crowded."""

    texts: tuple[str, ...]
    turned: bool
    height: float


def _category_labels(labels: Sequence[str], band: float) -> _CategoryLabels:
    if max((text_width(label, _TEXT_PT) for label in labels), default=0.0) <= band - 2:
        return _CategoryLabels(tuple(labels), False, _UNDER + _TEXT_PT + _GAP)
    every = max(1, math.ceil(_TEXT_PT * _TURNED_STEP / band))
    texts = tuple(
        shortened(label, _TEXT_PT, _TURNED_LABEL_MAX_PT) if index % every == 0 else ""
        for index, label in enumerate(labels)
    )
    longest = max(text_width(text, _TEXT_PT) for text in texts)
    return _CategoryLabels(texts, True, longest * _COS45 + _UNDER + _TEXT_PT + _GAP)


def _draw_category_labels(
    svg: _Svg, labels: _CategoryLabels, plot: _Plot, band: float, below: float
) -> None:
    """Each category under its column; ``below`` is the band kept for values under zero."""
    top = plot.bottom + below + _UNDER
    for index, text in enumerate(labels.texts):
        x = plot.left + band * (index + 0.5)
        if labels.turned:
            svg.text(x, top + _TEXT_PT * 0.7, text, anchor="end", turned=True)
        else:
            svg.text(x, top + _TEXT_PT, text, anchor="middle")


# ---------------------------------------------------------------------------
# Marks
# ---------------------------------------------------------------------------
def _upright_bar(x: float, base: float, width: float, tip: float) -> str:
    """A vertical bar's path: square on its baseline, rounded at its data end."""
    radius = min(_CORNER_PT, width / 2, abs(base - tip) / 2)
    toward = -1 if tip < base else 1
    edge = tip - toward * radius
    return (
        f"M{_n(x)} {_n(base)} L{_n(x)} {_n(edge)} Q{_n(x)} {_n(tip)} {_n(x + radius)} {_n(tip)} "
        f"L{_n(x + width - radius)} {_n(tip)} Q{_n(x + width)} {_n(tip)} {_n(x + width)} "
        f"{_n(edge)} L{_n(x + width)} {_n(base)} Z"
    )


def _lying_bar(y: float, base: float, height: float, tip: float) -> str:
    """A horizontal bar's path: square on its baseline, rounded at its data end."""
    radius = min(_CORNER_PT, height / 2, abs(tip - base) / 2)
    toward = 1 if tip > base else -1
    edge = tip - toward * radius
    return (
        f"M{_n(base)} {_n(y)} L{_n(edge)} {_n(y)} Q{_n(tip)} {_n(y)} {_n(tip)} {_n(y + radius)} "
        f"L{_n(tip)} {_n(y + height - radius)} Q{_n(tip)} {_n(y + height)} {_n(edge)} "
        f"{_n(y + height)} L{_n(base)} {_n(y + height)} Z"
    )


def _thickness(slot: float, count: int) -> tuple[float, float]:
    """A bar's thickness and the paper between two touching bars of one slot."""
    space = _BAR_SPACE_PT if count > 1 else 0.0
    thickness = min(slot * _BAR_FILL / count - space, _BAR_MAX_PT)
    if thickness < 1.5:
        return slot * _BAR_FILL / count, 0.0
    return thickness, space


def _zero(scale: Scale) -> Decimal:
    return min(max(Decimal(0), scale.low), scale.high)


def _labelled(data: ChartData) -> bool:
    """Values are written beside single-series marks only, and only a few of them."""
    return len(data.series) == 1 and len(data.categories) <= typography.CHART_VALUE_LABELS_MAX


def _fit_in_band(data: ChartData, band: float, language: str) -> bool:
    """Whether every value written above a column fits the column's band."""
    return values_fit(data.series[0], _TEXT_PT, band - 2, language)


def _draw_columns(
    svg: _Svg, data: ChartData, plot: _Plot, scale: Scale, language: str, *, written: bool
) -> None:
    band = plot.width / len(data.categories)
    thickness, space = _thickness(band, len(data.series))
    group = thickness * len(data.series) + space * (len(data.series) - 1)
    base = scale.at(_zero(scale), plot.bottom, plot.top)
    for index in range(len(data.categories)):
        start = plot.left + band * (index + 0.5) - group / 2
        for k, series in enumerate(data.series):
            value = series.values[index]
            if value is None:
                continue
            x = start + k * (thickness + space)
            tip = scale.at(value, plot.bottom, plot.top)
            if tip != base:
                svg.path(_upright_bar(x, base, thickness, tip), data.color(k))
            if written:
                y = tip - _GAP if value >= 0 else tip + _GAP + _TEXT_PT
                svg.text(
                    x + thickness / 2, y, _value_text(series, value, language), anchor="middle"
                )


def _runs(values: Sequence[Decimal | None]) -> list[list[tuple[int, Decimal]]]:
    """The unbroken stretches of a series: a missing value is a gap, never a zero."""
    runs: list[list[tuple[int, Decimal]]] = [[]]
    for index, value in enumerate(values):
        if value is None:
            if runs[-1]:
                runs.append([])
        else:
            runs[-1].append((index, value))
    return [run for run in runs if run]


def _draw_lines(
    svg: _Svg, data: ChartData, plot: _Plot, scale: Scale, language: str, *, area: bool
) -> None:
    band = plot.width / len(data.categories)
    base = scale.at(_zero(scale), plot.bottom, plot.top)
    markers = len(data.categories) <= _MARKERS_MAX
    for k, series in enumerate(data.series):
        for run in _runs(series.values):
            points = [
                (plot.left + band * (index + 0.5), scale.at(value, plot.bottom, plot.top))
                for index, value in run
            ]
            if area and len(points) > 1:
                outline = " ".join(f"L{_n(x)} {_n(y)}" for x, y in points)
                d = f"M{_n(points[0][0])} {_n(base)} {outline} L{_n(points[-1][0])} {_n(base)} Z"
                svg.path(d, data.color(k), opacity=_AREA_OPACITY)
            if len(points) > 1:
                svg.polyline(points, data.color(k))
            if markers or len(points) == 1:
                for x, y in points:
                    svg.marker(x, y, data.color(k))
    if len(data.series) == 1 and (present := _runs(data.series[0].values)):
        index, value = present[-1][-1]
        x = plot.left + band * (index + 0.5) + _MARKER_R + _GAP
        y = scale.at(value, plot.bottom, plot.top) + _TEXT_PT * 0.35
        svg.text(x, y, _value_text(data.series[0], value, language))


# ---------------------------------------------------------------------------
# Forms
# ---------------------------------------------------------------------------
def _upright(data: ChartData, width: float, language: str) -> _Svg:
    """Columns, lines and areas: categories along the bottom, values up the left."""
    height = typography.CHART_FIGURE_HEIGHT_PT
    svg = _Svg(width, height)
    top = _PAD + _series_legend(svg, data.series, _PAD, data)
    values = [value for one in data.series for value in one.present()]
    scale = nice_scale(values, from_zero=data.form in ("column", "area"))
    left = _PAD + _ticks_width(scale, data.axis, language) + _GAP
    right = width - _PAD
    if data.form in ("line", "area") and len(data.series) == 1:
        last = data.series[0].present()[-1]
        right -= text_width(_value_text(data.series[0], last, language), _TEXT_PT) + _GAP * 2
    band = (right - left) / len(data.categories)
    labels = _category_labels(data.categories, band)
    if labels.turned:
        # The first turned label reaches left of its column: the plot moves right
        # rather than let it leave the figure.
        reach = _PAD + text_width(labels.texts[0], _TEXT_PT) * _COS45 - band / 2
        if reach > left:
            left = reach
            band = (right - left) / len(data.categories)
            labels = _category_labels(data.categories, band)
    written = _labelled(data) and data.form == "column" and _fit_in_band(data, band, language)
    headroom = _TEXT_PT + _GAP if written else _GAP
    # A value under a negative column is written below its tip: never on a label.
    below = _TEXT_PT + _GAP if written and min(values) < 0 else 0.0
    plot = _Plot(left, top + headroom, right, height - labels.height - below)
    _value_grid(svg, scale, plot, data.axis, language)
    if data.form == "column":
        _draw_columns(svg, data, plot, scale, language, written=written)
    else:
        _draw_lines(svg, data, plot, scale, language, area=data.form == "area")
    _draw_category_labels(svg, labels, plot, band, below)
    return svg


def _bar_marks(
    svg: _Svg,
    data: ChartData,
    labels: Sequence[str],
    plot: _Plot,
    scale: Scale,
    language: str,
    *,
    labels_end: float,
) -> None:
    """Each category's label beside its bars, each value at its bar's tip."""
    step = typography.CHART_BAR_STEP_PT
    thickness, space = _thickness(step, len(data.series))
    group = thickness * len(data.series) + space * (len(data.series) - 1)
    base = scale.at(_zero(scale), plot.left, plot.right)
    for index, label in enumerate(labels):
        middle = plot.top + step * (index + 0.5)
        svg.text(labels_end, middle + _TEXT_PT * 0.35, label, anchor="end")
        for k, series in enumerate(data.series):
            value = series.values[index]
            if value is None:
                continue
            y = middle - group / 2 + k * (thickness + space)
            tip = scale.at(value, plot.left, plot.right)
            if tip != base:
                svg.path(_lying_bar(y, base, thickness, tip), data.color(k))
            if len(data.series) == 1:
                x, anchor = (tip + _GAP, "start") if value >= 0 else (tip - _GAP, "end")
                text = _value_text(series, value, language)
                svg.text(x, y + thickness / 2 + _TEXT_PT * 0.35, text, anchor=anchor)


def _value_ticks_below(
    svg: _Svg, scale: Scale, plot: _Plot, series: ChartSeries, language: str
) -> None:
    """A horizontal value axis: vertical hairlines, round ticks under the plot."""
    for tick in scale.ticks:
        x = scale.at(tick, plot.left, plot.right)
        color, width = (typography.RULE, 0.8) if tick == 0 else (typography.RULE_LIGHT, 0.5)
        svg.line(x, plot.top, x, plot.bottom, color, width)
        text = tick_text(tick, scale, series.kind, series.unit, language)
        svg.text(x, plot.bottom + _UNDER + _TEXT_PT, text, anchor="middle", color=typography.MUTED)


def _widest_value(series: ChartSeries, values: Sequence[Decimal], language: str) -> float:
    return widest_value(series, list(values), _TEXT_PT, language)


def _bars(data: ChartData, width: float, language: str) -> _Svg:
    """Horizontal bars: a long label reads beside its bar; the figure grows per bar."""
    step = typography.CHART_BAR_STEP_PT
    count = len(data.categories)
    legend = _series_legend(_Svg(width, 0), data.series, _PAD, data)
    svg = _Svg(width, _PAD + legend + count * step + _UNDER + _TEXT_PT + _GAP * 2)
    top = _PAD + _series_legend(svg, data.series, _PAD, data)
    labels = [shortened(label, _TEXT_PT, width * _BAR_LABEL_SHARE) for label in data.categories]
    labels_end = _PAD + max(text_width(label, _TEXT_PT) for label in labels)
    left = labels_end + _GAP
    values = [value for one in data.series for value in one.present()]
    scale = nice_scale(values, from_zero=True)
    right = width - _PAD
    if len(data.series) == 1:
        # A value is written at its bar's tip: the plot keeps room on that side —
        # left of the value area too, so a negative value never lands on a name.
        right -= _widest_value(data.series[0], [v for v in values if v >= 0], language) + _GAP
        reserve = _widest_value(data.series[0], [v for v in values if v < 0], language)
        left += reserve + _GAP if reserve else 0.0
    plot = _Plot(left, top, right, top + count * step)
    _value_ticks_below(svg, scale, plot, data.axis, language)
    _bar_marks(svg, data, labels, plot, scale, language, labels_end=labels_end)
    return svg


def _axis_title_left(svg: _Svg, text: str, plot: _Plot) -> None:
    """A vertical axis's name, turned to read upwards beside its ticks."""
    x, middle = _PAD + _TEXT_PT, (plot.top + plot.bottom) / 2
    title = escape(shortened(text, _TEXT_PT, plot.bottom - plot.top))
    svg.parts.append(
        f'<text x="{_n(x)}" y="{_n(middle)}" font-family="{_FONT}" font-size="{_n(_TEXT_PT)}" '
        f'fill="#{typography.INK}" text-anchor="middle" '
        f'transform="rotate(-90 {_n(x)} {_n(middle)})">{title}</text>'
    )


def _pairs(across: ChartSeries, ups: Sequence[ChartSeries]) -> list[list[tuple[Decimal, Decimal]]]:
    """Each Y series' points: a row missing either value is no point."""
    return [
        [
            (x, y)
            for x, y in zip(across.values, one.values, strict=True)
            if x is not None and y is not None
        ]
        for one in ups
    ]


def _across_axis(svg: _Svg, scale: Scale, plot: _Plot, across: ChartSeries, language: str) -> None:
    """The horizontal value axis of a scatter: its ticks, and its name below them."""
    for tick in scale.ticks:
        x = scale.at(tick, plot.left, plot.right)
        text = tick_text(tick, scale, across.kind, across.unit, language)
        svg.text(x, plot.bottom + _UNDER + _TEXT_PT, text, anchor="middle", color=typography.MUTED)
    middle = plot.left + plot.width / 2
    svg.text(
        middle, svg.height - _PAD, shortened(across.name, _TEXT_PT, plot.width), anchor="middle"
    )


def _scatter(data: ChartData, width: float, language: str) -> _Svg:
    """A relation: the first measure along the bottom, the others up the left."""
    height = typography.CHART_FIGURE_HEIGHT_PT
    svg = _Svg(width, height)
    across, ups = data.series[0], data.series[1:]
    top = _PAD + _series_legend(svg, ups, _PAD, data)
    pairs = _pairs(across, ups)
    xs = [x for points in pairs for x, _y in points] or [Decimal(0)]
    ys = [y for points in pairs for _x, y in points] or [Decimal(0)]
    x_scale, y_scale = nice_scale(xs, from_zero=False), nice_scale(ys, from_zero=False)
    title_band = _TEXT_PT + _GAP if len(ups) == 1 else 0.0
    left = _PAD + title_band + _ticks_width(y_scale, ups[0], language) + _GAP
    last_tick = tick_text(x_scale.ticks[-1], x_scale, across.kind, across.unit, language)
    right = width - _PAD - text_width(last_tick, _TEXT_PT) / 2
    plot = _Plot(left, top + _GAP, right, height - (_UNDER + _TEXT_PT * 2 + _GAP * 3))
    _value_grid(svg, y_scale, plot, ups[0], language)
    _across_axis(svg, x_scale, plot, across, language)
    if len(ups) == 1:
        _axis_title_left(svg, ups[0].name, plot)
    for k, points in enumerate(pairs):
        for x_value, y_value in points:
            svg.marker(
                x_scale.at(x_value, plot.left, plot.right),
                y_scale.at(y_value, plot.bottom, plot.top),
                data.color(k),
            )
    return svg


def _shares(data: ChartData, language: str) -> list[tuple[str, Decimal, str]]:
    """Each part that has a value: its colour, its value, and « name · 46 % ».

    A part's colour follows its ROW, never its rank: a part with no value
    leaves its colour unused rather than repainting its neighbours.
    """
    series = data.series[0]
    total = sum(series.present(), Decimal(0))
    parts: list[tuple[str, Decimal, str]] = []
    for index, (label, value) in enumerate(zip(data.categories, series.values, strict=True)):
        if value is None or value <= 0:
            continue
        share = value / total
        written = display(share, "percent", "", _share_decimals(share), language)
        parts.append((data.color(index), value, f"{label} · {written}"))
    return parts


def _share_decimals(share: Decimal) -> int:
    """Whole percents, unless that would write « 0 % » for a part that exists."""
    decimals = 0
    while (
        decimals < _SHARE_MAX_DECIMALS and (share * 100).quantize(Decimal(1).scaleb(-decimals)) == 0
    ):
        decimals += 1
    return decimals


def _segmented(data: ChartData, width: float, language: str) -> _Svg:
    """One whole, one bar: each part its own block, its name and share in the legend."""
    parts = _shares(data, language)
    total = sum((value for _color, value, _text in parts), Decimal(0))
    entries = [(color, text) for color, _value, text in parts]
    legend_height = _legend(_Svg(width, 0), entries, 0)
    svg = _Svg(width, _PAD * 3 + _SEGMENT_PT + _GAP * 2 + legend_height)
    span = width - _PAD * 2 - _BAR_SPACE_PT * (len(parts) - 1)
    x = _PAD
    for color, value, _text in parts:
        block = span * float(value / total)
        radius = min(_SEGMENT_CORNER_PT, block / 2)
        svg.rect(x, _PAD * 2, block, _SEGMENT_PT, color, radius=radius)
        x += block + _BAR_SPACE_PT
    _legend(svg, entries, _PAD * 2 + _SEGMENT_PT + _GAP * 2)
    return svg


def _point(cx: float, cy: float, radius: float, angle: float) -> str:
    return f"{_n(cx + radius * math.sin(angle))} {_n(cy - radius * math.cos(angle))}"


def _slice(cx: float, cy: float, outer: float, inner: float, start: float, end: float) -> str:
    """One slice between two angles (radians, clockwise from twelve o'clock)."""
    large = 1 if end - start > math.pi else 0
    arc = f"A{_n(outer)} {_n(outer)} 0 {large} 1 {_point(cx, cy, outer, end)}"
    if inner <= 0:
        return f"M{_n(cx)} {_n(cy)} L{_point(cx, cy, outer, start)} {arc} Z"
    back = f"A{_n(inner)} {_n(inner)} 0 {large} 0 {_point(cx, cy, inner, start)}"
    return f"M{_point(cx, cy, outer, start)} {arc} L{_point(cx, cy, inner, end)} {back} Z"


def _round(data: ChartData, width: float, language: str) -> _Svg:
    """A pie or a doughnut — drawn only because the person named one."""
    svg = _Svg(width, _PIE_HEIGHT_PT)
    parts = _shares(data, language)
    total = sum((value for _color, value, _text in parts), Decimal(0))
    outer = (_PIE_HEIGHT_PT - _PAD * 4) / 2
    inner = outer * _DOUGHNUT_HOLE if data.form == "doughnut" else 0.0
    cx, cy = _PAD * 2 + outer, _PIE_HEIGHT_PT / 2
    angle = 0.0
    for color, value, _text in parts:
        sweep = 2 * math.pi * float(value / total)
        # A whole circle is no arc: the last slice stops a hair short of closing.
        end = angle + min(sweep, 2 * math.pi - 1e-4)
        svg.path(_slice(cx, cy, outer, inner, angle, end), color, stroke=_PAPER)
        angle += sweep
    offset_x = cx + outer + _PAD * 4
    legend = _Svg(width - offset_x - _PAD, 0)
    height = _legend(legend, [(color, text) for color, _value, text in parts], 0, stacked=True)
    offset_y = max(_PAD, cy - height / 2)
    svg.parts.append(
        f'<g transform="translate({_n(offset_x)} {_n(offset_y)})">' + "".join(legend.parts) + "</g>"
    )
    return svg


_FORMS: dict[str, Callable[[ChartData, float, str], _Svg]] = {
    "column": _upright,
    "line": _upright,
    "area": _upright,
    "bar": _bars,
    "scatter": _scatter,
    "segmented": _segmented,
    "pie": _round,
    "doughnut": _round,
}

# Boot-time completeness (ADR-085): every form a chart can take is drawn.
assert set(_FORMS) == set(CHART_FORMS), "_FORMS must cover every chart form"


def describe(data: ChartData, language: str) -> str:
    """The figure in words, for a screen reader: every value, series by series."""
    named = len(data.series) == 1 and data.title == data.series[0].name
    parts = [data.title] if data.title and not named else []
    for series in data.series:
        pairs = "; ".join(
            f"{label}: {_value_text(series, value, language) if value is not None else '—'}"
            for label, value in zip(data.categories, series.values, strict=True)
        )
        parts.append(f"{series.name} — {pairs}")
    return ". ".join(parts)


def draw_chart(data: ChartData, width_pt: float, language: str) -> Figure:
    """The chart as an SVG figure at a report's text width.

    Args:
        data: What to draw (``charts.chart_data``).
        width_pt: The width it is laid out at.
        language: The reader's backend-canonical language.

    Returns:
        The figure; its height follows from its form.
    """
    svg = _FORMS[data.form](data, width_pt, language)
    description = describe(data, language)
    return Figure(svg.render(data.title, description), svg.width, svg.height, description)
