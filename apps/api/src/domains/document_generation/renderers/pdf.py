"""pdf: stylesheet, cover, exact contents, bookmarks, tables, figures, sources (ADR-226, ADR-274).

Unlike Word, we paginate this document ourselves — so its table of contents
carries EXACT page numbers, obtained by laying the document out again until the
headings stop moving. If they never settle, the contents keeps its entries and
drops the numbers: a wrong number is worse than no number.

A long document opens on a cover — its title block and its picture on a page of
their own, stamped with neither running head nor page number — then its
contents, then its body: three layouts joined, so neither the cover nor the
contents can move a heading of the body.

Every figure — a chart, a drawn picture — is laid out as an empty ROOM of its
exact size and drawn into it afterwards (``pdf_layout.finish``): a chart as
vectors whose words stay text, a picture as the JPEG it was encoded as. Every
address the document prints opens when clicked, and the sources the text cites
as [n] close it, numbered, each with its address.

Tables carry no header background: with ``border-collapse``, MuPDF repaints a
phantom header rectangle at the top of every continuation page (measured
2026-09-08). The recipe lives in ``typography.pdf_css``.
"""

from __future__ import annotations

import functools
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC
from html import escape
from typing import Any

from src.domains.document_generation import typography
from src.domains.document_generation.charts import ChartData, chart_data
from src.domains.document_generation.computation import (
    compute_table,
    numeric_columns,
    totals_row_index,
)
from src.domains.document_generation.context import RenderContext
from src.domains.document_generation.fit import SANS_CHAR_WIDTH_EM
from src.domains.document_generation.inline import parse_inline
from src.domains.document_generation.normalize import (
    NUMBERED_LEVELS,
    HeadingNumberer,
    document_is_numbered,
)
from src.domains.document_generation.pictures import picture_key
from src.domains.document_generation.renderers import pdf_layout
from src.domains.document_generation.renderers.chart_svg import draw_chart
from src.domains.document_generation.renderers.page_figures import plan_band
from src.domains.document_generation.renderers.page_pictures import PAGE
from src.domains.document_generation.schemas import (
    BLOCK_KINDS,
    DocumentContent,
    Illustration,
    SectionBlock,
    SectionedContent,
    Source,
)
from src.domains.document_generation.typography import PageSize

#: How many times the contents may be re-laid out before its numbers are dropped.
MAX_TOC_PASSES = 3
#: The title owns h1, so content headings shift one level down.
_HEADING_SHIFT = 1
_MAX_HTML_HEADING = 5
#: The room of the document's cover picture.
COVER_ROOM = "cover-picture"
#: Splits the localized "{title} — {url}" around a source's two parts.
_SOURCE_TOKENS = re.compile(r"(\{title\}|\{url\})")
_POINTS_PER_INCH = 72.0
#: The blocks laid out as a figure: a room, a number, a caption.
_FIGURE_KINDS = frozenset({"chart", "illustration"})


def _inline_html(text: str) -> str:
    """The model's inline emphasis as escaped HTML, its addresses as links."""
    parts: list[str] = []
    for span in parse_inline(text):
        piece = escape(span.text)
        if span.code:
            piece = f"<code>{piece}</code>"
        if span.italic:
            piece = f"<i>{piece}</i>"
        if span.bold:
            piece = f"<b>{piece}</b>"
        if span.url:
            piece = f'<a href="{escape(span.url)}">{piece}</a>'
        parts.append(piece)
    return "".join(parts)


_SIMPLE_BLOCKS: dict[str, Callable[[SectionBlock], str]] = {
    "paragraph": lambda block: f"<p>{_inline_html(block.text)}</p>",
    "bullets": lambda block: "<ul>"
    + "".join(f"<li>{_inline_html(item)}</li>" for item in block.items)
    + "</ul>",
    "numbered": lambda block: "<ol>"
    + "".join(f"<li>{_inline_html(item)}</li>" for item in block.items)
    + "</ol>",
    "quote": lambda block: f"<blockquote>{_inline_html(block.text)}</blockquote>",
    "callout": lambda block: f'<div class="callout">{_inline_html(block.text)}</div>',
}

