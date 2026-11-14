"""A computed column's expression: one grammar, two readings (ADR-274 amendment, ADR-388).

The writer says what a column IS — « the margin is revenue minus cost » — and
never computes it: a model does arithmetic badly and says nothing when it is
wrong. The same parsed tree then gives:

- the Excel text a workbook recalculates (``to_excel``), so the sheet stays
  alive when the reader changes a value;
- the exact value (``evaluate``), cached beside the formula for every reader
  that never recalculates — a preview pane, a phone, the chat's own excerpt —
  and written as plain data in Word, PDF, slides and CSV.

The two readings must agree, so the grammar is the subset whose Excel meaning is
known exactly: ``+ - * / ^`` and parentheses, ``ROUND`` (half away from zero, as
Excel rounds), ``ABS``, ``MIN`` / ``MAX`` of values, ``SUM`` / ``AVERAGE`` of a
whole column, ``RUNNING_SUM`` (the column from its first row down to this one),
``PREVIOUS`` (the row above), and ``IF`` choosing one of two values on a
condition: two values compared (``= <> < <= > >=``), a column equal or not to a
quoted text, ``AND`` / ``OR`` / ``NOT`` of conditions. A name between braces is a
column of the same table or, in a workbook, one of its inputs — a column's
name winning over an input's, except in that column's own formula: a column
never reads itself, so there its name is the input of that name, or nothing (a
writer names a column after the input it shows: ``Rent`` computed as
``{Rent}``, measured 2026-11-13). A function name is read whatever its case,
``==`` and ``!=`` as ``=`` and ``<>``.

Where Excel is not arithmetic, its reading is mirrored:

- an empty cell is 0 in arithmetic and in a comparison, and is skipped by an
  aggregate, a running sum, and ``MIN`` / ``MAX`` when the reference is bare —
  so is a computed cell with no value, which the workbook holds as an empty
  text (``IFERROR(…, "")``) and whatever reads it in arithmetic has none either;
- ``IF`` computes only the value it chooses, and when that value is a bare
  reference it returns the REFERENCE — ``MIN`` then skips an empty cell through
  it as through the reference itself; ``AND`` and ``OR`` read every condition;
- two numbers compare on 15 significant digits, a text without case.

A workbook's KEY FIGURES are computed once, not per row: their formulas read
the inputs and the other figures by name, and a sheet's whole column through
``SUM({Sheet/Column})`` or ``AVERAGE({Sheet/Column})`` — never a row, which they
do not have (``parse_formula(..., sheets=...)``, ``workbook_figures.py``).

What Excel would read otherwise is refused: a comparison reading the row above
bare — itself, or as the value an ``IF`` returns — since the first row's is the
header, a text larger than any number. A comparison reading so a column that may
have no value is refused by the normalization, which knows the columns
(``columns.py``).

Nothing is executed: the text is parsed by ``ast`` and every node outside the
grammar is refused. Excel binds a unary minus tighter than ``^`` and reads ``^``
from the left, so every nested operation is parenthesized on the way out — the
workbook computes what the cached value says.
"""

from __future__ import annotations

import ast
import operator
import re
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from decimal import (
    ROUND_HALF_UP,
    Decimal,
    DivisionByZero,
    InvalidOperation,
    Overflow,
    localcontext,
)
from typing import Literal, Protocol

from src.core.constants import DOCUMENT_GENERATION_FORMULA_MAX_CHARS

FormulaFailure = Literal[
    "empty", "too_long", "braces", "syntax", "unknown_reference", "reads_itself", "unsupported"
]

#: A name between braces: anything but a brace.
_REFERENCE = re.compile(r"\{([^{}]*)\}")
#: What a reference becomes before ``ast`` reads the text; refused if typed.
_PLACEHOLDER_PREFIX = "__lia_ref_"
#: Excel's spelling, read as Python's: a quoted text whole, a function name in
#: capitals, an operator translated; everything else is copied as written.
_SPELLING = re.compile(
    r"""(?P<text>"[^"]*"|'[^']*')|(?P<call>[A-Za-z_]\w*)(?=\s*\()|(?P<operator><>|<=|>=|!=|==|=|\^)"""
)
_PYTHON_OPERATORS = {"<>": "!=", "=": "==", "^": "**"}
#: ``ROUND``'s digits, as Excel accepts them and as a sheet needs them.
_ROUND_DIGITS = range(-6, 7)
#: Digits kept by every operation: beyond any figure a sheet shows.
_PRECISION = 28
#: Significant digits two numbers are compared on — Excel's.
_COMPARISON_DIGITS = 15
#: The exponent bound, Excel's own: past 9.99E+307 the workbook answers #NUM!, and
#: no float holds the value it would cache beside the formula — an absurd power
#: overflows at once instead of computing.
_EXPONENT_LIMIT = 307

