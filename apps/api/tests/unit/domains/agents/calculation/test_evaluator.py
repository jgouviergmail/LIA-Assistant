"""The calculator evaluates arithmetic EXACTLY, says when it rounded, and refuses the rest.

A model does arithmetic badly and says nothing when it is wrong: « 17.5 % of
1 234.56 » comes back plausible and false. The evaluator computes in decimal —
``0.1 + 0.2`` is ``0.3``, not ``0.30000000000000004`` — flags every result it
had to round, and never executes anything: the expression is parsed, walked
node by node, and anything that is not arithmetic is refused with a reason the
model can act on.
"""

from __future__ import annotations

from decimal import DivisionImpossible, InvalidOperation

import pytest

from src.core.constants import CALCULATOR_PRECISION_DIGITS_CEILING
from src.domains.agents.calculation import evaluator
from src.domains.agents.calculation.evaluator import (
    CONSTANTS,
    FUNCTIONS,
    CalculationError,
    evaluate,
)

pytestmark = pytest.mark.unit

MAX_CHARS = 500
PRECISION = 28


def _text(expression: str) -> str:
    return evaluate(expression, max_chars=MAX_CHARS, precision=PRECISION).text


def _refusal(expression: str, *, max_chars: int = MAX_CHARS) -> CalculationError:
    with pytest.raises(CalculationError) as caught:
        evaluate(expression, max_chars=max_chars, precision=PRECISION)
    return caught.value


class TestExactArithmetic:
    @pytest.mark.parametrize(
        ("expression", "expected"),
        [
            ("0.1 + 0.2", "0.3"),
            ("1234.56 * 17.5 / 100", "216.048"),
            ("2 ** 10", "1024"),
            ("(1 + 2) * 3", "9"),
            ("-(3)", "-3"),
            ("+4", "4"),
            ("1e3 + 1", "1001"),
            ("1_000 * 3", "3000"),
            ("10 - 10", "0"),
            ("0.5 - 0.5", "0"),
            ("-0.0", "0"),
            ("0 ** 0", "1"),
        ],
    )
    def test_the_value_is_the_decimal_one(self, expression: str, expected: str) -> None:
        assert _text(expression) == expected

    @pytest.mark.parametrize(
        ("expression", "expected"),
        [
            ("7 // 2", "3"),
            ("-7 // 2", "-4"),
            ("7 // -2", "-4"),
            ("-7 % 3", "2"),
            ("7 % -3", "-2"),
            ("7.5 % 2", "1.5"),
        ],
    )
    def test_floor_division_and_modulo_follow_python(self, expression: str, expected: str) -> None:
        """Decimal truncates toward zero where Python floors: the calculator floors."""
        assert _text(expression) == expected

    def test_an_exact_result_says_so(self) -> None:
        assert evaluate("0.1 + 0.2", max_chars=MAX_CHARS, precision=PRECISION).exact is True

    def test_a_rounded_result_says_so(self) -> None:
        result = evaluate("1 / 3", max_chars=MAX_CHARS, precision=PRECISION)

        assert result.exact is False
        assert result.text == "0." + "3" * PRECISION

    def test_the_precision_is_the_one_asked_for(self) -> None:
        assert evaluate("2 / 3", max_chars=MAX_CHARS, precision=10).text == "0.6666666667"

    def test_the_evaluated_expression_is_returned_as_read(self) -> None:
        result = evaluate("  2 ^ 3  ", max_chars=MAX_CHARS, precision=PRECISION)

        assert result.expression == "2 ** 3"


class TestMechanicalRepairs:
    """What cannot mean anything else is repaired, never refused (CLAUDE.md, ADR-184)."""

    @pytest.mark.parametrize(
        ("expression", "expected"),
        [
            ("2 ^ 10", "1024"),
            ("12 × 3 ÷ 4 − 1", "8"),
            ("3 · 4", "12"),
        ],
    )
    def test_typographic_operators_are_read(self, expression: str, expected: str) -> None:
        assert _text(expression) == expected


