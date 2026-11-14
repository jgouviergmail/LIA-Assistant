"""What a table's columns ARE: kinds, units, formulas, totals, a summary (ADR-274 amendment).

The writer declares a column when its cells alone cannot say what it is — a
year and a postal code are integers too — or when the renderer must compute it:
a model does arithmetic badly and says nothing when it is wrong, so a margin, a
rate or a total is DECLARED here and computed by ``computation.py``.

Every incoherence is repaired, none is refused (ADR-184), and the result is a
fixed point — normalizing twice changes nothing:

- a declaration finds its column whatever its case and spacing; an unknown kind,
  total or direction reads « nothing »; a unit only belongs to an amount or a
  quantity; a kind the cells contradict stops typing them but stays declared;
- a percentage is written with its sign: plain numbers declared ``percent`` read as
  the workbook reads them — fractions — only when every one of them is one, and
  the declaration goes otherwise (« 20 » would be shown « 2 000 % »);
- a formula that cannot be computed — an unknown name, text as an operand, a
  number compared to a text, a comparison reading bare a column that may have
  no value, a cycle — is dropped: the column keeps the cells the writer wrote,
  or disappears when it has none (a new column, or one left empty for the
  renderer to fill), and every formula reading a column that disappears fails
  in turn: no value is ever computed from a computation that failed. A column
  never reads itself: in its own formula its name is the input of that name;
- only the members of a cycle lose their formula — a column READING a cycle
  computes on what the cycle's columns keep, or goes with them;
- a computed column's cells are blanked: the renderer computes every value;
- a summary keeps what it can compute, or goes;
- a chart keeps the measures it can draw on ONE axis — a value in another unit
  goes, because two scales on one plot invent a correlation — or goes when
  nothing is left to draw, or when the table has fewer than two rows (one bar
  is a number, not a chart).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from decimal import Decimal

from src.core.constants import DOCUMENT_GENERATION_COLUMN_CHOICES_MAX
from src.domains.document_generation.formulas import (
    Formula,
    FormulaError,
    blank_columns,
    parse_formula,
)
from src.domains.document_generation.sanitize import strip_control_characters
from src.domains.document_generation.schemas import (
    BETTER_DIRECTIONS,
    CHART_FORMS,
    CHART_INTENTS,
    COLUMN_KINDS,
    SUMMARY_FUNCTIONS,
    TOTAL_FUNCTIONS,
    ChartSpec,
    ColumnSpec,
    GroupSummary,
    TableSheet,
)
from src.domains.document_generation.tables import (
    ColumnKind,
    ColumnType,
    infer_column_types,
    normalize_sheet,
    sanitize_headers,
)
from src.domains.document_generation.typography import CHART_MAX_SERIES, CHART_SCATTER_MAX_SERIES

#: A unit is a currency code or a symbol, never a phrase.
UNIT_MAX_CHARS = 12
#: A name a formula reads — an input's or a key figure's.
NAME_MAX_CHARS = 60
#: An amount shows at most cents.
AMOUNT_MAX_DECIMALS = 2
#: The kinds a unit belongs to.
UNIT_KINDS = frozenset({"amount", "quantity"})
_MEASURE_TOTALS = frozenset({"sum", "average", "min", "max"})
#: The inferred types a declared kind agrees with.
_COMPATIBLE: dict[str, frozenset[ColumnKind]] = {
    "amount": frozenset({ColumnKind.INT, ColumnKind.DECIMAL}),
    "quantity": frozenset({ColumnKind.INT, ColumnKind.DECIMAL}),
    "percent": frozenset({ColumnKind.PERCENT}),
    "date": frozenset({ColumnKind.DATE}),
    "datetime": frozenset({ColumnKind.DATETIME, ColumnKind.DATE}),
    "year": frozenset({ColumnKind.INT}),
}
#: Numbers written without a sign: what a ``percent`` declaration may still read.
_PLAIN_NUMBERS = frozenset({ColumnKind.INT, ColumnKind.DECIMAL})
#: What a formula may compute with: numbers, and dates as Excel serials.
_OPERAND_TYPES = frozenset(
    {ColumnKind.INT, ColumnKind.DECIMAL, ColumnKind.PERCENT, ColumnKind.DATE, ColumnKind.DATETIME}
)
#: The type a computed column takes, by its declared kind.
_COMPUTED_TYPES: dict[str, ColumnType] = {
    "amount": ColumnType(ColumnKind.DECIMAL, AMOUNT_MAX_DECIMALS),
    "quantity": ColumnType(ColumnKind.DECIMAL, AMOUNT_MAX_DECIMALS),
    "percent": ColumnType(ColumnKind.PERCENT, 1),
    "date": ColumnType(ColumnKind.DATE),
    "datetime": ColumnType(ColumnKind.DATETIME),
    "year": ColumnType(ColumnKind.INT),
    "": ColumnType(ColumnKind.DECIMAL, AMOUNT_MAX_DECIMALS),
}


def amount_decimals(needed: int) -> int:
    """An amount shows whole units or cents — « 1 200,5 € » is no amount anyone writes."""
    return 0 if needed == 0 else AMOUNT_MAX_DECIMALS


def column_key(name: str) -> str:
    """How a column name is matched: case and spacing never decide."""
    return " ".join(name.split()).casefold()


def _clean(text: str) -> str:
    return strip_control_characters(" ".join(text.split()))


def _one_of(value: str, allowed: tuple[str, ...]) -> str:
    normalized = value.strip().casefold()
    return normalized if normalized in allowed else ""


def _choices(values: list[str]) -> list[str]:
    kept: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = _clean(value)
        if cleaned and cleaned.casefold() not in seen:
            seen.add(cleaned.casefold())
            kept.append(cleaned)
    return kept[:DOCUMENT_GENERATION_COLUMN_CHOICES_MAX]


def _clean_spec(spec: ColumnSpec) -> ColumnSpec:
    kind = _one_of(spec.kind, COLUMN_KINDS)
    return ColumnSpec(
        header=_clean(spec.header),
        kind=kind,
        unit=_clean(spec.unit)[:UNIT_MAX_CHARS] if kind in UNIT_KINDS else "",
        formula=spec.formula.strip(),
        total=_one_of(spec.total, TOTAL_FUNCTIONS),
        better=_one_of(spec.better, BETTER_DIRECTIONS),
        choices=_choices(spec.choices),
    )


def computed_type(kind: str) -> ColumnType:
    """The type a computed value takes, by its declared kind (a computed column's, a key figure's)."""
    return _COMPUTED_TYPES.get(kind, _COMPUTED_TYPES[""])


def effective_type(spec: ColumnSpec | None, inferred: ColumnType, *, empty: bool) -> ColumnType:
    """The type a column's cells take, honouring its declared kind when they agree.

    Args:
        spec: The column's declaration, if any.
        inferred: The type its cells agree on (``tables.infer_column_types``).
        empty: Whether the column has no value at all.

    Returns:
        The column's type. A computed column takes its kind's type; a declared
        kind the cells contradict leaves the inferred type standing.
    """
    kind = spec.kind if spec is not None else ""
    if spec is not None and spec.formula:
        return computed_type(kind)
    if kind in ("text", "code"):
        return ColumnType(ColumnKind.TEXT)
    compatible = _COMPATIBLE.get(kind)
    if compatible is None or not (empty or inferred.kind in compatible):
        return inferred
    if kind in UNIT_KINDS:
        scale = amount_decimals(inferred.decimals) if kind == "amount" else inferred.decimals
        return ColumnType(ColumnKind.DECIMAL, scale)
    if kind == "year":
        return ColumnType(ColumnKind.INT)
    if empty and inferred.kind is ColumnKind.TEXT:
        return _COMPUTED_TYPES[kind]
    return inferred


def reads_as_percent(inferred: ColumnType, cells: Iterable[str]) -> bool:
    """Whether values declared ``percent`` may be shown as percentages.

    A percentage is written with its sign (« 12.5% »). Without it a number is read
    as the workbook reads it — a fraction, 0.2 for 20 % — which holds only when
    every number is one: « 20 » shown « 2 000 % » is a false figure, and nothing
    says whether the writer meant 20 % (ADR-184: no intent is invented), so such
    values are shown as they were written.

    Args:
        inferred: The type the written cells agree on.
        cells: The written cells.

    Returns:
        False for plain numbers one of which is beyond one; True otherwise.
    """
    if inferred.kind not in _PLAIN_NUMBERS:
        return True
    return all(abs(Decimal(cell)) <= 1 for cell in map(str.strip, cells) if cell)


def declared_kind(spec: ColumnSpec | None) -> str:
    """The kind a column keeps: what the writer declared, never text for a computation.

    A kind the cells contradict stays declared — it only stops typing them
    (``effective_type``): the cells keep what they are, and a second pass over a
    table whose amounts were already written out for a reader finds the same
    declaration, which is what makes normalization a fixed point.
    """
    if spec is None:
        return ""
    if spec.formula and spec.kind in ("text", "code"):
        return ""
    return spec.kind


def leads_back[Node](start: Node, edges: Mapping[Node, set[Node]]) -> bool:
    """Whether what a computed value reads leads back to it — a column, or a key figure.

    Args:
        start: The value.
        edges: What each value reads.

    Returns:
        True when it is on a cycle.
    """
    seen: set[Node] = set()
    pending = list(edges[start])
    while pending:
        column = pending.pop()
        if column == start:
            return True
        if column not in seen:
            seen.add(column)
            pending.extend(edges.get(column, ()))
    return False


def _in_cycles(formulas: dict[int, Formula], headers: Sequence[str]) -> set[int]:
    """Computed columns on a cycle: each needs itself, through the others, to be computed.

    A column that only READS a cycle is no member: once the cycle's formulas are
    dropped it computes on what their columns keep, or goes with them
    (``_settle_formulas``).
    """
    position = {name: index for index, name in enumerate(headers)}
    edges = {
        column: {position[name] for name in formula.columns if position[name] in formulas}
        for column, formula in formulas.items()
    }
    return {column for column in edges if leads_back(column, edges)}


class _Draft:
    """A table being canonicalized: headers, rows and the declarations by position."""

    def __init__(self, headers: list[str], rows: list[list[str]]) -> None:
        self.headers = headers
        self.rows = rows
        self.specs: dict[int, ColumnSpec] = {}
        self.appended: set[int] = set()

    def empty(self, position: int) -> bool:
        return all(not row[position].strip() for row in self.rows)

    def inferred(self, computed: set[int]) -> list[ColumnType]:
        """Types from the written cells; a computed column's cells do not vote."""
        visible = [
            [cell if index not in computed else "" for index, cell in enumerate(row)]
            for row in self.rows
        ]
        return infer_column_types(self.headers, visible)

    def remove(self, positions: set[int]) -> None:
        keep = [index for index in range(len(self.headers)) if index not in positions]
        renumber = {old: new for new, old in enumerate(keep)}
        self.headers = [self.headers[index] for index in keep]
        self.rows = [[row[index] for index in keep] for row in self.rows]
        self.specs = {renumber[old]: spec for old, spec in self.specs.items() if old in renumber}
        self.appended = {renumber[old] for old in self.appended if old in renumber}