BinaryOperator = Literal["+", "-", "*", "/", "^"]
ScalarFunction = Literal["ROUND", "ABS", "MIN", "MAX"]
AggregateFunction = Literal["SUM", "AVERAGE"]
ComparisonOperator = Literal["=", "<>", "<", "<=", ">", ">="]
LogicalFunction = Literal["AND", "OR", "NOT"]

_BINARY: dict[type[ast.operator], BinaryOperator] = {
    ast.Add: "+",
    ast.Sub: "-",
    ast.Mult: "*",
    ast.Div: "/",
    ast.Pow: "^",
}
_COMPARISONS: dict[type[ast.cmpop], ComparisonOperator] = {
    ast.Eq: "=",
    ast.NotEq: "<>",
    ast.Lt: "<",
    ast.LtE: "<=",
    ast.Gt: ">",
    ast.GtE: ">=",
}
_ORDERS: dict[ComparisonOperator, Callable[[Decimal, Decimal], bool]] = {
    "=": operator.eq,
    "<>": operator.ne,
    "<": operator.lt,
    "<=": operator.le,
    ">": operator.gt,
    ">=": operator.ge,
}
#: The conditions of several conditions; ``NOT`` takes one.
_JOINTS: dict[str, LogicalFunction] = {"AND": "AND", "OR": "OR"}
_NOT: LogicalFunction = "NOT"


class FormulaError(ValueError):
    """A formula the grammar refuses.

    Attributes:
        reason: A bounded code, never the formula itself (it is the writer's text).
    """

    def __init__(self, reason: FormulaFailure) -> None:
        super().__init__(reason)
        self.reason: FormulaFailure = reason


class FormulaValueError(ArithmeticError):
    """A row whose formula has no value: a division by zero, no previous row…

    Excel shows an error there; the workbook wraps it in ``IFERROR(…, "")`` and
    every other reader gets an empty cell — the same blank everywhere.
    """


# ---------------------------------------------------------------------------
# The tree
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Number:
    """A literal."""

    value: Decimal


@dataclass(frozen=True, slots=True)
class ColumnRef:
    """This row's cell in a column of the same table."""

    name: str


@dataclass(frozen=True, slots=True)
class InputRef:
    """One of the workbook's inputs."""

    name: str


@dataclass(frozen=True, slots=True)
class Negation:
    """A unary minus."""

    operand: Node


@dataclass(frozen=True, slots=True)
class Binary:
    """Two operands and an operator."""

    operator: BinaryOperator
    left: Node
    right: Node


@dataclass(frozen=True, slots=True)
class Call:
    """A function of values (``ROUND``'s digits travel as a ``Number``)."""

    function: ScalarFunction
    arguments: tuple[Node, ...]


@dataclass(frozen=True, slots=True)
class Aggregate:
    """A function of a whole column."""

    function: AggregateFunction
    column: str


@dataclass(frozen=True, slots=True)
class Previous:
    """The cell of the row above, in a column."""

    column: str


@dataclass(frozen=True, slots=True)
class RunningSum:
    """A column summed from its first row down to this one."""

    column: str


@dataclass(frozen=True, slots=True)
class SheetAggregate:
    """A function of a whole column of a named sheet (a key figure's)."""

    function: AggregateFunction
    sheet: str
    column: str


@dataclass(frozen=True, slots=True)
class Choice:
    """``IF``: one of two values, on a condition."""

    condition: Condition
    then: Node
    otherwise: Node


@dataclass(frozen=True, slots=True)
class Comparison:
    """Two values compared."""

    operator: ComparisonOperator
    left: Node
    right: Node


@dataclass(frozen=True, slots=True)
class TextMatch:
    """A column's text equal — or not — to a quoted text, whatever the case."""

    column: str
    text: str
    equal: bool


@dataclass(frozen=True, slots=True)
class Logical:
    """``AND``, ``OR`` or ``NOT`` of conditions."""

    function: LogicalFunction
    conditions: tuple[Condition, ...]


