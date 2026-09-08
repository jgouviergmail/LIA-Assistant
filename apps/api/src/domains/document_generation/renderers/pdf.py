"""pdf: stylesheet, title block, exact contents, bookmarks, tables (ADR-226, ADR-274).

Unlike Word, we paginate this document ourselves — so its table of contents
carries EXACT page numbers, obtained by laying the document out again until the
headings stop moving. If they never settle, the contents keeps its entries and
drops the numbers: a wrong number is worse than no number.

Tables carry no header background: with ``border-collapse``, MuPDF repaints a
phantom header rectangle at the top of every continuation page (measured
2026-09-08). The recipe lives in ``typography.pdf_css``.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC
from html import escape

from src.domains.document_generation import typography
from src.domains.document_generation.context import RenderContext
from src.domains.document_generation.inline import parse_inline
from src.domains.document_generation.normalize import (
    NUMBERED_LEVELS,
    HeadingNumberer,
    document_is_numbered,
)
from src.domains.document_generation.renderers import pdf_layout
from src.domains.document_generation.schemas import (
    BLOCK_KINDS,
    DocumentContent,
    SectionBlock,
    SectionedContent,
)
from src.domains.document_generation.tables import infer_column_types
from src.domains.document_generation.typography import PageSize

#: How many times the contents may be re-laid out before its numbers are dropped.
MAX_TOC_PASSES = 3
#: The title owns h1, so content headings shift one level down.
_HEADING_SHIFT = 1
_MAX_HTML_HEADING = 5


def _inline_html(text: str) -> str:
    """The model's inline emphasis as escaped HTML."""
    parts: list[str] = []
    for span in parse_inline(text):
        piece = escape(span.text)
        if span.code:
            piece = f"<code>{piece}</code>"
        if span.italic:
            piece = f"<i>{piece}</i>"
        if span.bold:
            piece = f"<b>{piece}</b>"
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
# headings carry ids and numbers, tables carry a caption and column types —
# so the guard states the complement rather than pretending to be total.
_STRUCTURED_KINDS = frozenset({"heading", "table"})
assert (
    set(_SIMPLE_BLOCKS) == BLOCK_KINDS - _STRUCTURED_KINDS
), "_SIMPLE_BLOCKS plus the structured kinds must cover the vocabulary"


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

    def _front_matter(self) -> list[str]:
        parts = [f"<h1>{escape(self.content.title)}</h1>"]
        if self.content.subtitle:
            parts.append(f'<p class="subtitle">{escape(self.content.subtitle)}</p>')
        if self.context.date_line:
            parts.append(f'<p class="date">{escape(self.context.date_line)}</p>')
        return parts

    def _contents(self, toc_pages: dict[str, int] | None) -> list[str]:
        parts = [f"<h2>{escape(self.context.label('documents.toc_heading'))}</h2>"]
        for element_id, level, text in self.headings:
            if level > NUMBERED_LEVELS:
                continue
            page = toc_pages.get(element_id) if toc_pages else None
            suffix = f" — {page}" if page else ""
            parts.append(f'<p class="toc{level}" id="toc-{element_id}">{escape(text)}{suffix}</p>')
        return parts

    def _table(self, block: SectionBlock, index: int, number: int) -> str:
        sheet = block.table
        if sheet is None:
            return ""
        types = infer_column_types(sheet.headers, sheet.rows)
        classes = ['class="num"' if column.numeric else "" for column in types]
        header = (
            "<tr>"
            + "".join(
                f"<th {css}>{escape(name)}</th>"
                for name, css in zip(sheet.headers, classes, strict=True)
            )
            + "</tr>"
        )
        rows = "".join(
            f'<tr id="r-{index}-{row_index}">'
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

    def front(self, toc_pages: dict[str, int] | None) -> str:
        """Title block, and the contents when the document is a long one."""
        parts = self._front_matter()
        if self.numbered:
            parts += self._contents(toc_pages)
        return "".join(parts)

    def body(self) -> str:
        """The content itself — never the contents, so its pagination is stable."""
        parts: list[str] = []
        tables = 0
        headings = iter(self.headings)
        for index, block in enumerate(self.content.blocks):
            if block.kind == "heading":
                element_id, level, text = next(headings)
                tag = min(level + _HEADING_SHIFT, _MAX_HTML_HEADING)
                parts.append(f'<h{tag} id="{element_id}">{escape(text)}</h{tag}>')
            elif block.kind == "table":
                tables += 1
                parts.append(self._table(block, index, tables))
            else:
                parts.append(_SIMPLE_BLOCKS[block.kind](block))
        return "".join(parts)

    def build(self, toc_pages: dict[str, int] | None) -> str:
        """Front matter and body in one Story (short documents take one page flow)."""
        return self.front(toc_pages) + self.body()


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


def _long_document(html: _Html, css: str, page_size: PageSize) -> tuple[pdf_layout.LaidOut, bool]:
    """Contents on its own page(s), then the body, with EXACT page numbers.

    The body is laid out ONCE — it never contains the contents, so nothing it
    does can move — and the front matter is laid out twice at most: once to
    learn how many pages the contents takes, once with the numbers that follow
    from it. If adding the numbers changes the front's own length (a two-digit
    number wrapping a line), the second pass is repeated within
    ``MAX_TOC_PASSES``; failing that the contents keeps its entries and drops
    the numbers, because a wrong number is worse than no number.
    """
    body = pdf_layout.lay_out(html.body(), css, page_size)
    relative = _heading_pages(body)
    front = pdf_layout.lay_out(html.front(None), css, page_size)
    for _pass in range(MAX_TOC_PASSES):
        numbered = {eid: page + front.pages for eid, page in relative.items()}
        candidate = pdf_layout.lay_out(html.front(numbered), css, page_size)
        if candidate.pages == front.pages:
            return pdf_layout.concatenate(candidate, body), True
        front = candidate
    # No convergence: the entries stay, the numbers go. The links do NOT — they
    # are computed from the final positions, so they point at the right pages
    # whether or not a number is printed beside them.
    return pdf_layout.concatenate(pdf_layout.lay_out(html.front({}), css, page_size), body), False


def render_pdf(content: DocumentContent, context: RenderContext) -> bytes:
    """A PDF a reader can navigate: exact contents, bookmarks, running head."""
    if not isinstance(content, SectionedContent):
        raise ValueError("pdf rendering requires SectionedContent")
    html = _Html(content, context)
    css = typography.pdf_css()
    if html.numbered:
        laid, _converged = _long_document(html, css, context.page_size)
    else:
        laid = pdf_layout.lay_out(html.build(None), css, context.page_size)

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
    )