def _attach(draft: _Draft, specs: list[ColumnSpec], raw_headers: list[str], language: str) -> None:
    """Each declaration finds its column; a new computed column is appended."""
    index: dict[str, int] = {}
    for position, name in enumerate(draft.headers):
        index.setdefault(column_key(name), position)
    for position, name in enumerate(raw_headers):
        index.setdefault(column_key(name), position)
    appended: list[ColumnSpec] = []
    for raw in specs:
        spec = _clean_spec(raw)
        key = column_key(spec.header)
        if not key:
            # A nameless declaration describes no column, not the unnamed one.
            continue
        if key in index:
            draft.specs.setdefault(index[key], spec)
        elif spec.formula:
            index[key] = len(draft.headers) + len(appended)
            appended.append(spec)
    if appended:
        first = len(draft.headers)
        draft.headers = sanitize_headers(
            [*draft.headers, *(spec.header for spec in appended)], language
        )
        draft.rows = [row + [""] * len(appended) for row in draft.rows]
        for offset, spec in enumerate(appended):
            draft.specs[first + offset] = spec
            draft.appended.add(first + offset)
    for position, spec in draft.specs.items():
        draft.specs[position] = spec.model_copy(update={"header": draft.headers[position]})


def _readable(draft: _Draft, computed: set[int]) -> tuple[set[int], set[int]]:
    """The columns a formula may read as numbers, and those it may compare to a text.

    A number is a written number or date, or a computed value; a text is a
    written text. An empty column is both: it reads 0, and the empty text.
    """
    inferred = draft.inferred(computed)
    numbers: set[int] = set()
    texts: set[int] = set()
    for position in range(len(draft.headers)):
        kind = effective_type(draft.specs.get(position), inferred[position], empty=False).kind
        if position in computed or draft.empty(position) or kind in _OPERAND_TYPES:
            numbers.add(position)
        if position not in computed and (draft.empty(position) or kind is ColumnKind.TEXT):
            texts.add(position)
    return numbers, texts


