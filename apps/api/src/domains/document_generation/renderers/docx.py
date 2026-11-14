"""docx: named styles, fields, numbering, table of contents (ADR-226, ADR-274).

Everything is a NAMED style (``docx_styles``), and everything Word computes
itself — page numbers, the table of contents, heading numbers — is a field or a
numbering definition rather than text pretending to be one.

The long-document apparatus follows ONE predicate (``document_is_numbered``):
a cover page, the table of contents, heading numbering and a page break before
each part switch on together, so a two-page note never grows an apparatus it
does not need. The cover carries neither running head nor page number (Word's
« different first page »).

Word's table of contents is PRE-RENDERED without page numbers (the ``\\n``
switch): the field is empty until Word recomputes it, so a document opened and
printed straight away would otherwise show a blank contents page. F9 regenerates
it identically.

A table of ``DOCX_LANDSCAPE_MIN_COLUMNS`` columns or more is set on landscape
pages of its own — a section Word turns, its running head and footer carried
on — and the document turns back for what follows. Every address the document
prints opens when clicked, and the sources the text cites as [n] close it,
numbered, each with its address.
"""

from __future__ import annotations

import io
import re
from collections.abc import Callable, Sequence
from typing import Any

import docx
from docx.enum.section import WD_ORIENT, WD_SECTION
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.opc.constants import RELATIONSHIP_TYPE
from docx.shared import Cm, Emu, Inches, Length, Mm, Pt, RGBColor

from src.domains.document_generation import typography
from src.domains.document_generation.charts import chart_data
from src.domains.document_generation.computation import (
    compute_table,
    numeric_columns,
    totals_row_index,
)
from src.domains.document_generation.context import RenderContext
from src.domains.document_generation.fit import AVG_CHAR_WIDTH_EM
from src.domains.document_generation.inline import parse_inline
from src.domains.document_generation.normalize import HeadingNumberer, document_is_numbered
from src.domains.document_generation.pictures import Picture, picture_key
from src.domains.document_generation.raster import svg_to_png
from src.domains.document_generation.renderers import docx_ooxml as ooxml
from src.domains.document_generation.renderers.chart_svg import draw_chart
from src.domains.document_generation.renderers.docx_styles import CALLOUT_STYLE, define_styles
from src.domains.document_generation.renderers.office_theme import recolor_theme
from src.domains.document_generation.renderers.page_figures import BandRow, plan_band
from src.domains.document_generation.renderers.page_pictures import PAGE
from src.domains.document_generation.schemas import (
    BLOCK_KINDS,
    DocumentContent,
    Illustration,
    KeyFigure,
    SectionBlock,
    SectionedContent,
    Source,
)

#: Splits the localized "Page {page} / {total}" around its two fields.
_PAGE_OF_TOKENS = re.compile(r"(\{page\}|\{total\})")
#: Splits the localized "{title} — {url}" around a source's two parts.
_SOURCE_TOKENS = re.compile(r"(\{title\}|\{url\})")
_TOC_FIELD = 'TOC \\o "1-{levels}" \\h \\z \\u \\n'
_LETTER_SIZE_IN = (8.5, 11)
_A4_SIZE_MM = (210, 297)
#: The style that heads the sources: like a part's heading, never numbered, never
#: in the contents (``docx_ooxml.detach_toc_heading``) — the apparatus' own heading.
_SOURCES_STYLE = "TOC Heading"


