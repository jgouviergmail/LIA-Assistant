"""A number compares by its digits across conventions, and by its value past a multiplier."""

from __future__ import annotations

import pytest

from src.domains.radio.numbers import StatedNumber, readings_of, stated_numbers

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("3 900 emplois", [StatedNumber("3900", None, True)]),
        ("09:30", [StatedNumber("9", None, False), StatedNumber("30", None, False)]),
        (
            "entre 18 et 24 degrés",
            [StatedNumber("18", None, False), StatedNumber("24", None, False)],
        ),
        ("1'000", [StatedNumber("1000", None, True)]),
        ("en l'an 2026", [StatedNumber("2026", None, False)]),
        ("0", [StatedNumber("0", None, False)]),
        ("0,5 %", [StatedNumber("05", None, True)]),
        ("007", [StatedNumber("7", None, False)]),
        ("aucun chiffre", []),
    ],
)
def test_digits_compare_across_conventions(text: str, expected: list[StatedNumber]) -> None:
    assert stated_numbers(text) == expected


@pytest.mark.parametrize(
    ("text", "digits", "value"),
    [
        ("60万", "60", "600000"),  # Chinese counts in ten thousands
        ("近60万名信徒", "60", "600000"),
        ("1.5亿", "15", "150000000"),
        ("3千", "3", "3000"),
        ("3,9 milliards", "39", "3900000000"),
        ("3.9 billion", "39", "3900000000"),
        ("150 Millionen", "150", "150000000"),
        ("1.234,5 millones", "12345", "1234500000"),
        ("3,900 millions", "3900", "3900000000"),  # a mark before three digits groups
    ],
)
def test_a_multiplier_adds_the_value_and_keeps_the_digits(
    text: str, digits: str, value: str
) -> None:
    (number,) = stated_numbers(text)
    assert (number.digits, number.value, number.grouped) == (digits, value, True)
    assert number.readings == {digits, value}


def test_the_same_figure_in_three_conventions_meets() -> None:
    """The French fact's « 600 000 » is what a Chinese « 60万 » says."""
    french, chinese = readings_of("près de 600 000 fidèles"), readings_of("近60万名信徒")
    assert french & chinese == {"600000"}
    assert "3900000000" in readings_of("3.9 billion dollars") & readings_of("39亿美元")


def test_a_word_that_multiplies_nothing_changes_nothing() -> None:
    (number,) = stated_numbers("12 mil millones")  # « mil » is a thousand, not listed
    assert (number.value, number.grouped) == (None, False)
    assert readings_of("3 900 emplois") == {"3900"}
