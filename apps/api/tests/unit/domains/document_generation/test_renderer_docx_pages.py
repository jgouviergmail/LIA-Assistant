"""docx: key figures, pictures, a cover, landscape pages, sources and links (ADR-274).

python-docx's own reader is the oracle here; Word's verdict on the same files is
the owner's measurement (``task documents:corpus:measure``).
"""

import io
from dataclasses import replace

import docx
import pytest
from docx.enum.section import WD_ORIENT
from docx.opc.constants import RELATIONSHIP_TYPE
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph

from src.core.config import settings
from src.core.document_preferences import DocumentPreferences
from src.domains.document_generation import typography
from src.domains.document_generation.context import RenderContext
from src.domains.document_generation.normalize import normalize_content
from src.domains.document_generation.renderers import render_document
from src.domains.document_generation.schemas import (
    DocumentType,
    Illustration,
    KeyFigure,
    SectionBlock,
    SectionedContent,
    Source,
    TableSheet,
)
from tests.helpers.document_pictures import synthetic_pictures

pytestmark = [pytest.mark.unit]

_COVER = Illustration(subject="A harbour at dawn", alt="Boats at rest in a harbour.")


@pytest.fixture(autouse=True)
def _threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the long-document threshold: the test must not depend on a tunable."""
    monkeypatch.setattr(settings, "document_generation_toc_min_headings", 4)


def _context(*, drawn: bool = True) -> RenderContext:
    return RenderContext(language="en", preferences=DocumentPreferences(images_allowed=drawn))


def _render(content: SectionedContent, *, drawn: bool = True) -> docx.document.Document:
    context = _context(drawn=drawn)
    if drawn:
        context = replace(context, pictures=synthetic_pictures(normalize_content(content, context)))
    return docx.Document(io.BytesIO(render_document(DocumentType.DOCX, content, context)))


def _report(*blocks: SectionBlock, **fields: object) -> SectionedContent:
    return SectionedContent(filename_stem="r", title="Report", blocks=list(blocks), **fields)  # type: ignore[arg-type]


def _long(*blocks: SectionBlock, **fields: object) -> SectionedContent:
    parts = [
        block
        for part in range(1, 5)
        for block in (
            SectionBlock(kind="heading", level=1, text=f"Part {part}"),
            SectionBlock(kind="paragraph", text="Body text."),
        )
    ]
    return _report(*parts, *blocks, **fields)


def _figures(*values: str) -> SectionBlock:
    return SectionBlock(
        kind="figures",
        figures=[KeyFigure(value=value, label=f"what {value} measures") for value in values],
    )


def _wide_table(columns: int = typography.DOCX_LANDSCAPE_MIN_COLUMNS) -> SectionBlock:
    headers = [f"Column {index}" for index in range(columns)]
    return SectionBlock(
        kind="table", table=TableSheet(name="t", headers=headers, rows=[["1"] * columns])
    )


def _fill(cell: object) -> str | None:
    shading = cell._tc.tcPr.find(qn("w:shd"))  # type: ignore[attr-defined]
    return None if shading is None else shading.get(qn("w:fill"))


def _section_of(document: docx.document.Document, element: object) -> int:
    """Which section an element stands in: how many section breaks come before it."""
    index = 0
    for child in document.element.body.iterchildren():
        if child is element:
            return index
        if child.tag == qn("w:p") and child.find(f"{qn('w:pPr')}/{qn('w:sectPr')}") is not None:
            index += 1
    raise AssertionError("element not in the body")


def _hyperlinks(document: docx.document.Document) -> dict[str, str]:
    """Every link's relationship id -> address."""
    return {
        rel_id: rel.target_ref
        for rel_id, rel in document.part.rels.items()
        if rel.reltype == RELATIONSHIP_TYPE.HYPERLINK and rel.is_external
    }


