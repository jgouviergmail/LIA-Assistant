"""A chart: what the writer means, the form the data can bear (ADR-274 amendment).

The writer declares an INTENT and the renderer chooses the form from the data,
because the right form depends on things the writer does not count — how many
categories, how long their labels, whether a value is negative:

- **compare**: columns while the labels are few and short, horizontal bars once
  they are many or long (a label reads beside its bar, never crushed under
  it), thin columns again past what bars can hold on a page;
- **trend**: a line over the ordered categories;
- **share**: one segmented bar of at most six parts, at a glance; a whole of
  more parts, of several series or of negative parts is COMPARED instead
  (bars on one baseline are read more exactly than slices — the reason a pie
  is drawn only when the person names it);
- **relation**: a scatter, the first value along the horizontal axis.

A form the writer names (because the person did) is honoured when the data can
bear it, and replaced by the intent's own choice otherwise. Every value comes
from ``computation.py`` — the figure a chart draws is the figure a table shows.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from src.domains.document_generation.computation import (
    Column,
    ComputedTable,
    display_cell,
    display_kind,
    numeric_value,
)
from src.domains.document_generation.fit import display_columns
from src.domains.document_generation.numbers import display
from src.domains.document_generation.schemas import ColumnSpec, TableSheet
from src.domains.document_generation.tables import ColumnKind
from src.domains.document_generation.typography import (
    CHART_BAR_MAX_CATEGORIES,
    CHART_COLUMN_MAX_CATEGORIES,
    CHART_SHARE_MAX_PARTS,
    CHART_SHORT_LABEL_COLUMNS,
    NEUTRAL_SERIES,
)

#: The forms that show the parts of ONE whole.
SHARE_FORMS = frozenset({"segmented", "pie", "doughnut"})


@dataclass(frozen=True, slots=True)
class ChartSeries:
    """One drawn measure: its name, one value per category, and how it reads."""

    name: str
    values: tuple[Decimal | None, ...]
    kind: str
    unit: str
    decimals: int

    def present(self) -> list[Decimal]:
        """The values that exist (a row without one is a gap, never a zero)."""
        return [value for value in self.values if value is not None]


@dataclass(frozen=True, slots=True)
class ChartData:
    """A chart as every renderer draws it.

    Attributes:
        form: The form chosen (``column``, ``bar``, ``line``, ``area``, ``scatter``,
            ``segmented``, ``pie`` or ``doughnut``).
        title: The writer's title, possibly empty.
        category: The header of the column naming each point.
        categories: One label per row, as the reader writes it.
        series: The drawn measures; a scatter's first is its horizontal axis.
        category_position: The category column's index in the table.
        value_positions: Each series' column index in the table.
        colors: The tone's series colours, in order: the first series takes the
            first; a part of a whole takes its ROW's.
    """

    form: str
    title: str
    category: str
    categories: tuple[str, ...]
    series: tuple[ChartSeries, ...]
    category_position: int
    value_positions: tuple[int, ...]
    colors: tuple[str, ...] = NEUTRAL_SERIES

    def color(self, index: int) -> str:
        """The colour of series (or part) ``index``; never cycled within the cap."""
        return self.colors[index % len(self.colors)]

    @property
    def axis(self) -> ChartSeries:
        """The series whose format the value axis reads (a scatter's: its first Y)."""
        return self.series[1] if self.form == "scatter" else self.series[0]


def _compared(categories: int, long_labels: bool) -> str:
    if categories <= CHART_COLUMN_MAX_CATEGORIES and not long_labels:
        return "column"
    return "bar" if categories <= CHART_BAR_MAX_CATEGORIES else "column"


def _bears(form: str, *, categories: int, series: int, negative: bool) -> bool:
    """Whether the data can be drawn in ``form`` without misleading."""
    if form in ("line", "area"):
        return categories >= 2
    if form == "bar":
        return categories <= CHART_BAR_MAX_CATEGORIES
    if form == "scatter":
        return series >= 2
    if form in SHARE_FORMS:
        return series == 1 and 2 <= categories <= CHART_SHARE_MAX_PARTS and not negative
    return form == "column"


def chart_form(
    intent: str,
    form: str,
    *,
    categories: int,
    series: int,
    negative: bool,
    long_labels: bool,
) -> str:
    """The form a chart is drawn in.

    Args:
        intent: What the chart shows (``compare``, ``trend``, ``share``, ``relation``).
        form: The form the writer named, or empty.
        categories: How many points each series has.
        series: How many measures are drawn.
        negative: Whether any drawn value is below zero.
        long_labels: Whether a category label is too long to stand under a column.

    Returns:
        The form, always one the data can bear.
    """
    compared = _compared(categories, long_labels)
    if intent == "relation":
        return "scatter" if series >= 2 else compared
    if form and _bears(form, categories=categories, series=series, negative=negative):
        return form
    if intent == "trend":
        return "line" if categories >= 2 else compared
    if intent == "share":
        if _bears("segmented", categories=categories, series=series, negative=negative):
            return "segmented"
        if series == 1 and not negative and categories <= CHART_BAR_MAX_CATEGORIES:
            # Too many parts to glance at: they are ranked on bars, one baseline.
            return "bar"
    return compared


def _series(table: ComputedTable, position: int) -> ChartSeries:
    column: Column = table.columns[position]
    values = tuple(
        None if (row, position) in table.errors else numeric_value(cells[position])
        for row, cells in enumerate(table.cells)
    )
    percent = column.type.kind is ColumnKind.PERCENT
    return ChartSeries(
        name=column.header,
        values=values,
        kind=display_kind(column) or ("percent" if percent else "quantity"),
        unit=column.unit,
        decimals=column.type.decimals,
    )


def chart_data(
    table: ComputedTable, language: str, colors: tuple[str, ...] = NEUTRAL_SERIES
) -> ChartData | None:
    """What a renderer draws for a table's chart, or ``None`` when it declares none.

    Args:
        table: A computed canonical table (its chart already settled).
        language: The reader's backend-canonical language (category labels).
        colors: The document's tone's series colours (``typography.palette_for``).

    Returns:
        The chart's form, labels and values; ``None`` as well when no drawn value
        exists at all.
    """
    spec = table.chart
    if spec is None or not table.cells:
        return None
    category = table.position(spec.category)
    positions = [table.position(name) for name in spec.values]
    labels = tuple(display_cell(table, row, category, language) for row in range(len(table.cells)))
    series = tuple(_series(table, position) for position in positions)
    if not any(one.present() for one in series):
        # Every drawn value failed (a ratio over zeros): a figure of nothing is no figure.
        return None
    long_labels = any(display_columns(label) > CHART_SHORT_LABEL_COLUMNS for label in labels)
    form = chart_form(
        spec.intent,
        spec.form,
        categories=len(labels),
        series=len(series),
        negative=any(value < 0 for one in series for value in one.present()),
        long_labels=long_labels,
    )
    if form in SHARE_FORMS and not sum(series[0].present(), Decimal(0)):
        # A whole of nothing has no parts to show: its values are compared.
        form = _compared(len(labels), long_labels)
    return ChartData(
        form=form,
        title=spec.title,
        category=spec.category,
        categories=labels,
        series=series,
        category_position=category,
        value_positions=tuple(positions),
        colors=colors,
    )


def _written(series: ChartSeries, index: int, language: str) -> str:
    value = series.values[index]
    if value is None:
        return ""
    return display(value, series.kind, series.unit, series.decimals, language)


def chart_table(data: ChartData, language: str) -> TableSheet:
    """The drawn values as a table: what a format that cannot draw shows instead.

    Args:
        data: The chart.
        language: The reader's backend-canonical language.

    Returns:
        One row per category, one column per series, values in the reader's
        conventions, each series declaring its kind so numbers align right.
    """
    return TableSheet(
        name=data.title or data.category,
        headers=[data.category, *(series.name for series in data.series)],
        rows=[
            [label, *(_written(series, index, language) for series in data.series)]
            for index, label in enumerate(data.categories)
        ],
        columns=[
            ColumnSpec(header=series.name, kind=series.kind, unit=series.unit)
            for series in data.series
        ],
    )
