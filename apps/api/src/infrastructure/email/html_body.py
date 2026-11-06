"""What a message written with formatting may hold (ADR-369, lot 7.4).

The page's editor writes HTML, and whatever reaches the server is a stranger's. Nothing is
filtered out of it: what leaves is REBUILT from an allowlist, so a mark nobody thought of
never passes, and what is left open is closed. The words survive the marks that carried
them, except inside what holds code, which goes whole. One pass over bounded input.
"""

from __future__ import annotations

from html import escape
from html.parser import HTMLParser
from typing import Final
from urllib.parse import urlsplit

#: The marks the composer's editor writes.
_KEPT_MARKS: Final = frozenset(
    {"a", "b", "blockquote", "div", "em", "i", "li", "ol", "p", "s", "strong", "u", "ul"}
)
#: What holds code or a page of its own: it goes with everything inside it.
_DROPPED_WHOLE: Final = frozenset(
    {
        "embed",
        "frame",
        "frameset",
        "iframe",
        "math",
        "noembed",
        "noframes",
        "noscript",
        "object",
        "script",
        "style",
        "svg",
        "template",
        "title",
    }
)
_LINK_SCHEMES: Final = frozenset({"http", "https", "mailto"})


def _followable(href: str | None) -> str | None:
    """A link's address when people can follow it; anything else leaves its words alone.

    ``urlsplit`` takes out what browsers ignore in a URL and lower-cases the scheme, so a
    scheme hidden behind them is read as itself, and an allowlist refuses all the rest.
    """
    if not href:
        return None
    try:
        scheme = urlsplit(href).scheme
    except ValueError:
        return None
    return href if scheme in _LINK_SCHEMES else None


class _Rebuilder(HTMLParser):
    """Writes out what the allowlist keeps, each mark closed in the order it opened."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.written: list[str] = []
        self.opened: list[str] = []
        self.dropping: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.dropping or tag in _DROPPED_WHOLE:
            self.dropping.append(tag)
        elif tag == "br":
            self.written.append("<br>")
        elif tag == "a":
            href = _followable(dict(attrs).get("href"))
            if href is not None:
                self.written.append(f'<a href="{escape(href, quote=True)}">')
                self.opened.append(tag)
        elif tag in _KEPT_MARKS:
            self.written.append(f"<{tag}>")
            self.opened.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "br" and not self.dropping:
            self.written.append("<br>")

    def handle_endtag(self, tag: str) -> None:
        if self.dropping:
            if tag in self.dropping:
                del self.dropping[self.dropping.index(tag) :]
            return
        if tag in self.opened:
            while self.opened:
                closed = self.opened.pop()
                self.written.append(f"</{closed}>")
                if closed == tag:
                    return

    def handle_data(self, data: str) -> None:
        if not self.dropping:
            self.written.append(escape(data, quote=False))


def clean_message_html(html: str) -> str:
    """The message as it may leave.

    Args:
        html: What the page sent: a stranger's markup.

    Returns:
        The same words under the marks the allowlist keeps, every mark closed.
    """
    rebuilder = _Rebuilder()
    rebuilder.feed(html)
    rebuilder.close()
    closing = (f"</{tag}>" for tag in reversed(rebuilder.opened))
    return "".join((*rebuilder.written, *closing))
