"""How a typed value reads in the reader's language (ADR-274 amendment).

A workbook stores NUMBERS and shows them through a format code: the reader's
own system draws the separators, so ``excel_format`` writes only what a format
code says — grouping, decimals, the currency on the reader's side, red for a
negative amount. Word, PDF, slides and Markdown show TEXT, so ``display`` writes
the reader's conventions itself: the decimal mark and the digit grouping of
their language, the currency on its side, the percent sign spaced as their
typography spaces it, the date in their order.

Rounding is half away from zero, as the workbook rounds: a value shown in a
report and the same value recomputed by Excel never disagree on the last digit.
A year and a code are never grouped — that is what declaring a column's kind
buys over guessing it from its cells.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Context, Decimal, DefaultContext
from typing import Final

NARROW_NBSP: Final = " "
NBSP: Final = " "
#: Kinds whose values are numbers, aligned right wherever they are drawn.
NUMERIC_KINDS: Final = frozenset({"amount", "quantity", "percent", "year"})


@dataclass(frozen=True, slots=True)
class Conventions:
    """How one language writes a number and a date.

    Attributes:
        decimal: The decimal mark.
        group: The digit-group separator.
        currency_first: Whether the currency precedes the number.
        percent: What separates a number from its percent sign.
        date: The ``strftime`` pattern of a date.
        excel_date: The same order as an Excel format code.
    """

    decimal: str
    group: str
    currency_first: bool
    percent: str
    date: str
    excel_date: str


CONVENTIONS: dict[str, Conventions] = {
    "fr": Conventions(",", NARROW_NBSP, False, NARROW_NBSP, "%d/%m/%Y", "dd/mm/yyyy"),
    "en": Conventions(".", ",", True, "", "%Y-%m-%d", "yyyy-mm-dd"),
    "es": Conventions(",", ".", False, NBSP, "%d/%m/%Y", "dd/mm/yyyy"),
    "de": Conventions(",", ".", False, NBSP, "%d.%m.%Y", "dd.mm.yyyy"),
    "it": Conventions(",", ".", False, "", "%d/%m/%Y", "dd/mm/yyyy"),
    "zh-CN": Conventions(".", ",", True, "", "%Y-%m-%d", "yyyy-mm-dd"),
}

#: The symbol of a currency a writer names by its ISO code; any other code
#: reads as itself.
CURRENCY_SYMBOLS: dict[str, str] = {
    "EUR": "€",
    "USD": "$",
    "GBP": "£",
    "JPY": "¥",
    "CNY": "¥",
    "INR": "₹",
    "KRW": "₩",
    "RUB": "₽",
    "BRL": "R$",
}


def conventions(language: str) -> Conventions:
    """The conventions of a backend-canonical language (English when unknown)."""
    return CONVENTIONS.get(language, CONVENTIONS["en"])


def _symbol(unit: str) -> str:
    cleaned = unit.strip().replace('"', "")
    return CURRENCY_SYMBOLS.get(cleaned.upper(), cleaned)


def _grouped(digits: str, separator: str) -> str:
    head = len(digits) % 3 or 3
    groups = [digits[:head], *(digits[index : index + 3] for index in range(head, len(digits), 3))]
    return separator.join(groups)


def rounded(value: Decimal, decimals: int) -> Decimal:
    """``value`` at ``decimals`` places, half away from zero, whatever its size.

    ``quantize`` refuses a result longer than its context's precision — 28
    digits by default, which ``(1 + 6) ^ 40`` exceeds: the context is as wide as
    the number, so a value a formula computed is always one a reader can read.

    Args:
        value: Any finite number.
        decimals: Digits kept after the decimal mark.

    Returns:
        The rounded number, as the workbook rounds it.
    """
    # Its whole digits, its decimals, and the one a carry may add (9.99 -> 10.0).
    digits = max(value.adjusted(), 0) + decimals + 2
    return value.quantize(
        Decimal(1).scaleb(-decimals),
        rounding=ROUND_HALF_UP,
        context=Context(prec=max(digits, DefaultContext.prec)),
    )


def _number(value: Decimal, decimals: int, rules: Conventions, *, grouped: bool) -> str:
    """``|value|`` with the language's marks; the sign is the caller's."""
    # ``copy_abs``, never ``abs``: the latter rounds to the context's 28 digits.
    whole, _, fraction = f"{rounded(value.copy_abs(), decimals):f}".partition(".")
    body = _grouped(whole, rules.group) if grouped else whole
    return f"{body}{rules.decimal}{fraction}" if fraction else body


def _sign(value: Decimal, decimals: int) -> str:
    """A minus only for a value that stays negative once rounded: never « -0 ».

    Rounded as the number it stands before is: -0.005 reads « -0.01 », as in the
    workbook — a sign decided by another rounding would write it positive.
    """
    return "-" if value < 0 and rounded(value.copy_abs(), decimals) != 0 else ""


def _amount(value: Decimal, unit: str, decimals: int, rules: Conventions) -> str:
    sign = _sign(value, decimals)
    number = _number(value, decimals, rules, grouped=True)
    symbol = _symbol(unit)
    if not symbol:
        return f"{sign}{number}"
    if rules.currency_first:
        spacing = NBSP if symbol[-1].isalpha() else ""
        return f"{sign}{symbol}{spacing}{number}"
    return f"{sign}{number}{NBSP}{symbol}"


def _signed(value: Decimal, decimals: int, rules: Conventions, *, grouped: bool) -> str:
    return f"{_sign(value, decimals)}{_number(value, decimals, rules, grouped=grouped)}"


def display(
    value: Decimal | date | datetime | str | None,
    kind: str,
    unit: str,
    decimals: int,
    language: str,
) -> str:
    """One value as text, in the reader's conventions.

    Args:
        value: The typed value; a string is shown as it is.
        kind: The column's kind (``amount``, ``quantity``, ``percent``, ``date``,
            ``datetime``, ``year``, ``code``, ``text`` or empty).
        unit: The currency code or unit symbol, possibly empty.
        decimals: Digits after the decimal mark (percent: of the percentage).
        language: The reader's backend-canonical language.

    Returns:
        The text, empty for no value.
    """
    if value is None:
        return ""
    rules = conventions(language)
    if isinstance(value, datetime):
        return value.strftime(f"{rules.date} %H:%M")
    if isinstance(value, date):
        return value.strftime(rules.date)
    if isinstance(value, str):
        return value
    if kind == "amount":
        return _amount(value, unit, decimals, rules)
    if kind == "percent":
        return f"{_signed(value * 100, decimals, rules, grouped=True)}{rules.percent}%"
    if kind == "year":
        return _signed(value, 0, rules, grouped=False)
    text = _signed(value, decimals, rules, grouped=True)
    symbol = _symbol(unit)
    return f"{text}{NBSP}{symbol}" if kind == "quantity" and symbol else text


def _digits(decimals: int) -> str:
    return f"#,##0.{'0' * decimals}" if decimals > 0 else "#,##0"


def excel_format(kind: str, unit: str, decimals: int, language: str) -> str:
    """The Excel number format of a declared column kind.

    Args:
        kind: The column's kind.
        unit: The currency code or unit symbol, possibly empty.
        decimals: Digits after the decimal mark.
        language: The reader's backend-canonical language (currency side, date order).

    Returns:
        A format code; ``@`` keeps text and codes as text.
    """
    rules = conventions(language)
    symbol = _symbol(unit)
    if kind == "amount":
        if not symbol:
            core = _digits(decimals)
        elif rules.currency_first:
            spacing = NBSP if symbol[-1].isalpha() else ""
            core = f'"{symbol}{spacing}"{_digits(decimals)}'
        else:
            core = f'{_digits(decimals)}"{NBSP}{symbol}"'
        return f"{core};[Red]-{core}"
    if kind == "quantity":
        return f'{_digits(decimals)}"{NBSP}{symbol}"' if symbol else _digits(decimals)
    if kind == "percent":
        return f"0.{'0' * decimals}%" if decimals > 0 else "0%"
    if kind == "date":
        return rules.excel_date
    if kind == "datetime":
        return f"{rules.excel_date} hh:mm"
    if kind == "year":
        return "0"
    return "@"
