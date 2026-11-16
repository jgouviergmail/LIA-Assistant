"""How an HTML document becomes readable Markdown — one door (ADR-291).

Lives in the core since 2026-11-12: it was a pure function inside
``rag_spaces/processing``, a document-processing module, so a reader that only
wanted the conversion (the export of one discussion) would have had to import a
whole feature domain for it. The knowledge spaces and the kept answers still
reach the SAME function through ``rag_spaces.processing.html_to_markdown``.
"""

from __future__ import annotations

from src.core.markup_detection import looks_like_html


def html_to_markdown(raw_html: str) -> str:
    """Readable Markdown from HTML — the one reading of « how HTML becomes text ».

    Shared by the file extractor, the kept-answer renderer and the export of a
    discussion (a ``lia-response`` document is HTML): scripts, styles and
    images never reach the text.

    Only ``img`` is on the strip list, on purpose. markdownify drops a
    ``script`` or ``style`` element WITH its content by default; naming them in
    ``strip`` replaces that with « remove the tag, keep the text » — measured
    2026-09-16: ``.x{}alert(1)`` at the top of every converted page.

    Args:
        raw_html: The markup.

    Returns:
        The Markdown text.
    """
    from markdownify import markdownify

    # ATX headings (``## Title``): the form every other Markdown of the corpus
    # uses (mail threads, minutes, kept answers), so a heading reads the same
    # whatever produced it.
    return str(markdownify(raw_html, strip=["img"], heading_style="ATX"))


def is_html_document(content: str) -> bool:
    """Whether an answer IS an HTML document: it opens on a tag, as the ``html`` display mode
    draws it, and holds real markup.

    A Markdown answer that merely carries an HTML block is valid Markdown as it stands:
    converting it would escape every mark of its prose and fold its paragraphs. Measured on a
    development base, 2026-11-12: of 2 184 visible answers, 2 161 hold no tag, 12 open on one,
    5 carry a block inside Markdown. One predicate for every reader that converts an answer —
    the export of a discussion, a kept answer's document and its excerpt.

    Args:
        content: What LIA answered.

    Returns:
        True for a document.
    """
    opened = content.lstrip()
    return opened.startswith("<") and looks_like_html(opened)


def as_markdown(content: str) -> str:
    """An answer's text as Markdown: Markdown verbatim, an HTML document converted.

    Args:
        content: What LIA answered — Markdown, or an HTML document in the
            ``html`` display mode.

    Returns:
        The Markdown text.
    """
    return html_to_markdown(content) if is_html_document(content) else content
