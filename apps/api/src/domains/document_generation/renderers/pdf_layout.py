"""Two-pass Story layout, stamping, outline and links (ADR-274).

PyMuPDF's Story paginates HTML but knows nothing of page numbers, running heads
or bookmarks. Elements carry ids; ``lay_out`` records the page each id landed
on, so the caller can write a table of contents with EXACT page numbers — laid
out again until the pages stop moving — and ``finish`` then stamps every page,
sets the outline and links the entries.

The Story writes no link of its own: it reports where each word of an ``<a>``
landed (measured 2026-11-13: one rectangle per word and per space), and
``finish`` turns those words — joined line by line — into the links a reader
clicks.
"""

from __future__ import annotations

import functools
import io
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from src.domains.document_generation import typography
from src.domains.document_generation.raster import pymupdf as _pymupdf
from src.domains.document_generation.typography import PageSize

#: The addresses a document links to: a reader opens nothing else.
_WEB_PREFIXES = ("http://", "https://")
#: Two words of one link are on the same line when their boxes align this closely.
_SAME_LINE_PT = 0.5
#: ... and are neighbours when no more than this separates them.
_ADJACENT_PT = 1.0


class DocumentLayoutError(RuntimeError):
    """A layout pass that never ends: more pages than any document can need.

    Raised instead of letting a worker thread spin: the Story's cycle is a defect
    of the HTML it was given, never something a retry could repair.
    """


@dataclass(frozen=True, slots=True)
class Placed:
    """Where an identified element landed."""

    page: int
    rect: Any


@dataclass(frozen=True, slots=True)
class Link:
    """Where a web address was laid out: one rectangle per line it spans."""

    page: int
    rect: Any
    uri: str


@dataclass(frozen=True, slots=True)
class LaidOut:
    """One layout pass: the bytes, the page count, where the ids and the links landed."""

    pdf: bytes
    pages: int
    positions: dict[str, Placed] = field(default_factory=dict)
    links: tuple[Link, ...] = ()


@dataclass(frozen=True, slots=True)
class Room:
    """What ``finish`` draws into a room the Story laid out empty.

    Attributes:
        drawing: An SVG figure, drawn as vectors whose words stay text, or a
            JPEG picture, embedded as it was encoded.
        width_pt: The room's width.
        height_pt: The room's height.
    """

    drawing: str | bytes
    width_pt: float
    height_pt: float


def content_rect(page_size: PageSize) -> Any:
    """The area the Story lays text into (margins from typography)."""
    left, top, right, bottom = typography.PDF_MARGIN_PT
    paper = _pymupdf().paper_rect(typography.page_rect_name(page_size))
    return paper + (left, top, -right, -bottom)


def _join(links: list[Link], word: Link) -> None:
    """Add a word of a link to the line it continues, or start a line of its own."""
    if links:
        last = links[-1]
        continues = (
            last.page == word.page
            and last.uri == word.uri
            and abs(last.rect.y0 - word.rect.y0) < _SAME_LINE_PT
            and abs(last.rect.y1 - word.rect.y1) < _SAME_LINE_PT
            and abs(word.rect.x0 - last.rect.x1) <= _ADJACENT_PT
        )
        if continues:
            links[-1] = Link(last.page, last.rect | word.rect, last.uri)
            return
    links.append(word)


def _recorder(positions: dict[str, Placed], links: list[Link], page: int) -> Callable[[Any], None]:
    """A one-argument callback bound to ONE page.

    PyMuPDF refuses a callback of any other arity, so the page cannot be a
    parameter — a factory binds it by value instead of capturing the loop
    variable.
    """

    def record(position: Any) -> None:
        if position.id and position.id not in positions:
            positions[position.id] = Placed(page, _pymupdf().Rect(position.rect))
        address = position.href or ""
        if address.startswith(_WEB_PREFIXES):
            _join(links, Link(page, _pymupdf().Rect(position.rect), address))

    return record