Node = (
    Number
    | ColumnRef
    | InputRef
    | Negation
    | Binary
    | Call
    | Aggregate
    | Previous
    | RunningSum
    | SheetAggregate
    | Choice
)
Condition = Comparison | TextMatch | Logical


@dataclass(frozen=True, slots=True)
class Formula:
    """A parsed expression and how it reads each name.

    Attributes:
        tree: The expression.
        numbers: The columns it reads as numbers.
        texts: The columns it compares to a quoted text.
        inputs: The workbook inputs it reads.
        compared: The columns a comparison reads bare: a cell there with no value
            would be compared by Excel as a text, so such a column must always
            have one (the normalization's check).
        sheet_columns: The ``(sheet, column)`` pairs a key figure reads whole.
        compared_names: The names a comparison reads bare — an input always has
            a value; a key figure is held to the column's rule.
    """

    tree: Node
    numbers: frozenset[str]
    texts: frozenset[str]
    inputs: frozenset[str]
    compared: frozenset[str]
    sheet_columns: frozenset[tuple[str, str]] = frozenset()
    compared_names: frozenset[str] = frozenset()

    @property
    def columns(self) -> frozenset[str]:
        """Every column it reads, however it reads it."""
        return self.numbers | self.texts


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------
def _key(name: str) -> str:
    """How a name is matched: case and spacing never decide."""
    return " ".join(name.split()).casefold()


class _Names:
    """The names a formula may read, and how it read them."""

    def __init__(
        self,
        columns: Sequence[str],
        inputs: Sequence[str],
        itself: str | None = None,
        sheets: Mapping[str, Sequence[str]] | None = None,
    ) -> None:
        self._columns = {_key(name): name for name in columns}
        self._sheets = {
            _key(sheet): (sheet, {_key(column): column for column in headers})
            for sheet, headers in (sheets or {}).items()
        }
        self.sheet_columns: set[tuple[str, str]] = set()
        self._inputs = {_key(name): name for name in inputs if _key(name) not in self._columns}
        self._itself = _key(itself) if itself is not None else None
        # A column never reads itself: in its own formula, its name is the input of that name.
        self._own_input = next(
            (name for name in inputs if self._itself is not None and _key(name) == self._itself),
            None,
        )
        self.placeholders: dict[str, str] = {}
        self.numbers: set[str] = set()
        self.texts: set[str] = set()
        self.inputs: set[str] = set()
        self.compared: set[str] = set()
        self.compared_names: set[str] = set()

    def substitute(self, text: str) -> str:
        def replace(match: re.Match[str]) -> str:
            placeholder = f"{_PLACEHOLDER_PREFIX}{len(self.placeholders)}"
            self.placeholders[placeholder] = match.group(1)
            return placeholder

        return _REFERENCE.sub(replace, text)

    def _raw(self, placeholder: str) -> str:
        raw = self.placeholders.get(placeholder)
        if raw is None:
            raise FormulaError("unsupported")
        return raw

    def _named(self, placeholder: str) -> str:
        return _key(self._raw(placeholder))

    def _qualified(self, raw: str) -> tuple[str, str] | None:
        """``Sheet/Column`` as a sheet and one of its columns (a sheet title has no slash)."""
        for index, char in enumerate(raw):
            if char != "/":
                continue
            sheet = self._sheets.get(_key(raw[:index]))
            if sheet is not None and (column := sheet[1].get(_key(raw[index + 1 :]))):
                return sheet[0], column
        return None

    def aggregate(self, function: AggregateFunction, placeholder: str) -> Node:
        """A whole column: of this table, or a sheet's when a key figure names one."""
        qualified = self._qualified(self._raw(placeholder))
        if qualified is not None:
            self.sheet_columns.add(qualified)
            return SheetAggregate(function, *qualified)
        reference = self.resolve(placeholder)
        if not isinstance(reference, ColumnRef):
            raise FormulaError("unsupported")
        return Aggregate(function, reference.name)

    def resolve(self, placeholder: str) -> ColumnRef | InputRef:
        """A name read as a number: a column of the table, else an input.

        In a column's own formula, its name is the input of that name, or nothing.
        """
        key = self._named(placeholder)
        if key == self._itself:
            if self._own_input is None:
                raise FormulaError("reads_itself")
            self.inputs.add(self._own_input)
            return InputRef(self._own_input)
        if key in self._columns:
            self.numbers.add(self._columns[key])
            return ColumnRef(self._columns[key])
        if key in self._inputs:
            self.inputs.add(self._inputs[key])
            return InputRef(self._inputs[key])
        # A sheet's column is read whole, never as a row's value.
        if self._qualified(self._raw(placeholder)) is not None:
            raise FormulaError("unsupported")
        raise FormulaError("unknown_reference")

    def resolve_text(self, placeholder: str) -> str:
        """A name read as a text: a column of the table (an input is a number)."""
        key = self._named(placeholder)
        if key == self._itself:
            raise FormulaError("reads_itself" if self._own_input is None else "unsupported")
        if key in self._columns:
            self.texts.add(self._columns[key])
            return self._columns[key]
        raise FormulaError("unsupported" if key in self._inputs else "unknown_reference")


