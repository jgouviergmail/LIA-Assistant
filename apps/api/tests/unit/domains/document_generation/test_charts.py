"""A chart: what the writer means, the form the renderer draws (ADR-274 amendment).

The writer declares an INTENT — compare, trend, share, relation — and the
renderer chooses the form from the data: a share of nine parts is compared on
bars rather than sliced, a comparison of thirty labels is never thirty crushed
columns. A form the writer names is honoured when the data can bear it.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.domains.document_generation.charts import chart_data, chart_form
from src.domains.document_generation.columns import normalize_table
from src.domains.document_generation.computation import compute_table
from src.domains.document_generation.schemas import ChartSpec, ColumnSpec, TableSheet
from src.domains.document_generation.typography import (
    CHART_BAR_MAX_CATEGORIES,
    CHART_COLUMN_MAX_CATEGORIES,
    CHART_MAX_SERIES,
    CHART_SCATTER_MAX_SERIES,
    CHART_SHARE_MAX_PARTS,
)

pytestmark = [pytest.mark.unit]

FEW = CHART_COLUMN_MAX_CATEGORIES // 2
SEVERAL = CHART_COLUMN_MAX_CATEGORIES + 1
MANY = CHART_BAR_MAX_CATEGORIES + 1


def _form(
    intent: str,
    *,
    form: str = "",
    categories: int = FEW,
    series: int = 1,
    negative: bool = False,
    long_labels: bool = False,
) -> str:
    return chart_form(
        intent,
        form,
        categories=categories,
        series=series,
        negative=negative,
        long_labels=long_labels,
    )


class TestTheFormFollowsTheData:
    @pytest.mark.parametrize(
        ("intent", "kwargs", "expected"),
        [
            ("compare", {}, "column"),
            ("compare", {"categories": SEVERAL}, "bar"),
            ("compare", {"long_labels": True}, "bar"),
            ("compare", {"categories": MANY}, "column"),
            ("trend", {}, "line"),
            ("trend", {"categories": 300}, "line"),
            ("share", {}, "segmented"),
            ("share", {"categories": CHART_SHARE_MAX_PARTS + 1}, "bar"),
            ("share", {"series": 2}, "column"),
            ("share", {"negative": True}, "column"),
            ("relation", {"series": 2}, "scatter"),
            ("relation", {"series": 1}, "column"),
        ],
    )
    def test_an_intent_takes_the_form_its_data_can_bear(
        self, intent: str, kwargs: dict, expected: str
    ) -> None:
        assert _form(intent, **kwargs) == expected

    @pytest.mark.parametrize(
        ("form", "kwargs", "expected"),
        [
            ("pie", {}, "pie"),
            ("doughnut", {}, "doughnut"),
            ("pie", {"categories": CHART_SHARE_MAX_PARTS + 3}, "bar"),
            ("pie", {"series": 2}, "column"),
            ("segmented", {"negative": True}, "column"),
            ("area", {}, "area"),
            ("line", {"categories": MANY}, "line"),
            ("scatter", {"series": 1}, "column"),
            ("scatter", {"series": 2}, "scatter"),
            ("bar", {"categories": MANY}, "column"),
            ("column", {"categories": MANY}, "column"),
        ],
    )
    def test_a_named_form_is_honoured_when_the_data_allows_it(
        self, form: str, kwargs: dict, expected: str
    ) -> None:
        assert _form("compare", form=form, **kwargs) == expected

    def test_a_single_point_never_draws_a_line(self) -> None:
        assert _form("trend", categories=1) == "column"
        assert _form("compare", form="line", categories=1) == "column"

    def test_a_relation_is_a_scatter_whatever_form_was_named(self) -> None:
        """Its values run along two axes: no other form can draw them honestly."""
        assert _form("relation", form="line", series=2) == "scatter"


def _table(
    chart: ChartSpec,
    rows: list[list[str]] | None = None,
    columns: list[ColumnSpec] | None = None,
    headers: list[str] | None = None,
) -> TableSheet:
    table = normalize_table(
        TableSheet(
            name="Sales",
            headers=headers or ["Region", "Revenue", "Cost"],
            rows=(
                rows
                if rows is not None
                else [["North", "1000", "400"], ["South", "800", "0"], ["East", "500", "450"]]
            ),
            columns=(
                columns
                if columns is not None
                else [ColumnSpec(header="Revenue", kind="amount", unit="EUR")]
            ),
            chart=chart,
        ),
        "en",
    )
    assert table is not None
    return table


class TestTheDeclarationSettles:
    def test_names_are_matched_and_unknown_values_repaired(self) -> None:
        table = _table(
            ChartSpec(
                intent="sideways", form="radar", category="region", values=["revenue", "Ghost"]
            )
        )
        assert table.chart == ChartSpec(
            intent="compare", form="", category="Region", values=["Revenue"]
        )

    def test_defaults_are_the_first_label_column_and_every_measure(self) -> None:
        table = _table(ChartSpec(intent="compare"))
        assert table.chart is not None
        assert (table.chart.category, table.chart.values) == ("Region", ["Revenue", "Cost"])

    def test_a_chart_with_no_number_to_draw_is_dropped(self) -> None:
        table = _table(
            ChartSpec(intent="compare"), rows=[["a", "x", "y"], ["b", "z", "w"]], columns=[]
        )
        assert table.chart is None

    def test_one_row_is_a_number_not_a_chart(self) -> None:
        assert _table(ChartSpec(), rows=[["North", "1000", "400"]]).chart is None

    def test_a_computed_column_can_be_drawn(self) -> None:
        table = _table(
            ChartSpec(intent="compare", values=["Margin"]),
            columns=[ColumnSpec(header="Margin", formula="{Revenue} - {Cost}", kind="amount")],
        )
        assert table.chart is not None and table.chart.values == ["Margin"]

    def test_one_chart_one_axis(self) -> None:
        """A share and an amount never share a scale; nor do two currencies."""
        table = _table(
            ChartSpec(values=["Revenue", "Rate", "Cost"]),
            headers=["Region", "Revenue", "Rate", "Cost"],
            rows=[["North", "1000", "12%", "10"], ["South", "800", "8%", "20"]],
            columns=[
                ColumnSpec(header="Revenue", kind="amount", unit="EUR"),
                ColumnSpec(header="Cost", kind="amount", unit="USD"),
            ],
        )
        assert table.chart is not None and table.chart.values == ["Revenue"]

    def test_a_declared_year_is_a_point_in_time_never_a_measure(self) -> None:
        table = _table(
            ChartSpec(intent="trend"),
            headers=["Year", "Revenue", "Cost"],
            rows=[["2024", "10", "4"], ["2025", "12", "5"]],
            columns=[ColumnSpec(header="Year", kind="year")],
        )
        assert table.chart is not None
        assert (table.chart.category, table.chart.values) == ("Year", ["Revenue", "Cost"])

    def test_series_beyond_the_palette_are_not_drawn(self) -> None:
        headers = ["Label", *(f"M{index}" for index in range(CHART_MAX_SERIES + 2))]
        rows = [
            [f"r{row}", *(str(row + index) for index in range(len(headers) - 1))]
            for row in range(3)
        ]
        table = _table(ChartSpec(), headers=headers, rows=rows, columns=[])
        assert table.chart is not None and len(table.chart.values) == CHART_MAX_SERIES

    def test_a_relation_draws_two_units_and_three_series_at_most(self) -> None:
        headers = ["Item", "Price", "Weight", "W2", "W3", "W4", "Rate"]
        rows = [["a", "10", "1", "2", "3", "4", "5%"], ["b", "12", "2", "3", "4", "5", "6%"]]
        table = _table(
            ChartSpec(intent="relation", values=["Price", "Weight", "Rate", "W2", "W3", "W4"]),
            headers=headers,
            rows=rows,
            columns=[
                ColumnSpec(header="Price", kind="amount", unit="EUR"),
                ColumnSpec(header="Weight", kind="quantity", unit="kg"),
            ],
        )
        assert table.chart is not None
        # Price runs along the horizontal axis; the percent shares no axis with
        # the weights; three Y series stay apart pair by pair.
        assert table.chart.values == ["Price", "Weight", "W2", "W3"]
        assert len(table.chart.values) == 1 + CHART_SCATTER_MAX_SERIES

    def test_normalizing_twice_changes_nothing(self) -> None:
        once = _table(ChartSpec(intent="Share", values=["cost"], title="  Costs  "))
        twice = normalize_table(once, "en")
        assert twice is not None and twice.chart == once.chart
        assert once.chart == ChartSpec(
            intent="share", category="Region", values=["Cost"], title="Costs"
        )


class TestTheDataTheRendererDraws:
    def test_categories_and_values_come_from_the_computed_table(self) -> None:
        table = _table(
            ChartSpec(intent="compare", values=["Margin"], title="Margin by region"),
            columns=[ColumnSpec(header="Margin", formula="{Revenue} - {Cost}", kind="amount")],
        )
        data = chart_data(compute_table(table), "en")
        assert data is not None
        assert data.form == "column"
        assert data.categories == ("North", "South", "East")
        assert data.series[0].name == "Margin"
        assert data.series[0].values == (Decimal(600), Decimal(800), Decimal(50))
        assert data.title == "Margin by region"
        assert data.value_positions == (3,) and data.category_position == 0

    def test_a_row_without_value_is_a_gap_not_a_zero(self) -> None:
        table = _table(
            ChartSpec(intent="trend", values=["Ratio"]),
            columns=[ColumnSpec(header="Ratio", formula="{Revenue} / {Cost}")],
        )
        data = chart_data(compute_table(table), "en")
        assert data is not None and data.series[0].values[1] is None
        assert data.series[0].present() == [Decimal("2.5"), Decimal("500") / Decimal("450")]

    def test_a_share_series_reads_as_a_percentage(self) -> None:
        table = _table(
            ChartSpec(intent="share", values=["Rate"]),
            headers=["Region", "Rate"],
            rows=[["North", "60%"], ["South", "40%"]],
            columns=[],
        )
        data = chart_data(compute_table(table), "en")
        assert data is not None and data.form == "segmented"
        assert (data.series[0].kind, data.series[0].values) == (
            "percent",
            (Decimal("0.6"), Decimal("0.4")),
        )

    def test_a_whole_of_nothing_is_compared_not_split(self) -> None:
        table = _table(
            ChartSpec(intent="share", values=["Cost"]),
            rows=[["North", "1", "0"], ["South", "2", "0"]],
        )
        data = chart_data(compute_table(table), "en")
        assert data is not None and data.form == "column"

    def test_a_date_category_reads_in_the_reader_conventions(self) -> None:
        table = _table(
            ChartSpec(intent="trend"),
            headers=["Day", "Visits"],
            rows=[["2026-11-02", "10"], ["2026-11-03", "12"]],
            columns=[ColumnSpec(header="Day", kind="date")],
        )
        data = chart_data(compute_table(table), "fr")
        assert data is not None and data.categories == ("02/11/2026", "03/11/2026")

    def test_no_declared_chart_draws_nothing(self) -> None:
        table = normalize_table(TableSheet(name="t", headers=["a", "b"], rows=[["x", "1"]]), "en")
        assert table is not None and chart_data(compute_table(table), "en") is None
