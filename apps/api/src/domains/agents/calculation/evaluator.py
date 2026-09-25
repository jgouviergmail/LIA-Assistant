"""An arithmetic expression, evaluated EXACTLY and never executed (ADR-318).

A model does arithmetic badly and says nothing when it is wrong: a percentage
of an amount, a split bill, a unit price come back plausible and false. This
module is the calculator's engine and holds four rules:

- **Nothing is executed.** The expression is parsed by ``ast`` and walked node
  by node. A node that is not arithmetic — a name that is not a published
  constant, a call to anything but a published function, an attribute, a
  comparison, a string — is refused before any value is computed.
- **Decimal, not binary floating point.** ``0.1 + 0.2`` is ``0.3``. Every
  operation runs in one ``decimal`` context at the published precision, whose
  ``Inexact`` flag says whether ANY step rounded; the result carries it, so
  « exact » is a fact rather than a hope. A power too large to hold overflows
  in a fraction of a millisecond (measured: ``9 ** 9 ** 9`` in 0.26 ms) instead
  of computing a number with a billion digits.
- **The walk is iterative.** The published length admits a chain of a thousand
  operations — a tree a thousand levels deep — and a recursive walk would meet
  Python's recursion limit inside a tool call that already sits deep in the
  stack.
- **What is not a number is refused, never displayed.** ``0 ** -1`` gives an
  infinity and ``ln(0)`` a negative one without raising (measured); both are
  refusals here, never a result.

What cannot mean anything else is repaired before parsing (``^`` is a power,
``×`` a product). What could mean two things is refused with a reason the model
can act on: a decimal comma, a percent sign.
"""

from __future__ import annotations

import ast
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import (
    ROUND_CEILING,
    ROUND_FLOOR,
    ROUND_HALF_EVEN,
    ROUND_HALF_UP,
    Context,
    Decimal,
    DivisionByZero,
    DivisionImpossible,
    Inexact,
    InvalidOperation,
    Overflow,
    localcontext,
)
from typing import Final, Literal, NoReturn

__all__ = [
    "CONSTANTS",
    "FUNCTIONS",
    "Calculation",
    "CalculationError",
    "CalculationFailure",
    "evaluate",
]

CalculationFailure = Literal[
    "too_long", "syntax", "unsupported", "domain", "division_by_zero", "overflow"
]

#: Digits carried beyond the published precision while a transcendental function
#: is computed, then rounded away: ``log(8, 2)`` must read 3, not 2.999…9.
_GUARD_DIGITS: Final = 5

#: The exponent bound of both contexts. Far beyond any quantity a person asks
#: about, and what turns an absurd power into an immediate overflow.
_EXPONENT_LIMIT: Final = 999_999

#: π to more digits than the widest precision the settings admit plus the guard.
_PI: Final = Decimal("3.1415926535897932384626433832795028841971693993751058209749445923")

#: Typographic spellings of an operator that can mean nothing else.
_REPAIRS: Final[tuple[tuple[str, str], ...]] = (
    ("^", "**"),
    ("×", "*"),
    ("·", "*"),
    ("÷", "/"),
    ("−", "-"),
)

#: Where a value leaves plain notation for scientific notation (adjusted exponent).
_PLAIN_MIN_EXPONENT: Final = -7

_GRAMMAR: Final = (
    "Write numbers with a dot as the decimal separator and no thousands separator, "
    "the operators + - * / // % ** and parentheses; % is the remainder, so write a "
    "percentage as x * p / 100."
)


class CalculationError(ValueError):
    """An expression the calculator refuses, with a reason the model can act on.

    Attributes:
        reason: A bounded code, never the expression itself.
    """

    def __init__(self, reason: CalculationFailure, message: str) -> None:
        super().__init__(message)
        self.reason: CalculationFailure = reason