def _invalid_formulas(draft: _Draft, inputs: Sequence[str]) -> set[int]:
    """Computed columns whose formula cannot be computed on this table.

    Each column is read as what it holds — a number as a number, a text as a
    text — and a comparison never reads bare a column that may have no value:
    the workbook holds such a cell as an empty text, which Excel compares as
    larger than any number where the cached value has none.
    """
    computed = {position for position, spec in draft.specs.items() if spec.formula}
    numbers, texts = _readable(draft, computed)
    parsed: dict[int, Formula] = {}
    invalid: set[int] = set()
    for position in computed:
        try:
            formula = parse_formula(
                draft.specs[position].formula,
                columns=draft.headers,
                inputs=inputs,
                itself=draft.headers[position],
            )
        except FormulaError:
            invalid.add(position)
            continue
        if any(draft.headers.index(name) not in numbers for name in formula.numbers) or any(
            draft.headers.index(name) not in texts for name in formula.texts
        ):
            invalid.add(position)
            continue
        parsed[position] = formula
    blank = blank_columns(
        {draft.headers[position]: formula for position, formula in parsed.items()}
    )
    invalid |= {position for position, formula in parsed.items() if formula.compared & blank}
    return invalid | _in_cycles(parsed, draft.headers)


def _settle_formulas(draft: _Draft, inputs: Sequence[str]) -> None:
    """Drop what cannot be computed until everything left can be.

    A column whose formula is dropped keeps what the writer wrote in it; one with
    nothing written — a new column, or one left empty for the renderer to fill —
    goes, and the formulas reading it fail on the next pass: a value is never
    computed from the void a failed computation left.
    """
    while invalid := _invalid_formulas(draft, inputs):
        gone = {position for position in invalid if draft.empty(position)}
        for position in invalid - gone:
            draft.specs[position] = draft.specs[position].model_copy(update={"formula": ""})
        draft.remove(gone)


