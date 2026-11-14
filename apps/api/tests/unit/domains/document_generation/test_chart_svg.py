"""A chart drawn as SVG: round axes, honest marks, words that never collide.

The layout oracle is INDEPENDENT of the module: each figure is rendered by
MuPDF — the engine that lays it out in a PDF and rasterizes it for Word — and
the words it actually drew are read back with their boxes. No word may leave
the figure, and no two words may overlap, whatever the form, the language or
the length of a label.
"""

from __future__ import annotations

import importlib
from decimal import Decimal
from xml.etree import ElementTree

import pytest

from src.domains.document_generation import typography
from src.domains.document_generation.charts import ChartData, chart_data
from src.domains.document_generation.columns import normalize_table
from src.domains.document_generation.computation import compute_table
from src.domains.document_generation.renderers.chart_scale import nice_scale, shortened, tick_text
from src.domains.document_generation.renderers.chart_svg import describe, draw_chart
from src.domains.document_generation.schemas import ChartSpec, ColumnSpec, TableSheet

pytestmark = [pytest.mark.unit]

#: A4 text width in Word (16 cm), the narrowest a figure is drawn at.
WIDTH = 453.5
_SVG = "{http://www.w3.org/2000/svg}"


def _data(
    headers: list[str],
    rows: list[list[str]],
    chart: ChartSpec,
    columns: list[ColumnSpec] | None = None,
    language: str = "en",
) -> ChartData:
    table = normalize_table(
        TableSheet(name="t", headers=headers, rows=rows, columns=columns or [], chart=chart),
        language,
    )
    assert table is not None
    data = chart_data(compute_table(table), language)
    assert data is not None
    return data


CASES: dict[str, tuple[ChartData, str]] = {
    "column_negative": (
        _data(
            ["Region", "Revenue"],
            [["North", "1200"], ["South", "800.5"], ["East", "-150"], ["West", "430"]],
            ChartSpec(),
            [ColumnSpec(header="Revenue", kind="amount", unit="EUR")],
            "fr",
        ),
        "fr",
    ),
    "columns_grouped": (
        _data(
            ["Quarter", "North", "South", "East"],
            [["Q1", "120", "80", "60"], ["Q2", "150", "90", "40"], ["Q3", "170", "110", "70"]],
            ChartSpec(),
        ),
        "en",
    ),
    "bars_long_labels": (
        _data(
            ["Department", "Headcount"],
            [
                [f"Department of a very long and winding name {i}", str(10 + i * 7)]
                for i in range(12)
            ],
            ChartSpec(),
        ),
        "en",
    ),
    "bars_negative": (
        _data(
            ["Team", "Delta"],
            [[f"Team {i}", str((-1) ** i * (100 + i * 40))] for i in range(10)],
            ChartSpec(),
            [ColumnSpec(header="Delta", kind="amount", unit="USD")],
        ),
        "en",
    ),
    "bars_negative_on_a_tick": (
        _data(
            ["Team", "Delta"],
            [
                [f"Team number {i}", value]
                for i, value in enumerate(
                    ["-500", "300", "200", "-100", "450", "120", "80", "60", "40"]
                )
            ],
            ChartSpec(),
            [ColumnSpec(header="Delta", kind="amount", unit="EUR")],
            "fr",
        ),
        "fr",
    ),
    "columns_wide_values": (
        _data(
            ["Unit", "Budget"],
            [[f"U{i}", str(12345678 + i * 1111111) + ".25"] for i in range(8)],
            ChartSpec(),
            [ColumnSpec(header="Budget", kind="amount", unit="EUR")],
            "fr",
        ),
        "fr",
    ),
    "thin_columns": (
        _data(
            ["Item", "Units"],
            [[f"Item {i}", str(5 + i % 17)] for i in range(45)],
            ChartSpec(),
        ),
        "de",
    ),
    "line_gap_percent": (
        _data(
            ["Month", "Revenue"],
            [["Jan", "100"], ["Feb", "120"], ["Mar", "130"], ["Apr", "150"], ["May", "141"]],
            ChartSpec(intent="trend", values=["Growth"]),
            [
                ColumnSpec(
                    header="Growth", formula="{Revenue} / PREVIOUS({Revenue}) - 1", kind="percent"
                )
            ],
            "de",
        ),
        "de",
    ),
    "area_many_dates": (
        _data(
            ["Day", "Visits"],
            [[f"2026-10-{day:02d}", str(100 + (day * 37) % 90)] for day in range(1, 31)],
            ChartSpec(intent="trend", form="area"),
            [ColumnSpec(header="Day", kind="date")],
            "fr",
        ),
        "fr",
    ),
    "scatter_two_units": (
        _data(
            ["Shop", "Area", "Sales"],
            [[f"S{i}", str(50 + i * 13), str(200 + i * 41)] for i in range(14)],
            ChartSpec(intent="relation"),
            [
                ColumnSpec(header="Area", kind="quantity", unit="m²"),
                ColumnSpec(header="Sales", kind="amount", unit="EUR"),
            ],
        ),
        "en",
    ),
    "segmented": (
        _data(
            ["Channel", "Orders"],
            [["Web", "540"], ["Shops", "310"], ["Phone", "90"], ["Partners", "60"]],
            ChartSpec(intent="share"),
            language="es",
        ),
        "es",
    ),
    "doughnut_chinese": (
        _data(
            ["渠道", "订单"],
            [["网站直销渠道", "540"], ["门店", "310"], ["电话", "90"]],
            ChartSpec(intent="share", form="doughnut"),
            language="zh-CN",
        ),
        "zh-CN",
    ),
    "pie": (
        _data(
            ["Channel", "Orders"],
            [["Web", "540"], ["Shops", "310"], ["Phone", "90"], ["Partners", "60"]],
            ChartSpec(intent="share", form="pie"),
            language="it",
        ),
        "it",
    ),
}