class TestFunctionsAndConstants:
    @pytest.mark.parametrize(
        ("expression", "expected"),
        [
            ("round(2.5)", "3"),
            ("round(2.675, 2)", "2.68"),
            ("round(-2.5)", "-3"),
            ("round(1234.5, -2)", "1200"),
            ("floor(-2.5)", "-3"),
            ("ceil(2.1)", "3"),
            ("abs(-4.2)", "4.2"),
            ("min(3, 1.5, 2)", "1.5"),
            ("max(3, 1.5, 2)", "3"),
            ("sqrt(16)", "4"),
            ("log10(1000)", "3"),
            ("log(8, 2)", "3"),
            ("radians(180) - pi", "0"),
            ("degrees(pi)", "180"),
        ],
    )
    def test_the_value(self, expression: str, expected: str) -> None:
        assert _text(expression) == expected

    def test_rounding_is_half_up_as_a_person_expects(self) -> None:
        """Python's ``round`` is the banker's (2.5 → 2); nobody asking a calculator means that."""
        assert _text("round(0.125, 2)") == "0.13"

    def test_an_irrational_result_is_approximate(self) -> None:
        result = evaluate("sqrt(2)", max_chars=MAX_CHARS, precision=PRECISION)

        assert result.exact is False
        assert result.text.startswith("1.414213562373095048801688724")

    def test_trigonometry_is_approximate_even_when_it_lands_on_a_round_number(self) -> None:
        result = evaluate("sin(pi / 2)", max_chars=MAX_CHARS, precision=PRECISION)

        assert result.text == "1"
        assert result.exact is False

    def test_the_published_names_are_the_ones_evaluated(self) -> None:
        """What the manifest lists is read from here; every name must actually work."""
        for name in FUNCTIONS:
            arguments = "8, 2" if name == "log" else "0.5"
            evaluate(f"{name}({arguments})", max_chars=MAX_CHARS, precision=PRECISION)
        for name in CONSTANTS:
            evaluate(name, max_chars=MAX_CHARS, precision=PRECISION)


class TestDisplay:
    def test_a_large_value_is_written_in_scientific_notation(self) -> None:
        assert _text("10 ** 40") == "1e+40"

    def test_a_value_beyond_the_precision_is_rounded_and_flagged(self) -> None:
        result = evaluate("2 ** 100", max_chars=MAX_CHARS, precision=PRECISION)

        assert result.exact is False
        assert result.text == "1.267650600228229401496703205e+30"

    def test_a_small_value_keeps_plain_notation(self) -> None:
        assert _text("1 / 1000000") == "0.000001"