def _final_spec(
    spec: ColumnSpec, inferred: ColumnType, *, empty: bool, cells: Sequence[str]
) -> ColumnSpec:
    """The canonical declaration once the cells and the formula have spoken."""
    kind = declared_kind(spec)
    # A computed column's cells are blank here: only written numbers can contradict.
    if kind == "percent" and not reads_as_percent(inferred, cells):
        kind = ""
    # A computed column's type is its kind's: a computed DATE is no number to sum.
    numeric = effective_type(spec, inferred, empty=empty).numeric
    total = spec.total if spec.total == "count" or (spec.total and numeric) else ""
    return ColumnSpec(
        header=spec.header,
        kind=kind,
        unit=spec.unit if kind in UNIT_KINDS else "",
        formula=spec.formula,
        total=total,
        better=spec.better if numeric else "",
        choices=[] if spec.formula else spec.choices,
    )


def _is_set(spec: ColumnSpec) -> bool:
    return bool(spec.kind or spec.formula or spec.total or spec.better or spec.choices)


def _measures(
    names: list[str], index: dict[str, int], draft: _Draft, allowed: set[int]
) -> list[str]:
    """The measures a summary can compute: known, numeric, each once."""
    measures: list[str] = []
    for name in names:
        position = index.get(column_key(name))
        header = draft.headers[position] if position is not None else ""
        if position in allowed and header not in measures:
            measures.append(header)
    return measures


def _summary(
    summary: GroupSummary | None, draft: _Draft, numeric: set[int], groupable: set[int]
) -> GroupSummary | None:
    """The summary, reduced to what can be computed on this table.

    Rows group by a written column of words or whole numbers: a workbook matches
    a group through a criterion, and a date or a decimal there is read through
    the reader's regional settings — the recalculated sum could then differ from
    the one cached.
    """
    if summary is None or not draft.rows:
        return None
    index = {column_key(name): position for position, name in enumerate(draft.headers)}
    by = index.get(column_key(summary.by))
    if by is None or by not in groupable:
        return None
    function = _one_of(summary.function, SUMMARY_FUNCTIONS) or "sum"
    measures = _measures(summary.measures, index, draft, numeric - {by})
    if function == "count":
        measures = []
    elif not measures:
        return None
    return GroupSummary(
        by=draft.headers[by], measures=measures, function=function, title=_clean(summary.title)
    )


class _Settled:
    """A table's declarations once settled, and what its columns can do."""

    def __init__(self, draft: _Draft, computed: set[int]) -> None:
        inferred = draft.inferred(computed)
        empty = {position: draft.empty(position) for position in range(len(draft.headers))}
        self.specs: dict[int, ColumnSpec] = {
            position: _final_spec(
                spec,
                inferred[position],
                empty=empty[position],
                cells=[row[position] for row in draft.rows],
            )
            for position, spec in draft.specs.items()
        }
        types = [
            effective_type(self.specs.get(position), inferred[position], empty=empty[position])
            for position in range(len(draft.headers))
        ]
        self.types = types
        self.numeric = {position for position, kind in enumerate(types) if kind.numeric}
        self.groupable = {
            position
            for position, kind in enumerate(types)
            if position not in computed and kind.kind in (ColumnKind.TEXT, ColumnKind.INT)
        }

    def declared(self) -> list[ColumnSpec]:
        """The declarations worth keeping, in column order."""
        return [
            self.specs[position] for position in sorted(self.specs) if _is_set(self.specs[position])
        ]


