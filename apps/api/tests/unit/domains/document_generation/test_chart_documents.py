"""A chart in every report format: a figure, a native chart, or its values (ADR-274 amendment).

What each format can do decides what the reader gets — a vector figure in a
PDF, a described picture in Word, a native chart on a slide, the table of its
values in Markdown and plain text — and the FIGURES are the same everywhere,
because they come from one computation. Normalization says when a chart
exists at all: a table that declares one is followed by it, a chart that
cannot be drawn shows its data instead, and twice is the same as once.
"""

from __future__ import annotations

import importlib
import io
import zipfile

import pytest

from src.domains.document_generation.context import RenderContext
from src.domains.document_generation.normalize import normalize_content
from src.domains.document_generation.renderers import render_document
from src.domains.document_generation.schemas import (
    ChartSpec,
    ColumnSpec,
    DocumentType,
    SectionBlock,
    SectionedContent,
    Slide,
    SlideContent,
    TableSheet,
)

pytestmark = [pytest.mark.unit]

_CONTEXT = RenderContext(language="en")


def _sales(chart: ChartSpec | None = None, rows: list[list[str]] | None = None) -> TableSheet:
    return TableSheet(
        name="Sales",
        headers=["Region", "Revenue", "Cost"],
        rows=rows or [["North", "1000", "400"], ["South", "800", "0"], ["East", "500", "450"]],
        columns=[
            ColumnSpec(header="Revenue", kind="amount", unit="EUR"),
            ColumnSpec(header="Margin", formula="{Revenue} - {Cost}", kind="amount", unit="EUR"),
        ],
        chart=chart,
    )


def _report(*blocks: SectionBlock) -> SectionedContent:
    return SectionedContent(filename_stem="report", title="Report", blocks=list(blocks))


def _normalized(content: SectionedContent | SlideContent) -> SectionedContent | SlideContent:
    canonical = normalize_content(content, _CONTEXT)
    assert isinstance(canonical, SectionedContent | SlideContent)
    return canonical


class TestWhenAChartExists:
    def test_a_table_that_declares_a_chart_is_followed_by_it(self) -> None:
        content = _normalized(
            _report(
                SectionBlock(
                    kind="table", table=_sales(ChartSpec(values=["Margin"])), caption="Sales"
                )
            )
        )
        assert isinstance(content, SectionedContent)
        assert [block.kind for block in content.blocks] == ["table", "chart"]
        table, chart = content.blocks
        assert table.table is not None and table.table.chart is None
        assert chart.table is not None and chart.table.chart is not None
        assert chart.table.chart.values == ["Margin"]

    def test_a_chart_block_carries_the_computable_table_and_one_name(self) -> None:
        content = _normalized(
            _report(
                SectionBlock(kind="chart", table=_sales(ChartSpec(title="Margins")), caption="")
            )
        )
        assert isinstance(content, SectionedContent)
        (chart,) = content.blocks
        assert chart.kind == "chart" and chart.caption == "Margins"
        assert chart.table is not None and chart.table.chart is not None
        assert chart.table.chart.title == "Margins"
        # The formula stays symbolic: the figure is computed where it is drawn.
        assert any(spec.formula for spec in chart.table.columns)

    def test_a_chart_that_cannot_be_drawn_shows_its_data(self) -> None:
        content = _normalized(
            _report(SectionBlock(kind="chart", table=_sales(rows=[["North", "1000", "400"]])))
        )
        assert isinstance(content, SectionedContent)
        assert [block.kind for block in content.blocks] == ["table"]

    def test_twice_is_the_same_as_once(self) -> None:
        once = _normalized(
            _report(
                SectionBlock(
                    kind="table", table=_sales(ChartSpec(intent="share", values=["Revenue"]))
                ),
                SectionBlock(kind="chart", table=_sales(), caption="Plain"),
            )
        )
        twice = normalize_content(once, _CONTEXT)
        assert twice == once

    def test_a_table_slide_that_declares_a_chart_is_followed_by_a_chart_slide(self) -> None:
        deck = _normalized(
            SlideContent(
                filename_stem="deck",
                title="Deck",
                slides=[Slide(title="Sales", kind="table", table=_sales(ChartSpec()))],
            )
        )
        assert isinstance(deck, SlideContent)
        assert [slide.kind for slide in deck.slides] == ["table", "chart"]
        assert normalize_content(deck, _CONTEXT) == deck