class TestTheBandOfKeyFigures:
    def test_figures_are_a_row_of_shaded_tiles_value_over_label(self) -> None:
        document = _render(_report(_figures("42%", "+18%", "$1.2M")))
        (table,) = document.tables
        cells = table.rows[0].cells
        assert len(cells) == 3
        assert {_fill(cell) for cell in cells} == {typography.BAND}
        first = cells[0]
        value_run = first.paragraphs[0].runs[0]
        assert (value_run.text, value_run.bold) == ("42%", True)
        assert value_run.font.size.pt == typography.PAGE_FIGURE_VALUE_PT[3]
        assert first.paragraphs[1].text == "what 42% measures"
        assert first.paragraphs[1].runs[0].font.size.pt == typography.PAGE_FIGURE_LABEL_PT
        assert len({cell.width for cell in cells}) == 1
        assert table._tbl.tblPr.find(qn("w:tblCellSpacing")) is not None

    def test_six_figures_make_two_rows_of_three(self) -> None:
        document = _render(_report(_figures(*"123456")))
        assert [len(table.rows[0].cells) for table in document.tables] == [3, 3]

    def test_two_rows_stand_apart_or_word_joins_them_into_one_table(self) -> None:
        document = _render(_report(_figures(*"12345")))
        first, second = (table._tbl for table in document.tables)
        between = first.getnext()
        assert between.tag == qn("w:p") and between.getnext() is second
        spacing = Paragraph(between, None).paragraph_format
        assert spacing.line_spacing.pt == 1

    def test_a_toned_band_takes_its_palette(self) -> None:
        document = _render(_report(_figures("42%"), tone="warm"))
        palette = typography.palette_for("warm")
        (cell,) = document.tables[0].rows[0].cells
        assert _fill(cell) == palette.wash
        assert str(cell.paragraphs[0].runs[0].font.color.rgb) == palette.title_ink

    def test_the_tile_properties_stand_in_schema_order(self) -> None:
        """Out of order, Word « repairs » the file: spacing before margins before the look."""
        document = _render(_report(_figures("42%")))
        children = [child.tag for child in document.tables[0]._tbl.tblPr]
        spacing, margins = children.index(qn("w:tblCellSpacing")), children.index(
            qn("w:tblCellMar")
        )
        assert spacing < margins
        if qn("w:tblLook") in children:
            assert margins < children.index(qn("w:tblLook"))
        tile = document.tables[0].rows[0].cells[0]._tc.tcPr
        tags = [child.tag for child in tile]
        assert tags.index(qn("w:tcW")) < tags.index(qn("w:shd"))


class TestPictures:
    def test_a_picture_is_a_figure_counted_with_the_charts(self) -> None:
        chart = SectionBlock(
            kind="chart",
            caption="Revenue",
            table=TableSheet(
                name="r", headers=["Region", "Revenue"], rows=[["North", "10"], ["South", "12"]]
            ),
        )
        picture = SectionBlock(
            kind="illustration",
            illustration=Illustration(subject="A harbour", alt="Boats at rest."),
            caption="The harbour",
        )
        document = _render(_report(chart, picture))
        captions = [p.text for p in document.paragraphs if p.style.name == "Caption"]
        assert captions == ["Figure 1 — Revenue", "Figure 2 — The harbour"]
        shapes = document.inline_shapes
        assert len(shapes) == 2
        assert shapes[1]._inline.docPr.get("descr") == "Boats at rest."
        assert (
            shapes[1].width
            <= document.sections[0].page_width - 2 * document.sections[0].left_margin
        )

    def test_a_picture_nobody_drew_writes_nothing_not_even_its_caption(self) -> None:
        picture = SectionBlock(
            kind="illustration", illustration=Illustration(subject="A harbour"), caption="Port"
        )
        document = _render(_report(SectionBlock(kind="paragraph", text="x"), picture), drawn=False)
        assert len(document.inline_shapes) == 0
        assert not [p for p in document.paragraphs if p.style.name == "Caption"]

    def test_a_short_document_s_picture_stands_under_its_title(self) -> None:
        document = _render(
            _report(SectionBlock(kind="paragraph", text="Body."), illustration=_COVER)
        )
        assert document.paragraphs[0].text == "Report"
        assert len(document.inline_shapes) == 1
        holder = document.inline_shapes[0]._inline.getparent().getparent().getparent()
        assert holder is document.paragraphs[1]._p
        assert document.inline_shapes[0]._inline.docPr.get("descr") == _COVER.alt


