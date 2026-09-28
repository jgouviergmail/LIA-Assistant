"""The numbers a text states, and how two texts' numbers compare.

A line may say a number only when a fact it cites states it (the verifier's
rule), and an analyst's point only when the article does. The two texts are
often in two languages, so a number compares by its DIGITS whatever the
separators — « 3,9 », « 3.9 » and « 3 900 » across conventions — and, when a
multiplier follows it, by its VALUE as well: « 60万 » (Chinese counts in ten
thousands) is the « 600 000 » of the French fact it came from, « 39亿 » the
« 3.9 billion » of an English one. Measured 2026-09-26: one model family wrote
large Chinese figures that way, every such line was dropped and the bulletin
refused. The bare digits stay a reading of their own, so nothing that compared
before compares differently now.

What this cannot see, and says so: a number written out in words — Chinese
characters included (« 二十万 »), which are not parsed: « 一 » is also a letter
of everyday words (一些, 一起), so reading it as a figure would drop sound lines
— and a multiplier abbreviated (« 3,9 Mrd. » compares by its digits alone).
The model verifier reads those.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Final

#: A number: digits, possibly grouped by a separator. A space only groups when
#: exactly three digits follow (« 3 900 »), so « between 18 and 24 » stays two.
_NUMBER_RE: Final[re.Pattern[str]] = re.compile(
    r"\d+(?:(?:[.,'\u2019]|[ \u00a0\u202f](?=\d{3}(?!\d)))\d+)*"
)
#: The Chinese multipliers, written right after the digits (« 60万 »).
_CJK_POWERS: Final[dict[str, int]] = {"千": 3, "万": 4, "萬": 4, "亿": 8, "億": 8}
#: The words of the catalogue's languages that multiply the number before them.
_WORD_POWERS: Final[dict[str, int]] = {
    **dict.fromkeys(
        (
            "million",
            "millions",
            "millionen",
            "millón",
            "millones",
            "milione",
            "milioni",
            "milhão",
            "milhões",
        ),
        6,
    ),
    **dict.fromkeys(
        (
            "milliard",
            "milliards",
            "milliarde",
            "milliarden",
            "miliardo",
            "miliardi",
            "billion",
            "billions",
            "bilhão",
            "bilhões",
        ),
        9,
    ),
}
_WORD_AFTER_RE: Final[re.Pattern[str]] = re.compile(r"[ \u00a0\u202f]+(\w+)")
_GROUPING: Final[dict[int, int | None]] = str.maketrans("", "", " \u00a0\u202f'\u2019")
_MARKS_RE: Final[re.Pattern[str]] = re.compile(r"[.,]")
#: A decimal part has this many digits only when it is a thousands group.
_GROUP_DIGITS: Final[int] = 3


@dataclass(frozen=True, slots=True)
class StatedNumber:
    """One number a text states.

    Attributes:
        digits: Its digits, separators dropped. Leading zeros go from a PLAIN
            integer only (« 09:30 » is 9 and 30), never from a grouped one:
            « 0,5 » stays ``05`` and never passes for a « 5 ».
        value: Its value as digits when a multiplier follows it (« 60万 »
            is ``600000``), else ``None``.
        grouped: Written with a separator or a multiplier — never a small
            count a transition may say freely.
    """

    digits: str
    value: str | None
    grouped: bool

    @property
    def readings(self) -> frozenset[str]:
        """Every digit string it compares as."""
        return frozenset(r for r in (self.digits, self.value) if r is not None)


def stated_numbers(text: str) -> list[StatedNumber]:
    """The numbers ``text`` states, in reading order.

    Args:
        text: Any text.

    Returns:
        One entry per number.
    """
    found: list[StatedNumber] = []
    for match in _NUMBER_RE.finditer(text):
        raw = match.group(0)
        plain = raw.isdigit()
        digits = (raw.lstrip("0") or "0") if plain else re.sub(r"\D", "", raw)
        power = _power_after(text, match.end())
        value = _scaled(raw, power) if power else None
        found.append(StatedNumber(digits, value, grouped=not plain or bool(power)))
    return found


def readings_of(text: str) -> frozenset[str]:
    """Every digit string the numbers of ``text`` compare as."""
    return frozenset(reading for number in stated_numbers(text) for reading in number.readings)


def _power_after(text: str, end: int) -> int:
    power = _CJK_POWERS.get(text[end : end + 1])
    if power is not None:
        return power
    word = _WORD_AFTER_RE.match(text, end)
    return _WORD_POWERS.get(word.group(1).casefold(), 0) if word else 0


def _scaled(raw: str, power: int) -> str | None:
    """The value of ``raw`` times ten to ``power``, as digits; ``None`` when not whole.

    One kind of mark followed by three digits groups thousands (« 3,900 »);
    otherwise the last mark is the decimal one (« 3,9 », « 1.234,5 »).
    """
    number = raw.translate(_GROUPING)
    last = max(number.rfind("."), number.rfind(","))
    if last >= 0:
        marks = _MARKS_RE.findall(number)
        tail = number[last + 1 :]
        decimal = len(set(marks)) == 2 or (len(marks) == 1 and len(tail) != _GROUP_DIGITS)
        number = (
            f"{_MARKS_RE.sub('', number[:last])}.{tail}" if decimal else _MARKS_RE.sub("", number)
        )
    try:
        value = Decimal(number).scaleb(power)
    except InvalidOperation:
        return None
    return str(int(value)) if value == value.to_integral_value() else None


__all__ = ["StatedNumber", "readings_of", "stated_numbers"]
