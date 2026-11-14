"""A workbook's key figures: computed once, from its inputs and its sheets (ADR-388).

A summary whose rows are different quantities — a year's income, the expenses of
every month, the share they leave — is no column formula: a column formula is the
same for every row and reads its own sheet. Measured 2026-11-13, three workbooks
of ten left such a summary empty, or nested choices among its line labels past
the bound. The writer declares those quantities as FIGURES: a label, and a
formula reading the inputs and the other figures by name, and a sheet's whole
column through ``SUM({Sheet/Column})`` or ``AVERAGE({Sheet/Column})`` — never a
row, which a figure does not have. The renderer computes each once and writes
it live, its value cached (``renderers/xlsx_figures.py``).

Normalization repairs, never refuses (ADR-184): a figure with no label or no
formula, a repeated label, one past the published bound, a formula the grammar
refuses (a row read, a text column, an unknown name) goes; so do a cycle's
members, and every figure reading a figure that went — a value is never computed
from a computation that failed. An input wins over a figure of the same name,
and a figure never reads itself: in its own formula its name is the input's.

A figure with no value (a division by zero) holds an empty text in the workbook,
as a computed cell does, and is held to a column's rules: ``MIN`` and ``MAX``
skip it, arithmetic on it has no value either, and no comparison reads bare a
figure that may have none — Excel would find the text larger than any number.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from contextlib import suppress
from decimal import Decimal

from src.core.constants import DOCUMENT_GENERATION_WORKBOOK_FIGURES_MAX
from src.domains.document_generation.columns import (
    NAME_MAX_CHARS,
    UNIT_KINDS,
    UNIT_MAX_CHARS,
    column_key,
    leads_back,
)
from src.domains.document_generation.computation import (
    ComputedTable,
    aggregate,
    compute_table,
    input_values,
    numeric_value,
)
from src.domains.document_generation.formulas import (
    AggregateFunction,
    Formula,
    FormulaError,
    FormulaValueError,
    evaluate,
    may_error,
    parse_formula,
    spreading_names,
)
from src.domains.document_generation.sanitize import strip_control_characters
from src.domains.document_generation.schemas import (
    FIGURE_KINDS,
    SheetInput,
    TableSheet,
    WorkbookFigure,
)
from src.domains.document_generation.tables import ColumnKind


def _clean(text: str) -> str:
    return strip_control_characters(" ".join(text.split()))


def _cleaned(figure: WorkbookFigure) -> WorkbookFigure:
    kind = figure.kind.strip().casefold()
    kind = kind if kind in FIGURE_KINDS else ""
    return WorkbookFigure(
        label=_clean(figure.label)[:NAME_MAX_CHARS],
        formula=figure.formula.strip(),
        kind=kind,
        unit=_clean(figure.unit)[:UNIT_MAX_CHARS] if kind in UNIT_KINDS else "",
    )


def _names(labels: Sequence[str], inputs: Sequence[str], itself: str) -> list[str]:
    """What a figure's formula reads by name: the inputs, then the other figures."""
    taken = {column_key(name) for name in inputs}
    own = column_key(itself)
    others = [
        label for label in labels if column_key(label) not in taken and column_key(label) != own
    ]
    return [*inputs, *others]


def parse_figure(
    figure: WorkbookFigure,
    *,
    labels: Sequence[str],
    inputs: Sequence[str],
    sheets: Mapping[str, Sequence[str]],
) -> Formula:
    """A figure's formula, read against the workbook's names.

    Args:
        figure: The figure.
        labels: Every figure's label (the figure's own is never read).
        inputs: The workbook's input names; one wins over a figure of its name.
        sheets: Each sheet's columns a figure may read whole.

    Returns:
        The parsed formula.

    Raises:
        FormulaError: When the grammar refuses it.
    """
    return parse_formula(
        figure.formula,
        columns=(),
        inputs=_names(labels, inputs, figure.label),
        itself=figure.label,
        sheets=sheets,
    )


def _figures_named(names: Iterable[str], labels: Sequence[str], inputs: Sequence[str]) -> set[str]:
    """The figures among names a formula reads (an input of the same name is the input)."""
    keys = {column_key(label): label for label in labels}
    taken = {column_key(name) for name in inputs}
    return {
        keys[column_key(name)]
        for name in names
        if column_key(name) in keys and column_key(name) not in taken
    }


def figure_reads(formula: Formula, labels: Sequence[str], inputs: Sequence[str]) -> set[str]:
    """The figures a figure's formula reads (an input of the same name is the input)."""
    return _figures_named(formula.inputs, labels, inputs)


def _readable(inputs: Sequence[SheetInput], sheets: Sequence[TableSheet]) -> dict[str, list[str]]:
    """Each sheet's columns a figure may read whole: numbers and dates, written or computed."""
    values = input_values(inputs)
    readable: dict[str, list[str]] = {}
    for sheet in sheets:
        table = compute_table(sheet, values)
        readable[sheet.name] = [
            column.header for column in table.columns if column.type.kind is not ColumnKind.TEXT
        ]
    return readable


def _invalid(
    figures: Sequence[WorkbookFigure],
    inputs: Sequence[str],
    sheets: Mapping[str, Sequence[str]],
) -> set[str]:
    """The figures that cannot be computed: refused by the grammar, comparing bare a
    figure that may have no value, or on a cycle."""
    labels = [figure.label for figure in figures]
    parsed: dict[str, Formula] = {}
    for figure in figures:
        with suppress(FormulaError):
            parsed[figure.label] = parse_figure(figure, labels=labels, inputs=inputs, sheets=sheets)
    edges = {
        label: figure_reads(formula, labels, inputs) & parsed.keys()
        for label, formula in parsed.items()
    }
    cyclic = {label for label in edges if leads_back(label, edges)}
    blank = blank_figures(parsed, inputs)
    compared = {
        label
        for label, formula in parsed.items()
        if _figures_named(formula.compared_names, labels, inputs) & blank
    }
    return (set(labels) - parsed.keys()) | cyclic | compared


