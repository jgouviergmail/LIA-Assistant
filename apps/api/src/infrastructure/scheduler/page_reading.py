"""A watched page, read without a model (ADR-387).

What a page-change routine reads at each check, and how its run is shown the
news:

- **the read** is the one every public page gets (``fetch_public``): every hop
  validated and requested on the address the check saw (ADR-326), the body
  bounded, the reader named (``PAGE_WATCH_USER_AGENT``), the whole read bounded
  in time. A page answers or it does not: an address that leads to no public
  page is ``PageNotPublicError`` (nothing was opened, and the person can fix
  it), anything else that kept the page away is ``PageUnreadableError`` naming
  how — never « nothing changed »;
- **the lines** are what a person reads: the visible text, one line per block
  (the head, scripts, styles, templates and hidden blocks dropped), blanks
  folded, the person's filter applied, a repeated line kept once, each line and
  their number bounded, the total kept. Plain text is read line by line and
  JSON one value per line; a body that is no text is not a page;
- **the note** shows the run the lines that are new, as another site's words
  (``wrap_external_content``), bounded with the rest counted — and says when the
  page holds more lines than are watched: a change past them is not seen.

The parse is CPU work on up to ``PAGE_WATCH_MAX_BYTES``: the read hands it to
a thread, never to the event loop.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from functools import cache
from typing import Final, Literal

import httpx
from lxml import etree
from lxml import html as lxml_html

from src.core.constants import (
    PAGE_WATCH_LINE_MAX_CHARS,
    PAGE_WATCH_MAX_BYTES,
    PAGE_WATCH_MAX_LINES,
    PAGE_WATCH_NOTE_MAX_CHARS,
    PAGE_WATCH_TIMEOUT_SECONDS,
    PAGE_WATCH_USER_AGENT,
)
from src.core.external_content import wrap_external_content
from src.core.prompt_store import parse_prompt_sections, read_prompt_file
from src.domains.briefing.exceptions import ConnectorNotConfiguredError
from src.domains.radio.newsroom.fetch import FetchOutcome, fetch_public
from src.domains.radio.newsroom.fulltext import decode_page

#: How the note's envelope names what it wraps.
_SOURCE_TYPE: Final = "watched_page"

#: Elements whose content nobody reads on the page.
_UNREAD: Final = frozenset(
    {"head", "script", "style", "noscript", "template", "svg", "math", "iframe", "object", "canvas"}
)

#: Elements that start a line of their own.
_BLOCKS: Final = frozenset(
    {
        "address", "article", "aside", "blockquote", "body", "br", "caption", "dd",
        "details", "dialog", "div", "dl", "dt", "fieldset", "figcaption", "figure",
        "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hgroup",
        "hr", "legend", "li", "main", "nav", "ol", "option", "p", "pre", "section",
        "summary", "table", "tbody", "td", "tfoot", "th", "thead", "tr", "ul",
    }
)  # fmt: skip

#: Media types read as markup (tags dropped), and as JSON.
_MARKUP: Final = frozenset({"text/html", "application/xhtml+xml", "application/xml", "text/xml"})
_JSON: Final = "application/json"


def _parser() -> lxml_html.HTMLParser:
    """A parser of one's own: lxml parsers are not shared across threads.

    No limit on a deep page (the body is bounded in bytes), no comment kept.
    """
    return lxml_html.HTMLParser(huge_tree=True, remove_comments=True, remove_pis=True)


class PageNotPublicError(ConnectorNotConfiguredError):
    """The address leads to no public page at this check — the person can fix it."""

    def __init__(self) -> None:
        super().__init__("page")


class PageUnreadableError(Exception):
    """The page could not be read; ``reason`` says how, in a bounded vocabulary.

    Attributes:
        reason: A ``FetchOutcome`` value, ``timeout`` or ``not_text``.
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class PageLines:
    """The lines of one page as a person reads them.

    Attributes:
        lines: The lines kept, in page order.
        total: How many lines the page had once filtered, before the bound.
    """

    lines: tuple[str, ...]
    total: int


@dataclass(frozen=True, slots=True)
class PageReading:
    """One check's reading of a watched page.

    Attributes:
        url: The address that answered, after its redirects.
        lines: The lines kept, in page order.
        total: How many lines the page had once filtered, before the bound.
    """

    url: str
    lines: tuple[str, ...]
    total: int


def _kind(media_type: str | None) -> Literal["markup", "json", "text"]:
    """How a body of this declared media type is read.

    Raises:
        PageUnreadableError: ``not_text`` for a body that is no text.
    """
    if media_type is None or media_type in _MARKUP or media_type.endswith("+xml"):
        return "markup"
    if media_type == _JSON or media_type.endswith("+json"):
        return "json"
    if media_type.startswith("text/"):
        return "text"
    raise PageUnreadableError("not_text")


def _unread(tag: str, element: etree._Element) -> bool:
    """Whether nobody reads this element's content on the page."""
    if tag in _UNREAD or element.get("hidden") is not None:
        return True
    style = (element.get("style") or "").replace(" ", "").lower()
    return "display:none" in style


