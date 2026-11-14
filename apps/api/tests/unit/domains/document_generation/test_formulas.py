"""A computed column's expression: one grammar, two readings (ADR-274 amendment).

The same tree gives the Excel formula a workbook recalculates AND the value a
reader that never recalculates shows — a preview pane, a phone, the chat's own
excerpt. The two must agree, so the oracle of every value test is an
independent computation, never the module under test.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.domains.document_generation.formulas import (
    FormulaError,
    FormulaValueError,
    blank_columns,
    evaluate,
    may_error,
    parse_formula,
    spreading_names,
    to_excel,
)

pytestmark = [pytest.mark.unit]

COLUMNS = ["Revenue (EUR)", "Cost (EUR)", "Units", "Month", "Category"]
INPUTS = ["Tax rate", "Growth"]


class _Row:
    """One row of a sheet, as the evaluator reads it."""

    def __init__(
        self,
        values: dict[str, Decimal | None],
        previous: dict[str, Decimal | None] | None = None,
        columns: dict[str, list[Decimal | None]] | None = None,
        texts: dict[str, str] | None = None,
        running: dict[str, Decimal] | None = None,
        without_value: frozenset[str] = frozenset(),
    ) -> None:
        self._values = values
        self._previous = previous
        self._columns = columns or {}
        self._texts = texts or {}
        self._running = running or {}
        self._without_value = without_value

    def value(self, column: str) -> Decimal | None:
        if column in self._without_value:
            raise FormulaValueError("a computed cell with no value")
        return self._values.get(column)

    def text(self, column: str) -> str:
        return self._texts.get(column, "")

    def running_sum(self, column: str) -> Decimal:
        return self._running[column]

    def sheet_aggregate(self, function: str, sheet: str, column: str) -> Decimal:
        raise FormulaValueError("a row formula reads no other sheet")

    def previous(self, column: str) -> Decimal | None:
        if self._previous is None:
            raise FormulaValueError("first row")
        return self._previous.get(column)

    def aggregate(self, function: str, column: str) -> Decimal:
        numbers = [value for value in self._columns.get(column, []) if value is not None]
        if function == "SUM":
            return sum(numbers, Decimal(0))
        if not numbers:
            raise FormulaValueError("an average of nothing")
        return sum(numbers, Decimal(0)) / len(numbers)

    def input(self, name: str) -> Decimal:
        return {"Tax rate": Decimal("0.25"), "Growth": Decimal("0.1")}[name]


class _Cells:
    """Where each name lives in an Excel sheet."""

    def cell(self, column: str) -> str:
        return {
            "Revenue (EUR)": "B7",
            "Cost (EUR)": "C7",
            "Units": "D7",
            "Month": "A7",
            "Category": "E7",
        }[column]

    def previous_cell(self, column: str) -> str:
        return {"Revenue (EUR)": "B6", "Cost (EUR)": "C6"}[column]

    def column_range(self, column: str) -> str:
        return {"Revenue (EUR)": "B$2:B$11", "Cost (EUR)": "C$2:C$11"}[column]

    def running_range(self, column: str) -> str:
        return {"Revenue (EUR)": "B$2:B7", "Cost (EUR)": "C$2:C7"}[column]

    def sheet_range(self, sheet: str, column: str) -> str:
        return {("Monthly budget", "Total"): "'Monthly budget'!$D$2:$D$13"}[(sheet, column)]

    def input_name(self, name: str) -> str:
        return {"Tax rate": "Tax_rate", "Growth": "Growth"}[name]


def _row(
    revenue: str | None = "1000",
    cost: str | None = "400",
    units: str | None = "8",
    category: str = "Food",
) -> _Row:
    return _Row(
        {
            "Revenue (EUR)": Decimal(revenue) if revenue is not None else None,
            "Cost (EUR)": Decimal(cost) if cost is not None else None,
            "Units": Decimal(units) if units is not None else None,
        },
        previous={"Revenue (EUR)": Decimal("800"), "Cost (EUR)": Decimal("300")},
        columns={
            "Revenue (EUR)": [Decimal("1000"), Decimal("800"), None, Decimal("200")],
            "Cost (EUR)": [Decimal("400"), Decimal("300")],
        },
        texts={"Category": category},
        running={"Revenue (EUR)": Decimal("1800")},
    )


def _formula(text: str):
    return parse_formula(text, columns=COLUMNS, inputs=INPUTS)


class TestTheGrammarAcceptsWhatASheetNeeds:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("{Revenue (EUR)} - {Cost (EUR)}", Decimal("600")),
            ("({Revenue (EUR)} - {Cost (EUR)}) / {Revenue (EUR)}", Decimal("0.6")),
            ("{Revenue (EUR)} * (1 - {Tax rate})", Decimal("750")),
            ("{Revenue (EUR)} / PREVIOUS({Revenue (EUR)}) - 1", Decimal("0.25")),
            ("{Revenue (EUR)} / SUM({Revenue (EUR)})", Decimal("0.5")),
            ("AVERAGE({Revenue (EUR)})", Decimal("2000") / Decimal("3")),
            ("ROUND({Revenue (EUR)} / 3, 2)", Decimal("333.33")),
            ("ROUND(2.5, 0)", Decimal("3")),
            ("ROUND(-2.5, 0)", Decimal("-3")),
            ("ROUND(1234, -2)", Decimal("1200")),
            ("ABS({Cost (EUR)} - {Revenue (EUR)})", Decimal("600")),
            ("MAX({Units}, 10)", Decimal("10")),
            ("MIN({Units}, 10, 3)", Decimal("3")),
            ("2 ^ 3 ^ 2", Decimal("512")),
            ("-2 ^ 2", Decimal("-4")),
            ("(-2) ^ 2", Decimal("4")),
            ("{ revenue  (eur) }", Decimal("1000")),
        ],
    )
    def test_the_value_is_the_arithmetic(self, text: str, expected: Decimal) -> None:
        assert evaluate(_formula(text), _row()) == expected

    def test_a_blank_cell_counts_as_zero_like_excel(self) -> None:
        """Excel reads an empty cell as 0 in arithmetic: the cached value must agree."""
        assert evaluate(_formula("{Revenue (EUR)} - {Cost (EUR)}"), _row(cost=None)) == 1000

    def test_an_average_ignores_blank_cells_like_excel(self) -> None:
        assert evaluate(_formula("AVERAGE({Revenue (EUR)})"), _row()) == Decimal("2000") / 3


class TestWhatHasNoValueHasNoValue:
    @pytest.mark.parametrize(
        "text",
        [
            "{Revenue (EUR)} / 0",
            "{Revenue (EUR)} / {Cost (EUR)}",
            "(-8) ^ 0.5",
        ],
    )
    def test_an_impossible_operation_raises_for_a_blank_cache(self, text: str) -> None:
        row = _row(cost="0")
        with pytest.raises(FormulaValueError):
            evaluate(_formula(text), row)

    def test_the_first_row_has_no_previous(self) -> None:
        first = _Row({"Revenue (EUR)": Decimal("1")}, previous=None)
        with pytest.raises(FormulaValueError):
            evaluate(_formula("{Revenue (EUR)} / PREVIOUS({Revenue (EUR)})"), first)

    @pytest.mark.parametrize("text", ["10 ^ 400", "{Revenue (EUR)} * 1e305", "2 ^ 99999"])
    def test_a_result_beyond_what_excel_holds_has_no_value(self, text: str) -> None:
        """Excel answers #NUM! past 9.99E+307, and no float holds the value a
        workbook would cache beside the formula: the row is blank everywhere."""
        with pytest.raises(FormulaValueError):
            evaluate(_formula(text), _row())

    def test_the_largest_values_excel_holds_are_values(self) -> None:
        assert evaluate(_formula("{Revenue (EUR)} * 1e304"), _row()) == Decimal("1e307")


class TestTheGrammarRefusesEverythingElse:
    @pytest.mark.parametrize(
        "text",
        [
            "",
            "   ",
            "{Unknown} + 1",
            "__import__('os')",
            "{Revenue (EUR)}.real",
            "{Revenue (EUR)} if 1 else 2",
            "[1, 2]",
            "'text'",
            "True + 1",
            "SUM({Revenue (EUR)}, {Cost (EUR)})",
            "SUM(1 + 2)",
            "SUM({Tax rate})",
            "PREVIOUS({Revenue (EUR)} + 1)",
            "ROUND({Units})",
            "ROUND({Units}, 1.5)",
            "ROUND({Units}, 9)",
            "MIN({Units})",
            "LOG({Units})",
            "{Revenue (EUR)} % 2",
            "{Revenue (EUR)} // 2",
            "{Revenue (EUR)} == 2",
            "({Units} > 1) * 2",
            "{Revenue (EUR)",
            "{Revenue (EUR)} }",
            "1 +",
            "x + 1",
            "f(1)",
            "ROUND(x=1, n=2)",
            # A literal no float holds reads as infinity: no sheet has such a number.
            "{Units} * 1e999",
        ],
    )
    def test_a_construct_outside_the_grammar_is_refused(self, text: str) -> None:
        with pytest.raises(FormulaError):
            _formula(text)

    def test_a_formula_longer_than_the_published_bound_is_refused(self) -> None:
        from src.core.constants import DOCUMENT_GENERATION_FORMULA_MAX_CHARS

        long_text = "+".join(["{Units}"] * (DOCUMENT_GENERATION_FORMULA_MAX_CHARS // 7 + 2))
        with pytest.raises(FormulaError):
            _formula(long_text)

    def test_a_column_name_wins_over_an_input_of_the_same_name(self) -> None:
        formula = parse_formula("{Units} * 2", columns=["Units"], inputs=["Units"])
        assert formula.columns == frozenset({"Units"}) and formula.inputs == frozenset()


class TestTheExcelReading:
    @pytest.mark.parametrize(
        ("text", "excel"),
        [
            ("{Revenue (EUR)} - {Cost (EUR)}", "B7-C7"),
            ("{Revenue (EUR)} * (1 - {Tax rate})", "B7*(1-Tax_rate)"),
            ("{Revenue (EUR)} / PREVIOUS({Revenue (EUR)}) - 1", "(B7/B6)-1"),
            ("{Revenue (EUR)} / SUM({Revenue (EUR)})", "B7/SUM(B$2:B$11)"),
            ("ROUND({Revenue (EUR)} / 3, 2)", "ROUND(B7/3,2)"),
            ("-2 ^ 2", "-(2^2)"),
            ("(-2) ^ 2", "(-2)^2"),
            ("2 ^ 3 ^ 2", "2^(3^2)"),
            ("MIN({Units}, 10)", "MIN(D7,10)"),
            ("{Units} * 0.000001", "D7*0.000001"),
            ("{Units} * 1e3", "D7*1000"),
        ],
    )
    def test_the_formula_keeps_the_python_meaning(self, text: str, excel: str) -> None:
        """Excel binds unary minus tighter than ``^`` and reads ``^`` left to right:
        every nested operation is parenthesized, so the workbook computes what the
        cached value says."""
        assert to_excel(_formula(text), _Cells()) == excel

    @pytest.mark.parametrize(
        ("text", "errors"),
        [
            ("{Revenue (EUR)} - {Cost (EUR)}", False),
            ("{Revenue (EUR)} / {Cost (EUR)}", True),
            ("2 ^ {Units}", True),
            ("PREVIOUS({Revenue (EUR)})", True),
            ("AVERAGE({Revenue (EUR)})", True),
            ("ROUND({Units}, 0)", False),
        ],
    )
    def test_only_what_can_fail_is_wrapped(self, text: str, errors: bool) -> None:
        assert may_error(_formula(text)) is errors


class TestAConditionChoosesAValue:
    """``IF`` reads as Excel reads it: the oracle of each case is the comparison
    written in the test, on the row ``_row`` builds (8 units, cost 400, « Food »)."""

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("IF({Units} >= 8, {Revenue (EUR)} * 0.9, {Revenue (EUR)})", Decimal("900")),
            ("IF({Units} > 8, 1, 2)", Decimal(2)),
            ("IF({Units} = 8, 1, 2)", Decimal(1)),
            ("IF({Units} <> 8, 1, 2)", Decimal(2)),
            ("IF({Units} == 8, 1, 2)", Decimal(1)),
            ("IF({Units} != 8, 1, 2)", Decimal(2)),
            ("IF({Units} <= 7, 1, 2)", Decimal(2)),
            ("IF({Units} < 9, 1, 2)", Decimal(1)),
            ("IF({Units} + 1 > {Cost (EUR)} / 50, 1, 2)", Decimal(1)),
            ("IF(AND({Units} > 1, {Cost (EUR)} < 500), 1, 0)", Decimal(1)),
            ("IF(AND({Units} > 1, {Cost (EUR)} > 500), 1, 0)", Decimal(0)),
            ("IF(OR({Units} > 1, {Cost (EUR)} > 500), 1, 0)", Decimal(1)),
            ("IF(OR({Units} > 100, {Cost (EUR)} > 500), 1, 0)", Decimal(0)),
            ("IF(NOT({Units} > 100), 1, 0)", Decimal(1)),
            ('IF({Category} = "food", 1, 0)', Decimal(1)),
            ('IF("FOOD" = {Category}, 1, 0)', Decimal(1)),
            ('IF({Category} <> "Food", 1, 0)', Decimal(0)),
            ("IF({Category} = 'Rent', 1, 0)", Decimal(0)),
            ('IF({Category} = "Food = cost", 1, 0)', Decimal(0)),
            ("IF({Units} > 1, IF({Units} > 5, 2, 1), 0)", Decimal(2)),
            ("IF({Units} > 1, 3, 0) * 2", Decimal(6)),
            ("if({Units} > 1, round({Units} / 3, 1), 0)", Decimal("2.7")),
            ("If(Or({Units} > 1), Max({Units}, 10), 0)", Decimal(10)),
        ],
    )
    def test_the_value_is_the_one_the_condition_chooses(self, text: str, expected: Decimal) -> None:
        assert evaluate(_formula(text), _row()) == expected

    @pytest.mark.parametrize(
        "text",
        [
            "IF({Revenue (EUR)} / 3 * 3 = {Revenue (EUR)}, 1, 0)",
            "IF(1 / 3 * 3 = 1, 1, 0)",
            "IF(0.1 + 0.2 = 0.3, 1, 0)",
            "IF(2 / 3 = 0.666666666666667, 1, 0)",
        ],
    )
    def test_numbers_compare_on_fifteen_significant_digits_like_excel(self, text: str) -> None:
        """Excel compares two numbers on 15 significant digits: the exact quotient
        kept to 28 digits must not decide otherwise than the workbook will."""
        assert evaluate(_formula(text), _row()) == 1

    def test_only_the_value_chosen_is_computed_like_excel(self) -> None:
        text = "IF({Cost (EUR)} = 0, 0, {Revenue (EUR)} / {Cost (EUR)})"
        assert evaluate(_formula(text), _row(cost="0")) == 0

    def test_a_condition_without_value_leaves_the_row_without_value(self) -> None:
        with pytest.raises(FormulaValueError):
            evaluate(_formula("IF({Revenue (EUR)} / {Cost (EUR)} > 1, 1, 0)"), _row(cost="0"))

    def test_and_reads_every_condition_like_excel(self) -> None:
        """Excel's AND evaluates all its arguments: one without value spreads."""
        text = "IF(AND({Units} > 100, {Revenue (EUR)} / {Cost (EUR)} > 1), 1, 0)"
        with pytest.raises(FormulaValueError):
            evaluate(_formula(text), _row(cost="0"))

    def test_an_empty_cell_compares_as_zero_like_excel(self) -> None:
        assert evaluate(_formula("IF({Cost (EUR)} = 0, 1, 2)"), _row(cost=None)) == 1

    def test_an_empty_text_cell_is_the_empty_text(self) -> None:
        assert evaluate(_formula('IF({Category} = "", 1, 2)'), _row(category="")) == 1