def _spelled(match: re.Match[str]) -> str:
    token = match.group()
    if match.lastgroup == "text":
        # A backslash would be an escape to Python and a character to Excel.
        if "\\" in token:
            raise FormulaError("unsupported")
        return token
    if match.lastgroup == "call":
        return token.upper()
    return _PYTHON_OPERATORS.get(token, token)


def _number(value: object) -> Number:
    # ``bool`` is an ``int``: ``True + 1`` is not arithmetic a sheet means.
    if type(value) not in (int, float):
        raise FormulaError("unsupported")
    number = Decimal(repr(value))
    if not number.is_finite():
        # ``1e999`` reads as infinity: no sheet holds such a number, Excel has no
        # such literal, and no reader could show what it computes.
        raise FormulaError("unsupported")
    return Number(number)


def _only(arguments: list[ast.expr], count: int) -> list[ast.expr]:
    if len(arguments) != count:
        raise FormulaError("unsupported")
    return arguments


def _column_argument(arguments: list[ast.expr], names: _Names) -> str:
    """The one bare column a column function accepts."""
    (node,) = _only(arguments, 1)
    if not isinstance(node, ast.Name):
        raise FormulaError("unsupported")
    reference = names.resolve(node.id)
    if not isinstance(reference, ColumnRef):
        raise FormulaError("unsupported")
    return reference.name


def _round_digits(node: ast.expr) -> Number:
    sign = 1
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        sign, node = -1, node.operand
    if not isinstance(node, ast.Constant) or type(node.value) is not int:
        raise FormulaError("unsupported")
    digits = sign * node.value
    if digits not in _ROUND_DIGITS:
        raise FormulaError("unsupported")
    return Number(Decimal(digits))


_ValueParser = Callable[[list[ast.expr], _Names], Node]


def _aggregate(function: AggregateFunction) -> _ValueParser:
    def parse(arguments: list[ast.expr], names: _Names) -> Node:
        (node,) = _only(arguments, 1)
        if not isinstance(node, ast.Name):
            raise FormulaError("unsupported")
        return names.aggregate(function, node.id)

    return parse


def _extremum(function: ScalarFunction) -> _ValueParser:
    def parse(arguments: list[ast.expr], names: _Names) -> Node:
        if len(arguments) < 2:
            raise FormulaError("unsupported")
        return Call(function, tuple(_node(argument, names) for argument in arguments))

    return parse


def _previous(arguments: list[ast.expr], names: _Names) -> Node:
    return Previous(_column_argument(arguments, names))


def _running_sum(arguments: list[ast.expr], names: _Names) -> Node:
    return RunningSum(_column_argument(arguments, names))


def _round(arguments: list[ast.expr], names: _Names) -> Node:
    value, digits = _only(arguments, 2)
    return Call("ROUND", (_node(value, names), _round_digits(digits)))


def _abs(arguments: list[ast.expr], names: _Names) -> Node:
    (value,) = _only(arguments, 1)
    return Call("ABS", (_node(value, names),))


def _if(arguments: list[ast.expr], names: _Names) -> Node:
    condition, then, otherwise = _only(arguments, 3)
    return Choice(_condition(condition, names), _node(then, names), _node(otherwise, names))


#: Every function that gives a value, by its (capitalized) name.
_VALUE_FUNCTIONS: dict[str, _ValueParser] = {
    "SUM": _aggregate("SUM"),
    "AVERAGE": _aggregate("AVERAGE"),
    "MIN": _extremum("MIN"),
    "MAX": _extremum("MAX"),
    "ROUND": _round,
    "ABS": _abs,
    "PREVIOUS": _previous,
    "RUNNING_SUM": _running_sum,
    "IF": _if,
}