def _render(kind: DocumentType, content: SectionedContent | SlideContent) -> bytes:
    return render_document(kind, normalize_content(content, _CONTEXT), _CONTEXT)


class TestEachFormatDrawsWhatItCan:
    def _chart_report(self) -> SectionedContent:
        return _report(
            SectionBlock(kind="paragraph", text="Before."),
            SectionBlock(
                kind="chart", table=_sales(ChartSpec(values=["Margin"])), caption="Margin"
            ),
            SectionBlock(kind="paragraph", text="After."),
        )

    def test_the_pdf_draws_a_vector_figure_whose_words_are_text(self) -> None:
        pymupdf = importlib.import_module("pymupdf")
        data = _render(DocumentType.PDF, self._chart_report())
        with pymupdf.open(stream=data, filetype="pdf") as document:
            page = document[0]
            text = page.get_text()
            assert "€600" in text and "€800" in text and "€50" in text
            assert "Figure 1 — Margin" in text
            assert page.get_drawings(), "the bars are vector paths"
            assert text.index("Before.") < text.index("Figure 1") < text.index("After.")

    def test_word_holds_a_described_picture_and_its_caption(self) -> None:
        data = _render(DocumentType.DOCX, self._chart_report())
        with zipfile.ZipFile(io.BytesIO(data)) as package:
            body = package.read("word/document.xml").decode("utf-8")
            assert [name for name in package.namelist() if name.startswith("word/media/")]
        assert 'descr="Margin — North: €600; South: €800; East: €50"' in body
        assert "Figure 1 — Margin" in body

    def test_a_slide_holds_a_native_chart(self) -> None:
        data = _render(
            DocumentType.PPTX,
            SlideContent(
                filename_stem="deck",
                title="Deck",
                slides=[
                    Slide(title="Margins", kind="chart", table=_sales(ChartSpec(values=["Margin"])))
                ],
            ),
        )
        pptx = importlib.import_module("pptx")
        presentation = pptx.Presentation(io.BytesIO(data))
        charts = [
            shape.chart
            for slide in presentation.slides
            for shape in slide.shapes
            if shape.has_chart
        ]
        assert len(charts) == 1
        plot = charts[0].plots[0]
        assert list(plot.categories) == ["North", "South", "East"]
        assert list(plot.series[0].values) == [600.0, 800.0, 50.0]

    def test_a_slide_writes_its_few_values_unless_too_wide(self) -> None:
        pptx = importlib.import_module("pptx")

        def labelled(rows: list[list[str]]) -> bool:
            data = _render(
                DocumentType.PPTX,
                SlideContent(
                    filename_stem="deck",
                    title="Deck",
                    slides=[
                        Slide(
                            title="Values",
                            kind="chart",
                            table=_sales(ChartSpec(values=["Revenue"]), rows),
                        )
                    ],
                ),
            )
            presentation = pptx.Presentation(io.BytesIO(data))
            chart = next(
                shape.chart
                for slide in presentation.slides
                for shape in slide.shapes
                if shape.has_chart
            )
            return bool(chart.plots[0].has_data_labels)

        assert labelled([["North", "1000", "1"], ["South", "800", "1"], ["East", "500", "1"]])
        wide = [[f"U{i}", str(12345678 + i * 1111111) + ".25", "1"] for i in range(8)]
        assert not labelled(wide)

    @pytest.mark.parametrize("kind", [DocumentType.MD, DocumentType.TXT])
    def test_a_text_says_every_value_of_the_figure(self, kind: DocumentType) -> None:
        text = _render(kind, self._chart_report()).decode("utf-8")
        assert "Figure 1 — Margin" in text
        for value in ("€600", "€800", "€50"):
            assert value in text

    def test_a_bar_chart_keeps_its_value_axis_below_on_a_slide(self) -> None:
        rows = [[f"A region with a long name {index}", str(index + 1), "0"] for index in range(4)]
        data = _render(
            DocumentType.PPTX,
            SlideContent(
                filename_stem="deck",
                title="Deck",
                slides=[
                    Slide(
                        title="Bars",
                        kind="chart",
                        table=_sales(ChartSpec(values=["Revenue"]), rows),
                    )
                ],
            ),
        )
        with zipfile.ZipFile(io.BytesIO(data)) as package:
            name = next(name for name in package.namelist() if name.startswith("ppt/charts/chart"))
            chart = package.read(name).decode("utf-8")
        assert '<c:barDir val="bar"/>' in chart
        assert '<c:orientation val="maxMin"/>' in chart
        value_axis = chart[chart.index("<c:valAx>") :]
        assert '<c:crosses val="max"/>' in value_axis