class TestARunningSum:
    def test_it_reads_the_column_down_to_this_row(self) -> None:
        assert evaluate(_formula("RUNNING_SUM({Revenue (EUR)})"), _row()) == Decimal("1800")

    def test_it_composes_like_any_value(self) -> None:
        text = "{Revenue (EUR)} / RUNNING_SUM({Revenue (EUR)})"
        assert evaluate(_formula(text), _row()) == Decimal(1000) / Decimal(1800)


class TestMinAndMaxSkipAReferenceHoldingNoNumber:
    """Excel's MIN and MAX ignore an empty cell, or a text, that a bare reference
    holds — the header above the first row, a computed cell with no value — but an
    expression reads an empty cell as 0. Of nothing, they answer 0."""

    def test_an_empty_cell_is_skipped(self) -> None:
        assert evaluate(_formula("MIN({Cost (EUR)}, 500)"), _row(cost=None)) == 500
        assert evaluate(_formula("MAX({Cost (EUR)}, -5)"), _row(cost=None)) == -5

    def test_an_expression_reads_an_empty_cell_as_zero(self) -> None:
        assert evaluate(_formula("MIN({Cost (EUR)} + 0, 500)"), _row(cost=None)) == 0

    def test_the_header_above_the_first_row_is_skipped(self) -> None:
        first = _Row({"Revenue (EUR)": Decimal("1")}, previous=None)
        assert evaluate(_formula("MAX(PREVIOUS({Revenue (EUR)}), 7)"), first) == 7

    def test_a_computed_cell_with_no_value_is_skipped(self) -> None:
        row = _Row({"Units": Decimal("8")}, without_value=frozenset({"Cost (EUR)"}))
        assert evaluate(_formula("MAX({Cost (EUR)}, {Units})"), row) == 8
        with pytest.raises(FormulaValueError):
            evaluate(_formula("MAX({Cost (EUR)} * 1, {Units})"), row)

    def test_with_nothing_left_the_answer_is_zero(self) -> None:
        assert evaluate(_formula("MIN({Cost (EUR)}, {Units})"), _row(cost=None, units=None)) == 0

    def test_an_if_returns_the_reference_it_chooses(self) -> None:
        """Excel's IF returns a reference, which MIN reads as the reference itself."""
        text = "MIN(IF({Units} > 1, {Cost (EUR)}, 0), 500)"
        assert evaluate(_formula(text), _row(cost=None)) == 500
        assert evaluate(_formula(text), _row(cost="7")) == 7
        assert evaluate(_formula(text), _row(cost=None, units="0")) == 0


