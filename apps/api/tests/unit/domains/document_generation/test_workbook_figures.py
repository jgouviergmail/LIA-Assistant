"""A workbook's key figures: computed once, from its inputs and its sheets (ADR-388).

A summary whose rows are different quantities — a year's income, the expenses of
every month, the share they leave — is no column formula: measured 2026-11-13,
three workbooks of ten left such a summary empty, or nested choices among its
line labels past the bound. A key figure says it: a label, and a formula reading
the inputs, the other figures, and a sheet's whole column. Every value here is
the arithmetic written in the test, never the module's.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.core.constants import DOCUMENT_GENERATION_WORKBOOK_FIGURES_MAX
from src.domains.document_generation.columns import normalize_table
from src.domains.document_generation.computation import compute_table, input_values
from src.domains.document_generation.schemas import (
    ColumnSpec,
    SheetInput,
    TableSheet,
    WorkbookFigure,
)
from src.domains.document_generation.workbook_figures import (
    blank_figures,
    compute_figures,
    normalize_figures,
    parsed_figures,
)

pytestmark = [pytest.mark.unit]

INPUTS = [SheetInput(name="Bonus", value="1500"), SheetInput(name="Months", value="12")]


def _sheet() -> TableSheet:
    sheet = normalize_table(
        TableSheet(
            name="Monthly budget",
            headers=["Month", "Income", "Expenses", "Note"],
            rows=[["2026-01", "3200", "2000", "rent paid"], ["2026-02", "3200", "2500", "car"]],
            columns=[ColumnSpec(header="Balance", formula="{Income} - {Expenses}")],
        ),
        "en",
        inputs=("Bonus", "Months"),
    )
    assert sheet is not None
    return sheet


def _figures(*figures: WorkbookFigure) -> list[WorkbookFigure]:
    return normalize_figures(list(figures), INPUTS, [_sheet()])


def _labels(figures: list[WorkbookFigure]) -> list[str]:
    return [figure.label for figure in figures]


ANNUAL_INCOME = WorkbookFigure(
    label="Annual income",
    formula="SUM({Monthly budget/Income}) + {Bonus}",
    kind="amount",
    unit="EUR",
)
ANNUAL_BALANCE = WorkbookFigure(label="Annual balance", formula="SUM({Monthly budget/Balance})")
SAVINGS_RATE = WorkbookFigure(
    label="Savings rate", formula="{Annual balance} / {Annual income}", kind="percent"
)


class TestAFigureIsKeptAsTheWriterSaidIt:
    def test_a_valid_figure_is_kept(self) -> None:
        assert _figures(ANNUAL_INCOME) == [ANNUAL_INCOME]

    def test_figures_read_one_another_whatever_their_order(self) -> None:
        kept = _figures(SAVINGS_RATE, ANNUAL_INCOME, ANNUAL_BALANCE)
        assert _labels(kept) == ["Savings rate", "Annual income", "Annual balance"]

    def test_a_figure_named_like_an_input_reads_it_in_its_own_formula(self) -> None:
        bonus = WorkbookFigure(label="Bonus", formula="{Bonus} / {Months}")
        assert _figures(bonus) == [bonus]

    @pytest.mark.parametrize(("kind", "expected"), [("text", ""), ("code", ""), (" Date ", "date")])
    def test_a_figure_is_a_number_or_a_date(self, kind: str, expected: str) -> None:
        (figure,) = _figures(WorkbookFigure(label="X", formula="{Bonus}", kind=kind))
        assert figure.kind == expected

    def test_the_label_kind_and_unit_are_cleaned(self) -> None:
        raw = WorkbookFigure(
            label="  Annual   income ", formula=" {Bonus} ", kind="Money", unit="EUR"
        )
        (figure,) = _figures(raw)
        assert (figure.label, figure.formula, figure.kind, figure.unit) == (
            "Annual income",
            "{Bonus}",
            "",
            "",
        )


class TestWhatCannotBeComputedGoes:
    @pytest.mark.parametrize(
        "formula",
        [
            "{Monthly budget/Income}",
            "SUM({Monthly budget/Note})",
            "SUM({Monthly budget/Ghost})",
            "PREVIOUS({Monthly budget/Income})",
            "{Ghost}",
            "",
            "1 +",
        ],
    )
    def test_a_figure_that_reads_a_row_text_or_nothing_goes(self, formula: str) -> None:
        assert _figures(WorkbookFigure(label="X", formula=formula)) == []

    def test_a_nameless_or_repeated_figure_goes(self) -> None:
        kept = _figures(
            WorkbookFigure(label="  ", formula="{Bonus}"),
            ANNUAL_INCOME,
            WorkbookFigure(label="annual INCOME", formula="{Bonus}"),
        )
        assert kept == [ANNUAL_INCOME]

    def test_a_cycle_goes_with_whatever_reads_it(self) -> None:
        kept = _figures(
            WorkbookFigure(label="A", formula="{B} + 1"),
            WorkbookFigure(label="B", formula="{A} + 1"),
            WorkbookFigure(label="C", formula="{A} * 2"),
            ANNUAL_INCOME,
        )
        assert kept == [ANNUAL_INCOME]

    def test_a_figure_reading_one_that_went_goes_too(self) -> None:
        kept = _figures(
            WorkbookFigure(label="Broken", formula="SUM({Monthly budget/Note})"),
            WorkbookFigure(label="Twice", formula="{Broken} * 2"),
            ANNUAL_INCOME,
        )
        assert kept == [ANNUAL_INCOME]

    def test_the_published_bound_is_held(self) -> None:
        many = [
            WorkbookFigure(label=f"F{index}", formula="{Bonus}")
            for index in range(DOCUMENT_GENERATION_WORKBOOK_FIGURES_MAX + 3)
        ]
        kept = _figures(*many)
        assert _labels(kept) == [f"F{index}" for index in range(len(kept))]
        assert len(kept) == DOCUMENT_GENERATION_WORKBOOK_FIGURES_MAX

    def test_normalization_is_a_fixed_point(self) -> None:
        once = _figures(
            SAVINGS_RATE,
            ANNUAL_INCOME,
            ANNUAL_BALANCE,
            WorkbookFigure(label="Broken", formula="{Ghost}"),
        )
        assert normalize_figures(once, INPUTS, [_sheet()]) == once


def _values(*figures: WorkbookFigure) -> dict[str, Decimal | None]:
    sheet = _sheet()
    values = input_values(INPUTS)
    tables = {sheet.name: compute_table(sheet, values)}
    return compute_figures(_figures(*figures), values, tables)


class TestEachFigureIsComputedOnce:
    def test_the_values_are_the_arithmetic(self) -> None:
        values = _values(SAVINGS_RATE, ANNUAL_INCOME, ANNUAL_BALANCE)
        income = Decimal(3200 + 3200) + Decimal(1500)
        balance = Decimal((3200 - 2000) + (3200 - 2500))
        assert values == {
            "Annual income": income,
            "Annual balance": balance,
            "Savings rate": balance / income,
        }

    def test_an_input_wins_over_a_figure_of_its_name_whatever_its_case(self) -> None:
        values = _values(
            WorkbookFigure(label="BONUS", formula="{Bonus} * 2"),
            WorkbookFigure(label="Half", formula="{bonus} * 0.5"),
        )
        assert values == {"BONUS": Decimal(3000), "Half": Decimal(750)}

    def test_a_figure_with_no_value_leaves_its_readers_without_one(self) -> None:
        values = _values(
            WorkbookFigure(label="Zero", formula="{Bonus} - 1500"),
            WorkbookFigure(label="Ratio", formula="{Bonus} / {Zero}"),
            WorkbookFigure(label="Twice", formula="{Ratio} * 2"),
        )
        assert values == {"Zero": Decimal(0), "Ratio": None, "Twice": None}


ZERO = WorkbookFigure(label="Zero", formula="{Bonus} - 1500")
RATIO = WorkbookFigure(label="Ratio", formula="{Bonus} / {Zero}")


class TestAFigureWithNoValueIsReadAsExcelReadsIt:
    """An empty text in the workbook, as a computed cell with no value is: held to a
    column's rules (ADR-388)."""

    def test_min_and_max_skip_it(self) -> None:
        values = _values(ZERO, RATIO, WorkbookFigure(label="Floor", formula="MIN({Ratio}, 5)"))
        assert values == {"Zero": Decimal(0), "Ratio": None, "Floor": Decimal(5)}

    def test_only_what_it_leaves_without_a_value_is_wrapped(self) -> None:
        sheet = _sheet()
        figures = _figures(
            ZERO,
            RATIO,
            WorkbookFigure(label="Floor", formula="MIN({Ratio}, 5)"),
            WorkbookFigure(label="Twice", formula="{Ratio} * 2"),
        )
        parsed = parsed_figures(
            figures,
            [item.name for item in INPUTS],
            {sheet.name: compute_table(sheet, input_values(INPUTS))},
        )
        assert blank_figures(parsed, [item.name for item in INPUTS]) == {"Ratio", "Twice"}

    def test_a_comparison_never_reads_bare_a_figure_that_may_have_none(self) -> None:
        kept = _figures(
            ANNUAL_INCOME,
            ANNUAL_BALANCE,
            SAVINGS_RATE,
            WorkbookFigure(label="Saver", formula="IF({Savings rate} >= 0.2, 1, 0)"),
            WorkbookFigure(label="Saver too", formula="IF({Savings rate} + 0 >= 0.2, 1, 0)"),
            WorkbookFigure(label="Large", formula="IF({Annual income} > 1000, 1, 0)"),
            WorkbookFigure(label="Big bonus", formula="IF({Bonus} > 100, 1, 0)"),
        )
        assert "Saver" not in _labels(kept)
        assert {"Saver too", "Large", "Big bonus"} <= set(_labels(kept))

    def test_an_input_wins_over_a_figure_of_its_name_in_a_comparison(self) -> None:
        kept = _figures(
            WorkbookFigure(label="Bonus", formula="{Bonus} / {Months}"),
            WorkbookFigure(label="Flag", formula="IF({Bonus} > 100, 1, 0)"),
        )
        assert _labels(kept) == ["Bonus", "Flag"]