class TestTheCover:
    def test_a_long_document_opens_on_a_cover_of_its_own(self) -> None:
        document = _render(_long(illustration=_COVER))
        section = document.sections[0]
        assert section.different_first_page_header_footer
        assert (
            document.paragraphs[0].paragraph_format.space_before.pt
            == typography.COVER_TITLE_DROP_PT
        )
        body = document.element.body
        breaks = body.xpath('.//w:br[@w:type="page"]')
        assert len(breaks) == 2  # the cover's, then the contents'
        contents = next(p for p in document.paragraphs if p.style.name == "TOC Heading")
        picture = document.inline_shapes[0]._inline
        ordered = list(body.iter())
        assert ordered.index(picture) < ordered.index(breaks[0]) < ordered.index(contents._p)

    def test_a_short_document_has_no_cover(self) -> None:
        document = _render(_report(SectionBlock(kind="paragraph", text="Body.")))
        assert not document.sections[0].different_first_page_header_footer
        assert not document.element.body.xpath('.//w:br[@w:type="page"]')
        assert document.paragraphs[0].paragraph_format.space_before is None


class TestLandscapePages:
    def test_a_wide_table_turns_its_pages_and_the_document_turns_back(self) -> None:
        document = _render(
            _report(
                SectionBlock(kind="paragraph", text="Before."),
                _wide_table(),
                SectionBlock(kind="paragraph", text="After."),
            )
        )
        portrait, landscape, back = document.sections
        assert portrait.orientation == WD_ORIENT.PORTRAIT
        assert landscape.orientation == WD_ORIENT.LANDSCAPE
        assert landscape.page_width > landscape.page_height
        assert (back.orientation, back.page_width) == (WD_ORIENT.PORTRAIT, portrait.page_width)
        for section in (landscape, back):
            assert section.header.is_linked_to_previous
            assert section.footer.is_linked_to_previous
            assert not section.different_first_page_header_footer

    def test_a_table_one_column_short_stays_portrait(self) -> None:
        narrow = _wide_table(typography.DOCX_LANDSCAPE_MIN_COLUMNS - 1)
        assert len(_render(_report(narrow)).sections) == 1

    def test_wide_tables_in_a_row_share_their_landscape_pages(self) -> None:
        document = _render(_report(_wide_table(), _wide_table()))
        assert [section.orientation for section in document.sections] == [
            WD_ORIENT.PORTRAIT,
            WD_ORIENT.LANDSCAPE,
        ]

    def test_a_part_after_a_turn_opens_no_second_page(self) -> None:
        """The section break already opened the page: a page break too would leave one blank."""
        document = _render(
            _long(_wide_table(), SectionBlock(kind="heading", level=1, text="Annex"))
        )
        annex = next(p for p in document.paragraphs if p.text == "Annex")
        assert not annex.paragraph_format.page_break_before
        parts = [
            p for p in document.paragraphs if p.style.name == "Heading 1" and p.text != "Annex"
        ]
        assert [bool(p.paragraph_format.page_break_before) for p in parts] == [
            False,
            True,
            True,
            True,
        ]

    def test_a_heading_turns_with_the_wide_table_it_announces(self) -> None:
        """« Keep with next » stops at a section: left behind, it would stand alone."""
        document = _render(
            _report(
                SectionBlock(kind="paragraph", text="Before."),
                SectionBlock(kind="heading", level=2, text="The figures"),
                _wide_table(),
                SectionBlock(kind="paragraph", text="After."),
            )
        )
        heading = next(p for p in document.paragraphs if p.text == "The figures")
        assert _section_of(document, heading._p) == 1  # the landscape one
        assert _section_of(document, document.tables[0]._tbl) == 1
        before = next(p for p in document.paragraphs if p.text == "Before.")
        assert _section_of(document, before._p) == 0

    def test_no_blank_page_when_the_first_part_opens_on_a_wide_table(self) -> None:
        """The section break opens the page the contents' break would have: never both."""
        parts = [
            block
            for part in range(2, 5)
            for block in (
                SectionBlock(kind="heading", level=1, text=f"Part {part}"),
                SectionBlock(kind="paragraph", text="Body."),
            )
        ]
        content = _report(
            SectionBlock(kind="heading", level=1, text="Part 1"), _wide_table(), *parts
        )
        document = _render(content)
        breaks = document.element.body.xpath('.//w:br[@w:type="page"]')
        assert len(breaks) == 1  # the cover's alone
        first = next(p for p in document.paragraphs if p.text == "Part 1")
        assert _section_of(document, first._p) == 1
        assert not first.paragraph_format.page_break_before

    def test_a_long_document_s_turned_pages_keep_their_running_head(self) -> None:
        """The cover's « different first page » is cloned with its section: a turned
        section that kept it would show no running head and no page number."""
        document = _render(_long(_wide_table(), SectionBlock(kind="paragraph", text="After.")))
        cover, *turned = document.sections
        assert cover.different_first_page_header_footer
        assert len(turned) == 2
        assert not any(section.different_first_page_header_footer for section in turned)