class TestTheConditionalGrammarRefusesWhatExcelReadsOtherwise:
    @pytest.mark.parametrize(
        "text",
        [
            "IF({Units} > 1, 2)",
            "IF({Units} > 1, 2, 3, 4)",
            "IF({Units}, 1, 2)",
            "IF({Units} > 1, {Units} > 2, 3)",
            "{Units} > 1",
            "IF(1 < {Units} < 5, 1, 0)",
            'IF({Category} = "x", "a", "b")',
            '"food"',
            'IF({Category} > "food", 1, 0)',
            'IF({Units} + 1 = "x", 1, 0)',
            'IF("a" = "b", 1, 0)',
            'IF({Tax rate} = "x", 1, 0)',
            "IF({Category} = 'say \"hi\"', 1, 0)",
            'IF({Category} = "{Units}", 1, 0)',
            'IF({Category} = "a\\b", 1, 0)',
            'IF({Category} = "a\\\\b", 1, 0)',
            'IF({Category} = "tab\there", 1, 0)',
            "IF(PREVIOUS({Units}) > 1, 1, 0)",
            "IF(AND(), 1, 0)",
            "IF(AND({Units}), 1, 0)",
            "IF(NOT({Units} > 1, {Units} < 3), 1, 0)",
            "IF({Units} > 1 and {Units} < 3, 1, 0)",
            "IF(not {Units} > 1, 1, 0)",
            "IF({Units} in 1, 1, 0)",
            "IF({Units} is 1, 1, 0)",
            "AND({Units} > 1)",
            "RUNNING_SUM({Tax rate})",
            "RUNNING_SUM({Units} + 1)",
            "RUNNING_SUM()",
            "RUNNING_SUM({Units}, {Cost (EUR)})",
            "IF(TRUE, 1, 0)",
            "IF({Units} =< 1, 1, 0)",
            "IF(f'{Units}' = 1, 1, 0)",
            "IF({Units} = b'1', 1, 0)",
        ],
    )
    def test_a_construct_outside_the_grammar_is_refused(self, text: str) -> None:
        with pytest.raises(FormulaError):
            _formula(text)

    def test_a_comparison_reading_a_column_through_an_if_records_it(self) -> None:
        formula = _formula("IF(IF({Units} > 1, {Cost (EUR)}, 0) > 5, 1, 0)")
        assert formula.compared == frozenset({"Units", "Cost (EUR)"})
        with pytest.raises(FormulaError):
            _formula("IF(IF({Units} > 1, PREVIOUS({Units}), 0) > 5, 1, 0)")

    def test_a_formula_says_how_it_reads_each_column(self) -> None:
        formula = _formula(
            'IF(AND({Category} = "food", {Units} > 1), {Revenue (EUR)}, MIN({Cost (EUR)}, 5))'
        )
        assert formula.texts == frozenset({"Category"})
        assert formula.numbers == frozenset({"Units", "Revenue (EUR)", "Cost (EUR)"})
        assert formula.compared == frozenset({"Units"})
        assert formula.columns == formula.texts | formula.numbers