def lay_out(html: str, css: str, page_size: PageSize, *, archive: Any | None = None) -> LaidOut:
    """Paginate the HTML, recording the FIRST page and rect of every identified element.

    Args:
        html: The document body, ids included.
        css: The stylesheet.
        page_size: Which paper.
        archive: A ``pymupdf.Archive`` holding the files the HTML's ``<img>``
            tags name, when it has any.

    Returns:
        The rendered bytes, the position of every id and where every link landed.

    Raises:
        DocumentLayoutError: When the pass reaches ``PDF_MAX_PAGES`` without
            ending — a cycle, never a document.
    """
    story = _pymupdf().Story(html=html, user_css=css, archive=archive)
    buffer = io.BytesIO()
    writer = _pymupdf().DocumentWriter(buffer)
    mediabox = _pymupdf().paper_rect(typography.page_rect_name(page_size))
    where = content_rect(page_size)
    positions: dict[str, Placed] = {}
    links: list[Link] = []
    page_no = 0
    more = True
    while more:
        if page_no >= typography.PDF_MAX_PAGES:
            writer.close()
            raise DocumentLayoutError(
                f"the layout did not end within {typography.PDF_MAX_PAGES} pages"
            )
        page_no += 1
        device = writer.begin_page(mediabox)
        more, _filled = story.place(where)
        story.element_positions(_recorder(positions, links, page_no))
        story.draw(device)
        writer.end_page()
    writer.close()
    return LaidOut(pdf=buffer.getvalue(), pages=page_no, positions=positions, links=tuple(links))


#: The image a figure's ROOM is laid out with: one pixel of paper, sized by its tag.
FIGURE_ROOM = "figure-room.png"


@functools.cache
def _paper_pixel() -> bytes:
    """One WHITE pixel. A transparent one is drawn BLACK by the Story, which
    ignores its alpha (measured 2026-11-13): the figure drawn over it left a
    black hairline at its antialiased edges."""
    pixmap = _pymupdf().Pixmap(_pymupdf().csRGB, _pymupdf().IRect(0, 0, 1, 1), False)
    pixmap.clear_with(255)
    data: bytes = pixmap.tobytes("png")
    return data


def figure_archive() -> Any:
    """The archive the HTML's figure rooms read their pixel of paper from.

    A figure is NOT laid out by the Story: an SVG ``<img>`` comes out as a bitmap
    at about 96 dpi (measured 2026-11-13: 604 x 333 px for 453 pt), its words
    no longer text. The Story lays out an empty room of the figure's exact
    size instead, and ``finish`` draws the figure into it — as vectors, or as
    the picture's own JPEG.
    """
    archive = _pymupdf().Archive()
    archive.add((_paper_pixel(), FIGURE_ROOM))
    return archive


@functools.cache
def paragraph_width(css: str, page_size: PageSize) -> float:
    """The width the Story gives a paragraph — measured, never assumed.

    It is NOT the content area: the body keeps a default margin of its own
    (measured 2026-11-13: 462 pt of the 483 pt an A4 content area offers).

    Args:
        css: The stylesheet the document is laid out with.
        page_size: Which paper.

    Returns:
        The width in points.
    """
    probe = "width-probe"
    laid = lay_out(f'<p id="{probe}">.</p>', css, page_size)
    return float(laid.positions[probe].rect.width)


def _draw_rooms(page: Any, number: int, laid: LaidOut, rooms: Mapping[str, Room]) -> None:
    """Draw each room of this page: a chart as vectors whose words stay text, a picture as is.

    A room the Story still squeezed (a figure taller than a page, which no form
    produces) receives its drawing scaled down whole: a figure never overflows.
    """
    for element_id, room in rooms.items():
        placed = laid.positions.get(element_id)
        if placed is None or placed.page != number:
            continue
        scale = min(1.0, placed.rect.height / room.height_pt, placed.rect.width / room.width_pt)
        drawn_width, drawn_height = room.width_pt * scale, room.height_pt * scale
        left = placed.rect.x0 + (placed.rect.width - drawn_width) / 2
        top = placed.rect.y0
        target = _pymupdf().Rect(left, top, left + drawn_width, top + drawn_height)
        if isinstance(room.drawing, bytes):
            # Embedded as the JPEG it is: a decoded copy would weigh ten times more.
            page.insert_image(target, stream=room.drawing)
            continue
        with _pymupdf().open("svg", room.drawing.encode("utf-8")) as drawing:
            vector = _pymupdf().open("pdf", drawing.convert_to_pdf())
        page.show_pdf_page(target, vector, 0)
        vector.close()


def concatenate(front: LaidOut, body: LaidOut) -> LaidOut:
    """Front matter then body, the body's positions and links shifted by the front's pages.

    A table of contents belongs on its own page, and PyMuPDF's Story knows no
    page break — so the two are laid out separately and joined here. It also
    makes the contents numbers EXACT rather than iterated: the body never
    contains the contents, so its pagination cannot move when numbers appear.
    """
    merged = _pymupdf().open(stream=front.pdf, filetype="pdf")
    tail = _pymupdf().open(stream=body.pdf, filetype="pdf")
    merged.insert_pdf(tail)
    tail.close()
    output: bytes = merged.tobytes()
    merged.close()
    positions = dict(front.positions)
    for element_id, placed in body.positions.items():
        positions[element_id] = Placed(placed.page + front.pages, placed.rect)
    links = front.links + tuple(
        Link(link.page + front.pages, link.rect, link.uri) for link in body.links
    )
    return LaidOut(pdf=output, pages=front.pages + body.pages, positions=positions, links=links)


