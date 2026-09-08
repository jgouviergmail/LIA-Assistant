"""Two-pass Story layout, stamping, outline and links (ADR-274).

PyMuPDF's Story paginates HTML but knows nothing of page numbers, running heads
or bookmarks. Elements carry ids; ``lay_out`` records the page each id landed
on, so the caller can write a table of contents with EXACT page numbers — laid
out again until the pages stop moving — and ``finish`` then stamps every page,
sets the outline and links the entries.
"""

from __future__ import annotations

import io
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

import fitz  # type: ignore[import-untyped]  # PyMuPDF

from src.domains.document_generation import typography
from src.domains.document_generation.typography import PageSize


@dataclass(frozen=True, slots=True)
class Placed:
    """Where an identified element landed."""

    page: int
    rect: Any


@dataclass(frozen=True, slots=True)
class LaidOut:
    """One layout pass: the bytes, the page count, and where the ids landed."""

    pdf: bytes
    pages: int
    positions: dict[str, Placed] = field(default_factory=dict)


def content_rect(page_size: PageSize) -> Any:
    """The area the Story lays text into (margins from typography)."""
    left, top, right, bottom = typography.PDF_MARGIN_PT
    return fitz.paper_rect(typography.page_rect_name(page_size)) + (left, top, -right, -bottom)


def _recorder(positions: dict[str, Placed], page: int) -> Callable[[Any], None]:
    """A one-argument callback bound to ONE page.

    PyMuPDF refuses a callback of any other arity, so the page cannot be a
    parameter — a factory binds it by value instead of capturing the loop
    variable.
    """

    def record(position: Any) -> None:
        if position.id and position.id not in positions:
            positions[position.id] = Placed(page, fitz.Rect(position.rect))

    return record


def lay_out(html: str, css: str, page_size: PageSize) -> LaidOut:
    """Paginate the HTML, recording the FIRST page and rect of every identified element.

    Args:
        html: The document body, ids included.
        css: The stylesheet.
        page_size: Which paper.

    Returns:
        The rendered bytes and the position of every id.
    """
    story = fitz.Story(html=html, user_css=css)
    buffer = io.BytesIO()
    writer = fitz.DocumentWriter(buffer)
    mediabox = fitz.paper_rect(typography.page_rect_name(page_size))
    where = content_rect(page_size)
    positions: dict[str, Placed] = {}
    page_no = 0
    more = True
    while more:
        page_no += 1
        device = writer.begin_page(mediabox)
        more, _filled = story.place(where)
        story.element_positions(_recorder(positions, page_no))
        story.draw(device)
        writer.end_page()
    writer.close()
    return LaidOut(pdf=buffer.getvalue(), pages=page_no, positions=positions)


def concatenate(front: LaidOut, body: LaidOut) -> LaidOut:
    """Front matter then body, the body's positions shifted by the front's pages.

    A table of contents belongs on its own page, and PyMuPDF's Story knows no
    page break — so the two are laid out separately and joined here. It also
    makes the contents numbers EXACT rather than iterated: the body never
    contains the contents, so its pagination cannot move when numbers appear.
    """
    merged = fitz.open(stream=front.pdf, filetype="pdf")
    tail = fitz.open(stream=body.pdf, filetype="pdf")
    merged.insert_pdf(tail)
    tail.close()
    output: bytes = merged.tobytes()
    merged.close()
    positions = dict(front.positions)
    for element_id, placed in body.positions.items():
        positions[element_id] = Placed(placed.page + front.pages, placed.rect)
    return LaidOut(pdf=output, pages=front.pages + body.pages, positions=positions)


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
        A ``fitz.Font`` covering all of them.
    """
    helvetica = fitz.Font("helv")
    if all(helvetica.has_glyph(ord(char)) for text in texts for char in text):
        return helvetica
    return fitz.Font("cjk")


def finish(
    laid: LaidOut,
    *,
    header: str,
    footer_label: Callable[[int, int], str],
    outline: Sequence[tuple[int, str, int]],
    links: Sequence[tuple[str, int]],
    metadata: dict[str, str],
) -> bytes:
    """Stamp the running head and footer, set the outline, link the entries.

    Args:
        laid: The layout pass to finish.
        header: The running head (the document's title).
        footer_label: ``(page, total) -> text``, localized by the caller.
        outline: ``(level, title, page)`` bookmarks.
        links: ``(element id, target page)`` for the contents entries.
        metadata: Title, subject and creation date.

    Returns:
        The final PDF bytes.
    """
    document = fitz.open(stream=laid.pdf, filetype="pdf")
    left, _top, _right, _bottom = typography.PDF_MARGIN_PT
    grey = _grey()
    total = document.page_count
    font = stamp_font(header, *(footer_label(page, total) for page in range(1, total + 1)))
    size = typography.PDF_STAMP_PT
    for number, page in enumerate(document, start=1):
        label = footer_label(number, total)
        writer = fitz.TextWriter(page.rect)
        # A TextWriter measures y from the BOTTOM of the page, where
        # ``insert_text`` measures it from the top — swapping the two stamps is
        # exactly what happened when this loop was rewritten (measured).
        writer.append(
            (left, page.rect.height - typography.PDF_HEADER_BASELINE_PT),
            header,
            font=font,
            fontsize=size,
        )
        writer.append(
            (
                (page.rect.width - font.text_length(label, fontsize=size)) / 2,
                typography.PDF_FOOTER_BASELINE_FROM_BOTTOM_PT,
            ),
            label,
            font=font,
            fontsize=size,
        )
        writer.write_text(page, color=grey)
    if outline:
        document.set_toc([[level, title, page] for level, title, page in outline])
    for element_id, target_page in links:
        placed = laid.positions.get(element_id)
        if placed is None:
            continue
        document[placed.page - 1].insert_link(
            {
                "kind": fitz.LINK_GOTO,
                "from": placed.rect,
                "page": target_page - 1,
                "to": fitz.Point(0, 0),
            }
        )
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