class TestTheConditionalExcelReading:
    @pytest.mark.parametrize(
        ("text", "excel"),
        [
            ("IF({Units} >= 8, {Revenue (EUR)} * 0.9, {Revenue (EUR)})", "IF(D7>=8,B7*0.9,B7)"),
            ("IF({Units} = 8, 1, 2)", "IF(D7=8,1,2)"),
            ("IF({Units} == 8, 1, 2)", "IF(D7=8,1,2)"),
            ("IF({Units} != 8, 1, 2)", "IF(D7<>8,1,2)"),
            ("IF({Units} <> 8, 1, 2)", "IF(D7<>8,1,2)"),
            (
                "IF(AND({Units} > 1, NOT({Cost (EUR)} < 500)), 1, 0)",
                "IF(AND(D7>1,NOT(C7<500)),1,0)",
            ),
            ("IF(OR({Units} > 1, {Units} < 0), 1, 0)", "IF(OR(D7>1,D7<0),1,0)"),
            ("IF({Category} = 'food', 1, 0)", 'IF(E7="food",1,0)'),
            ('IF("Food" <> {Category}, 1, 0)', 'IF(E7<>"Food",1,0)'),
            ("IF({Units} + 1 > {Cost (EUR)} * 2, 1, 0)", "IF((D7+1)>(C7*2),1,0)"),
            ("IF(-{Units} < 0, 1, 0)", "IF((-D7)<0,1,0)"),
            ("IF({Units} > 1, 3, 0) * 2", "IF(D7>1,3,0)*2"),
            ("RUNNING_SUM({Revenue (EUR)})", "SUM(B$2:B7)"),
            ("{Revenue (EUR)} / RUNNING_SUM({Revenue (EUR)})", "B7/SUM(B$2:B7)"),
            ("if({Units} ^ 2 > 1, 1, 0)", "IF((D7^2)>1,1,0)"),
        ],
    )
    def test_the_formula_keeps_its_meaning(self, text: str, excel: str) -> None:
        assert to_excel(_formula(text), _Cells()) == excel

    @pytest.mark.parametrize(
        ("text", "errors"),
        [
            ("IF({Units} > 1, {Revenue (EUR)} / {Units}, 0)", True),
            ("IF({Revenue (EUR)} / {Units} > 1, 1, 0)", True),
            ("IF(AND({Units} > 1, PREVIOUS({Units}) + 0 > 1), 1, 0)", True),
            ("IF({Units} > 1, 1, 0)", False),
            ('IF({Category} = "a", 1, 0)', False),
            ("RUNNING_SUM({Revenue (EUR)})", False),
        ],
    )
    def test_only_what_can_fail_is_wrapped(self, text: str, errors: bool) -> None:
        assert may_error(_formula(text)) is errors