def _axis(settled: _Settled, position: int) -> tuple[bool, str]:
    """The axis a measure is drawn on: whether it is a share, and its unit."""
    spec = settled.specs.get(position)
    return (
        settled.types[position].kind is ColumnKind.PERCENT,
        spec.unit.casefold() if spec is not None else "",
    )


def _same_axis(first: tuple[bool, str], other: tuple[bool, str]) -> bool:
    """One scale: both shares or both not, and no two different declared units."""
    return first[0] == other[0] and (not first[1] or not other[1] or first[1] == other[1])


def _chart_values(
    wanted: Sequence[int | None],
    category: int,
    measures: list[int],
    settled: _Settled,
    *,
    free_first: bool,
) -> list[int]:
    """The measures drawn: known, numeric, each once, on one axis.

    A relation's first value runs along the OTHER axis — the one place two
    units meet — and the scatter keeps the series that stay apart pair by pair.
    """
    values: list[int] = []
    for position in wanted:
        if position is None or position == category or position in values:
            continue
        if position not in measures:
            continue
        shared = values[1:] if free_first else values
        if shared and not _same_axis(_axis(settled, shared[0]), _axis(settled, position)):
            continue
        values.append(position)
    return values[: 1 + CHART_SCATTER_MAX_SERIES] if free_first else values[:CHART_MAX_SERIES]


def _chart_measures(settled: _Settled) -> list[int]:
    """The columns a chart can measure: numbers, never a declared year."""
    return [
        position
        for position in sorted(settled.numeric)
        if (spec := settled.specs.get(position)) is None or spec.kind != "year"
    ]


def _chart_category(named: int | None, columns: int, measures: list[int]) -> int:
    """The column naming each point: the one named, else the first that is no measure."""
    if named is not None:
        return named
    return next((position for position in range(columns) if position not in measures), 0)


def _chart(chart: ChartSpec | None, draft: _Draft, settled: _Settled) -> ChartSpec | None:
    """The chart, reduced to what can be drawn on one axis of this table.

    The category defaults to the first column that is not a measure (the first
    column when every one is), the values to every measure; a declared year is
    a point in time, never a measure.
    """
    if chart is None or len(draft.rows) < 2:
        return None
    index = {column_key(name): position for position, name in enumerate(draft.headers)}
    measures = _chart_measures(settled)
    category = _chart_category(index.get(column_key(chart.category)), len(draft.headers), measures)
    wanted = [index.get(column_key(name)) for name in chart.values] if chart.values else measures
    intent = _one_of(chart.intent, CHART_INTENTS) or "compare"
    values = _chart_values(wanted, category, measures, settled, free_first=intent == "relation")
    if not values:
        return None
    return ChartSpec(
        intent=intent,
        form=_one_of(chart.form, CHART_FORMS),
        category=draft.headers[category],
        values=[draft.headers[position] for position in values],
        title=_clean(chart.title),
    )


def _blank_computed(draft: _Draft, computed: set[int]) -> None:
    """A computed column's cells are the renderer's to fill."""
    draft.rows = [
        [cell if index not in computed else "" for index, cell in enumerate(row)]
        for row in draft.rows
    ]


def normalize_table(
    sheet: TableSheet, language: str, *, inputs: Sequence[str] = ()
) -> TableSheet | None:
    """A table in canonical form: rectangular, legal headers, declarations settled.

    Args:
        sheet: The writer's table.
        language: Reader's language, for generated headers.
        inputs: The workbook's input names a formula may read (none elsewhere).

    Returns:
        The canonical table, or ``None`` when there is nothing to render.
    """
    base = normalize_sheet(sheet, language)
    if base is None:
        return None
    draft = _Draft(list(base.headers), [list(row) for row in base.rows])
    _attach(draft, sheet.columns, list(sheet.headers), language)
    _settle_formulas(draft, inputs)
    if not draft.headers:
        return None
    computed = {position for position, spec in draft.specs.items() if spec.formula}
    _blank_computed(draft, computed)
    settled = _Settled(draft, computed)
    draft.specs = settled.specs
    return TableSheet(
        name=base.name,
        headers=draft.headers,
        rows=draft.rows,
        columns=settled.declared(),
        summary=_summary(sheet.summary, draft, settled.numeric, settled.groupable),
        chart=_chart(sheet.chart, draft, settled),
    )
