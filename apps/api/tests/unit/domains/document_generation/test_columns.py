"""What a table's columns ARE, in canonical form (ADR-274 amendment).

Every incoherence a writer can produce in a column declaration is repaired,
never refused (ADR-184): an unknown kind reads « inferred », a formula that
cannot be computed is dropped — the column keeps the cells the writer wrote,
or disappears when it had none — and normalizing twice changes nothing.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.domains.document_generation.columns import normalize_table
from src.domains.document_generation.schemas import ColumnSpec, GroupSummary, TableSheet

pytestmark = [pytest.mark.unit]


def _sheet(*specs: ColumnSpec, summary: GroupSummary | None = None, **overrides) -> TableSheet:
    base = {
        "name": "Sales",
        "headers": ["Region", "Revenue", "Cost", "Code"],
        "rows": [
            ["North", "1000", "400", "01"],
            ["South", "800", "300", "02"],
            ["North", "500", "450", "03"],
        ],
        "columns": list(specs),
        "summary": summary,
    }
    return TableSheet(**{**base, **overrides})


def _table(*specs: ColumnSpec, inputs: tuple[str, ...] = (), **overrides) -> TableSheet:
    table = normalize_table(_sheet(*specs, **overrides), "en", inputs=inputs)
    assert table is not None
    return table


class TestDeclarationsAttachToTheirColumn:
    def test_a_spec_finds_its_column_whatever_its_case_and_spacing(self) -> None:
        table = _table(ColumnSpec(header="  revenue ", kind="amount", unit="EUR"))
        assert [(spec.header, spec.kind, spec.unit) for spec in table.columns] == [
            ("Revenue", "amount", "EUR")
        ]

    def test_an_unknown_kind_or_total_is_repaired_to_nothing(self) -> None:
        table = _table(ColumnSpec(header="Revenue", kind="money", total="median"))
        assert table.columns == []

    def test_a_unit_only_belongs_to_an_amount_or_a_quantity(self) -> None:
        table = _table(ColumnSpec(header="Code", kind="code", unit="EUR"))
        assert table.columns[0].unit == ""

    def test_a_spec_for_no_column_and_without_formula_is_dropped(self) -> None:
        assert _table(ColumnSpec(header="Ghost", kind="amount")).columns == []

    def test_a_nameless_spec_never_lands_on_the_unnamed_column(self) -> None:
        table = _table(
            ColumnSpec(header=" ", kind="amount"),
            headers=["Region", ""],
            rows=[["North", "5"]],
        )
        assert table.columns == []

    def test_choices_are_cleaned_unique_and_bounded(self) -> None:
        from src.core.constants import DOCUMENT_GENERATION_COLUMN_CHOICES_MAX

        many = [f"v{index}" for index in range(DOCUMENT_GENERATION_COLUMN_CHOICES_MAX + 10)]
        table = _table(ColumnSpec(header="Region", choices=[" North", "north", "", *many]))
        choices = table.columns[0].choices
        assert choices[0] == "North" and "north" not in choices
        assert len(choices) == DOCUMENT_GENERATION_COLUMN_CHOICES_MAX


class TestComputedColumns:
    def test_a_new_computed_column_is_appended_with_empty_cells(self) -> None:
        table = _table(ColumnSpec(header="Margin", formula="{Revenue} - {Cost}", kind="amount"))
        assert table.headers[-1] == "Margin"
        assert all(row[-1] == "" for row in table.rows)
        assert table.columns[0].formula == "{Revenue} - {Cost}"

    def test_a_computed_column_the_writer_filled_is_blanked_for_the_renderer(self) -> None:
        table = _table(ColumnSpec(header="Cost", formula="{Revenue} * 0.4"))
        assert [row[2] for row in table.rows] == ["", "", ""]

    def test_an_unknown_reference_drops_the_formula_and_keeps_the_written_cells(self) -> None:
        table = _table(ColumnSpec(header="Cost", formula="{Ghost} * 2"))
        assert [row[2] for row in table.rows] == ["400", "300", "450"]
        assert table.columns == []

    def test_an_appended_column_whose_formula_fails_disappears(self) -> None:
        table = _table(ColumnSpec(header="Margin", formula="{Revenue} -"))
        assert "Margin" not in table.headers

    def test_a_formula_over_text_is_dropped(self) -> None:
        table = _table(ColumnSpec(header="Twice", formula="{Region} * 2"))
        assert "Twice" not in table.headers

    def test_a_cycle_is_dropped(self) -> None:
        table = _table(
            ColumnSpec(header="A", formula="{B} + 1"),
            ColumnSpec(header="B", formula="{A} + 1"),
            ColumnSpec(header="C", formula="{C} + 1"),
        )
        assert not {"A", "B", "C"} & set(table.headers)

    def test_a_chain_of_computed_columns_is_kept(self) -> None:
        table = _table(
            ColumnSpec(header="Margin", formula="{Revenue} - {Cost}"),
            ColumnSpec(header="Rate", formula="{Margin} / {Revenue}", kind="percent"),
        )
        assert table.headers[-2:] == ["Margin", "Rate"]

    def test_an_input_is_readable_only_in_a_workbook_that_declares_it(self) -> None:
        spec = ColumnSpec(header="Net", formula="{Revenue} * (1 - {Tax rate})")
        assert "Net" not in _table(spec).headers
        assert "Net" in _table(spec, inputs=("Tax rate",)).headers

    def test_a_computed_column_with_a_text_kind_loses_the_kind(self) -> None:
        table = _table(ColumnSpec(header="Margin", formula="{Revenue} - {Cost}", kind="code"))
        assert table.columns[0].kind == ""

    def test_a_new_column_never_takes_an_existing_name(self) -> None:
        table = _table(
            ColumnSpec(header="Margin", formula="{Revenue} - {Cost}"),
            ColumnSpec(header="margin", formula="{Revenue} * 2"),
        )
        assert table.headers.count("Margin") == 1


class TestTotalsAndSummaries:
    def test_a_sum_needs_numbers_a_count_does_not(self) -> None:
        table = _table(
            ColumnSpec(header="Region", total="sum"),
            ColumnSpec(header="Code", kind="code", total="count"),
            ColumnSpec(header="Revenue", total="sum"),
        )
        assert {spec.header: spec.total for spec in table.columns} == {
            "Code": "count",
            "Revenue": "sum",
        }

    def test_a_computed_date_is_never_summed(self) -> None:
        table = _table(
            ColumnSpec(header="Due", formula="{Revenue} + 30", kind="date", total="sum"),
            summary=GroupSummary(by="Region", measures=["Due"]),
        )
        assert table.columns[0].total == ""
        assert table.summary is None

    def test_a_summary_keeps_only_what_it_can_compute(self) -> None:
        table = _table(
            summary=GroupSummary(by="region", measures=["Revenue", "Region", "Ghost"], function="x")
        )
        assert table.summary == GroupSummary(by="Region", measures=["Revenue"], function="sum")

    def test_a_summary_by_an_unknown_column_is_dropped(self) -> None:
        assert _table(summary=GroupSummary(by="Ghost", measures=["Revenue"])).summary is None

    def test_rows_never_group_by_a_date_or_a_decimal(self) -> None:
        """A workbook matches a group by a criterion, read through regional settings."""
        assert _table(summary=GroupSummary(by="Revenue", function="count")).summary is not None
        dated = _table(
            summary=GroupSummary(by="Day", function="count"),
            headers=["Day", "Revenue"],
            rows=[["2026-01-01", "1"], ["2026-01-02", "2"]],
        )
        assert dated.summary is None

    def test_a_group_matches_without_case_like_a_workbook_criterion(self) -> None:
        from src.domains.document_generation.computation import compute_table

        table = compute_table(
            _table(
                summary=GroupSummary(by="Region", measures=["Revenue"]),
                rows=[["North", "1", "0", "a"], ["north", "2", "0", "b"]],
            )
        )
        assert table.summary is not None and table.summary.groups == (("North", (Decimal(3),)),)

    def test_a_count_summary_needs_no_measure(self) -> None:
        table = _table(summary=GroupSummary(by="Region", function="count"))
        assert table.summary == GroupSummary(by="Region", measures=[], function="count")

    def test_an_empty_table_has_no_summary(self) -> None:
        table = _table(summary=GroupSummary(by="Region", measures=["Revenue"]), rows=[])
        assert table.summary is None


class TestTheCanonicalFormIsAFixedPoint:
    def test_normalizing_twice_changes_nothing(self) -> None:
        once = _table(
            ColumnSpec(header="revenue", kind="amount", unit="EUR", total="sum", better="higher"),
            ColumnSpec(header="Margin", formula="{Revenue} - {Cost}", total="sum"),
            ColumnSpec(header="Region", choices=["North", "South"]),
            summary=GroupSummary(by="Region", measures=["Margin"]),
        )
        twice = normalize_table(once, "en")
        assert twice == once


class TestConditionsReadEachColumnAsWhatItHolds:
    """A text is compared in a text column, a number in a number column; a bare
    comparison never reads a column that may have no value — the workbook holds
    such a cell as an empty text, which Excel would compare as larger than any
    number where the cached value has none."""

    def _formulas(self, table: TableSheet) -> dict[str, str]:
        return {spec.header: spec.formula for spec in table.columns}

    def test_a_text_compared_in_a_text_column_is_kept(self) -> None:
        text = 'IF({Region} = "North", {Revenue}, 0)'
        table = _table(ColumnSpec(header="North", formula=text))
        assert self._formulas(table)["North"] == text

    def test_a_code_column_compares_as_a_text(self) -> None:
        table = _table(ColumnSpec(header="First", formula='IF({Code} = "01", 1, 0)'))
        assert "First" in table.headers

    def test_a_text_compared_in_a_number_column_is_dropped(self) -> None:
        table = _table(ColumnSpec(header="Flag", formula='IF({Revenue} = "1000", 1, 0)'))
        assert "Flag" not in table.headers

    def test_a_number_compared_in_a_text_column_is_dropped(self) -> None:
        table = _table(ColumnSpec(header="Flag", formula="IF({Region} > 1, 1, 0)"))
        assert "Flag" not in table.headers

    def test_a_bare_comparison_of_a_column_that_may_have_no_value_is_dropped(self) -> None:
        table = _table(
            ColumnSpec(header="Ratio", formula="{Revenue} / {Cost}"),
            ColumnSpec(header="High", formula="IF({Ratio} > 2, 1, 0)"),
        )
        assert "Ratio" in table.headers and "High" not in table.headers

    def test_through_an_expression_the_same_reading_is_kept(self) -> None:
        """``{Ratio} * 1`` fails on the empty text where the cached value has none: both blank."""
        table = _table(
            ColumnSpec(header="Ratio", formula="{Revenue} / {Cost}"),
            ColumnSpec(header="High", formula="IF({Ratio} * 1 > 2, 1, 0)"),
        )
        assert "High" in table.headers

    def test_a_running_sum_of_itself_is_a_cycle(self) -> None:
        table = _table(ColumnSpec(header="Total", formula="RUNNING_SUM({Total})"))
        assert "Total" not in table.headers

    def test_a_conditional_table_is_a_fixed_point(self) -> None:
        once = _table(
            ColumnSpec(header="Ratio", formula="{Revenue} / {Cost}"),
            ColumnSpec(header="North", formula='IF({Region} = "North", {Revenue}, 0)'),
            ColumnSpec(header="Cumulative", formula="RUNNING_SUM({North})"),
        )
        assert normalize_table(once, "en") == once


class TestNoValueIsComputedFromAComputationThatFailed:
    """A column a formula reads holds what the writer wrote or what is computed:
    never the void a failed computation left. The measured case (2026-11-13): a
    column named like its input read itself, its formula went, and the totals that
    read it were computed on nothing — or dropped, leaving columns delivered empty."""

    BUDGET = ["Month", "Rent", "Food", "Total"]
    EMPTY = [["2026-01", "", "", ""], ["2026-02", "", "", ""]]

    def _budget(self, *specs: ColumnSpec, inputs: tuple[str, ...], rows=None) -> TableSheet:
        table = normalize_table(
            TableSheet(
                name="Budget",
                headers=list(self.BUDGET),
                rows=[list(row) for row in (rows or self.EMPTY)],
                columns=list(specs),
            ),
            "en",
            inputs=inputs,
        )
        assert table is not None
        return table

    def _formulas(self, table: TableSheet) -> dict[str, str]:
        return {spec.header: spec.formula for spec in table.columns if spec.formula}

    def test_a_column_named_like_its_input_shows_the_input(self) -> None:
        table = self._budget(
            ColumnSpec(header="Rent", formula="{Rent}"),
            ColumnSpec(header="Food", formula="{Food}"),
            ColumnSpec(header="Total", formula="{Rent} + {Food}"),
            inputs=("Rent", "Food"),
        )
        assert self._formulas(table) == {
            "Rent": "{Rent}",
            "Food": "{Food}",
            "Total": "{Rent} + {Food}",
        }

    def test_an_empty_column_whose_formula_fails_goes_with_every_column_reading_it(
        self,
    ) -> None:
        table = self._budget(
            ColumnSpec(header="Rent", formula="{Rent}"),
            ColumnSpec(header="Food", formula="{Food}"),
            ColumnSpec(header="Total", formula="{Rent} + {Food}"),
            inputs=("Food",),
        )
        assert table.headers == ["Month", "Food"]
        assert self._formulas(table) == {"Food": "{Food}"}

    def test_a_column_keeping_what_the_writer_wrote_still_feeds_its_readers(self) -> None:
        rows = [["2026-01", "1050", "", ""], ["2026-02", "1050", "", ""]]
        table = self._budget(
            ColumnSpec(header="Rent", formula="{Ghost}"),
            ColumnSpec(header="Total", formula="{Rent} + 1"),
            inputs=(),
            rows=rows,
        )
        assert [row[1] for row in table.rows] == ["1050", "1050"]
        assert self._formulas(table) == {"Total": "{Rent} + 1"}

    def test_only_the_members_of_a_cycle_lose_their_formula(self) -> None:
        rows = [["2026-01", "1050", "520", ""], ["2026-02", "1050", "520", ""]]
        table = self._budget(
            ColumnSpec(header="Rent", formula="{Food} + 1"),
            ColumnSpec(header="Food", formula="{Rent} + 1"),
            ColumnSpec(header="Total", formula="{Rent} + {Food}"),
            inputs=(),
            rows=rows,
        )
        assert self._formulas(table) == {"Total": "{Rent} + {Food}"}
        assert [row[1:3] for row in table.rows] == [["1050", "520"], ["1050", "520"]]

    def test_an_empty_cycle_goes_with_its_readers(self) -> None:
        table = self._budget(
            ColumnSpec(header="Rent", formula="{Food} + 1"),
            ColumnSpec(header="Food", formula="{Rent} + 1"),
            ColumnSpec(header="Total", formula="{Rent} + {Food}"),
            inputs=(),
        )
        assert table.headers == ["Month"]

    def test_a_table_left_with_no_column_is_nothing_to_render(self) -> None:
        sheet = TableSheet(
            name="Budget",
            headers=["Rent", "Food"],
            rows=[["", ""], ["", ""]],
            columns=[
                ColumnSpec(header="Rent", formula="{Rent}"),
                ColumnSpec(header="Food", formula="{Rent} + 1"),
            ],
        )
        assert normalize_table(sheet, "en") is None

    def test_the_settled_table_is_a_fixed_point(self) -> None:
        once = self._budget(
            ColumnSpec(header="Rent", formula="{Rent}"),
            ColumnSpec(header="Food", formula="{Ghost}"),
            ColumnSpec(header="Total", formula="{Rent} + {Food}"),
            inputs=("Rent",),
        )
        assert normalize_table(once, "en", inputs=("Rent",)) == once