class TestRefusals:
    """Every refusal names what went wrong, so the model can correct its own call."""

    def test_an_empty_expression(self) -> None:
        assert _refusal("   ").reason == "syntax"

    def test_an_expression_past_the_published_length(self) -> None:
        refusal = _refusal("1+" * 300 + "1")

        assert refusal.reason == "too_long"
        assert str(MAX_CHARS) in str(refusal)

    @pytest.mark.parametrize(
        "expression",
        [
            "__import__('os').system('id')",
            "(1).__class__",
            "open('/etc/passwd')",
            "[1, 2]",
            "{1: 2}",
            "1 if 2 else 3",
            "lambda: 1",
            "1 < 2",
            "not 1",
            "1 and 2",
            "'a' * 3",
            "True + 1",
            "2j",
            "x + 1",
            "round(2.5, ndigits=1)",
            "sqrt(*[4])",
        ],
    )
    def test_anything_that_is_not_arithmetic(self, expression: str) -> None:
        assert _refusal(expression).reason == "unsupported"

    def test_a_decimal_comma_is_refused_with_the_hint(self) -> None:
        refusal = _refusal("1234,56 * 2")

        assert refusal.reason == "unsupported"
        assert "decimal separator" in str(refusal)

    def test_a_percent_sign_is_refused_with_the_hint(self) -> None:
        refusal = _refusal("200 * 15%")

        assert refusal.reason == "syntax"
        assert "/ 100" in str(refusal)

    @pytest.mark.parametrize(
        "expression", ["abs()", "sqrt(4, 5)", "max()", "log(1, 2, 3)", "round(1, 2, 3)"]
    )
    def test_a_wrong_number_of_arguments(self, expression: str) -> None:
        assert _refusal(expression).reason == "unsupported"

    def test_round_takes_a_whole_number_of_decimals(self) -> None:
        assert _refusal("round(2.5, 1.5)").reason == "unsupported"

    @pytest.mark.parametrize("expression", ["1 / 0", "5 // 0", "5 % 0", "0 ** -1"])
    def test_a_division_by_zero(self, expression: str) -> None:
        assert _refusal(expression).reason == "division_by_zero"

    @pytest.mark.parametrize(
        "expression", ["sqrt(-1)", "ln(0)", "ln(-1)", "log(10, 1)", "asin(2)", "(-8) ** (1/3)"]
    )
    def test_an_undefined_result(self, expression: str) -> None:
        assert _refusal(expression).reason == "domain"

    @pytest.mark.parametrize("expression", ["10 ** 10 ** 10", "9 ** 9 ** 9", "exp(10 ** 7)"])
    def test_a_result_too_large_fails_fast(self, expression: str) -> None:
        assert _refusal(expression).reason == "overflow"

    @pytest.mark.parametrize("expression", ["10 ** 40 // 3", "10 ** 40 % 3"])
    def test_an_integer_quotient_wider_than_the_precision_is_an_overflow(
        self, expression: str
    ) -> None:
        assert _refusal(expression).reason == "overflow"

    @pytest.mark.parametrize("expression", ["round(1, 29)", "round(1e30, 2)"])
    def test_round_keeps_only_what_the_precision_holds(self, expression: str) -> None:
        assert _refusal(expression).reason == "domain"

    @pytest.mark.parametrize(
        ("expression", "arity"),
        [("log(1, 2, 3)", "1 or 2"), ("max()", "at least 1"), ("sqrt(4, 5)", "takes 1 —")],
    )
    def test_the_arity_is_named(self, expression: str, arity: str) -> None:
        assert arity in str(_refusal(expression))

    def test_nesting_beyond_the_parser_is_a_syntax_refusal(self) -> None:
        assert _refusal("(" * 250 + "1" + ")" * 250, max_chars=1000).reason == "syntax"

    def test_a_long_chain_is_evaluated_without_recursion_trouble(self) -> None:
        """The published bound admits a long chain; the walk must hold it."""
        assert evaluate("1+" * 999 + "1", max_chars=2000, precision=PRECISION).text == "1000"


class TestTheImplementationSeams:
    @pytest.mark.parametrize(
        "error",
        [DivisionImpossible(), InvalidOperation([DivisionImpossible])],
        ids=["pure-python-subclass", "c-implementation-argument"],
    )
    def test_an_impossible_division_is_read_whichever_decimal_runs(
        self, error: InvalidOperation
    ) -> None:
        assert evaluator._is_division_impossible(error) is True

    def test_another_invalid_operation_is_not_one(self) -> None:
        assert evaluator._is_division_impossible(InvalidOperation([InvalidOperation])) is False

    def test_pi_carries_the_widest_admitted_precision_and_its_guard(self) -> None:
        """A deployment may raise the precision to its ceiling, and transcendental
        functions compute with guard digits on top: π must hold them all, or the
        precision silently stops where π's digits do."""
        digits = len(evaluator._PI.as_tuple().digits)

        assert digits >= CALCULATOR_PRECISION_DIGITS_CEILING + evaluator._GUARD_DIGITS
