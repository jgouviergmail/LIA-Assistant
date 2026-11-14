"""A workbook's chart: native, fed by the cells, gaps kept as gaps (ADR-274 amendment).

The oracle is the file itself — the chart part Excel reads (``xl/charts``), the
drawing that anchors it, and the sheets — parsed as XML, never the module's
own idea of what it wrote.
"""

from __future__ import annotations

import io
import re
import zipfile
from xml.etree import ElementTree

import pytest

from src.domains.document_generation import typography
from src.domains.document_generation.context import RenderContext
from src.domains.document_generation.renderers import render_document
from src.domains.document_generation.schemas import (
    ChartSpec,
    ColumnSpec,
    DocumentType,
    TableSheet,
    TabularContent,
)

pytestmark = [pytest.mark.unit]

_C = "{http://schemas.openxmlformats.org/drawingml/2006/chart}"
_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"


def _workbook(
    chart: ChartSpec | None,
    *,
    headers: list[str] | None = None,
    rows: list[list[str]] | None = None,
    columns: list[ColumnSpec] | None = None,
) -> zipfile.ZipFile:
    content = TabularContent(
        filename_stem="sales",
        title="Sales",
        sheets=[
            TableSheet(
                name="Sales",
                headers=headers or ["Region", "Revenue", "Cost"],
                rows=rows
                or [["North", "1000", "400"], ["South", "800", "0"], ["East", "500", "450"]],
                columns=columns or [],
                chart=chart,
            )
        ],
    )
    data = render_document(DocumentType.XLSX, content, RenderContext(language="en"))
    return zipfile.ZipFile(io.BytesIO(data))


def _chart(book: zipfile.ZipFile) -> ElementTree.Element:
    return ElementTree.fromstring(book.read("xl/charts/chart1.xml"))


def _refs(chart: ElementTree.Element, tag: str) -> list[str]:
    return [
        element.text or ""
        for element in chart.iter(f"{_C}{tag}")
        for element in element.iter(f"{_C}f")
    ]


class TestTheChartReadsTheCells:
    def test_a_comparison_is_native_columns_over_the_table(self) -> None:
        book = _workbook(ChartSpec(values=["Revenue"]))
        chart = _chart(book)
        assert chart.find(f".//{_C}barChart/{_C}barDir").get("val") == "col"
        assert _refs(chart, "cat") == ["Sales!$A$2:$A$4"]
        assert _refs(chart, "val") == ["Sales!$B$2:$B$4"]
        assert len(list(chart.iter(f"{_C}ser"))) == 1

    def test_one_series_has_no_legend_its_few_values_are_written(self) -> None:
        chart = _chart(_workbook(ChartSpec(values=["Revenue"])))
        assert chart.find(f".//{_C}legend") is None
        assert chart.find(f".//{_C}ser/{_C}dLbls/{_C}showVal").get("val") == "1"

    def test_several_series_take_the_palette_in_order_and_a_legend(self) -> None:
        chart = _chart(_workbook(ChartSpec()))
        fills = [
            ser.find(f"{_C}spPr/{_A}solidFill/{_A}srgbClr").get("val")
            for ser in chart.iter(f"{_C}ser")
        ]
        assert fills == list(typography.NEUTRAL_SERIES[:2])
        assert chart.find(f".//{_C}legend") is not None

    def test_the_chart_sits_beside_the_table_and_the_sheet_prints_landscape(self) -> None:
        book = _workbook(ChartSpec())
        drawing = book.read("xl/drawings/drawing1.xml").decode("utf-8")
        column = re.search(r"<xdr:from><xdr:col>(\d+)</xdr:col>", drawing)
        row = re.search(
            r"<xdr:from><xdr:col>\d+</xdr:col><xdr:colOff>\d+</xdr:colOff><xdr:row>(\d+)", drawing
        )
        assert column is not None and int(column.group(1)) == 4  # three columns, one apart
        assert row is not None and int(row.group(1)) == 1  # under the frozen header
        assert 'orientation="landscape"' in book.read("xl/worksheets/sheet1.xml").decode("utf-8")

    def test_no_declared_chart_writes_no_chart(self) -> None:
        book = _workbook(None)
        assert not [name for name in book.namelist() if name.startswith("xl/charts/")]