def normalize_figures(
    figures: Sequence[WorkbookFigure],
    inputs: Sequence[SheetInput],
    sheets: Sequence[TableSheet],
) -> list[WorkbookFigure]:
    """A workbook's key figures in canonical form, each one computable.

    Args:
        figures: The writer's figures.
        inputs: The canonical inputs.
        sheets: The canonical sheets.

    Returns:
        The figures kept, in the writer's order, at most the published bound.
    """
    kept: list[WorkbookFigure] = []
    seen: set[str] = set()
    for raw in figures:
        figure = _cleaned(raw)
        key = column_key(figure.label)
        if key and figure.formula and key not in seen:
            seen.add(key)
            kept.append(figure)
    kept = kept[:DOCUMENT_GENERATION_WORKBOOK_FIGURES_MAX]
    if not kept:
        # Most workbooks declare none: their sheets are not computed for nothing.
        return []
    names = [item.name for item in inputs]
    readable = _readable(inputs, sheets)
    # A figure reading one that went fails on the next pass: nothing is computed
    # from a computation that failed.
    while invalid := _invalid(kept, names, readable):
        kept = [figure for figure in kept if figure.label not in invalid]
    return kept


class _Workbook:
    """The workbook as a key figure reads it: names and whole columns, never a row."""

    def __init__(
        self,
        inputs: Mapping[str, Decimal],
        tables: Mapping[str, ComputedTable],
        figures: Mapping[str, Decimal | None],
    ) -> None:
        self._inputs = inputs
        self._tables = tables
        self._figures = figures

    def value(self, column: str) -> Decimal | None:
        raise FormulaValueError("a figure reads no row")

    def text(self, column: str) -> str:
        raise FormulaValueError("a figure reads no row")

    def previous(self, column: str) -> Decimal | None:
        raise FormulaValueError("a figure reads no row")

    def aggregate(self, function: AggregateFunction, column: str) -> Decimal:
        raise FormulaValueError("a figure reads no row")

    def running_sum(self, column: str) -> Decimal:
        raise FormulaValueError("a figure reads no row")

    def sheet_aggregate(self, function: AggregateFunction, sheet: str, column: str) -> Decimal:
        table = self._tables[sheet]
        position = table.position(column)
        numbers = [
            None if (row, position) in table.errors else numeric_value(cells[position])
            for row, cells in enumerate(table.cells)
        ]
        value = aggregate(function.lower(), numbers)
        if value is None:
            raise FormulaValueError("an average of nothing")
        return value

    def input(self, name: str) -> Decimal:
        if name in self._inputs:
            return self._inputs[name]
        value = self._figures.get(name)
        if value is None:
            raise FormulaValueError("a figure read has no value")
        return value


def parsed_figures(
    figures: Sequence[WorkbookFigure],
    inputs: Sequence[str],
    tables: Mapping[str, ComputedTable],
) -> dict[str, Formula]:
    """Each canonical figure's formula, read against the computed sheets.

    Args:
        figures: The canonical figures.
        inputs: The workbook's input names.
        tables: Each sheet's computed table, by its name.

    Returns:
        ``label -> formula``; a figure the grammar refuses (none, once
        normalized) is left out.
    """
    labels = [figure.label for figure in figures]
    sheets = {name: [column.header for column in table.columns] for name, table in tables.items()}
    parsed: dict[str, Formula] = {}
    for figure in figures:
        with suppress(FormulaError):
            parsed[figure.label] = parse_figure(figure, labels=labels, inputs=inputs, sheets=sheets)
    return parsed


def compute_figures(
    figures: Sequence[WorkbookFigure],
    inputs: Mapping[str, Decimal],
    tables: Mapping[str, ComputedTable],
) -> dict[str, Decimal | None]:
    """Each canonical figure's value, computed once, each after the figures it reads.

    Args:
        figures: The canonical figures.
        inputs: The workbook's input values, by name.
        tables: Each sheet's computed table, by its name.

    Returns:
        ``label -> value``, ``None`` where a figure has none (a division by zero,
        an average of nothing, a figure it reads with none).
    """
    parsed = parsed_figures(figures, list(inputs), tables)
    labels = list(parsed)
    reads = {
        label: figure_reads(formula, labels, list(inputs)) for label, formula in parsed.items()
    }
    values: dict[str, Decimal | None] = {}
    reader = _Workbook(inputs, tables, values)
    pending = list(parsed)
    while ready := [label for label in pending if reads[label] <= values.keys()]:
        for label in ready:
            try:
                values[label] = evaluate(parsed[label], reader)
            except FormulaValueError:
                values[label] = None
            pending.remove(label)
    return values


def blank_figures(parsed: Mapping[str, Formula], inputs: Sequence[str]) -> frozenset[str]:
    """The figures that may have no value: by their own operations, or by what they read.

    Args:
        parsed: Each figure's formula, by label.
        inputs: The workbook's input names.

    Returns:
        The labels the workbook wraps in ``IFERROR``.
    """
    labels = list(parsed)
    reads = {
        label: _figures_named(spreading_names(formula), labels, inputs)
        for label, formula in parsed.items()
    }
    blank = {label for label, formula in parsed.items() if may_error(formula)}
    while spread := {label for label in labels if label not in blank and reads[label] & blank}:
        blank |= spread
    return frozenset(blank)