class TestAColumnWithNoValueSpreads:
    """A computed cell with no value holds an empty text in the workbook: whatever
    reads it in arithmetic has no value either, so it must be wrapped too — but an
    aggregate, a running sum, or MIN and MAX on a bare reference skip it."""

    def test_the_columns_that_may_have_no_value(self) -> None:
        columns = ["A", "B", "Ratio", "Twice", "Total", "Cumul", "Floor", "Plain", "Chosen"]
        texts = {
            "Ratio": "{A} / {B}",
            "Twice": "{Ratio} * 2",
            "Total": "{A} + SUM({Ratio})",
            "Cumul": "RUNNING_SUM({Ratio})",
            "Floor": "MAX({Ratio}, 0)",
            "Plain": "{A} + 1",
            "Chosen": "IF({A} > 1, {Twice}, 0)",
        }
        formulas = {name: parse_formula(text, columns=columns) for name, text in texts.items()}
        assert blank_columns(formulas) == frozenset({"Ratio", "Twice", "Chosen"})

    def test_nothing_without_a_failing_operation(self) -> None:
        formulas = {"Plain": parse_formula("{A} + 1", columns=["A", "Plain"])}
        assert blank_columns(formulas) == frozenset()


class TestAColumnNeverReadsItself:
    """Measured 2026-11-13 on a real writer: a monthly ``Rent`` column computed as
    ``{Rent}`` beside an input « Rent » — in 3 workbooks of 5. A column never reads
    itself, so in its own formula its name can only be the input of that name."""

    BUDGET = ["Month", "Rent", "Bonus", "Total"]

    def test_its_own_name_is_the_input_of_that_name(self) -> None:
        formula = parse_formula("{Rent}", columns=self.BUDGET, inputs=["Rent"], itself="Rent")
        assert formula.inputs == frozenset({"Rent"}) and formula.columns == frozenset()

    def test_whatever_its_case_and_spacing(self) -> None:
        formula = parse_formula(
            "IF({Month} = 12, { bonus }, 0)",
            columns=self.BUDGET,
            inputs=["Bonus"],
            itself="BONUS",
        )
        assert formula.inputs == frozenset({"Bonus"}) and formula.columns == {"Month"}

    def test_another_column_still_reads_the_column(self) -> None:
        formula = parse_formula(
            "{Rent} + {Bonus}", columns=self.BUDGET, inputs=["Rent"], itself="Total"
        )
        assert formula.columns == frozenset({"Rent", "Bonus"}) and formula.inputs == frozenset()

    @pytest.mark.parametrize(
        "text",
        [
            "{Rent}",
            "{Rent} * 2",
            "PREVIOUS({Rent})",
            "RUNNING_SUM({Rent})",
            'IF({Rent} = "a", 1, 0)',
        ],
    )
    def test_without_an_input_of_that_name_a_column_reading_itself_is_refused(
        self, text: str
    ) -> None:
        with pytest.raises(FormulaError) as refused:
            parse_formula(text, columns=self.BUDGET, inputs=["Bonus"], itself="Rent")
        assert refused.value.reason == "reads_itself"

    @pytest.mark.parametrize("text", ["PREVIOUS({Rent})", "SUM({Rent})", 'IF({Rent} = "a", 1, 0)'])
    def test_the_input_is_never_read_as_a_column_or_a_text(self, text: str) -> None:
        with pytest.raises(FormulaError):
            parse_formula(text, columns=self.BUDGET, inputs=["Rent"], itself="Rent")

    def test_the_workbook_reads_the_input_by_its_name(self) -> None:
        formula = parse_formula(
            "{Growth} * 1.1", columns=["Month", "Growth"], inputs=["Growth"], itself="Growth"
        )
        assert to_excel(formula, _Cells()) == "Growth*1.1"