def _spans(svg: str) -> tuple[list[tuple[str, tuple[float, float, float, float]]], object]:
    """Every word MuPDF drew, with its box, and the page it was drawn on."""
    pymupdf = importlib.import_module("pymupdf")
    page = pymupdf.open("svg", svg.encode("utf-8"))[0]
    spans = [
        (span["text"], tuple(span["bbox"]))
        for block in page.get_text("dict")["blocks"]
        for line in block.get("lines", [])
        for span in line["spans"]
        if span["text"].strip()
    ]
    return spans, page.rect


def _overlap(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    width = min(a[2], b[2]) - max(a[0], b[0])
    height = min(a[3], b[3]) - max(a[1], b[1])
    return max(0.0, width) * max(0.0, height)


class TestWordsNeverCollide:
    @pytest.mark.parametrize("name", sorted(CASES))
    def test_every_word_stays_inside_the_figure(self, name: str) -> None:
        data, language = CASES[name]
        figure = draw_chart(data, WIDTH, language)
        spans, page = _spans(figure.svg)
        assert spans, name
        for text, (x0, y0, x1, y1) in spans:
            assert x0 >= -0.5 and y0 >= -0.5, (name, text)
            assert x1 <= page.width + 0.5 and y1 <= page.height + 0.5, (name, text)

    @pytest.mark.parametrize("name", sorted(CASES))
    def test_no_two_words_overlap(self, name: str) -> None:
        """Turned labels are read back unturned by MuPDF: their boxes are skipped."""
        data, language = CASES[name]
        spans, _page = _spans(draw_chart(data, WIDTH, language).svg)
        flat = [(text, box) for text, box in spans if box[3] - box[1] < typography.PDF_STAMP_PT * 2]
        for index, (text, box) in enumerate(flat):
            for other, other_box in flat[index + 1 :]:
                assert _overlap(box, other_box) < 1.0, (name, text, other)


class TestTheAxisIsRound:
    @pytest.mark.parametrize(
        ("values", "from_zero", "ticks"),
        [
            (["0", "170"], True, ["0", "50", "100", "150", "200"]),
            (["-150", "1200"], True, ["-200", "0", "200", "400", "600", "800", "1000", "1200"]),
            (["0.059", "0.2"], False, ["0.05", "0.1", "0.15", "0.2"]),
            (["0", "0"], True, ["0", "0.25", "0.5", "0.75", "1"]),
            (["1000", "1000"], False, ["900", "950", "1000", "1050", "1100"]),
        ],
    )
    def test_ticks_are_round_numbers_holding_every_value(
        self, values: list[str], from_zero: bool, ticks: list[str]
    ) -> None:
        scale = nice_scale([Decimal(value) for value in values], from_zero=from_zero)
        assert [tick.normalize() for tick in scale.ticks] == [Decimal(t).normalize() for t in ticks]

    def test_a_bar_axis_holds_zero_a_line_axis_need_not(self) -> None:
        values = [Decimal(100), Decimal(190)]
        assert nice_scale(values, from_zero=True).low == 0
        assert nice_scale(values, from_zero=False).low > 0

    def test_a_tick_is_as_precise_as_its_step(self) -> None:
        scale = nice_scale([Decimal("0.059"), Decimal("0.2")], from_zero=False)
        assert tick_text(Decimal("0.05"), scale, "percent", "", "fr") == "5 %"
        money = nice_scale([Decimal(0), Decimal(1700)], from_zero=True)
        assert tick_text(Decimal(500), money, "amount", "EUR", "en") == "€500"


class TestTheMarks:
    def _paths(self, svg: str, color: str) -> int:
        root = ElementTree.fromstring(svg)
        return sum(1 for path in root.iter(f"{_SVG}path") if path.get("fill") == f"#{color}")

    def test_one_series_needs_no_legend_and_writes_its_few_values(self) -> None:
        data, language = CASES["column_negative"]
        svg = draw_chart(data, WIDTH, language).svg
        assert self._paths(svg, typography.NEUTRAL_SERIES[0]) == 4
        assert "Revenue" not in svg.split("</desc>")[1]
        assert "-150,00" in svg.split("</desc>")[1]

    def test_several_series_are_named_by_a_legend(self) -> None:
        data, language = CASES["columns_grouped"]
        drawn = draw_chart(data, WIDTH, language).svg.split("</desc>")[1]
        for name in ("North", "South", "East"):
            assert f">{name}<" in drawn
        assert ">120<" not in drawn  # values of grouped bars stay in the table

    def test_many_columns_carry_no_value_labels(self) -> None:
        data, language = CASES["thin_columns"]
        drawn = draw_chart(data, WIDTH, language).svg.split("</desc>")[1]
        assert ">21<" not in drawn  # 5 + 16, a value no tick can be

    def test_a_missing_value_breaks_the_line(self) -> None:
        data = _data(
            ["Month", "Value"],
            [["Jan", "1"], ["Feb", "2"], ["Mar", ""], ["Apr", "3"], ["May", "4"]],
            ChartSpec(intent="trend"),
        )
        root = ElementTree.fromstring(draw_chart(data, WIDTH, "en").svg)
        assert len(list(root.iter(f"{_SVG}polyline"))) == 2

    def test_a_part_keeps_the_colour_of_its_row(self) -> None:
        """Colour follows the entity, never its rank: a part with nothing draws nothing."""
        data = _data(
            ["Channel", "Orders"],
            [["Web", "5"], ["Shops", "0"], ["Phone", "3"]],
            ChartSpec(intent="share"),
        )
        root = ElementTree.fromstring(draw_chart(data, WIDTH, "en").svg)
        fills = [rect.get("fill") for rect in root.iter(f"{_SVG}rect")][1:]
        colours = typography.NEUTRAL_SERIES
        assert f"#{colours[1]}" not in fills
        assert f"#{colours[0]}" in fills and f"#{colours[2]}" in fills

    def test_words_are_escaped(self) -> None:
        data = _data(
            ["Label", "Value"],
            [["<b>&co</b>", "1"], ["x", "2"]],
            ChartSpec(title="A & B"),
        )
        root = ElementTree.fromstring(draw_chart(data, WIDTH, "en").svg)
        assert any(element.text == "<b>&co</b>" for element in root.iter(f"{_SVG}text"))


class TestTheDescription:
    def test_it_says_every_value_and_every_gap(self) -> None:
        data, language = CASES["line_gap_percent"]
        text = describe(data, language)
        assert text.startswith("Growth — Jan: —; Feb: 20,0")
        assert text.count(";") == len(data.categories) - 1

    def test_the_figure_carries_it_for_a_screen_reader(self) -> None:
        data, language = CASES["segmented"]
        figure = draw_chart(data, WIDTH, language)
        assert figure.description in figure.svg.replace("&amp;", "&")


class TestShortening:
    def test_a_label_that_fits_is_untouched(self) -> None:
        assert shortened("North", 8, 100) == "North"

    def test_a_long_label_ends_with_an_ellipsis_inside_the_width(self) -> None:
        from src.domains.document_generation.renderers.chart_scale import text_width

        text = shortened("A very long department name indeed", 8, 60)
        assert text.endswith("…") and text_width(text, 8) <= 60


class TestWhatIsNotDrawn:
    def test_a_chart_whose_every_value_failed_draws_nothing(self) -> None:
        table = normalize_table(
            TableSheet(
                name="t",
                headers=["Region", "Revenue", "Cost"],
                rows=[["North", "10", "0"], ["South", "20", "0"]],
                columns=[ColumnSpec(header="Ratio", formula="{Revenue} / {Cost}")],
                chart=ChartSpec(values=["Ratio"]),
            ),
            "en",
        )
        assert table is not None and table.chart is not None
        assert chart_data(compute_table(table), "en") is None

    def test_a_part_that_exists_never_reads_zero_percent(self) -> None:
        data = _data(
            ["Channel", "Orders"],
            [["Web", "990"], ["Phone", "4"], ["Shops", "6"]],
            ChartSpec(intent="share"),
        )
        drawn = draw_chart(data, WIDTH, "en").svg.split("</desc>")[1]
        assert "Phone · 0.4%" in drawn and "Web · 99%" in drawn

    def test_wide_values_are_not_written_over_their_neighbours(self) -> None:
        data, language = CASES["columns_wide_values"]
        drawn = draw_chart(data, WIDTH, language).svg.split("</desc>")[1]
        assert "12 345 678" not in drawn and "345" not in drawn