#: Every function the grammar reads, by name: what a writer is told it may use.
FUNCTIONS: frozenset[str] = frozenset({*_VALUE_FUNCTIONS, *_JOINTS, _NOT})


def _function(node: ast.Call) -> str:
    """The name a call names; keywords and computed callees are no Excel."""
    if not isinstance(node.func, ast.Name) or node.keywords:
        raise FormulaError("unsupported")
    return node.func.id


def _text(node: ast.expr) -> str | None:
    """The quoted text a node is, or ``None`` when it is none.

    A quote inside would end Excel's text, a reference inside was the writer's
    braces, a control character is no text a cell compares to.
    """
    if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
        return None
    text = node.value
    if '"' in text or _PLACEHOLDER_PREFIX in text or not text.isprintable():
        raise FormulaError("unsupported")
    return text


def _references(node: Node) -> Iterator[ColumnRef | Previous | InputRef]:
    """The cells a value may BE rather than compute from: a bare reference, or one an
    ``IF`` returns as its value — Excel's IF returns the reference itself."""
    if isinstance(node, ColumnRef | Previous | InputRef):
        yield node
    elif isinstance(node, Choice):
        yield from _references(node.then)
        yield from _references(node.otherwise)


def _compared(node: ast.expr, names: _Names) -> Node:
    """A value a comparison reads; a column or a name it may BE is recorded, a row above
    refused."""
    value = _node(node, names)
    for reference in _references(value):
        if isinstance(reference, Previous):
            # The first row's « row above » is the header: Excel would compare its text.
            raise FormulaError("unsupported")
        if isinstance(reference, InputRef):
            names.compared_names.add(reference.name)
        else:
            names.compared.add(reference.name)
    return value


def _comparison(node: ast.Compare, names: _Names) -> Condition:
    """Two values compared, or a column compared to a quoted text."""
    if len(node.ops) != 1:
        raise FormulaError("unsupported")
    sign = _COMPARISONS.get(type(node.ops[0]))
    if sign is None:
        raise FormulaError("unsupported")
    left, right = node.left, node.comparators[0]
    left_text, right_text = _text(left), _text(right)
    if left_text is None and right_text is None:
        return Comparison(sign, _compared(left, names), _compared(right, names))
    column, text = (right, left_text) if left_text is not None else (left, right_text)
    # A text is equal or not: its order is the reader's collation, not the workbook's.
    if sign not in ("=", "<>") or not isinstance(column, ast.Name) or text is None:
        raise FormulaError("unsupported")
    return TextMatch(names.resolve_text(column.id), text, sign == "=")


def _condition(node: ast.expr, names: _Names) -> Condition:
    if isinstance(node, ast.Compare):
        return _comparison(node, names)
    if isinstance(node, ast.Call):
        function = _function(node)
        joint = _JOINTS.get(function)
        if joint is not None and node.args:
            return Logical(joint, tuple(_condition(item, names) for item in node.args))
        if function == _NOT and len(node.args) == 1:
            return Logical(_NOT, (_condition(node.args[0], names),))
    raise FormulaError("unsupported")


def _node(node: ast.expr, names: _Names) -> Node:
    if isinstance(node, ast.Constant):
        return _number(node.value)
    if isinstance(node, ast.Name):
        return names.resolve(node.id)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub | ast.UAdd):
        operand = _node(node.operand, names)
        return Negation(operand) if isinstance(node.op, ast.USub) else operand
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
        return Binary(_BINARY[type(node.op)], _node(node.left, names), _node(node.right, names))
    if isinstance(node, ast.Call):
        parse = _VALUE_FUNCTIONS.get(_function(node))
        if parse is not None:
            return parse(node.args, names)
    raise FormulaError("unsupported")


