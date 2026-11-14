"""A canonical table, computed (ADR-274 amendment).

One computation serves every format, so a figure never differs between them:

- the workbook writes each computed cell as a formula AND caches the value
  computed here, for the readers that never recalculate;
- Word, PDF, slides and Markdown receive the values themselves, written in the
  reader's conventions (``materialize_table``), with the totals row and the
  grouped summary as ordinary rows and tables;
- CSV receives the values in machine form (``machine_text``).

The semantics are Excel's, because the workbook recalculates: an empty cell is 0
in arithmetic and skipped by an aggregate or a running sum; a row whose formula
has no value (a division by zero, no row above) is blank everywhere — an empty
TEXT in the workbook, so a column reading it may have none either
(``Column.may_blank``); a text is compared as the workbook holds it; a COUNT
total counts every row of a computed column (Excel's COUNTA counts a formula
that answers "").
Dates compute as Excel serials (days since 1899-12-30), so « end − start » is a
number of days and « start + 7 » a date.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from src.core.i18n_documents import document_label
from src.domains.document_generation.columns import (
    UNIT_KINDS,
    amount_decimals,
    column_key,
    computed_type,
    declared_kind,
    effective_type,
)
from src.domains.document_generation.formulas import (
    AggregateFunction,
    Formula,
    FormulaError,
    FormulaValueError,
    blank_columns,
    evaluate,
    parse_formula,
)
from src.domains.document_generation.numbers import NUMERIC_KINDS, display, rounded
from src.domains.document_generation.sanitize import neutralize_formula
from src.domains.document_generation.schemas import ChartSpec, ColumnSpec, SheetInput, TableSheet
from src.domains.document_generation.tables import ColumnKind, ColumnType, infer_column_types

CellValue = Decimal | date | datetime | str | None

#: Day zero of Excel's serial dates (1900 system, as every current workbook).
EXCEL_EPOCH = datetime(1899, 12, 30)
_SECONDS_PER_DAY = Decimal(86400)
#: Digits a computed value keeps in CSV: enough for any figure, never 28 of noise.
_CSV_DECIMALS = 6
_DATE_KINDS = (ColumnKind.DATE, ColumnKind.DATETIME)
#: Decimals a computed column shows at most: cents, and a tenth of a percent.
_COMPUTED_MAX_DECIMALS = {ColumnKind.DECIMAL: 2, ColumnKind.PERCENT: 1}


@dataclass(frozen=True, slots=True)
class Column:
    """One column, as the renderers read it once its declaration has settled."""

    header: str
    kind: str
    unit: str
    type: ColumnType
    formula: Formula | None
    total: str
    better: str
    choices: tuple[str, ...]
    #: Whether some row may have no value (``formulas.blank_columns``): the
    #: workbook wraps its formula in ``IFERROR`` and charts it through a gap-safe copy.
    may_blank: bool = False

    @property
    def computed(self) -> bool:
        """Whether every cell of the column is computed by the renderer."""
        return self.formula is not None


@dataclass(frozen=True, slots=True)
class Summary:
    """A table grouped by one of its columns, one value per group and measure."""

    title: str
    by: str
    function: str
    measures: tuple[str, ...]
    groups: tuple[tuple[str, tuple[Decimal | None, ...]], ...]


@dataclass(frozen=True, slots=True)
class ComputedTable:
    """A table and every value the renderers show."""

    name: str
    columns: tuple[Column, ...]
    raw: tuple[tuple[str, ...], ...]
    cells: tuple[tuple[CellValue, ...], ...]
    errors: frozenset[tuple[int, int]]
    totals: tuple[Decimal | None, ...]
    summary: Summary | None
    chart: ChartSpec | None = None

    @property
    def has_totals(self) -> bool:
        """Whether a totals row follows the data."""
        return bool(self.cells) and any(column.total for column in self.columns)

    def position(self, header: str) -> int:
        """The index of a column, by its canonical header."""
        return next(index for index, column in enumerate(self.columns) if column.header == header)


# ---------------------------------------------------------------------------
# Typed values
# ---------------------------------------------------------------------------
def serial(value: date | datetime) -> Decimal:
    """A date as Excel counts it: days (and fractions of a day) since its epoch."""
    moment = value if isinstance(value, datetime) else datetime(value.year, value.month, value.day)
    delta = moment.replace(tzinfo=None) - EXCEL_EPOCH
    return Decimal(delta.days) + Decimal(delta.seconds) / _SECONDS_PER_DAY


def from_serial(value: Decimal, kind: ColumnKind) -> date | datetime | None:
    """The date (or moment) of an Excel serial; ``None`` for one no calendar holds.

    A start date plus a duration written in seconds lands in year 12 900: the
    workbook shows « ##### » there, and every other reader an empty cell — never
    an exception after the document was paid for.
    """
    try:
        moment = EXCEL_EPOCH + timedelta(days=float(value))
    except OverflowError:
        return None
    return moment if kind is ColumnKind.DATETIME else moment.date()


def typed_cell(cell: str, column: ColumnType) -> CellValue:
    """A written cell under its column's type; a cell that does not parse stays text."""
    value = cell.strip()
    if not value:
        return None
    try:
        if column.kind in (ColumnKind.INT, ColumnKind.DECIMAL):
            return Decimal(value)
        if column.kind is ColumnKind.PERCENT:
            return Decimal(value.rstrip("%").strip()) / 100
        if column.kind is ColumnKind.DATE:
            return date.fromisoformat(value)
        if column.kind is ColumnKind.DATETIME:
            return datetime.fromisoformat(value.replace(" ", "T"))
    except InvalidOperation, ValueError:
        return value
    return value