# Boot-time completeness (ADR-085). This map is deliberately PARTIAL —
# headings carry ids and numbers, tables carry a caption and column types,
# figures carry a room and a number, a band its measured sizes — so the guard
# states the complement rather than pretending to be total.
_STRUCTURED_KINDS = frozenset({"heading", "table", "figures", *_FIGURE_KINDS})
assert (
    set(_SIMPLE_BLOCKS) == BLOCK_KINDS - _STRUCTURED_KINDS
), "_SIMPLE_BLOCKS plus the structured kinds must cover the vocabulary"


def _room_html(element_id: str, room: pdf_layout.Room) -> str:
    """An empty room of the figure's exact size, for ``finish`` to draw into.

    The room is identified on its PARAGRAPH: an id on the image itself reports
    a zero-width point, the paragraph its exact box (measured).
    """
    size = f"width:{room.width_pt:.2f}pt;height:{room.height_pt:.2f}pt"
    return (
        f'<p class="figure" id="{element_id}">'
        f'<img src="{pdf_layout.FIGURE_ROOM}" style="{size}"/></p>'
    )


def _band_html(block: SectionBlock, width_pt: float) -> str:
    """Key figures as shaded tiles: a one-row table per row, its tiles one width.

    MuPDF honours a declared share of the width when the content is short
    (measured 2026-11-13: three tiles of 33.3 % laid out at 138 pt each). The
    rows stand in one band, so their gutters match the tiles' (``pdf_css``).
    """
    tables: list[str] = []
    for row in plan_band(block.figures, width_pt, narrow_em=SANS_CHAR_WIDTH_EM):
        share = f"{100 / len(row.figures):.2f}%"
        cells = "".join(
            f'<td style="width:{share}">'
            f'<p class="value" style="font-size:{row.value_pt:g}pt">{escape(figure.value)}</p>'
            + (f'<p class="label">{escape(figure.label)}</p>' if figure.label else "")
            + "</td>"
            for figure in row.figures
        )
        tables.append(f'<table class="figures"><tr>{cells}</tr></table>')
    return f'<div class="band">{"".join(tables)}</div>'


@dataclass(slots=True)
class _Count:
    """What one pass over the body has numbered so far."""

    headings: Iterator[tuple[str, int, str]]
    tables: int = 0
    figures: int = 0