@dataclass(frozen=True)
class Calculation:
    """One evaluated expression.

    Attributes:
        expression: The expression as it was read, after the typographic repairs.
        value: The result, at the published precision.
        exact: False when any step had to round — a division that does not
            terminate, an irrational function, a result wider than the precision.
        text: The result as it should be read: plain notation for ordinary
            magnitudes, scientific notation for the very large and very small.
    """

    expression: str
    value: Decimal
    exact: bool
    text: str


@dataclass
class _Walk:
    """The contexts of one evaluation and what they cannot record themselves."""

    context: Context
    extended: Context
    approximate: bool = False


_Function = Callable[[Sequence[Decimal], _Walk], Decimal]


@dataclass(frozen=True)
class _Signature:
    """How many arguments a function takes, and what it computes."""

    minimum: int
    maximum: int | None
    apply: _Function


def _context(precision: int) -> Context:
    return Context(
        prec=precision,
        rounding=ROUND_HALF_EVEN,
        Emin=-_EXPONENT_LIMIT,
        Emax=_EXPONENT_LIMIT,
        traps=[InvalidOperation, DivisionByZero, Overflow],
    )


def _refuse_domain(detail: str) -> CalculationError:
    return CalculationError("domain", f"The result is undefined: {detail}.")


def _transcendental(walk: _Walk, compute: Callable[[Context], Decimal]) -> Decimal:
    """Compute with guard digits, then round once to the published precision."""
    return walk.context.plus(compute(walk.extended))


def _positive(value: Decimal, function: str) -> Decimal:
    if value <= 0:
        raise _refuse_domain(f"{function}() needs a positive argument")
    return value


def _round(args: Sequence[Decimal], walk: _Walk) -> Decimal:
    value = args[0]
    places = args[1] if len(args) > 1 else Decimal(0)
    if places != places.to_integral_value():
        raise CalculationError("unsupported", "round(x, n) takes a whole number of decimals n.")
    limit = walk.context.prec
    if abs(places) > limit:
        raise _refuse_domain(f"round(x, n) keeps between -{limit} and {limit} decimals")
    quantum = Decimal(1).scaleb(-int(places), walk.context)
    try:
        return value.quantize(quantum, rounding=ROUND_HALF_UP, context=walk.context)
    except InvalidOperation as error:
        raise _refuse_domain("round(x, n) cannot keep that many decimals") from error


def _log(args: Sequence[Decimal], walk: _Walk) -> Decimal:
    value = _positive(args[0], "log")
    if len(args) == 1:
        return _transcendental(walk, lambda context: context.ln(value))
    base = args[1]
    if base <= 0 or base == 1:
        raise _refuse_domain("log(x, base) needs a positive base other than 1")
    return _transcendental(
        walk, lambda context: context.divide(context.ln(value), context.ln(base))
    )


def _float_function(function: Callable[[float], float], name: str) -> _Function:
    """A function decimal does not offer, computed in binary floating point.

    The result is therefore APPROXIMATE whatever it looks like: ``sin(pi / 2)``
    reads 1 and is flagged, because it is only as exact as a float.
    """

    def apply(args: Sequence[Decimal], walk: _Walk) -> Decimal:
        walk.approximate = True
        try:
            result = function(float(args[0]))
        except (ValueError, OverflowError) as error:
            raise _refuse_domain(f"{name}() is not defined for this value") from error
        return walk.context.plus(Decimal(repr(result)))

    return apply