def numeric_value(value: CellValue) -> Decimal | None:
    """What a formula reads in a cell: a number, a date as its serial, else nothing."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, date):
        return serial(value)
    return None


def input_value(item: SheetInput) -> Decimal | None:
    """An input as a formula reads it (a percentage as a fraction), or ``None``."""
    inferred = infer_column_types(["value"], [[item.value]])[0]
    return numeric_value(typed_cell(item.value, inferred))


def input_values(inputs: Sequence[SheetInput]) -> dict[str, Decimal]:
    """Each input's value as a formula reads it.

    Args:
        inputs: The workbook's canonical inputs.

    Returns:
        ``name -> value``; an input whose value does not parse is absent.
    """
    return {item.name: value for item in inputs if (value := input_value(item)) is not None}


# ---------------------------------------------------------------------------
# The computation
# ---------------------------------------------------------------------------
class _State:
    """The cells of one table while its computed columns are filled in."""

    def __init__(self, columns: list[Column], cells: list[list[CellValue]]) -> None:
        self.columns = columns
        self.cells = cells
        self.errors: set[tuple[int, int]] = set()
        self.position = {column.header: index for index, column in enumerate(columns)}

    def read(self, row: int, header: str) -> Decimal | None:
        position = self.position[header]
        if (row, position) in self.errors:
            raise FormulaValueError("the cell read has no value")
        return numeric_value(self.cells[row][position])

    def text(self, row: int, header: str) -> str:
        """A cell as the workbook writes its text (ADR-226's quote included)."""
        value = self.cells[row][self.position[header]]
        if value is None:
            return ""
        if not isinstance(value, str):
            # Normalization compares texts only in text columns.
            raise FormulaValueError("a number compared to a text")
        return neutralize_formula(value)

    def numbers(self, header: str) -> list[Decimal | None]:
        position = self.position[header]
        return [
            None if (row, position) in self.errors else numeric_value(cells[position])
            for row, cells in enumerate(self.cells)
        ]


class _Row:
    """One row as a formula reads it; whole-column aggregates are shared by every row."""

    def __init__(
        self,
        state: _State,
        row: int,
        inputs: Mapping[str, Decimal],
        aggregates: _Aggregates,
    ) -> None:
        self._state = state
        self._row = row
        self._inputs = inputs
        self._aggregates = aggregates

    def value(self, column: str) -> Decimal | None:
        return self._state.read(self._row, column)

    def text(self, column: str) -> str:
        return self._state.text(self._row, column)

    def previous(self, column: str) -> Decimal | None:
        if self._row == 0:
            raise FormulaValueError("no row above the first")
        return self._state.read(self._row - 1, column)

    def aggregate(self, function: AggregateFunction, column: str) -> Decimal:
        return self._aggregates.get(function, column)

    def running_sum(self, column: str) -> Decimal:
        return self._aggregates.running(column)[self._row]

    def sheet_aggregate(self, function: AggregateFunction, sheet: str, column: str) -> Decimal:
        # A row formula never names another sheet: the grammar refuses it.
        raise FormulaValueError("a row formula reads no other sheet")

    def input(self, name: str) -> Decimal:
        return self._inputs[name]


class _Aggregates:
    """A column's SUM, AVERAGE or running sums, computed once for every row that reads it.

    Computed per row, ``{Sales} / SUM({Sales})`` cost N² additions: 4 of the 5
    seconds of a 5 000-row sheet (measured 2026-11-13). A running sum is one
    pass too: each row reads its own prefix.
    """

    def __init__(self, state: _State) -> None:
        self._state = state
        self._values: dict[tuple[str, str], Decimal | None] = {}
        self._running: dict[str, list[Decimal]] = {}

    def get(self, function: AggregateFunction, column: str) -> Decimal:
        key = (function, column)
        if key not in self._values:
            self._values[key] = aggregate(function.lower(), self._state.numbers(column))
        value = self._values[key]
        if value is None:
            raise FormulaValueError("an average of nothing")
        return value

    def running(self, column: str) -> list[Decimal]:
        """Each row's sum of the column down to it, empty and valueless cells skipped."""
        if column not in self._running:
            total = Decimal(0)
            sums: list[Decimal] = []
            for value in self._state.numbers(column):
                if value is not None:
                    total += value
                sums.append(total)
            self._running[column] = sums
        return self._running[column]


def _fill(state: _State, position: int, inputs: Mapping[str, Decimal]) -> None:
    """Compute one column, row by row."""
    formula = state.columns[position].formula
    assert formula is not None
    # Every column it reads is final (computed earlier in the order): one
    # aggregate serves every row.
    aggregates = _Aggregates(state)
    for row in range(len(state.cells)):
        try:
            state.cells[row][position] = evaluate(formula, _Row(state, row, inputs, aggregates))
        except FormulaValueError:
            state.cells[row][position] = None
            state.errors.add((row, position))


def _fraction_digits(value: Decimal) -> int:
    exponent = value.normalize().as_tuple().exponent
    return max(0, -exponent) if isinstance(exponent, int) else 0


def _settled(column: Column, values: Sequence[CellValue]) -> Column:
    """A computed column showing the decimals its values need, as a written one does.

    A margin of whole amounts reads « 600 € » beside « 1 000 € », not « 600,00 € »;
    a rate that needs a fraction gets one — never more than cents, or a tenth of a
    percent.
    """
    ceiling = _COMPUTED_MAX_DECIMALS.get(column.type.kind)
    if ceiling is None:
        return column
    scale = 100 if column.type.kind is ColumnKind.PERCENT else 1
    needed = min(
        max(
            (_fraction_digits(value * scale) for value in values if isinstance(value, Decimal)),
            default=0,
        ),
        ceiling,
    )
    if column.type.kind is ColumnKind.DECIMAL and column.kind in ("amount", ""):
        # Shown as an amount (declared, or computed with no kind): units or cents.
        needed = amount_decimals(needed)
    return replace(column, type=ColumnType(column.type.kind, needed))


def computed_column(
    header: str, kind: str, unit: str, formula: Formula, values: Sequence[CellValue]
) -> Column:
    """Values computed apart from a table — a key figure's — as every format shows them.

    Args:
        header: What the values are.
        kind: Their declared kind (never a text).
        unit: Their unit, kept for an amount or a quantity.
        formula: The formula that computes them.
        values: The values, for the decimals they need.

    Returns:
        A computed column: its kind's type, the decimals its values need.
    """
    column = Column(
        header=header,
        kind=kind,
        unit=unit if kind in UNIT_KINDS else "",
        type=computed_type(kind),
        formula=formula,
        total="",
        better="",
        choices=(),
    )
    return _settled(column, values)


def _settle_decimals(state: _State, position: int) -> None:
    """Settle one computed column of the table on the values just computed."""
    state.columns[position] = _settled(
        state.columns[position], [cells[position] for cells in state.cells]
    )


def _order(columns: list[Column]) -> list[int]:
    """Computed columns, each after the computed columns it reads."""
    position = {column.header: index for index, column in enumerate(columns)}
    pending = [index for index, column in enumerate(columns) if column.formula is not None]
    ordered: list[int] = []
    while pending:
        ready = next(
            (
                index
                for index in pending
                if not {position[name] for name in _reads(columns[index])} & set(pending)
            ),
            None,
        )
        if ready is None:
            # Normalization drops every cycle: a table reaching here unnormalized
            # is a caller's defect, said by name rather than as a StopIteration.
            raise ValueError("computed columns read each other in a cycle")
        ordered.append(ready)
        pending.remove(ready)
    return ordered


def _reads(column: Column) -> frozenset[str]:
    return column.formula.columns if column.formula is not None else frozenset()


def _formulas(
    specs: Mapping[str, ColumnSpec], sheet: TableSheet, inputs: Sequence[str]
) -> dict[str, Formula]:
    """Each declared formula, parsed; one that does not parse leaves its column written."""
    formulas: dict[str, Formula] = {}
    for key, declared in specs.items():
        if not declared.formula:
            continue
        try:
            formulas[key] = parse_formula(
                declared.formula, columns=sheet.headers, inputs=inputs, itself=declared.header
            )
        except FormulaError:
            continue
    return formulas


def _column(
    header: str,
    spec: ColumnSpec | None,
    formula: Formula | None,
    inferred: ColumnType,
    *,
    empty: bool,
    may_blank: bool,
) -> Column:
    """One column as the renderers read it."""
    if spec is None:
        return Column(header, "", "", inferred, None, "", "", ())
    settled = spec if formula is not None else spec.model_copy(update={"formula": ""})
    return Column(
        header=header,
        kind=declared_kind(settled),
        unit=settled.unit,
        type=effective_type(settled, inferred, empty=empty),
        formula=formula,
        total=settled.total,
        better=settled.better,
        choices=tuple(settled.choices),
        may_blank=may_blank,
    )


def _columns(sheet: TableSheet, inputs: Sequence[str]) -> list[Column]:
    specs = {column_key(spec.header): spec for spec in sheet.columns}
    formulas = _formulas(specs, sheet, inputs)
    keys = [column_key(header) for header in sheet.headers]
    visible = [
        ["" if key in formulas else cell for key, cell in zip(keys, row, strict=True)]
        for row in sheet.rows
    ]
    inferred = infer_column_types(sheet.headers, visible)
    blank = blank_columns(
        {
            header: formulas[key]
            for header, key in zip(sheet.headers, keys, strict=True)
            if key in formulas
        }
    )
    return [
        _column(
            header,
            specs.get(key),
            formulas.get(key),
            inferred[index],
            empty=all(not row[index].strip() for row in visible),
            may_blank=header in blank,
        )
        for index, (header, key) in enumerate(zip(sheet.headers, keys, strict=True))
    ]


def aggregate(function: str, values: Sequence[Decimal | None]) -> Decimal | None:
    """``sum``, ``average``, ``min`` or ``max`` of a column, empty cells skipped.

    Excel's own answers: the sum of nothing is 0, so are its min and max; the
    average of nothing has no value.
    """
    numbers = [value for value in values if value is not None]
    if function == "sum":
        return sum(numbers, Decimal(0))
    if function == "average":
        return sum(numbers, Decimal(0)) / len(numbers) if numbers else None
    if not numbers:
        return Decimal(0)
    return min(numbers) if function == "min" else max(numbers)


def _total(state: _State, position: int) -> Decimal | None:
    column = state.columns[position]
    if not column.total:
        return None
    if column.total != "count":
        return aggregate(column.total, state.numbers(column.header))
    if column.computed:
        return Decimal(len(state.cells))
    return Decimal(sum(1 for cells in state.cells if cells[position] not in (None, "")))


def _summary(sheet: TableSheet, state: _State) -> Summary | None:
    summary = sheet.summary
    if summary is None:
        return None
    by = state.position[summary.by]
    # Excel's criteria compare without case: a group is its casefolded label, and
    # it shows the first spelling met — the cached value and the recalculated
    # one then count the same rows.
    groups: dict[str, list[int]] = {}
    spelling: dict[str, str] = {}
    for row, written in enumerate(sheet.rows):
        label = written[by].strip()
        if label:
            spelling.setdefault(label.casefold(), label)
            groups.setdefault(label.casefold(), []).append(row)
    measures = tuple(summary.measures)
    columns = {measure: state.numbers(measure) for measure in measures}
    results: list[tuple[str, tuple[Decimal | None, ...]]] = []
    for key in sorted(groups):
        label, rows = spelling[key], groups[key]
        if summary.function == "count":
            results.append((label, (Decimal(len(rows)),)))
        else:
            values = tuple(
                aggregate(summary.function, [columns[measure][row] for row in rows])
                for measure in measures
            )
            results.append((label, values))
    return Summary(summary.title, summary.by, summary.function, measures, tuple(results))


def compute_table(sheet: TableSheet, inputs: Mapping[str, Decimal] | None = None) -> ComputedTable:
    """Every value of a canonical table.

    Args:
        sheet: A table in canonical form (``columns.normalize_table``).
        inputs: The workbook's input values, by name (``input_values``).

    Returns:
        The computed table.
    """
    values = dict(inputs or {})
    columns = _columns(sheet, list(values))
    state = _State(
        columns,
        [
            [typed_cell(cell, column.type) for cell, column in zip(row, columns, strict=True)]
            for row in sheet.rows
        ],
    )
    for position in _order(columns):
        _fill(state, position, values)
        _settle_decimals(state, position)
    return ComputedTable(
        name=sheet.name,
        columns=tuple(state.columns),
        raw=tuple(tuple(row) for row in sheet.rows),
        cells=tuple(tuple(row) for row in state.cells),
        errors=frozenset(state.errors),
        totals=tuple(_total(state, position) for position in range(len(columns))),
        summary=_summary(sheet, state),
        chart=sheet.chart,
    )


# ---------------------------------------------------------------------------
# Readings for each family
# ---------------------------------------------------------------------------
def shown_value(column: Column, value: CellValue) -> CellValue:
    """A computed date column's serial as the date it is — nothing when no calendar
    holds it; any other value as it is."""
    if column.computed and isinstance(value, Decimal) and column.type.kind in _DATE_KINDS:
        return from_serial(value, column.type.kind)
    return value


def machine_text(column: Column, value: CellValue) -> str:
    """A computed value as CSV writes it: dot decimals, ISO dates, nothing for no value."""
    shown = shown_value(column, value)
    if shown is None:
        return ""
    if isinstance(shown, Decimal):
        if column.type.kind is ColumnKind.PERCENT:
            return f"{rounded(shown * 100, _CSV_DECIMALS).normalize():f}%"
        return f"{rounded(shown, _CSV_DECIMALS).normalize():f}"
    if isinstance(shown, datetime):
        return shown.strftime("%Y-%m-%d %H:%M")
    if isinstance(shown, date):
        return shown.isoformat()
    return shown


def display_kind(column: Column) -> str:
    """The kind a column is SHOWN as: declared, else what its computation produces.

    An undeclared WRITTEN column has none: its cells are shown as written, and a
    materialized table must not declare for it what the writer never did — a
    second pass would then rewrite cells the first one left alone.
    """
    if column.kind or not column.computed:
        return column.kind
    return "percent" if column.type.kind is ColumnKind.PERCENT else "amount"


def display_text(column: Column, value: CellValue, language: str) -> str:
    """A value as a report, a slide or a Markdown file writes it.

    A column whose kind the writer declared (or the renderer computed) reads in
    the reader's conventions; a cell that does not parse keeps what was written.
    """
    shown = shown_value(column, value)
    kind = display_kind(column)
    if shown is None:
        return ""
    if not kind or isinstance(shown, str):
        return str(shown)
    return display(shown, kind, column.unit, column.type.decimals, language)


def display_cell(table: ComputedTable, row: int, position: int, language: str) -> str:
    """One cell as a report shows it: a typed value in the reader's conventions,
    a written cell of an undeclared column as written, nothing where no value is.

    Args:
        table: The computed table.
        row: The data row.
        position: The column.
        language: The reader's backend-canonical language.

    Returns:
        The text drawn in that cell (or under that point of a chart).
    """
    column = table.columns[position]
    if (row, position) in table.errors:
        return ""
    if column.computed or column.kind:
        return display_text(column, table.cells[row][position], language)
    return table.raw[row][position]


def _display_row(table: ComputedTable, row: int, language: str) -> list[str]:
    return [display_cell(table, row, position, language) for position in range(len(table.columns))]


def _totals_row(table: ComputedTable, language: str) -> list[str]:
    row = [
        display_text(column, total, language) if total is not None else ""
        for column, total in zip(table.columns, table.totals, strict=True)
    ]
    if not table.columns[0].total:
        row[0] = document_label(language, "documents.total_label")
    return row


def _summary_sheet(table: ComputedTable, language: str) -> TableSheet | None:
    summary = table.summary
    if summary is None:
        return None
    by = table.columns[table.position(summary.by)]
    measures = summary_columns(table, language)
    title = summary.title or document_label(language, "documents.summary_title", column=by.header)
    return TableSheet(
        name=title,
        headers=[by.header, *(column.header for column in measures)],
        rows=[
            [
                label,
                *(
                    display_text(column, value, language)
                    for column, value in zip(measures, values, strict=True)
                ),
            ]
            for label, values in summary.groups
        ],
        columns=[
            ColumnSpec(header=column.header, kind=display_kind(column), unit=column.unit)
            for column in measures
            if display_kind(column)
        ],
    )


def summary_columns(table: ComputedTable, language: str) -> list[Column]:
    """The measure columns of a table's summary, as every format shows them.

    Args:
        table: A computed table with a summary.
        language: The reader's language (the count column's header).

    Returns:
        One column per value of a group: the count, or each measure.
    """
    summary = table.summary
    if summary is None:
        return []
    if summary.function == "count":
        count = document_label(language, "documents.count_label")
        return [Column(count, "quantity", "", ColumnType(ColumnKind.INT), None, "", "", ())]
    return [
        _summary_column(table.columns[table.position(name)], index, summary)
        for index, name in enumerate(summary.measures)
    ]


def _summary_column(source: Column, index: int, summary: Summary) -> Column:
    """A summary measure: computed values, shown as their source column is (an amount
    when it declared nothing), with the decimals the aggregates need."""
    percent = source.type.kind is ColumnKind.PERCENT
    kind = source.kind or ("percent" if percent else "amount")
    column = Column(
        header=source.header,
        kind=kind,
        unit=source.unit,
        type=ColumnType(ColumnKind.PERCENT if percent else ColumnKind.DECIMAL),
        formula=None,
        total="",
        better="",
        choices=(),
    )
    return _settled(column, [values[index] for _label, values in summary.groups])


def materialize_table(sheet: TableSheet, language: str) -> tuple[TableSheet, TableSheet | None]:
    """A canonical table as a report shows it: values written, totals as a row.

    Args:
        sheet: A table in canonical form.
        language: The reader's backend-canonical language.

    Returns:
        The table — computed values written in the reader's conventions, the
        totals row appended, each column keeping only its kind and unit — and
        its grouped summary as a table of its own, when it has one.
    """
    table = compute_table(sheet)
    rows = [_display_row(table, row, language) for row in range(len(table.cells))]
    if table.has_totals:
        rows.append(_totals_row(table, language))
    specs = [
        ColumnSpec(header=column.header, kind=display_kind(column), unit=column.unit)
        for column in table.columns
        if display_kind(column)
    ]
    shown = TableSheet(name=sheet.name, headers=list(sheet.headers), rows=rows, columns=specs)
    return shown, _summary_sheet(table, language)


def numeric_columns(sheet: TableSheet) -> list[bool]:
    """Which columns are drawn right-aligned: declared numbers, or cells that are.

    Args:
        sheet: A table in canonical (possibly materialized) form.

    Returns:
        One flag per header.
    """
    specs = {column_key(spec.header): spec for spec in sheet.columns}
    inferred = infer_column_types(sheet.headers, sheet.rows)
    flags: list[bool] = []
    for header, column in zip(sheet.headers, inferred, strict=True):
        spec = specs.get(column_key(header))
        declared = spec.kind if spec is not None else ""
        flags.append(declared in NUMERIC_KINDS if declared else column.numeric)
    return flags


def totals_row_index(sheet: TableSheet, language: str) -> int | None:
    """The index of the totals row a renderer draws in bold: the last, when labelled."""
    if not sheet.rows or not sheet.rows[-1]:
        return None
    label = document_label(language, "documents.total_label").casefold()
    return len(sheet.rows) - 1 if sheet.rows[-1][0].strip().casefold() == label else None