class _Html:
    """Builds the document's HTML; called once per layout pass."""

    def __init__(self, content: SectionedContent, context: RenderContext) -> None:
        self.content = content
        self.context = context
        self.numbered = document_is_numbered(content, context)
        numberer = HeadingNumberer()
        #: (id, level, numbered text) in document order.
        self.headings: list[tuple[str, int, str]] = [
            (
                f"h-{index}",
                block.level,
                f"{numberer.number(block.level) if self.numbered else ''} {block.text}".strip(),
            )
            for index, block in enumerate(content.blocks)
            if block.kind == "heading"
        ]
        self.palette = typography.palette_for(content.tone)
        self.css = typography.pdf_css(self.palette)
        #: Each figure's room by block index — a chart drawn ONCE, a picture as drawn.
        self.rooms: dict[int, pdf_layout.Room] = {
            index: room
            for index, block in enumerate(content.blocks)
            if (room := self._room_of(block)) is not None
        }
        self.cover = self._picture_room(content.illustration)
        #: Figures that start a page of their own (``squeezed`` says which).
        self.breaks: set[int] = set()

    @functools.cached_property
    def width(self) -> float:
        """The width the Story gives a paragraph: every figure and band is set to it."""
        return pdf_layout.paragraph_width(self.css, self.context.page_size)

    def _room_of(self, block: SectionBlock) -> pdf_layout.Room | None:
        if block.kind == "illustration":
            return self._picture_room(block.illustration)
        if block.kind != "chart" or block.table is None:
            return None
        data = _chart_of(block.table, self.context.language, self.palette.series)
        if data is None:
            return None
        figure = draw_chart(data, self.width, self.context.language)
        return pdf_layout.Room(figure.svg, figure.width_pt, figure.height_pt)

    def _picture_room(self, illustration: Illustration | None) -> pdf_layout.Room | None:
        """A drawn picture's room: its frame's width — the paragraph's, when narrower."""
        if illustration is None:
            return None
        picture = self.context.pictures.get(picture_key(PAGE.name, illustration.subject))
        if picture is None:
            return None
        width = min(PAGE.width_in * _POINTS_PER_INCH, self.width)
        return pdf_layout.Room(picture.data, width, width / PAGE.aspect)

    def squeezed(self, positions: dict[str, pdf_layout.Placed]) -> set[int]:
        """Figures the Story squeezed into a page's end, or parted from their caption.

        The Story never moves an image to the next page: it shrinks it into
        what is left (measured 2026-11-13: 250 pt laid out as 78 pt). Such a
        figure, and one whose caption fell onto the next page, starts a page of
        its own on the next pass.
        """
        squeezed: set[int] = set()
        for index, room in self.rooms.items():
            placed = positions.get(_figure_id(index))
            caption = positions.get(f"{_figure_id(index)}-caption")
            if index in self.breaks or placed is None:
                continue
            short = placed.rect.height < room.height_pt - 0.5
            if short or (caption is not None and caption.page != placed.page):
                squeezed.add(index)
        return squeezed

    def archive(self) -> Any | None:
        """The archive the rooms read, or ``None`` when there is no figure."""
        return pdf_layout.figure_archive() if self.rooms or self.cover else None

    def drawings(self) -> dict[str, pdf_layout.Room]:
        """Every room by its id, for ``pdf_layout.finish`` to draw into."""
        rooms = {_figure_id(index): room for index, room in self.rooms.items()}
        if self.cover is not None:
            rooms[COVER_ROOM] = self.cover
        return rooms

    def _figure(self, index: int, number: int, block: SectionBlock) -> str:
        """The figure's room at its exact size, its caption below it."""
        room = self.rooms.get(index)
        if room is None:
            return ""
        label = self.context.label("documents.figure_label", n=number)
        caption = f"{label} — {block.caption}" if block.caption else label
        element_id = _figure_id(index)
        return (
            _room_html(element_id, room)
            + f'<p class="caption" id="{element_id}-caption">{escape(caption)}</p>'
        )

    def _title_block(self) -> str:
        parts = [f"<h1>{escape(self.content.title)}</h1>"]
        if self.content.subtitle:
            parts.append(f'<p class="subtitle">{escape(self.content.subtitle)}</p>')
        if self.context.date_line:
            parts.append(f'<p class="date">{escape(self.context.date_line)}</p>')
        if self.cover is not None:
            parts.append(_room_html(COVER_ROOM, self.cover))
        return "".join(parts)

    def cover_page(self) -> str:
        """A long document's cover: its title block and picture, set lower on the page."""
        return f'<div class="cover">{self._title_block()}</div>'

    def contents(self, toc_pages: dict[str, int] | None) -> str:
        """The table of contents, numbered with ``toc_pages`` when they are known."""
        parts = [f"<h2>{escape(self.context.label('documents.toc_heading'))}</h2>"]
        for element_id, level, text in self.headings:
            if level > NUMBERED_LEVELS:
                continue
            page = toc_pages.get(element_id) if toc_pages else None
            suffix = f" — {page}" if page else ""
            parts.append(f'<p class="toc{level}" id="toc-{element_id}">{escape(text)}{suffix}</p>')
        return "".join(parts)

    def _table(self, block: SectionBlock, index: int, number: int) -> str:
        sheet = block.table
        if sheet is None:
            return ""
        classes = ['class="num"' if numeric else "" for numeric in numeric_columns(sheet)]
        totals = totals_row_index(sheet, self.context.language)
        header = (
            "<tr>"
            + "".join(
                f"<th {css}>{escape(name)}</th>"
                for name, css in zip(sheet.headers, classes, strict=True)
            )
            + "</tr>"
        )
        rows = "".join(
            f'<tr id="r-{index}-{row_index}"'
            + (' class="total">' if row_index == totals else ">")
            + "".join(
                f"<td {css}>{escape(value)}</td>" for value, css in zip(row, classes, strict=True)
            )
            + "</tr>"
            for row_index, row in enumerate(sheet.rows)
        )
        label = self.context.label("documents.table_label", n=number)
        caption = (
            f'<p class="caption">{escape(label)} — {escape(block.caption)}</p>'
            if block.caption
            else ""
        )
        # A many-column table runs off the page at the base size: MuPDF sizes
        # columns from their content whatever the declared width (measured).
        css_class = typography.pdf_table_class(len(sheet.headers))
        opening = f'<table class="{css_class}">' if css_class else "<table>"
        return f"{caption}{opening}{header}{rows}</table>"

    def _block(self, index: int, block: SectionBlock, count: _Count) -> str:
        """One block's HTML, numbered in the pass's count."""
        if block.kind == "heading":
            element_id, level, text = next(count.headings)
            tag = min(level + _HEADING_SHIFT, _MAX_HTML_HEADING)
            return f'<h{tag} id="{element_id}">{escape(text)}</h{tag}>'
        if block.kind == "table":
            count.tables += 1
            return self._table(block, index, count.tables)
        if block.kind in _FIGURE_KINDS:
            count.figures += 1 if index in self.rooms else 0
            return self._figure(index, count.figures, block)
        if block.kind == "figures":
            return _band_html(block, self.width)
        return _SIMPLE_BLOCKS[block.kind](block)

    def _sources(self) -> str:
        """The sources the text cites as [n], numbered, each with its address."""
        if not self.content.sources:
            return ""
        heading = escape(self.context.label("documents.sources_heading"))
        entries = "".join(
            f'<p class="source">[{number}]&#160;{self._source(source)}</p>'
            for number, source in enumerate(self.content.sources, start=1)
        )
        return f"<h2>{heading}</h2>{entries}"

    def _source(self, source: Source) -> str:
        """« Title — address », the address a link; the address alone when it is the title."""
        if not source.url:
            return escape(source.title)
        link = f'<a href="{escape(source.url)}">{escape(source.url)}</a>'
        if source.title == source.url:
            return link
        template = self.context.label("documents.source_entry", title="{title}", url="{url}")
        return "".join(
            (
                escape(source.title)
                if piece == "{title}"
                else link if piece == "{url}" else escape(piece)
            )
            for piece in _SOURCE_TOKENS.split(template)
        )

    def body(self) -> list[str]:
        """The content itself — never the contents, so its pagination is stable.

        It comes in PARTS, each laid out from the top of a page: a figure the
        Story squeezed starts a part of its own. A CSS page break would say the
        same, but MuPDF's Story cycles on one before a picture in a real
        document (measured 2026-11-13: pages 2 and 3 repeated without end).
        """
        parts: list[list[str]] = [[]]
        count = _Count(headings=iter(self.headings))
        cuts = {self._cut_before(index) for index in self.breaks}
        for index, block in enumerate(self.content.blocks):
            if index in cuts and parts[-1]:
                parts.append([])
            parts[-1].append(self._block(index, block, count))
        parts[-1].append(self._sources())
        return ["".join(part) for part in parts]

    def _cut_before(self, index: int) -> int:
        """Where a figure's page starts: with the heading that announces it.

        A heading — and the one paragraph that may introduce the figure — never
        stays alone at the foot of a page while its figure opens the next one.
        """
        blocks = self.content.blocks
        if index >= 1 and blocks[index - 1].kind == "heading":
            return index - 1
        introduced = index >= 2 and blocks[index - 1].kind == "paragraph"
        if introduced and blocks[index - 2].kind == "heading":
            return index - 2
        return index

    def build(self) -> list[str]:
        """A short document: its title block and its body in one flow, still cut at breaks."""
        parts = self.body()
        return [self._title_block() + parts[0], *parts[1:]]