class TestAGapStaysAGap:
    def _growth(self) -> zipfile.ZipFile:
        return _workbook(
            ChartSpec(intent="trend", values=["Growth"]),
            headers=["Month", "Revenue"],
            rows=[["Jan", "100"], ["Feb", "120"], ["Mar", "90"]],
            columns=[
                ColumnSpec(
                    header="Growth", formula="{Revenue} / PREVIOUS({Revenue}) - 1", kind="percent"
                )
            ],
        )

    def test_a_column_that_can_lack_a_value_is_read_through_a_hidden_copy(self) -> None:
        book = self._growth()
        chart = _chart(book)
        assert _refs(chart, "val") == ["ChartData!$A$1:$A$3"]
        workbook = book.read("xl/workbook.xml").decode("utf-8")
        assert re.search(r'<sheet name="ChartData"[^>]*state="hidden"', workbook)

    def test_the_copy_answers_na_where_the_table_has_no_value(self) -> None:
        book = self._growth()
        names = ElementTree.fromstring(book.read("xl/workbook.xml"))
        sheets = [sheet.get("name") for sheet in names.iter() if sheet.get("name")]
        hidden = f"xl/worksheets/sheet{sheets.index('ChartData') + 1}.xml"
        sheet = book.read(hidden).decode("utf-8")
        assert "IF(ISNUMBER(Sales!$C$2),Sales!$C$2,NA())" in sheet
        first = re.search(r'<c r="A1"[^>]*t="e"[^>]*><f>[^<]+</f><v>#N/A</v>', sheet)
        assert first is not None
        second = re.search(r'<c r="A2"[^>]*><f>[^<]+</f><v>([^<]+)</v>', sheet)
        assert second is not None and float(second.group(1)) == pytest.approx(0.2)

    def test_the_chart_shows_na_as_nothing(self) -> None:
        chart = self._growth().read("xl/charts/chart1.xml").decode("utf-8")
        assert 'dispNaAsBlank val="1"' in chart
        # « gap » is Excel's own default: XlsxWriter writes the element only otherwise.
        assert "dispBlanksAs" not in chart

    def test_a_written_column_is_read_in_place(self) -> None:
        chart = _chart(_workbook(ChartSpec(intent="trend", values=["Revenue"])))
        assert _refs(chart, "val") == ["Sales!$B$2:$B$4"]


class TestTheForms:
    def test_long_labels_lie_as_bars_the_first_on_top(self) -> None:
        chart = _chart(
            _workbook(
                ChartSpec(values=["Revenue"]),
                rows=[[f"A department with a long name {i}", str(i + 1), "1"] for i in range(4)],
            )
        )
        assert chart.find(f".//{_C}barChart/{_C}barDir").get("val") == "bar"
        orientations = [element.get("val") for element in chart.iter(f"{_C}orientation")]
        assert "maxMin" in orientations
        # The value axis stays at the bottom: it crosses the reversed categories at their end.
        value_axis = chart.find(f".//{_C}valAx")
        assert value_axis is not None and value_axis.find(f"{_C}crosses").get("val") == "max"

    def test_values_too_wide_for_their_column_are_not_written(self) -> None:
        rows = [[f"U{i}", str(12345678 + i * 1111111) + ".25", "1"] for i in range(8)]
        chart = _chart(
            _workbook(
                ChartSpec(values=["Revenue"]),
                rows=rows,
                columns=[ColumnSpec(header="Revenue", kind="amount", unit="EUR")],
            )
        )
        assert chart.find(f".//{_C}barDir").get("val") == "col"
        assert chart.find(f".//{_C}ser/{_C}dLbls") is None

    def test_a_share_is_one_segmented_bar_one_series_per_part(self) -> None:
        chart = _chart(
            _workbook(
                ChartSpec(intent="share", values=["Revenue"]),
                rows=[["Web", "540", "1"], ["Shops", "0", "1"], ["Phone", "90", "1"]],
            )
        )
        assert chart.find(f".//{_C}grouping").get("val") == "percentStacked"
        names = [ser.find(f"{_C}tx/{_C}strRef/{_C}f").text for ser in chart.iter(f"{_C}ser")]
        assert names == ["Sales!$A$2", "Sales!$A$4"]  # the empty part draws nothing
        fills = [
            ser.find(f"{_C}spPr/{_A}solidFill/{_A}srgbClr").get("val")
            for ser in chart.iter(f"{_C}ser")
        ]
        colours = typography.NEUTRAL_SERIES
        assert fills == [colours[0], colours[2]]  # colour follows the row, not the rank

    def test_a_relation_is_a_scatter_with_named_axes(self) -> None:
        chart = _chart(
            _workbook(
                ChartSpec(intent="relation", values=["Revenue", "Cost"]),
                columns=[ColumnSpec(header="Revenue", kind="amount", unit="EUR")],
            )
        )
        assert chart.find(f".//{_C}scatterChart") is not None
        assert _refs(chart, "xVal") == ["Sales!$B$2:$B$4"]
        assert _refs(chart, "yVal") == ["Sales!$C$2:$C$4"]
        titles = [
            "".join(text.text or "" for text in title.iter(f"{_A}t"))
            for title in chart.iter(f"{_C}title")
        ]
        assert "Revenue" in titles and "Cost" in titles