class _Figure:
    """A whole workbook as a figure reads it: its inputs, other figures, sheets' columns."""

    def __init__(self, sums: dict[tuple[str, str], list[Decimal | None]]) -> None:
        self._columns = sums

    def value(self, column: str) -> Decimal | None:
        raise FormulaValueError("a figure reads no row")

    def text(self, column: str) -> str:
        raise FormulaValueError("a figure reads no row")

    def previous(self, column: str) -> Decimal | None:
        raise FormulaValueError("a figure reads no row")

    def aggregate(self, function: str, column: str) -> Decimal:
        raise FormulaValueError("a figure reads no row")

    def running_sum(self, column: str) -> Decimal:
        raise FormulaValueError("a figure reads no row")

    def sheet_aggregate(self, function: str, sheet: str, column: str) -> Decimal:
        numbers = [value for value in self._columns[(sheet, column)] if value is not None]
        if function == "SUM":
            return sum(numbers, Decimal(0))
        if not numbers:
            raise FormulaValueError("an average of nothing")
        return sum(numbers, Decimal(0)) / len(numbers)

    def input(self, name: str) -> Decimal:
        return {"Months": Decimal(12), "Bonus": Decimal(1500)}[name]


SHEETS = {"Monthly budget": ["Month", "Total", "Share/Cost"], "Notes": ["Text"]}