def _figure_id(index: int) -> str:
    return f"fig-{index}"


def _chart_of(table: Any, language: str, colors: tuple[str, ...]) -> ChartData | None:
    return chart_data(compute_table(table), language, colors)


def _lay_out_parts(
    parts: list[str], css: str, page_size: PageSize, archive: Any | None
) -> pdf_layout.LaidOut:
    """Each part from the top of a page, the parts joined in order."""
    laid = pdf_layout.lay_out(parts[0], css, page_size, archive=archive)
    for part in parts[1:]:
        laid = pdf_layout.concatenate(
            laid, pdf_layout.lay_out(part, css, page_size, archive=archive)
        )
    return laid


def _whole_figures(
    html: _Html,
    render: Callable[[], list[str]],
    css: str,
    page_size: PageSize,
    archive: Any | None,
) -> pdf_layout.LaidOut:
    """Lay the HTML out until every figure has its whole room and its caption.

    Each pass that finds a squeezed figure gives it a page of its own, which
    only ever moves figures down: one pass per figure at most.
    """
    laid = _lay_out_parts(render(), css, page_size, archive)
    for _figure in html.rooms:
        squeezed = html.squeezed(laid.positions)
        if not squeezed:
            break
        html.breaks |= squeezed
        laid = _lay_out_parts(render(), css, page_size, archive)
    return laid


