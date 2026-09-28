"""An article page reduced to its text — what the expert analysis reads.

Readability (Mozilla's algorithm) finds the article in a page; tags go, entities
are unescaped, paragraphs become lines. A page that yields less than a
paragraph is a consent wall, a paywall or a script-rendered page (measured
2026-09-26: France 24's pages give about a hundred characters of chrome), and
answers ``None``: the summary of the feed is then all there is, and nothing
pretends otherwise.

The page is DECODED here, never by readability: its own byte path is broken in
the pinned release (a text pattern applied to bytes — every page raised,
measured 2026-09-26). The order is the web's: the charset the HTTP header
declares, else the page's own ``<meta>``, else UTF-8 — through the WHATWG
supersets (a page labelled ISO-8859-1 is windows-1252, one labelled GB2312 is
GB18030), so the accents of a Latin-1 page and the ideographs of a GBK one
survive.

Pure and synchronous (lxml work): called through ``asyncio.to_thread``.
"""

from __future__ import annotations

import html
import re
from typing import Final

from readability import Document
from readability.readability import Unparseable

#: Below this, an extraction is not an article.
ARTICLE_MIN_CHARS: Final[int] = 400
#: Above this, the rest of the article is dropped (the analyst reads a bounded text,
#: the radio page shows it): a longer article is filed as exactly its first
#: ARTICLE_MAX_CHARS characters, which is how :func:`was_cut` knows.
ARTICLE_MAX_CHARS: Final[int] = 12_000

#: How far into a page its ``<meta charset>`` is looked for.
_PRESCAN_BYTES: Final[int] = 4096
_META_CHARSET_RE: Final[re.Pattern[bytes]] = re.compile(
    rb"""<meta[^>]*?charset\s*=\s*["']?\s*([A-Za-z0-9._:-]+)""", re.I
)
#: Labels the web decodes as a larger charset than their name says.
_SUPERSETS: Final[dict[str, str]] = {
    "ascii": "cp1252",
    "us-ascii": "cp1252",
    "iso-8859-1": "cp1252",
    "latin1": "cp1252",
    "latin-1": "cp1252",
    "gb2312": "gb18030",
    "gbk": "gb18030",
}

_BLOCK_END_RE: Final[re.Pattern[str]] = re.compile(r"</(p|div|li|h[1-6]|blockquote)>", re.I)
_TAG_RE: Final[re.Pattern[str]] = re.compile(r"<[A-Za-z/!][^<>]*>")
_SPACES_RE: Final[re.Pattern[str]] = re.compile(r"[ \t\f\v]+")
_BLANK_LINES_RE: Final[re.Pattern[str]] = re.compile(r"\n\s*\n+")


def _meta_charset(content: bytes) -> str | None:
    match = _META_CHARSET_RE.search(content[:_PRESCAN_BYTES])
    return match.group(1).decode("ascii") if match else None


def decode_page(content: bytes, charset: str | None = None) -> str:
    """A page's bytes as text, decoded the way a browser would.

    Args:
        content: The page's bytes.
        charset: The charset the HTTP ``Content-Type`` declared, if any.

    Returns:
        The text (undecodable bytes replaced, never an error).
    """
    for label in (charset, _meta_charset(content)):
        if not label:
            continue
        name = label.strip().lower()
        try:
            return content.decode(_SUPERSETS.get(name, name), errors="replace")
        except LookupError:
            continue  # a label no codec knows: try the next source
    return content.decode("utf-8", errors="replace")


def extract_article(content: bytes, *, charset: str | None = None) -> str | None:
    """The article text of an HTML page, or ``None`` when there is no article.

    Args:
        content: The page's bytes.
        charset: The charset the HTTP ``Content-Type`` declared, if any.

    Returns:
        Plain text, one paragraph per line, bounded; ``None`` below
        :data:`ARTICLE_MIN_CHARS` or when the page cannot be parsed.
    """
    try:
        summary = Document(decode_page(content, charset)).summary(html_partial=True)
    except Unparseable:
        return None
    text = _BLOCK_END_RE.sub("\n", summary)
    text = html.unescape(_TAG_RE.sub(" ", text))
    text = _SPACES_RE.sub(" ", text)
    text = _BLANK_LINES_RE.sub("\n", "\n".join(line.strip() for line in text.splitlines()))
    text = text.strip()
    if len(text) < ARTICLE_MIN_CHARS:
        return None
    return text[:ARTICLE_MAX_CHARS]


def was_cut(text: str) -> bool:
    """Whether a filed text is only the head of its article.

    The newsroom files a text whole when it fits, else exactly its first
    :data:`ARTICLE_MAX_CHARS` characters — so a text of that length was cut.
    (An article of exactly that length reads as cut: the page then points to
    the outlet for a rest that is not there, never the other way round.)
    """
    return len(text) >= ARTICLE_MAX_CHARS


__all__ = ["ARTICLE_MAX_CHARS", "ARTICLE_MIN_CHARS", "decode_page", "extract_article", "was_cut"]