class _Writer:
    """Per-document state: the python-docx document, its numbering, its tables."""

    def __init__(self, content: SectionedContent, context: RenderContext) -> None:
        self.content = content
        self.context = context
        self.document = docx.Document()
        self.palette = typography.palette_for(content.tone)
        self.numbered = document_is_numbered(content, context)
        # No numberer here on purpose: WORD numbers the headings from the
        # numbering definition, and the contents entries count with their own
        # (a shared counter would number the contents and the body in one run).
        self.tables = 0
        self.figures = 0
        self.first_part_seen = False
        #: Whether the section being written is turned to landscape.
        self.landscape = False
        #: Whether the block being written opens a page a section break began.
        self.fresh_page = False
        #: The contents' closing page break, written before the first block —
        #: unless a section that turns opens that page itself.
        self.page_pending = False

    # -- setup ------------------------------------------------------------
    def setup(self) -> None:
        """Page, styles and document properties."""
        section = self.document.sections[0]
        if self.context.page_size == "letter":
            section.page_width, section.page_height = (Inches(n) for n in _LETTER_SIZE_IN)
        else:
            section.page_width, section.page_height = (Mm(n) for n in _A4_SIZE_MM)
        margin = Cm(typography.docx_margin_cm(self.context.page_size))
        section.left_margin = section.right_margin = margin
        section.top_margin = section.bottom_margin = margin
        # A long document opens on its cover: no running head, no page number.
        section.different_first_page_header_footer = self.numbered
        define_styles(self.document, numbered=self.numbered, palette=self.palette)
        if self.content.tone:
            recolor_theme(
                self.document.part.part_related_by(RELATIONSHIP_TYPE.THEME), self.palette.series
            )
        properties = self.document.core_properties
        properties.title = self.content.title
        properties.subject = self.content.subtitle
        properties.language = self.context.language
        if self.context.generated_at is not None:
            properties.created = ooxml.naive_utc(self.context.generated_at)

    # -- front matter -----------------------------------------------------
    def front_matter(self) -> None:
        """Title block — a cover page of its own when long — running head, footer, contents."""
        title = self.document.add_paragraph(self.content.title, style="Title")
        if self.numbered:
            title.paragraph_format.space_before = Pt(typography.COVER_TITLE_DROP_PT)
        if self.content.subtitle:
            self.document.add_paragraph(self.content.subtitle, style="Subtitle")
        if self.context.date_line:
            date = self.document.add_paragraph()
            date.add_run(self.context.date_line).font.color.rgb = RGBColor.from_string(
                typography.MUTED
            )
        cover = self.content.illustration
        picture = self._drawn(cover)
        if picture is not None and cover is not None:
            self._place(picture, cover, title=self.content.title)
        section = self.document.sections[0]
        header = section.header.paragraphs[0]
        header.text = self.content.title
        header.style = self.document.styles["Header"]
        self._footer(section)
        if self.numbered:
            self.document.add_page_break()
            self._table_of_contents()

    def _footer(self, section: Any) -> None:
        """« Page 2 / 7 » from PAGE and NUMPAGES, in the reader's word order."""
        footer = section.footer.paragraphs[0]
        footer.style = self.document.styles["Footer"]
        footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
        template = self.context.label("documents.page_of", page="{page}", total="{total}")
        for piece in _PAGE_OF_TOKENS.split(template):
            if piece == "{page}":
                ooxml.add_field(footer, "PAGE", "1")
            elif piece == "{total}":
                ooxml.add_field(footer, "NUMPAGES", "1")
            elif piece:
                footer.add_run(piece)

    def _toc_entries(self) -> list[tuple[int, str]]:
        numberer = HeadingNumberer()
        return [
            (block.level, f"{numberer.number(block.level)}\t{block.text}")
            for block in self.content.blocks
            if block.kind == "heading" and block.level <= ooxml.NUMBERED_LEVELS
        ]

    def _table_of_contents(self) -> None:
        self.document.add_paragraph(
            self.context.label("documents.toc_heading"), style="TOC Heading"
        )
        paragraph = None
        for index, (level, text) in enumerate(self._toc_entries()):
            paragraph = self.document.add_paragraph(style=f"TOC {level}")
            if index == 0:
                ooxml.open_field(paragraph, _TOC_FIELD.format(levels=ooxml.NUMBERED_LEVELS))
            paragraph.add_run(text)
        if paragraph is not None:
            ooxml.close_field(paragraph)
        self.page_pending = True

    # -- pages ------------------------------------------------------------
    def _text_width(self) -> Length:
        """The text width of the section being written."""
        section = self.document.sections[-1]
        return Emu(section.page_width - section.left_margin - section.right_margin)

    def _turn(self, landscape: bool) -> bool:
        """Turn the page when a wide table starts or ends; whether a new page opened."""
        if landscape == self.landscape:
            return False
        section = self.document.add_section(WD_SECTION.NEW_PAGE)
        # The clone keeps the cover's « different first page »: it would hide this
        # section's running head and page number on its first page.
        section.different_first_page_header_footer = False
        section.orientation = WD_ORIENT.LANDSCAPE if landscape else WD_ORIENT.PORTRAIT
        section.page_width, section.page_height = section.page_height, section.page_width
        self.landscape = landscape
        return True

    def write(self, block: SectionBlock, landscape: bool) -> None:
        """One block, on a page turned the way it needs.

        A section that turns opens a page of its own: the contents' closing
        page break is written only when none does, or the two together would
        leave a blank page between the contents and the first part.
        """
        turned = self._turn(landscape)
        if self.page_pending and not turned:
            self.document.add_page_break()
        self.page_pending = False
        self.fresh_page = turned
        _BLOCKS[block.kind](self, block)

    # -- blocks -----------------------------------------------------------
    def runs(self, paragraph: Any, text: str) -> None:
        """The model's inline emphasis as Word runs, its addresses as links."""
        for span in parse_inline(text):
            if span.url:
                ooxml.add_hyperlink(
                    paragraph,
                    span.url,
                    span.text,
                    color_hex=self.palette.link_ink,
                    bold=span.bold,
                    italic=span.italic,
                )
                continue
            run = paragraph.add_run(span.text)
            run.bold = span.bold or None
            run.italic = span.italic or None
            if span.code:
                run.font.name = typography.FONT_MONO

    def heading(self, block: SectionBlock) -> None:
        paragraph = self.document.add_heading(block.text, level=block.level)
        if self.numbered and block.level == 1:
            # A part opens a page — unless a section break just opened one.
            paragraph.paragraph_format.page_break_before = (
                self.first_part_seen and not self.fresh_page
            )
            self.first_part_seen = True

    def paragraph(self, block: SectionBlock) -> None:
        self.runs(self.document.add_paragraph(), block.text)

    def bullets(self, block: SectionBlock) -> None:
        for item in block.items:
            self.runs(self.document.add_paragraph(style="List Bullet"), item)

    def numbered_list(self, block: SectionBlock) -> None:
        """A fresh numbering instance per list, so every sequence restarts at 1."""
        num_id = ooxml.fresh_list_num(self.document, "List Number")
        for item in block.items:
            paragraph = self.document.add_paragraph(style="List Number")
            ooxml.set_paragraph_num(paragraph, num_id)
            self.runs(paragraph, item)

    def quote(self, block: SectionBlock) -> None:
        self.runs(self.document.add_paragraph(style="Quote"), block.text)

    def callout(self, block: SectionBlock) -> None:
        self.runs(self.document.add_paragraph(style=CALLOUT_STYLE), block.text)

    def table(self, block: SectionBlock) -> None:
        """A captioned table whose header repeats on every page it spans."""
        sheet = block.table
        if sheet is None:
            return
        self.tables += 1
        if block.caption:
            label = self.context.label("documents.table_label", n=self.tables)
            self.document.add_paragraph(f"{label} — {block.caption}", style="Caption")
        numeric = numeric_columns(sheet)
        totals = totals_row_index(sheet, self.context.language)
        table = self.document.add_table(rows=1, cols=len(sheet.headers))
        table.style = typography.DOCX_TABLE_STYLE
        table.autofit = True
        ooxml.set_table_look(table, first_column=False)
        for index, header in enumerate(sheet.headers):
            table.cell(0, index).text = header
        ooxml.mark_header_row(table.rows[0])
        for row_index, row in enumerate(sheet.rows):
            cells = table.add_row().cells
            for index, value in enumerate(row):
                paragraph = cells[index].paragraphs[0]
                paragraph.add_run(value).bold = row_index == totals or None
                if numeric[index]:
                    paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        self.document.add_paragraph()

    def chart(self, block: SectionBlock) -> None:
        """A figure at the text width, its words for a screen reader, its caption below."""
        if block.table is None:
            return
        data = chart_data(compute_table(block.table), self.context.language, self.palette.series)
        if data is None:
            return
        figure = draw_chart(data, self._text_width().pt, self.context.language)
        picture = self.document.add_picture(
            io.BytesIO(_raster(figure.svg)), width=Pt(figure.width_pt)
        )
        ooxml.describe_picture(picture, title=block.caption, description=figure.description)
        self.document.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
        self._caption(block.caption)

    def figures_band(self, block: SectionBlock) -> None:
        """Key figures as shaded tiles, each value over what it measures; a table per row.

        Two tables side by side in the XML are joined by Word into one, its grid
        taken from the first: the rows stand apart by a paragraph one point tall.
        """
        rows = plan_band(block.figures, self._text_width().pt, narrow_em=AVG_CHAR_WIDTH_EM)
        for index, row in enumerate(rows):
            if index:
                spacer = self.document.add_paragraph().paragraph_format
                spacer.space_before = spacer.space_after = Pt(0)
                spacer.line_spacing = Pt(1)
            table = self.document.add_table(rows=1, cols=len(row.figures))
            table.autofit = False
            # Word keeps half the spacing around each cell: two neighbours, one gap.
            ooxml.space_cells(
                table,
                spacing_pt=typography.PAGE_FIGURE_GAP_PT / 2,
                margin_pt=typography.PAGE_FIGURE_PADDING_PT,
            )
            for column in table.columns:
                column.width = Pt(row.tile_width_pt)
            for cell, figure in zip(table.rows[0].cells, row.figures, strict=True):
                self._tile(cell, figure, row)
        self.document.add_paragraph()

    def _tile(self, cell: Any, figure: KeyFigure, row: BandRow) -> None:
        """One shaded tile: the value in the row's size, what it measures under it."""
        cell.width = Pt(row.tile_width_pt)
        ooxml.shade_cell(cell, self.palette.wash)
        value = cell.paragraphs[0]
        value.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = value.add_run(figure.value)
        run.bold = True
        run.font.size = Pt(row.value_pt)
        run.font.color.rgb = RGBColor.from_string(self.palette.title_ink)
        if figure.label:
            label = cell.add_paragraph()
            label.alignment = WD_ALIGN_PARAGRAPH.CENTER
            words = label.add_run(figure.label)
            words.font.size = Pt(typography.PAGE_FIGURE_LABEL_PT)
            words.font.color.rgb = RGBColor.from_string(typography.MUTED)

    def illustration(self, block: SectionBlock) -> None:
        """A drawn picture as a figure, numbered with the charts, its caption below.

        A picture nobody drew writes nothing — not even a caption, which would
        number a figure that is not there.
        """
        picture = self._drawn(block.illustration)
        if picture is None or block.illustration is None:
            return
        self._place(picture, block.illustration, title=block.caption)
        self._caption(block.caption)

    def _drawn(self, illustration: Illustration | None) -> Picture | None:
        if illustration is None:
            return None
        return self.context.pictures.get(picture_key(PAGE.name, illustration.subject))

    def _place(self, picture: Picture, illustration: Illustration, *, title: str) -> None:
        """A picture centred at its frame's width — the text's, when narrower — and its words."""
        width = min(Inches(PAGE.width_in), self._text_width())
        shape = self.document.add_picture(io.BytesIO(picture.data), width=width)
        ooxml.describe_picture(shape, title=title, description=illustration.alt)
        self.document.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER

    def _caption(self, caption: str) -> None:
        """« Figure 2 — … »: one count for every figure, a chart or a picture."""
        self.figures += 1
        label = self.context.label("documents.figure_label", n=self.figures)
        self.document.add_paragraph(f"{label} — {caption}" if caption else label, style="Caption")

    # -- sources ----------------------------------------------------------
    def sources(self) -> None:
        """The sources the text cites as [n], numbered, each with its address."""
        if not self.content.sources:
            return
        self.fresh_page = self._turn(False)
        self.document.add_paragraph(
            self.context.label("documents.sources_heading"), style=_SOURCES_STYLE
        )
        hanging = Pt(typography.SOURCE_HANGING_PT)
        for number, source in enumerate(self.content.sources, start=1):
            paragraph = self.document.add_paragraph()
            paragraph.paragraph_format.left_indent = hanging
            paragraph.paragraph_format.first_line_indent = -hanging
            # The hanging indent is the tab stop: every entry's words align.
            paragraph.add_run(f"[{number}]\t")
            self._source(paragraph, source)

    def _source(self, paragraph: Any, source: Source) -> None:
        """« Title — address », the address a link; the address alone when it is the title."""
        if not source.url:
            paragraph.add_run(source.title)
            return
        if source.title == source.url:
            self._link(paragraph, source.url)
            return
        template = self.context.label("documents.source_entry", title="{title}", url="{url}")
        for piece in _SOURCE_TOKENS.split(template):
            if piece == "{title}":
                paragraph.add_run(source.title)
            elif piece == "{url}":
                self._link(paragraph, source.url)
            elif piece:
                paragraph.add_run(piece)

    def _link(self, paragraph: Any, url: str) -> None:
        ooxml.add_hyperlink(paragraph, url, url, color_hex=self.palette.link_ink)