def _outline(
    headings: list[tuple[str, int, str]], positions: dict[str, pdf_layout.Placed]
) -> list[tuple[int, str, int]]:
    """Bookmarks whose hierarchy a PDF reader accepts.

    A reader requires the first bookmark to be level 1 and refuses a level that
    jumps by more than one — while a document legitimately opens at heading
    level 2 (the title owns level 1) or skips a level. Depths are therefore
    RE-BASED on the shallowest heading and never allowed to jump.
    """
    placed = [
        (level, text, positions[eid].page) for eid, level, text in headings if eid in positions
    ]
    if not placed:
        return []
    shallowest = min(level for level, _text, _page in placed)
    outline: list[tuple[int, str, int]] = []
    previous = 0
    for level, text, page in placed:
        depth = min(level - shallowest + 1, previous + 1)
        outline.append((depth, text, page))
        previous = depth
    return outline


def _heading_pages(laid: pdf_layout.LaidOut) -> dict[str, int]:
    return {
        element_id: placed.page
        for element_id, placed in laid.positions.items()
        if element_id.startswith("h-")
    }


def _long_document(
    html: _Html, css: str, page_size: PageSize, archive: Any | None
) -> tuple[pdf_layout.LaidOut, bool]:
    """Cover, then contents on its own page(s), then the body, with EXACT page numbers.

    The body is laid out ONCE — it never contains the contents, so nothing it
    does can move — and so is the cover; the contents is laid out twice at most:
    once to learn how many pages it takes, once with the numbers that follow
    from it. If adding the numbers changes its own length (a two-digit number
    wrapping a line), the second pass is repeated within ``MAX_TOC_PASSES``;
    failing that the contents keeps its entries and drops the numbers, because
    a wrong number is worse than no number.
    """
    body = _whole_figures(html, html.body, css, page_size, archive)
    relative = _heading_pages(body)
    cover = pdf_layout.lay_out(html.cover_page(), css, page_size, archive=archive)
    front = pdf_layout.lay_out(html.contents(None), css, page_size)
    for _pass in range(MAX_TOC_PASSES):
        numbered = {eid: page + cover.pages + front.pages for eid, page in relative.items()}
        candidate = pdf_layout.lay_out(html.contents(numbered), css, page_size)
        if candidate.pages == front.pages:
            return pdf_layout.concatenate(pdf_layout.concatenate(cover, candidate), body), True
        front = candidate
    # No convergence: the entries stay, the numbers go. The links do NOT — they
    # are computed from the final positions, so they point at the right pages
    # whether or not a number is printed beside them.
    bare = pdf_layout.lay_out(html.contents({}), css, page_size)
    return pdf_layout.concatenate(pdf_layout.concatenate(cover, bare), body), False


def render_pdf(content: DocumentContent, context: RenderContext) -> bytes:
    """A PDF a reader can navigate: cover, exact contents, bookmarks, running head, links."""
    if not isinstance(content, SectionedContent):
        raise ValueError("pdf rendering requires SectionedContent")
    html = _Html(content, context)
    css = html.css
    archive = html.archive()
    if html.numbered:
        laid, _converged = _long_document(html, css, context.page_size, archive)
    else:
        laid = _whole_figures(html, html.build, css, context.page_size, archive)

    positions = laid.positions
    outline = _outline(html.headings, positions)
    # Contents entries link to their pages whenever a contents exists: the
    # positions come from the FINAL document, so a link is right even when the
    # numbers had to be dropped.
    links = (
        [
            (f"toc-{element_id}", positions[element_id].page)
            for element_id, _level, _text in html.headings
            if element_id in positions
        ]
        if html.numbered
        else []
    )
    created = (
        context.generated_at.astimezone(UTC).strftime("D:%Y%m%d%H%M%SZ")
        if context.generated_at
        else ""
    )
    return pdf_layout.finish(
        laid,
        header=content.title,
        footer_label=lambda page, total: context.label("documents.page_of", page=page, total=total),
        outline=outline,
        links=links,
        metadata={"title": content.title, "subject": content.subtitle, "creationDate": created},
        rooms=html.drawings(),
        cover=html.numbered,
    )