_FUNCTION_TABLE: Final[dict[str, _Signature]] = {
    "abs": _Signature(1, 1, lambda args, walk: walk.context.abs(args[0])),
    "round": _Signature(1, 2, _round),
    "floor": _Signature(
        1,
        1,
        lambda args, walk: args[0].to_integral_value(rounding=ROUND_FLOOR, context=walk.context),
    ),
    "ceil": _Signature(
        1,
        1,
        lambda args, walk: args[0].to_integral_value(rounding=ROUND_CEILING, context=walk.context),
    ),
    "min": _Signature(1, None, lambda args, _walk: min(args)),
    "max": _Signature(1, None, lambda args, _walk: max(args)),
    "sqrt": _Signature(
        1, 1, lambda args, walk: _transcendental(walk, lambda context: context.sqrt(args[0]))
    ),
    "exp": _Signature(
        1, 1, lambda args, walk: _transcendental(walk, lambda context: context.exp(args[0]))
    ),
    "ln": _Signature(
        1,
        1,
        lambda args, walk: _transcendental(
            walk, lambda context: context.ln(_positive(args[0], "ln"))
        ),
    ),
    "log": _Signature(1, 2, _log),
    "log10": _Signature(
        1,
        1,
        lambda args, walk: _transcendental(
            walk, lambda context: context.log10(_positive(args[0], "log10"))
        ),
    ),
    "sin": _Signature(1, 1, _float_function(math.sin, "sin")),
    "cos": _Signature(1, 1, _float_function(math.cos, "cos")),
    "tan": _Signature(1, 1, _float_function(math.tan, "tan")),
    "asin": _Signature(1, 1, _float_function(math.asin, "asin")),
    "acos": _Signature(1, 1, _float_function(math.acos, "acos")),
    "atan": _Signature(1, 1, _float_function(math.atan, "atan")),
    "radians": _Signature(
        1,
        1,
        lambda args, walk: _transcendental(
            walk, lambda context: context.divide(context.multiply(args[0], _PI), Decimal(180))
        ),
    ),
    "degrees": _Signature(
        1,
        1,
        lambda args, walk: _transcendental(
            walk, lambda context: context.divide(context.multiply(args[0], Decimal(180)), _PI)
        ),
    ),
}

_CONSTANT_TABLE: Final[dict[str, Callable[[_Walk], Decimal]]] = {
    "pi": lambda walk: walk.context.plus(_PI),
    "e": lambda walk: walk.context.plus(walk.extended.exp(Decimal(1))),
}

#: The functions the calculator evaluates, published by the manifest.
FUNCTIONS: Final[tuple[str, ...]] = tuple(_FUNCTION_TABLE)
#: The constants the calculator knows, published by the manifest.
CONSTANTS: Final[tuple[str, ...]] = tuple(_CONSTANT_TABLE)

_VOCABULARY: Final = (
    f"Functions: {', '.join(FUNCTIONS)}; constants: {', '.join(CONSTANTS)}; "
    "operators: + - * / // % **."
)


def _nonzero(divisor: Decimal) -> Decimal:
    if divisor.is_zero():
        raise CalculationError("division_by_zero", "Division by zero.")
    return divisor


def _floor_divide(left: Decimal, right: Decimal, context: Context) -> Decimal:
    """Python's floor division: decimal truncates toward zero, Python floors."""
    quotient = context.divide_int(left, _nonzero(right))
    remainder = context.remainder(left, right)
    if not remainder.is_zero() and (remainder < 0) != (right < 0):
        quotient = context.subtract(quotient, Decimal(1))
    return quotient


def _modulo(left: Decimal, right: Decimal, context: Context) -> Decimal:
    """Python's modulo: the remainder takes the sign of the divisor."""
    remainder = context.remainder(left, _nonzero(right))
    if not remainder.is_zero() and (remainder < 0) != (right < 0):
        remainder = context.add(remainder, right)
    return remainder


def _power(left: Decimal, right: Decimal, context: Context) -> Decimal:
    if left.is_zero():
        if right.is_zero():
            # Decimal refuses 0 ** 0; every calculator a person uses answers 1.
            return Decimal(1)
        if right < 0:
            raise CalculationError("division_by_zero", "Division by zero (0 to a negative power).")
    return context.power(left, right)


_BINARY: Final[dict[type[ast.operator], Callable[[Decimal, Decimal, Context], Decimal]]] = {
    ast.Add: lambda left, right, context: context.add(left, right),
    ast.Sub: lambda left, right, context: context.subtract(left, right),
    ast.Mult: lambda left, right, context: context.multiply(left, right),
    ast.Div: lambda left, right, context: context.divide(left, _nonzero(right)),
    ast.FloorDiv: _floor_divide,
    ast.Mod: _modulo,
    ast.Pow: _power,
}