def _figure(text: str, **names: object):
    return parse_formula(text, columns=(), inputs=["Months", "Bonus"], sheets=SHEETS, **names)


class TestAFigureReadsAWholeColumnOfASheet:
    """A key figure is computed once for the workbook: from its inputs, its other
    figures, and a sheet's WHOLE column — never a row, which it does not have."""

    def test_a_sheet_column_is_named_sheet_slash_column(self) -> None:
        formula = _figure("SUM({Monthly budget/Total}) + {Bonus}")
        assert formula.sheet_columns == frozenset({("Monthly budget", "Total")})
        assert formula.inputs == frozenset({"Bonus"}) and formula.columns == frozenset()

    def test_whatever_its_case_and_spacing_and_a_slash_in_the_column(self) -> None:
        formula = _figure("AVERAGE({ monthly BUDGET / share/cost })")
        assert formula.sheet_columns == frozenset({("Monthly budget", "Share/Cost")})

    def test_the_value_is_the_column_s_aggregate(self) -> None:
        workbook = _Figure({("Monthly budget", "Total"): [Decimal(100), None, Decimal(50)]})
        assert evaluate(_figure("SUM({Monthly budget/Total}) + {Bonus}"), workbook) == 1650
        assert evaluate(_figure("AVERAGE({Monthly budget/Total})"), workbook) == 75

    def test_an_average_of_nothing_has_no_value(self) -> None:
        workbook = _Figure({("Monthly budget", "Total"): [None, None]})
        with pytest.raises(FormulaValueError):
            evaluate(_figure("AVERAGE({Monthly budget/Total})"), workbook)

    def test_the_workbook_reads_the_sheet_s_range(self) -> None:
        assert to_excel(_figure("SUM({Monthly budget/Total}) * 2"), _Cells()) == (
            "SUM('Monthly budget'!$D$2:$D$13)*2"
        )

    def test_only_an_average_may_have_no_value(self) -> None:
        assert may_error(_figure("AVERAGE({Monthly budget/Total})")) is True
        assert may_error(_figure("SUM({Monthly budget/Total})")) is False

    @pytest.mark.parametrize(
        "text",
        [
            "{Monthly budget/Total}",
            "{Monthly budget/Total} * 2",
            "PREVIOUS({Monthly budget/Total})",
            "RUNNING_SUM({Monthly budget/Total})",
            'IF({Monthly budget/Total} = "a", 1, 0)',
            "SUM({Monthly budget/Ghost})",
            "SUM({Ghost sheet/Total})",
            "SUM({Notes/Text}, {Monthly budget/Total})",
        ],
    )
    def test_a_figure_reads_no_row_and_no_unknown_column(self, text: str) -> None:
        with pytest.raises(FormulaError):
            _figure(text)

    def test_a_row_formula_never_reads_another_sheet(self) -> None:
        with pytest.raises(FormulaError):
            parse_formula("SUM({Monthly budget/Total})", columns=["Month", "Total"])