def _grey() -> tuple[float, float, float]:
    return tuple(int(typography.MUTED[index : index + 2], 16) / 255 for index in (0, 2, 4))  # type: ignore[return-value]


def stamp_font(*texts: str) -> Any:
    """The lightest built-in font that can draw every stamp.

    Helvetica has no ideograph: it stamped a Chinese running head as "······"
    and its footer as "· 1 ··· 1 ·" on every page, while the BODY was fine —
    the Story embeds its own CJK fallback, the stamps do not (measured
    2026-09-08). Droid Sans Fallback is chosen only when Helvetica is short of
    a glyph, so a Latin document keeps the small file it had.

    Args:
        *texts: Every string that will be stamped on the document.

    Returns:
        A ``pymupdf.Font`` covering all of them.
    """
    helvetica = _pymupdf().Font("helv")
    if all(helvetica.has_glyph(ord(char)) for text in texts for char in text):
        return helvetica
    return _pymupdf().Font("cjk")


def _stamp(page: Any, header: str, label: str, font: Any) -> None:
    """The running head and the page footer, in the page's own top-down coordinates.

    The Story's page content flips the y axis (``1 0 0 -1 0 h cm``) and never
    closes it: whatever is appended after it inherits the flip. Unwrapped, the
    stamps came out at the right height but UPSIDE DOWN — the old code read « y
    from the bottom » and compensated the position only (found 2026-11-13 by
    looking at a page). The caller wraps the page's contents in q/Q first.
    """
    left, _top, _right, _bottom = typography.PDF_MARGIN_PT
    size = typography.PDF_STAMP_PT
    writer = _pymupdf().TextWriter(page.rect)
    writer.append((left, typography.PDF_HEADER_BASELINE_PT), header, font=font, fontsize=size)
    writer.append(
        (
            (page.rect.width - font.text_length(label, fontsize=size)) / 2,
            page.rect.height - typography.PDF_FOOTER_BASELINE_FROM_BOTTOM_PT,
        ),
        label,
        font=font,
        fontsize=size,
    )
    writer.write_text(page, color=_grey())


def _link(document: Any, laid: LaidOut, links: Sequence[tuple[str, int]]) -> None:
    """The contents entries to their pages, and every laid-out address to its page on the web."""
    for element_id, target_page in links:
        placed = laid.positions.get(element_id)
        if placed is None:
            continue
        document[placed.page - 1].insert_link(
            {
                "kind": _pymupdf().LINK_GOTO,
                "from": placed.rect,
                "page": target_page - 1,
                "to": _pymupdf().Point(0, 0),
            }
        )
    for address in laid.links:
        document[address.page - 1].insert_link(
            {"kind": _pymupdf().LINK_URI, "from": address.rect, "uri": address.uri}
        )


def finish(
    laid: LaidOut,
    *,
    header: str,
    footer_label: Callable[[int, int], str],
    outline: Sequence[tuple[int, str, int]],
    links: Sequence[tuple[str, int]],
    metadata: dict[str, str],
    rooms: Mapping[str, Room] | None = None,
    cover: bool = False,
) -> bytes:
    """Draw the rooms, stamp the running head and footer, set the outline, link.

    Args:
        laid: The layout pass to finish.
        header: The running head (the document's title).
        footer_label: ``(page, total) -> text``, localized by the caller.
        outline: ``(level, title, page)`` bookmarks.
        links: ``(element id, target page)`` for the contents entries; the
            addresses the layout recorded are linked whatever this says.
        metadata: Title, subject and creation date.
        rooms: ``room id -> Room`` for each figure laid out as an empty room.
        cover: Whether the first page is a cover, which carries no stamp.

    Returns:
        The final PDF bytes.
    """
    document = _pymupdf().open(stream=laid.pdf, filetype="pdf")
    total = document.page_count
    font = stamp_font(header, *(footer_label(page, total) for page in range(1, total + 1)))
    for number, page in enumerate(document, start=1):
        page.wrap_contents()
        _draw_rooms(page, number, laid, rooms or {})
        if not (cover and number == 1):
            _stamp(page, header, footer_label(number, total), font)
    if outline:
        document.set_toc([[level, title, page] for level, title, page in outline])
    _link(document, laid, links)
    document.set_metadata(
        {
            "title": metadata.get("title", ""),
            "subject": metadata.get("subject", ""),
            "creationDate": metadata.get("creationDate", ""),
        }
    )
    document.subset_fonts()
    output: bytes = document.tobytes()
    document.close()
    return output