_UNARY: Final[dict[type[ast.unaryop], Callable[[Decimal, Context], Decimal]]] = {
    ast.UAdd: lambda operand, context: context.plus(operand),
    ast.USub: lambda operand, context: context.minus(operand),
}


def _unsupported(what: str) -> CalculationError:
    return CalculationError("unsupported", f"{what} is not supported. {_VOCABULARY}")


def _arity(signature: _Signature) -> str:
    """How many arguments a function takes, in words."""
    low, high = signature.minimum, signature.maximum
    if high is None:
        return f"at least {low}"
    if high == low:
        return str(low)
    return f"{low} or {high}" if high == low + 1 else f"{low} to {high}"


def _call_operands(node: ast.Call) -> list[ast.expr]:
    """Validate a call and return its arguments, in order."""
    name = node.func.id if isinstance(node.func, ast.Name) else None
    signature = _FUNCTION_TABLE.get(name) if name is not None else None
    if name is None or signature is None:
        return _raise(_unsupported("This function"))
    if node.keywords or any(isinstance(arg, ast.Starred) for arg in node.args):
        return _raise(_unsupported(f"A keyword or unpacked argument to {name}()"))
    count = len(node.args)
    maximum = signature.maximum
    if count < signature.minimum or (maximum is not None and count > maximum):
        return _raise(
            _unsupported(f"{name}() with {count} argument(s) — it takes {_arity(signature)} —")
        )
    return list(node.args)


def _raise(error: CalculationError) -> NoReturn:
    raise error


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _operands(node: ast.AST) -> list[ast.expr]:
    """Validate one node and return the operands it is computed from.

    Args:
        node: A node of the parsed expression.

    Returns:
        Its operands, in evaluation order (empty for a leaf).

    Raises:
        CalculationError: When the node is not arithmetic.
    """
    if isinstance(node, ast.Constant):
        return [] if _is_number(node.value) else _raise(_unsupported("A non-numeric value"))
    if isinstance(node, ast.Name):
        return [] if node.id in _CONSTANT_TABLE else _raise(_unsupported("This name"))
    if isinstance(node, ast.BinOp):
        return (
            [node.left, node.right]
            if type(node.op) in _BINARY
            else _raise(_unsupported("This operator"))
        )
    if isinstance(node, ast.UnaryOp):
        return [node.operand] if type(node.op) in _UNARY else _raise(_unsupported("This operator"))
    if isinstance(node, ast.Call):
        return _call_operands(node)
    if isinstance(node, ast.Tuple):
        return _raise(
            CalculationError(
                "unsupported",
                "A comma separates function arguments only: use a dot as the decimal "
                "separator (1234.56), with no thousands separator.",
            )
        )
    return _raise(_unsupported(f"This construct ({type(node).__name__})"))


def _number(node: ast.Constant, source: str, context: Context) -> Decimal:
    """A literal, read from its SOURCE text so that ``0.1`` stays one tenth."""
    if isinstance(node.value, int):
        return context.plus(Decimal(node.value))
    segment = ast.get_source_segment(source, node) or repr(node.value)
    return context.plus(Decimal(segment.replace("_", "")))


def _reduce(node: ast.AST, values: list[Decimal], source: str, walk: _Walk) -> None:
    """Replace a node's computed operands on the stack by the node's value."""
    context = walk.context
    if isinstance(node, ast.Constant):
        values.append(_number(node, source, context))
    elif isinstance(node, ast.Name):
        values.append(_CONSTANT_TABLE[node.id](walk))
    elif isinstance(node, ast.BinOp):
        right, left = values.pop(), values.pop()
        values.append(_BINARY[type(node.op)](left, right, context))
    elif isinstance(node, ast.UnaryOp):
        values.append(_UNARY[type(node.op)](values.pop(), context))
    elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        count = len(node.args)
        arguments = values[len(values) - count :]
        del values[len(values) - count :]
        values.append(_FUNCTION_TABLE[node.func.id].apply(arguments, walk))