def _markup_text(text: str) -> str:
    """The visible text of a page, a line break at each block's edges.

    Walked iteratively: a page nested thousands deep reads like any other.
    """
    try:
        root = lxml_html.document_fromstring(text, parser=_parser())
    except etree.ParserError, ValueError:
        return ""
    parts: list[str] = []
    hidden = 0  # Depth inside an element nobody reads.
    for event, element in etree.iterwalk(root, events=("start", "end")):
        if not isinstance(element.tag, str):
            continue  # A comment the parser kept despite itself: never read.
        tag = element.tag.lower()
        if event == "start":
            if hidden or _unread(tag, element):
                hidden += 1
                continue
            if tag in _BLOCKS:
                parts.append("\n")
            parts.append(element.text or "")
            continue
        if hidden:
            hidden -= 1
            # Leaving the unread element itself: what follows it is read again.
            if not hidden:
                parts.append(element.tail or "")
            continue
        if tag in _BLOCKS:
            parts.append("\n")
        parts.append(element.tail or "")
    return "".join(parts)


def _json_text(text: str) -> str:
    """JSON one value per line; text that is not JSON stays as it came."""
    try:
        return json.dumps(json.loads(text), indent=1, ensure_ascii=False)
    except ValueError:
        return text


def _kept(raw_lines: Iterable[str], contains: str | None) -> PageLines:
    """The lines a check keeps: folded, filtered, cut, once each, bounded."""
    needle = contains.casefold() if contains else None
    kept: dict[str, None] = {}
    for raw in raw_lines:
        line = " ".join(raw.split())
        if not line or (needle is not None and needle not in line.casefold()):
            continue
        kept.setdefault(line[:PAGE_WATCH_LINE_MAX_CHARS], None)
    lines = tuple(kept)
    return PageLines(lines=lines[:PAGE_WATCH_MAX_LINES], total=len(lines))


def page_lines(
    content: bytes,
    charset: str | None,
    media_type: str | None,
    *,
    contains: str | None = None,
) -> PageLines:
    """The lines of a page as a person reads them. Pure; CPU-bound.

    Args:
        content: The body, as received.
        charset: The charset the ``Content-Type`` header declared, if any.
        media_type: The media type it declared, if any (``None`` reads as markup).
        contains: Keep only the lines holding this text, case-insensitive.

    Returns:
        The lines, in page order, with the total before the bound.

    Raises:
        PageUnreadableError: ``not_text`` for a body that is no text.
    """
    kind = _kind(media_type)
    text = decode_page(content, charset)
    if kind == "markup":
        text = _markup_text(text)
    elif kind == "json":
        text = _json_text(text)
    return _kept(text.split("\n"), contains)


async def read_page(url: str, *, contains: str | None) -> PageReading:
    """Read a watched page: its lines, or why it could not be read.

    Args:
        url: The page's address, as the routine keeps it.
        contains: Keep only the lines holding this text.

    Returns:
        The reading.

    Raises:
        PageNotPublicError: The address leads to no public page (at any hop).
        PageUnreadableError: The page did not answer, was too large, or was no text.
    """
    try:
        async with asyncio.timeout(PAGE_WATCH_TIMEOUT_SECONDS):
            async with httpx.AsyncClient(timeout=PAGE_WATCH_TIMEOUT_SECONDS) as client:
                result = await fetch_public(
                    client, url, max_bytes=PAGE_WATCH_MAX_BYTES, user_agent=PAGE_WATCH_USER_AGENT
                )
    except TimeoutError:
        raise PageUnreadableError("timeout") from None
    if result.outcome is FetchOutcome.BLOCKED:
        raise PageNotPublicError()
    if result.outcome is not FetchOutcome.OK:
        raise PageUnreadableError(result.outcome.value)
    found = await asyncio.to_thread(
        page_lines, result.content, result.charset, result.media_type, contains=contains
    )
    return PageReading(url=result.final_url, lines=found.lines, total=found.total)


@cache
def _note_lines() -> dict[str, str]:
    """The note's one-line templates (``page_watch_lines``), read once."""
    return dict(parse_prompt_sections(read_prompt_file("page_watch_lines"), 2))


def page_note(
    url: str, lines: Sequence[str], *, first: bool, watched: int = 0, unwatched: int = 0
) -> str:
    """What a run is shown, after the routine's instruction, of its page's news.

    Args:
        url: The watched page — the envelope's source.
        lines: The lines new on the page (all of them on a first report).
        first: Whether nothing from the page was reported yet.
        watched: How many lines of the page the check keeps.
        unwatched: How many more the page holds past them, where a change is
            not seen; 0 for a page watched whole.

    Returns:
        A header, the lines wrapped as another site's words, bounded at
        ``PAGE_WATCH_NOTE_MAX_CHARS`` with the rest counted, then the lines the
        page holds past the watched ones, when it has any.
    """
    templates = _note_lines()
    shown: list[str] = []
    used = 0
    for line in lines:
        if shown and used + len(line) + 1 > PAGE_WATCH_NOTE_MAX_CHARS:
            break
        shown.append(line)
        used += len(line) + 1
    parts = [
        templates["first" if first else "changed"].format(count=len(lines)),
        wrap_external_content("\n".join(shown), source_url=url, source_type=_SOURCE_TYPE),
    ]
    if len(shown) < len(lines):
        parts.append(templates["cut"].format(more=len(lines) - len(shown)))
    if unwatched:
        parts.append(templates["unwatched"].format(watched=watched, unwatched=unwatched))
    return "\n".join(parts)


__all__ = [
    "PageLines",
    "PageNotPublicError",
    "PageReading",
    "PageUnreadableError",
    "page_lines",
    "page_note",
    "read_page",
]