class TestThePdfFigureIsWhole:
    """Three defects found by LOOKING at a rendered page, each held here."""

    @pytest.mark.parametrize("paragraphs", [14, 20, 23, 26, 29])
    def test_a_figure_keeps_its_whole_height_beside_its_caption(self, paragraphs: int) -> None:
        """The Story squeezes a picture into what is left of a page (250 pt into 78):
        from 19 to 29 paragraphs before it, the figure used to come out squeezed or
        parted from its caption (measured with the fix removed)."""
        from src.domains.document_generation import typography

        pymupdf = importlib.import_module("pymupdf")
        filler = [
            SectionBlock(kind="paragraph", text=f"Paragraph {index}.")
            for index in range(paragraphs)
        ]
        data = _render(
            DocumentType.PDF,
            _report(
                *filler,
                SectionBlock(
                    kind="chart", table=_sales(ChartSpec(values=["Margin"])), caption="Margin"
                ),
                SectionBlock(kind="paragraph", text="After."),
            ),
        )
        with pymupdf.open(stream=data, filetype="pdf") as document:
            page = next(page for page in document if "Figure 1 — Margin" in page.get_text())
            paths = page.get_drawings()
            assert paths, "the figure is not on the page of its caption"
            height = max(path["rect"].y1 for path in paths) - min(path["rect"].y0 for path in paths)
            assert height >= typography.CHART_FIGURE_HEIGHT_PT - 1
            assert "€600" in page.get_text()
            assert max(path["rect"].y1 for path in paths) <= page.rect.height - 64

    def test_a_figure_stays_inside_the_text_column(self) -> None:
        pymupdf = importlib.import_module("pymupdf")
        data = _render(
            DocumentType.PDF,
            _report(SectionBlock(kind="chart", table=_sales(ChartSpec()), caption="Sales")),
        )
        with pymupdf.open(stream=data, filetype="pdf") as document:
            page = document[0]
            right = max(path["rect"].x1 for path in page.get_drawings())
            assert right <= page.rect.width - 56

    def test_the_room_of_a_figure_draws_nothing_by_itself(self) -> None:
        """A transparent pixel came out BLACK: the Story ignores its alpha."""
        pymupdf = importlib.import_module("pymupdf")
        from src.domains.document_generation import typography
        from src.domains.document_generation.renderers import pdf_layout

        room = f'<p class="figure"><img src="{pdf_layout.FIGURE_ROOM}" style="width:200pt;height:100pt"/></p>'
        laid = pdf_layout.lay_out(
            room, typography.pdf_css(), "a4", archive=pdf_layout.figure_archive()
        )
        with pymupdf.open(stream=laid.pdf, filetype="pdf") as document:
            pixmap = document[0].get_pixmap(dpi=36)
            assert min(pixmap.samples) >= 250


class TestAFigureTakesItsHeadingAlong:
    @pytest.mark.parametrize("paragraphs", [20, 23, 26])
    def test_a_heading_never_stays_alone_at_the_foot_of_a_page(self, paragraphs: int) -> None:
        pymupdf = importlib.import_module("pymupdf")
        filler = [
            SectionBlock(kind="paragraph", text=f"Paragraph {index}.")
            for index in range(paragraphs)
        ]
        data = _render(
            DocumentType.PDF,
            _report(
                *filler,
                SectionBlock(kind="heading", level=2, text="Monthly margin"),
                SectionBlock(kind="paragraph", text="The margin holds every month."),
                SectionBlock(
                    kind="chart", table=_sales(ChartSpec(values=["Margin"])), caption="Margin"
                ),
            ),
        )
        with pymupdf.open(stream=data, filetype="pdf") as document:
            page = next(page for page in document if "Figure 1 — Margin" in page.get_text())
            text = page.get_text()
            assert "Monthly margin" in text and "The margin holds every month." in text
