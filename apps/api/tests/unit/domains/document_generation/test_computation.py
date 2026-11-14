"""One computation for every format (ADR-274 amendment).

The oracle of each value is arithmetic written in the test itself — never the
module under test — because a figure in a report, a slide, a CSV and a workbook
must be the same figure.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from itertools import accumulate

import pytest

from src.domains.document_generation.charts import chart_data
from src.domains.document_generation.columns import normalize_table
from src.domains.document_generation.computation import (
    compute_table,
    input_values,
    machine_text,
    materialize_table,
    numeric_columns,
    totals_row_index,
)
from src.domains.document_generation.renderers.xlsx_parts import number_format
from src.domains.document_generation.schemas import (
    ChartSpec,
    ColumnSpec,
    GroupSummary,
    SheetInput,
    TableSheet,
)

pytestmark = [pytest.mark.unit]

ROWS = [
    ["North", "1000", "400", "2026-01-01", "2026-01-11"],
    ["South", "800", "0", "2026-02-01", "2026-02-03"],
    ["North", "500", "450", "2026-03-01", "2026-03-31"],
]


def _canonical(*specs: ColumnSpec, summary: GroupSummary | None = None, inputs=()) -> TableSheet:
    table = normalize_table(
        TableSheet(
            name="Sales",
            headers=["Region", "Revenue", "Cost", "Start", "End"],
            rows=[list(row) for row in ROWS],
            columns=list(specs),
            summary=summary,
        ),
        "en",
        inputs=inputs,
    )
    assert table is not None
    return table


def _column(table, header: str) -> list:
    position = table.position(header)
    return [row[position] for row in table.cells]


class TestTheValuesAreTheArithmetic:
    def test_a_difference_per_row(self) -> None:
        table = compute_table(_canonical(ColumnSpec(header="Margin", formula="{Revenue} - {Cost}")))
        assert _column(table, "Margin") == [
            Decimal(1000 - 400),
            Decimal(800 - 0),
            Decimal(500 - 450),
        ]

    def test_a_division_by_zero_leaves_that_row_without_value(self) -> None:
        table = compute_table(
            _canonical(ColumnSpec(header="Ratio", formula="{Revenue} / {Cost}", kind="quantity"))
        )
        position = table.position("Ratio")
        assert (1, position) in table.errors and table.cells[1][position] is None
        assert table.cells[0][position] == Decimal(1000) / Decimal(400)

    def test_a_row_reading_a_row_without_value_has_none_either(self) -> None:
        table = compute_table(
            _canonical(
                ColumnSpec(header="Ratio", formula="{Revenue} / {Cost}"),
                ColumnSpec(header="Twice", formula="{Ratio} * 2"),
            )
        )
        assert (1, table.position("Twice")) in table.errors

    def test_dates_compute_as_days(self) -> None:
        table = compute_table(_canonical(ColumnSpec(header="Days", formula="{End} - {Start}")))
        assert _column(table, "Days") == [
            Decimal((date(2026, 1, 11) - date(2026, 1, 1)).days),
            Decimal((date(2026, 2, 3) - date(2026, 2, 1)).days),
            Decimal((date(2026, 3, 31) - date(2026, 3, 1)).days),
        ]

    def test_a_date_plus_days_is_a_date(self) -> None:
        table = compute_table(
            _canonical(ColumnSpec(header="Due", formula="{Start} + 30", kind="date"))
        )
        column = table.columns[table.position("Due")]
        assert machine_text(column, table.cells[0][table.position("Due")]) == "2026-01-31"

    def test_a_share_of_the_column_total(self) -> None:
        table = compute_table(
            _canonical(
                ColumnSpec(header="Share", formula="{Revenue} / SUM({Revenue})", kind="percent")
            )
        )
        assert _column(table, "Share")[0] == Decimal(1000) / Decimal(1000 + 800 + 500)

    def test_an_input_is_read_by_name(self) -> None:
        inputs = [SheetInput(name="Tax rate", value="25%")]
        sheet = _canonical(
            ColumnSpec(header="Net", formula="{Revenue} * (1 - {Tax rate})"), inputs=("Tax rate",)
        )
        table = compute_table(sheet, input_values(inputs))
        assert _column(table, "Net")[0] == Decimal(1000) * (1 - Decimal("0.25"))


class TestAValueNoReaderCanShowNeverFailsTheDocument:
    """Proven 2026-11-14 on the rendered document: a compound rate written whole
    (``(1 + 6) ^ 40``) raised in every format — after the writer and the pictures
    were paid for — and so did a date computed far outside the calendar."""

    def test_a_long_number_reads_the_same_everywhere(self) -> None:
        sheet = _canonical(ColumnSpec(header="Power", formula="{Revenue} ^ 12", kind="quantity"))
        table = compute_table(sheet)
        column = table.columns[table.position("Power")]
        # 1000^12 = 10^36: thirty-seven digits, exact.
        assert machine_text(column, table.cells[0][table.position("Power")]) == str(1000**12)
        shown, _summary = materialize_table(sheet, "en")
        assert shown.rows[0][shown.headers.index("Power")] == f"{1000**12:,}"

    def test_a_result_excel_cannot_hold_is_a_row_without_value(self) -> None:
        table = compute_table(_canonical(ColumnSpec(header="Huge", formula="{Revenue} * 10 ^ 400")))
        position = table.position("Huge")
        assert [row[position] for row in table.cells] == [None, None, None]
        assert {(row, position) for row in range(3)} <= table.errors

    @pytest.mark.parametrize("formula", ["{Start} + 4000000", "{Start} - 900000"])
    def test_a_date_no_calendar_holds_is_blank(self, formula: str) -> None:
        sheet = _canonical(ColumnSpec(header="Due", formula=formula, kind="date"))
        table = compute_table(sheet)
        column = table.columns[table.position("Due")]
        assert machine_text(column, table.cells[0][table.position("Due")]) == ""
        shown, _summary = materialize_table(sheet, "fr")
        assert shown.rows[0][shown.headers.index("Due")] == ""


class TestTotalsAndSummaries:
    def test_each_total_is_the_function_over_the_column(self) -> None:
        table = compute_table(
            _canonical(
                ColumnSpec(header="Revenue", total="sum"),
                ColumnSpec(header="Cost", total="average"),
                ColumnSpec(header="Region", total="count"),
                ColumnSpec(header="Margin", formula="{Revenue} - {Cost}", total="max"),
            )
        )
        totals = dict(zip((column.header for column in table.columns), table.totals, strict=True))
        assert totals["Revenue"] == Decimal(1000 + 800 + 500)
        assert totals["Cost"] == Decimal(400 + 0 + 450) / 3
        assert totals["Region"] == 3
        assert totals["Margin"] == Decimal(800)

    def test_a_summary_groups_and_sorts(self) -> None:
        table = compute_table(
            _canonical(summary=GroupSummary(by="Region", measures=["Revenue"], function="sum"))
        )
        assert table.summary is not None
        assert table.summary.groups == (
            ("North", (Decimal(1000 + 500),)),
            ("South", (Decimal(800),)),
        )

    def test_a_count_summary(self) -> None:
        table = compute_table(_canonical(summary=GroupSummary(by="Region", function="count")))
        assert table.summary is not None
        assert table.summary.groups == (("North", (Decimal(2),)), ("South", (Decimal(1),)))


class TestAReportShowsTheValuesInTheReaderConventions:
    def test_computed_values_totals_and_summary_are_written_out(self) -> None:
        sheet = _canonical(
            ColumnSpec(header="Revenue", kind="amount", unit="EUR", total="sum"),
            ColumnSpec(header="Margin", formula="{Revenue} - {Cost}", kind="amount", unit="EUR"),
            summary=GroupSummary(by="Region", measures=["Revenue"]),
        )
        shown, summary = materialize_table(sheet, "fr")
        margin = shown.headers.index("Margin")
        assert shown.rows[0][margin] == "600 €"
        assert shown.rows[-1][0] == "Total"
        assert shown.rows[-1][shown.headers.index("Revenue")] == "2 300 €"
        assert summary is not None and summary.rows[0] == ["North", "1 500 €"]
        assert [spec.header for spec in shown.columns] == ["Revenue", "Margin"]
        assert all(not spec.formula and not spec.total for spec in shown.columns)

    def test_an_average_summary_shows_the_decimals_it_needs_not_twenty_eight(self) -> None:
        sheet = _canonical(summary=GroupSummary(by="Region", measures=["Cost"], function="average"))
        _shown, summary = materialize_table(sheet, "en")
        assert summary is not None
        assert summary.rows == [["North", f"{(400 + 450) / 2:.0f}"], ["South", "0"]]

    def test_a_materialized_table_is_a_fixed_point(self) -> None:
        sheet = _canonical(
            ColumnSpec(header="Revenue", kind="amount", unit="EUR", total="sum"),
            ColumnSpec(header="Rate", formula="{Cost} / {Revenue}", kind="percent"),
        )
        shown, _summary = materialize_table(sheet, "fr")
        again = normalize_table(shown, "fr")
        assert again is not None
        assert materialize_table(again, "fr")[0] == shown

    def test_declared_numbers_stay_right_aligned_once_written_out(self) -> None:
        sheet = _canonical(ColumnSpec(header="Revenue", kind="amount", unit="EUR"))
        shown, _summary = materialize_table(sheet, "fr")
        assert numeric_columns(shown) == [False, True, True, False, False]

    def test_the_totals_row_is_found_for_the_bold(self) -> None:
        sheet = _canonical(ColumnSpec(header="Revenue", total="sum"))
        shown, _summary = materialize_table(sheet, "de")
        assert totals_row_index(shown, "de") == len(shown.rows) - 1
        assert totals_row_index(sheet, "de") is None


def _rates(*cells: str, spec: ColumnSpec, **declared: object) -> TableSheet:
    table = normalize_table(
        TableSheet(
            name="Rates",
            headers=["Product", "Rate"],
            rows=[[f"P{index}", cell] for index, cell in enumerate(cells)],
            columns=[spec],
            **declared,
        ),
        "fr",
    )
    assert table is not None
    return table


_PERCENT = ColumnSpec(header="Rate", kind="percent")


class TestAPercentageIsWrittenWithItsSign:
    """Without it a number is read as the workbook reads it — a fraction — which holds
    only when every number of the column is one: « 20 » shown « 2 000 % » is a false
    figure, and nothing says the writer meant 20 %, so the column is shown as written."""

    def test_plain_numbers_above_one_are_shown_as_written_never_a_hundredfold(self) -> None:
        sheet = _rates("20", "35", spec=_PERCENT.model_copy(update={"total": "sum"}))
        shown, _summary = materialize_table(sheet, "fr")
        assert [row[1] for row in shown.rows] == ["20", "35", "55"]
        assert shown.columns == []

    def test_one_number_above_one_is_enough(self) -> None:
        shown, _summary = materialize_table(_rates("0.5", "20", spec=_PERCENT), "fr")
        assert [row[1] for row in shown.rows] == ["0.5", "20"]

    @pytest.mark.parametrize(
        ("cells", "shown"),
        [
            (("0.2", "0.355"), ["20,000 %", "35,500 %"]),
            (("-0.25", "1"), ["-25,00 %", "100,00 %"]),
            (("20%", "35.5%"), ["20,0 %", "35,5 %"]),
        ],
    )
    def test_fractions_and_signed_percentages_read_as_percentages(
        self, cells: tuple[str, ...], shown: list[str]
    ) -> None:
        written, _summary = materialize_table(_rates(*cells, spec=_PERCENT), "fr")
        assert [row[1] for row in written.rows] == shown
        assert [spec.kind for spec in written.columns] == ["percent"]

    def test_a_summary_and_a_chart_read_them_as_the_numbers_they_are(self) -> None:
        sheet = _rates(
            "20",
            "35",
            spec=_PERCENT,
            summary=GroupSummary(by="Product", measures=["Rate"]),
            chart=ChartSpec(intent="compare", category="Product", values=["Rate"]),
        )
        _shown, summary = materialize_table(sheet, "fr")
        chart = chart_data(compute_table(sheet), "fr")
        assert summary is not None and summary.rows == [["P0", "20"], ["P1", "35"]]
        assert chart is not None and [series.kind for series in chart.series] == ["quantity"]

    def test_the_workbook_formats_them_as_the_numbers_they_are(self) -> None:
        plain = compute_table(_rates("20", "35", spec=_PERCENT)).columns[1]
        fractions = compute_table(_rates("0.2", "0.35", spec=_PERCENT)).columns[1]
        assert number_format(plain, "fr") == plain.type.number_format
        assert "%" not in number_format(plain, "fr") and "%" in number_format(fractions, "fr")

    def test_a_declaration_that_went_stays_gone(self) -> None:
        sheet = _rates("20", "35", spec=_PERCENT)
        assert normalize_table(sheet, "fr") == sheet


class TestCsvCarriesMachineValues:
    def test_a_computed_number_is_plain_and_bounded(self) -> None:
        table = compute_table(_canonical(ColumnSpec(header="Third", formula="{Revenue} / 3")))
        column = table.columns[table.position("Third")]
        assert machine_text(column, table.cells[0][table.position("Third")]) == "333.333333"

    def test_a_computed_percentage_keeps_the_writer_convention(self) -> None:
        table = compute_table(
            _canonical(ColumnSpec(header="Rate", formula="{Cost} / {Revenue}", kind="percent"))
        )
        column = table.columns[table.position("Rate")]
        assert machine_text(column, table.cells[0][table.position("Rate")]) == "40%"


class TestConditionsAndRunningSums:
    """Each value is the arithmetic written here: a running sum is the sum of the
    column down to each row, a condition reads the cell as the workbook holds it."""

    def test_a_running_sum_is_the_sum_down_to_each_row(self) -> None:
        table = compute_table(
            _canonical(ColumnSpec(header="Cumulative", formula="RUNNING_SUM({Revenue})"))
        )
        assert _column(table, "Cumulative") == list(
            accumulate([Decimal(1000), Decimal(800), Decimal(500)])
        )

    def test_a_running_sum_skips_a_row_without_value(self) -> None:
        table = compute_table(
            _canonical(
                ColumnSpec(header="Ratio", formula="{Revenue} / {Cost}"),
                ColumnSpec(header="Cumulative", formula="RUNNING_SUM({Ratio})"),
            )
        )
        first = Decimal(1000) / Decimal(400)
        assert _column(table, "Cumulative") == [
            first,
            first,
            first + Decimal(500) / Decimal(450),
        ]

    def test_a_condition_on_a_text_reads_the_written_cell(self) -> None:
        table = compute_table(
            _canonical(
                ColumnSpec(header="North revenue", formula='IF({Region} = "north", {Revenue}, 0)')
            )
        )
        assert _column(table, "North revenue") == [Decimal(1000), Decimal(0), Decimal(500)]

    def test_a_text_compares_as_the_workbook_holds_it(self) -> None:
        """ADR-226 writes a text that would read as a formula behind a quote: the
        cached comparison reads that same text, so Excel's recalculation agrees."""
        sheet = normalize_table(
            TableSheet(
                name="Items",
                headers=["Item", "Amount"],
                rows=[["=SUM(1)", "5"], ["Food", "3"]],
                columns=[ColumnSpec(header="Flag", formula='IF({Item} = "=SUM(1)", 1, 0)')],
            ),
            "en",
        )
        assert sheet is not None
        assert _column(compute_table(sheet), "Flag") == [Decimal(0), Decimal(0)]

    def test_a_column_reading_one_that_may_have_no_value_may_have_none_too(self) -> None:
        table = compute_table(
            _canonical(
                ColumnSpec(header="Ratio", formula="{Revenue} / {Cost}"),
                ColumnSpec(header="Twice", formula="{Ratio} * 2"),
                ColumnSpec(header="Margin", formula="{Revenue} - {Cost}"),
                ColumnSpec(header="Best", formula="MAX({Ratio}, 0)"),
            )
        )
        flags = {column.header: column.may_blank for column in table.columns}
        assert flags["Ratio"] and flags["Twice"]
        assert not flags["Margin"] and not flags["Best"] and not flags["Revenue"]
        # MAX skips the reference holding no number, as Excel skips the empty text.
        assert _column(table, "Best")[1] == 0


class TestAColumnNamedLikeItsInput:
    def test_each_row_shows_the_input_and_the_total_reads_it(self) -> None:
        sheet = normalize_table(
            TableSheet(
                name="Budget",
                headers=["Month", "Rent", "Food", "Total"],
                rows=[["2026-01", "", "", ""], ["2026-02", "", "", ""]],
                columns=[
                    ColumnSpec(header="Rent", formula="{Rent}"),
                    ColumnSpec(header="Food", formula="{Food}"),
                    ColumnSpec(header="Total", formula="{Rent} + {Food}"),
                ],
            ),
            "en",
            inputs=("Rent", "Food"),
        )
        assert sheet is not None
        table = compute_table(sheet, {"Rent": Decimal(1050), "Food": Decimal(520)})
        assert _column(table, "Rent") == [Decimal(1050), Decimal(1050)]
        assert _column(table, "Total") == [Decimal(1050 + 520), Decimal(1050 + 520)]