def _walk(root: ast.expr, source: str, walk: _Walk) -> Decimal:
    """Evaluate a validated tree in post-order, with an explicit stack."""
    values: list[Decimal] = []
    pending: list[tuple[ast.AST, bool]] = [(root, False)]
    while pending:
        node, ready = pending.pop()
        if ready:
            _reduce(node, values, source, walk)
            continue
        operands = _operands(node)
        pending.append((node, True))
        pending.extend((operand, False) for operand in reversed(operands))
    return values[-1]


def _display(value: Decimal, context: Context) -> str:
    """The result as a person reads it."""
    if value.is_zero():
        return "0"
    normalized = value.normalize(context)
    exponent = normalized.adjusted()
    if _PLAIN_MIN_EXPONENT <= exponent < context.prec:
        return format(normalized, "f")
    return format(normalized, "e")


def _overflow() -> CalculationError:
    return CalculationError(
        "overflow",
        f"The result has too many digits to compute (beyond 1e+{_EXPONENT_LIMIT}, or an "
        "integer quotient wider than the precision).",
    )


def _is_division_impossible(error: InvalidOperation) -> bool:
    """Whether a trapped operation was an integer quotient wider than the precision.

    Read structurally, never from the message: the C implementation raises
    ``InvalidOperation`` itself and lists the precise condition in its first
    argument (measured on 3.14.7), the pure-Python one raises the subclass.
    """
    if isinstance(error, DivisionImpossible):
        return True
    first = error.args[0] if error.args else None
    return isinstance(first, list) and DivisionImpossible in first


def _repaired(expression: str) -> str:
    source = expression.strip()
    for spelling, operator in _REPAIRS:
        source = source.replace(spelling, operator)
    return source


def _parse(source: str) -> ast.Expression:
    if not source:
        raise CalculationError("syntax", f"The expression is empty. {_GRAMMAR}")
    try:
        return ast.parse(source, mode="eval")
    except (SyntaxError, ValueError, RecursionError, MemoryError) as error:
        detail = getattr(error, "msg", None) or type(error).__name__
        raise CalculationError(
            "syntax", f"The expression is not valid arithmetic ({detail}). {_GRAMMAR}"
        ) from error


def evaluate(expression: str, *, max_chars: int, precision: int) -> Calculation:
    """Evaluate an arithmetic expression exactly.

    Args:
        expression: The expression, as the model wrote it.
        max_chars: The published length bound.
        precision: Significant digits kept by every operation.

    Returns:
        The calculation, flagged approximate when any step rounded.

    Raises:
        CalculationError: When the expression is too long, not arithmetic, or
            has no finite value.
    """
    length = len(expression.strip())
    if length > max_chars:
        raise CalculationError(
            "too_long",
            f"The expression has {length} characters; the calculator accepts at most "
            f"{max_chars}. Split the computation into several calls.",
        )
    source = _repaired(expression)
    tree = _parse(source)
    with localcontext(_context(precision)) as active:
        walk = _Walk(context=active, extended=_context(precision + _GUARD_DIGITS))
        try:
            value = _walk(tree.body, source, walk)
        except DivisionByZero as error:
            raise CalculationError("division_by_zero", "Division by zero.") from error
        except Overflow as error:
            raise _overflow() from error
        except InvalidOperation as error:
            if _is_division_impossible(error):
                raise _overflow() from error
            raise _refuse_domain("no real number satisfies this expression") from error
        if not value.is_finite():
            raise _refuse_domain("no finite number satisfies this expression")
        exact = not (walk.approximate or active.flags[Inexact] or walk.extended.flags[Inexact])
        return Calculation(
            expression=source, value=value, exact=exact, text=_display(value, active)
        )