class TestSourcesAndLinks:
    def test_the_sources_close_the_document_numbered_each_a_link(self) -> None:
        sources = [
            Source(title="Annual report", url="https://example.org/report"),
            Source(title="A book"),
            Source(title="https://example.org/data", url="https://example.org/data"),
        ]
        document = _render(
            _report(SectionBlock(kind="paragraph", text="See [1]."), sources=sources)
        )
        heading = document.paragraphs[-4]
        assert (heading.style.name, heading.text) == ("TOC Heading", "Sources")
        entries = [p.text for p in document.paragraphs[-3:]]
        assert entries == [
            "[1]\tAnnual report — https://example.org/report",
            "[2]\tA book",
            "[3]\thttps://example.org/data",
        ]
        assert sorted(_hyperlinks(document).values()) == [
            "https://example.org/data",
            "https://example.org/report",
        ]
        first = document.paragraphs[-3].paragraph_format
        assert first.first_line_indent == -first.left_indent

    def test_a_link_wears_the_ink_a_running_text_can_read(self) -> None:
        sources = [Source(title="R", url="https://example.org/r")]
        document = _render(
            _report(SectionBlock(kind="paragraph", text="x"), tone="warm", sources=sources)
        )
        (link,) = document.element.body.xpath(".//w:hyperlink")
        color = link.xpath(".//w:color")[0].get(qn("w:val"))
        assert color == typography.palette_for("warm").link_ink
        assert link.xpath(".//w:u")[0].get(qn("w:val")) == "single"

    def test_an_address_in_the_text_opens_when_clicked_and_stays_printed(self) -> None:
        text = "See [the agency](https://example.org/a_b) for **details**."
        document = _render(_report(SectionBlock(kind="paragraph", text=text)))
        (link,) = document.element.body.xpath(".//w:hyperlink")
        assert _hyperlinks(document)[link.get(qn("r:id"))] == "https://example.org/a_b"
        paragraph = next(p for p in document.paragraphs if "agency" in p.text)
        assert paragraph.text == "See the agency (https://example.org/a_b) for details."

    def test_a_wide_table_at_the_end_turns_back_for_the_sources(self) -> None:
        document = _render(_report(_wide_table(), sources=[Source(title="A")]))
        assert document.sections[-1].orientation == WD_ORIENT.PORTRAIT

    def test_no_source_no_heading(self) -> None:
        document = _render(_report(SectionBlock(kind="paragraph", text="x")))
        assert "Sources" not in [p.text for p in document.paragraphs]