def parse_formula(
    text: str,
    *,
    columns: Sequence[str],
    inputs: Sequence[str] = (),
    itself: str | None = None,
    sheets: Mapping[str, Sequence[str]] | None = None,
) -> Formula:
    """Parse a computed column's expression against the names it may read.

    Args:
        text: The writer's expression, names between braces.
        columns: The table's column names (a name matches whatever its case and
            spacing).
        inputs: The workbook's input names; a column of the same name wins.
        itself: The column the formula computes. It never reads itself: there
            its name is the input of that name, or a refusal (``reads_itself``).
        sheets: A key figure's: each sheet's column names, read whole as
            ``SUM({Sheet/Column})`` or ``AVERAGE({Sheet/Column})``.

    Returns:
        The parsed formula.

    Raises:
        FormulaError: When the text is empty, too long, or outside the grammar.
    """
    stripped = text.strip()
    if not stripped:
        raise FormulaError("empty")
    if len(stripped) > DOCUMENT_GENERATION_FORMULA_MAX_CHARS:
        raise FormulaError("too_long")
    if _PLACEHOLDER_PREFIX in stripped:
        raise FormulaError("unsupported")
    names = _Names(columns, inputs, itself, sheets)
    source = names.substitute(stripped)
    if "{" in source or "}" in source:
        raise FormulaError("braces")
    try:
        parsed = ast.parse(_SPELLING.sub(_spelled, source), mode="eval")
    except (SyntaxError, ValueError) as exc:
        raise FormulaError("syntax") from exc
    tree = _node(parsed.body, names)
    return Formula(
        tree=tree,
        numbers=frozenset(names.numbers),
        texts=frozenset(names.texts),
        inputs=frozenset(names.inputs),
        compared=frozenset(names.compared),
        sheet_columns=frozenset(names.sheet_columns),
        compared_names=frozenset(names.compared_names),
    )


# ---------------------------------------------------------------------------
# The value
# ---------------------------------------------------------------------------
class RowValues(Protocol):
    """What one row of a table answers when a formula reads it."""

    def value(self, column: str) -> Decimal | None:
        """This row's cell; ``None`` when it is empty.

        Raises ``FormulaValueError`` when it is a computed cell with no value.
        """

    def text(self, column: str) -> str:
        """This row's cell as the workbook holds its text; empty when it is."""

    def previous(self, column: str) -> Decimal | None:
        """The row above; raises ``FormulaValueError`` on the first row."""

    def aggregate(self, function: AggregateFunction, column: str) -> Decimal:
        """A whole column's ``SUM`` or ``AVERAGE`` (empty cells skipped).

        The same for every row, so a reader computes it once; raises
        ``FormulaValueError`` for the average of a column with no number.
        """

    def running_sum(self, column: str) -> Decimal:
        """The column summed from its first row down to this one, as ``SUM`` sums."""

    def sheet_aggregate(self, function: AggregateFunction, sheet: str, column: str) -> Decimal:
        """A sheet's whole column, for a key figure (empty and valueless cells skipped)."""

    def input(self, name: str) -> Decimal:
        """One of the workbook's inputs."""


def _bare(node: Node, row: RowValues) -> Decimal | None:
    """What ``MIN`` and ``MAX`` read in an argument: a reference to no number is skipped.

    Excel ignores an empty cell or a text a reference holds — the header above
    the first row, a computed cell with no value, a key figure with none (a
    defined name is a reference) — while an expression reads an empty cell as 0
    and fails on a text. An ``IF`` returns the reference it chooses.
    """
    if isinstance(node, Choice):
        return _bare(node.then if _holds(node.condition, row) else node.otherwise, row)
    if not isinstance(node, ColumnRef | Previous | InputRef):
        return _value(node, row)
    try:
        if isinstance(node, ColumnRef):
            return row.value(node.name)
        if isinstance(node, InputRef):
            return row.input(node.name)
        return row.previous(node.column)
    except FormulaValueError:
        return None


def _scalar(call: Call, row: RowValues) -> Decimal:
    if call.function in ("MIN", "MAX"):
        values = [
            value for argument in call.arguments if (value := _bare(argument, row)) is not None
        ]
        if not values:
            return Decimal(0)
        return min(values) if call.function == "MIN" else max(values)
    values = [_value(argument, row) for argument in call.arguments]
    if call.function == "ROUND":
        exponent = Decimal(1).scaleb(-int(values[1]))
        return values[0].quantize(exponent, rounding=ROUND_HALF_UP)
    return abs(values[0])


def _binary(binary: Binary, row: RowValues) -> Decimal:
    left, right = _value(binary.left, row), _value(binary.right, row)
    if binary.operator == "+":
        return left + right
    if binary.operator == "-":
        return left - right
    if binary.operator == "*":
        return left * right
    if binary.operator == "/":
        return left / right
    return left**right


def _significant(value: Decimal) -> Decimal:
    """A number as Excel compares it: on 15 significant digits."""
    with localcontext() as context:
        context.prec = _COMPARISON_DIGITS
        context.rounding = ROUND_HALF_UP
        return +value