def _raster(svg: str) -> bytes:
    """The figure as a PNG Word can hold — python-docx writes no chart part."""
    return svg_to_png(svg.encode("utf-8"), dpi=typography.CHART_RASTER_DPI)


def _wide(block: SectionBlock) -> bool:
    return (
        block.kind == "table"
        and block.table is not None
        and len(block.table.headers) >= typography.DOCX_LANDSCAPE_MIN_COLUMNS
    )


def _landscape(blocks: Sequence[SectionBlock]) -> list[bool]:
    """Which blocks stand on landscape pages: each wide table, and the headings announcing it.

    « Keep with next » does not cross a section: a heading left on the portrait
    page would stand alone at its foot — or alone on a page of its own, after a
    part's page break — while its table opens the landscape one.
    """
    turned = [_wide(block) for block in blocks]
    for index in range(len(blocks) - 2, -1, -1):
        if blocks[index].kind == "heading" and turned[index + 1]:
            turned[index] = True
    return turned


_BLOCKS: dict[str, Callable[[_Writer, SectionBlock], None]] = {
    "heading": _Writer.heading,
    "paragraph": _Writer.paragraph,
    "bullets": _Writer.bullets,
    "numbered": _Writer.numbered_list,
    "quote": _Writer.quote,
    "callout": _Writer.callout,
    "table": _Writer.table,
    "chart": _Writer.chart,
    "figures": _Writer.figures_band,
    "illustration": _Writer.illustration,
}

# Boot-time completeness (ADR-085): every block kind the schema allows is drawn.
assert set(_BLOCKS) == BLOCK_KINDS, "_BLOCKS must cover every block kind"


def render_docx(content: DocumentContent, context: RenderContext) -> bytes:
    """A Word document a reader can restyle, navigate and print."""
    if not isinstance(content, SectionedContent):
        raise ValueError("docx rendering requires SectionedContent")
    writer = _Writer(content, context)
    writer.setup()
    writer.front_matter()
    for block, landscape in zip(content.blocks, _landscape(content.blocks), strict=True):
        writer.write(block, landscape)
    writer.sources()
    buf = io.BytesIO()
    writer.document.save(buf)
    return buf.getvalue()