class _Valueless(_Figure):
    """A workbook whose ``Ratio`` key figure has no value (a division by zero)."""

    def input(self, name: str) -> Decimal:
        if name == "Ratio":
            raise FormulaValueError("a figure read has no value")
        return super().input(name)


def _named(text: str):
    return parse_formula(text, columns=(), inputs=["Months", "Bonus", "Ratio"], sheets=SHEETS)


class TestANameIsAReference:
    """A defined name is a reference: what Excel does with a cell holding no number,
    it does with a key figure that has none — an empty text in the workbook."""

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("MIN({Ratio}, 5)", 5),
            ("MAX({Ratio}, {Months})", 12),
            ("MIN({Ratio}, {Ratio})", 0),
            ("MAX(IF({Months} > 1, {Ratio}, 3), 2)", 2),
        ],
    )
    def test_min_and_max_skip_a_name_with_no_value(self, text: str, expected: int) -> None:
        assert evaluate(_named(text), _Valueless({})) == expected

    @pytest.mark.parametrize("text", ["{Ratio} + 1", "ROUND({Ratio}, 2)", "MIN({Ratio} + 0, 5)"])
    def test_arithmetic_on_it_has_no_value(self, text: str) -> None:
        with pytest.raises(FormulaValueError):
            evaluate(_named(text), _Valueless({}))

    def test_a_comparison_records_the_names_it_reads_bare(self) -> None:
        formula = _named("IF(AND({Ratio} > 1, {Bonus} + 0 > 1), IF({Months} = 12, 1, 0), 0)")
        assert formula.compared_names == frozenset({"Ratio", "Months"})
        assert formula.compared == frozenset()

    def test_a_name_an_if_returns_is_compared_bare(self) -> None:
        formula = _named("IF(IF({Bonus} > 0, {Ratio}, 1) > 0.5, 1, 0)")
        assert formula.compared_names == frozenset({"Bonus", "Ratio"})

    def test_a_row_formula_records_its_compared_inputs_apart_from_its_columns(self) -> None:
        formula = parse_formula("IF({Units} > {Growth}, 1, 0)", columns=COLUMNS, inputs=INPUTS)
        assert (formula.compared, formula.compared_names) == (
            frozenset({"Units"}),
            frozenset({"Growth"}),
        )

    def test_min_and_max_do_not_spread_a_bare_name_s_missing_value(self) -> None:
        assert spreading_names(_named("MIN({Ratio}, 5) + {Bonus}")) == frozenset({"Bonus"})
        assert spreading_names(_named("MIN({Ratio} * 2, 5)")) == frozenset({"Ratio"})
        assert spreading_names(_named("SUM({Monthly budget/Total})")) == frozenset()