def _holds(condition: Condition, row: RowValues) -> bool:
    if isinstance(condition, Comparison):
        left, right = _value(condition.left, row), _value(condition.right, row)
        return _ORDERS[condition.operator](_significant(left), _significant(right))
    if isinstance(condition, TextMatch):
        same = row.text(condition.column).lower() == condition.text.lower()
        return same == condition.equal
    # Every condition is read, as Excel reads them: one with no value spreads.
    held = [_holds(item, row) for item in condition.conditions]
    if condition.function == "AND":
        return all(held)
    if condition.function == "OR":
        return any(held)
    return not held[0]


def _value(node: Node, row: RowValues) -> Decimal:
    if isinstance(node, Number):
        return node.value
    if isinstance(node, ColumnRef):
        return row.value(node.name) or Decimal(0)
    if isinstance(node, InputRef):
        return row.input(node.name)
    if isinstance(node, Negation):
        return -_value(node.operand, row)
    if isinstance(node, Binary):
        return _binary(node, row)
    if isinstance(node, Call):
        return _scalar(node, row)
    if isinstance(node, Aggregate):
        return row.aggregate(node.function, node.column)
    if isinstance(node, RunningSum):
        return row.running_sum(node.column)
    if isinstance(node, SheetAggregate):
        return row.sheet_aggregate(node.function, node.sheet, node.column)
    if isinstance(node, Choice):
        # Only the value chosen is computed, as Excel's IF computes it.
        return _value(node.then if _holds(node.condition, row) else node.otherwise, row)
    return row.previous(node.column) or Decimal(0)


def evaluate(formula: Formula, row: RowValues) -> Decimal:
    """The value of a formula on one row, as Excel computes it.

    Args:
        formula: The parsed formula.
        row: The row's cells, its neighbours' and the workbook's inputs.

    Returns:
        The exact value (``-0`` reads ``0``).

    Raises:
        FormulaValueError: When the row has no value: a division by zero, an
            impossible power, an overflow, no row above, a cell read that has none.
    """
    with localcontext() as context:
        context.prec = _PRECISION
        context.Emax, context.Emin = _EXPONENT_LIMIT, -_EXPONENT_LIMIT
        for trap in (DivisionByZero, InvalidOperation, Overflow):
            context.traps[trap] = True
        try:
            result = _value(formula.tree, row)
        except (DivisionByZero, InvalidOperation, Overflow) as exc:
            raise FormulaValueError("no value") from exc
    return result if result != 0 else Decimal(0)


# ---------------------------------------------------------------------------
# The Excel text
# ---------------------------------------------------------------------------
class ExcelCells(Protocol):
    """Where each name a formula reads lives in the sheet."""

    def cell(self, column: str) -> str:
        """This row's cell in the column, e.g. ``C7``."""

    def previous_cell(self, column: str) -> str:
        """The row above's cell, e.g. ``C6``."""

    def column_range(self, column: str) -> str:
        """The column's data cells, e.g. ``C$2:C$11``."""

    def running_range(self, column: str) -> str:
        """The column's first data cell down to this row's, e.g. ``C$2:C7``."""

    def sheet_range(self, sheet: str, column: str) -> str:
        """A sheet's data cells in a column, e.g. ``'Budget'!$C$2:$C$13``."""

    def input_name(self, name: str) -> str:
        """The defined name of an input."""


def _number_text(value: Decimal) -> str:
    """A literal Excel reads: plain notation, no trailing zeros."""
    text = format(value.normalize(), "f")
    return text if text != "-0" else "0"


def _operand(node: Node, cells: ExcelCells) -> str:
    text = _excel(node, cells)
    return f"({text})" if isinstance(node, Binary | Negation) else text


def _condition_excel(condition: Condition, cells: ExcelCells) -> str:
    if isinstance(condition, Comparison):
        left, right = _operand(condition.left, cells), _operand(condition.right, cells)
        return f"{left}{condition.operator}{right}"
    if isinstance(condition, TextMatch):
        sign = "=" if condition.equal else "<>"
        return f'{cells.cell(condition.column)}{sign}"{condition.text}"'
    items = ",".join(_condition_excel(item, cells) for item in condition.conditions)
    return f"{condition.function}({items})"


def _excel(node: Node, cells: ExcelCells) -> str:
    if isinstance(node, Number):
        return _number_text(node.value)
    if isinstance(node, ColumnRef):
        return cells.cell(node.name)
    if isinstance(node, InputRef):
        return cells.input_name(node.name)
    if isinstance(node, Negation):
        return f"-{_operand(node.operand, cells)}"
    if isinstance(node, Binary):
        return f"{_operand(node.left, cells)}{node.operator}{_operand(node.right, cells)}"
    if isinstance(node, Call):
        return (
            f"{node.function}({','.join(_excel(argument, cells) for argument in node.arguments)})"
        )
    if isinstance(node, Aggregate):
        return f"{node.function}({cells.column_range(node.column)})"
    if isinstance(node, RunningSum):
        return f"SUM({cells.running_range(node.column)})"
    if isinstance(node, SheetAggregate):
        return f"{node.function}({cells.sheet_range(node.sheet, node.column)})"
    if isinstance(node, Choice):
        condition = _condition_excel(node.condition, cells)
        return f"IF({condition},{_excel(node.then, cells)},{_excel(node.otherwise, cells)})"
    return cells.previous_cell(node.column)


def to_excel(formula: Formula, cells: ExcelCells) -> str:
    """The formula as Excel writes it, without the leading ``=``.

    Args:
        formula: The parsed formula.
        cells: Where its names live in the sheet.

    Returns:
        The Excel expression.
    """
    return _excel(formula.tree, cells)


# ---------------------------------------------------------------------------
# Where a row may have no value
# ---------------------------------------------------------------------------
def _children(item: Node | Condition) -> tuple[Node | Condition, ...]:
    if isinstance(item, Negation):
        return (item.operand,)
    if isinstance(item, Binary | Comparison):
        return (item.left, item.right)
    if isinstance(item, Call):
        return item.arguments
    if isinstance(item, Choice):
        return (item.condition, item.then, item.otherwise)
    if isinstance(item, Logical):
        return item.conditions
    return ()


def _walk(item: Node | Condition) -> Iterator[Node | Condition]:
    yield item
    for child in _children(item):
        yield from _walk(child)


def may_error(formula: Formula) -> bool:
    """Whether some row can have no value by its own operations.

    Args:
        formula: The parsed formula.

    Returns:
        True when it divides, raises to a power, reads the row above or averages.
    """
    return any(
        (isinstance(node, Binary) and node.operator in ("/", "^"))
        or isinstance(node, Previous)
        or (isinstance(node, Aggregate | SheetAggregate) and node.function == "AVERAGE")
        for node in _walk(formula.tree)
    )


def _spreading(item: Node | Condition) -> set[ColumnRef | InputRef]:
    """The references whose cell, when it has no value, leaves this expression without one.

    An aggregate and a running sum skip it, and so do ``MIN`` and ``MAX`` when
    the reference is bare — a column's cell, the row above, a name's; a column
    compared to a text is never computed.
    """
    if isinstance(item, ColumnRef | InputRef):
        return {item}
    if isinstance(item, Previous):
        return {ColumnRef(item.column)}
    children = _children(item)
    if isinstance(item, Call) and item.function in ("MIN", "MAX"):
        children = tuple(
            child for child in children if not isinstance(child, ColumnRef | Previous | InputRef)
        )
    spreading: set[ColumnRef | InputRef] = set()
    for child in children:
        spreading |= _spreading(child)
    return spreading


def spreading_names(formula: Formula) -> frozenset[str]:
    """The names whose missing value leaves the formula without one.

    An input always has a value; a key figure may have none (``workbook_figures``).

    Args:
        formula: The parsed formula.

    Returns:
        The names read, ``MIN`` and ``MAX`` skipping a bare one as Excel does.
    """
    return frozenset(item.name for item in _spreading(formula.tree) if isinstance(item, InputRef))


def blank_columns(formulas: Mapping[str, Formula]) -> frozenset[str]:
    """The computed columns where some row may have no value.

    A computed cell with no value holds an empty text in the workbook, and
    arithmetic on a text fails: whatever reads such a column may have no value
    either — the workbook wraps it in ``IFERROR`` too, and a chart reads it
    through a gap-safe copy.

    Args:
        formulas: Each computed column's formula, by its header.

    Returns:
        The headers of the columns that may have a row with no value.
    """
    blank = {name for name, formula in formulas.items() if may_error(formula)}
    reads = {
        name: {item.name for item in _spreading(formula.tree) if isinstance(item, ColumnRef)}
        for name, formula in formulas.items()
    }
    while spread := {name for name, read in reads.items() if name not in blank and read & blank}:
        blank |= spread
    return frozenset(blank)
