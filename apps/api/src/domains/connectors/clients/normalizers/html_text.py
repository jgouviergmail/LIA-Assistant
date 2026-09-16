"""HTML → text, once, for every e-mail provider (ADR-287).

Three readers used to turn a message body into text three ways: the Gmail
client's :class:`HTMLToTextConverter` (paragraphs, lists and links kept), a
regex in the IMAP normaliser (every paragraph and link lost), and the agent
formatter converting Graph bodies LATE, after the raw HTML had already
travelled through the registry. A model reasoning over e-mails needs the
same text whatever the mailbox, so the conversion lives here, at the client
boundary, and the normalisers all call it.

Two doors:

- :func:`html_to_text` — the body: structure kept (paragraphs, ``<br>``, list
  bullets, headers), ``<style>`` / ``<script>`` dropped, links kept as
  ``text [link](url)`` behind a technical label (ADR-256: what a model reads
  is English), long standalone urls shortened the same way;
- :func:`strip_html_to_line` — a snippet: one line, entities decoded,
  whitespace collapsed, capped.
"""

from __future__ import annotations

import re
from html import unescape
from html.parser import HTMLParser

import structlog

from src.core.constants import EMAILS_URL_SHORTEN_THRESHOLD_DEFAULT, HTML_TEXT_LINK_LABEL

logger = structlog.get_logger(__name__)

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_BLOCK_TAGS = frozenset({"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote"})
_IGNORED_TAGS = frozenset({"style", "script"})
_INLINE_PUNCTUATION = ".,;:!?'\")]}—"


class HTMLToTextConverter(HTMLParser):
    """Convert HTML to readable plain text.

    Preserves important structure:
    - Paragraphs: adds newlines around block elements
    - Line breaks: converts <br> to a newline
    - Links: converts <a href="url">text</a> to "text [link](url)"
    - Lists: adds a bullet for <li> items
    - Ignores: <style>, <script> content

    Example:
        >>> converter = HTMLToTextConverter()
        >>> converter.feed("<p>Hello <b>world</b>!</p><p>Second paragraph.</p>")
        >>> converter.get_text()
        'Hello world!\\n\\nSecond paragraph.'
    """

    def __init__(self, url_shorten_threshold: int = EMAILS_URL_SHORTEN_THRESHOLD_DEFAULT) -> None:
        """Initialize the parser.

        Args:
            url_shorten_threshold: Standalone urls longer than this are
                shortened to ``[link](url)``.
        """
        super().__init__()
        self.text_parts: list[str] = []
        self.ignore_content = False
        self.current_link_url: str | None = None
        self.url_shorten_threshold = url_shorten_threshold

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Handle opening HTML tags."""
        if tag in _BLOCK_TAGS or tag == "br":
            self.text_parts.append("\n")
        elif tag == "li":
            self.text_parts.append("\n• ")
        elif tag == "a":
            for attr_name, attr_value in attrs:
                if attr_name == "href" and attr_value:
                    self.current_link_url = attr_value
                    break
        elif tag in _IGNORED_TAGS:
            self.ignore_content = True

    def handle_endtag(self, tag: str) -> None:
        """Handle closing HTML tags."""
        if tag in _BLOCK_TAGS:
            self.text_parts.append("\n")
        elif tag == "a":
            if self.current_link_url:
                self.text_parts.append(f" [{HTML_TEXT_LINK_LABEL}]({self.current_link_url})")
                self.current_link_url = None
        elif tag in _IGNORED_TAGS:
            self.ignore_content = False

    def handle_data(self, data: str) -> None:
        """Handle text content."""
        if self.ignore_content or not data.strip():
            return
        normalized = " ".join(data.split())
        if not normalized:
            return
        # "This is <b>bold</b> text" must read "This is bold text", never "This isbold text".
        if self.text_parts:
            last_part = self.text_parts[-1]
            if (
                last_part
                and not last_part[-1].isspace()
                and not last_part.endswith("\n")
                and normalized[0] not in _INLINE_PUNCTUATION
            ):
                self.text_parts.append(" ")
        self.text_parts.append(normalized)

    def get_text(self) -> str:
        """Get the extracted plain text with normalized whitespace.

        Returns:
            Cleaned text: standalone urls longer than the threshold become
            ``[link](url)``, runs of blank lines collapse to one, every line
            is stripped, leading and trailing blank lines are removed.
        """
        text = "".join(self.text_parts)
        threshold = self.url_shorten_threshold

        def replace_long_url(match: re.Match[str]) -> str:
            url = match.group(0)
            if url.endswith(")"):  # already inside a [label](url)
                return url
            if len(url) > threshold:
                return f"[{HTML_TEXT_LINK_LABEL}]({url})"
            return url

        text = re.sub(r"https?://[^\s<>\"'\)]+", replace_long_url, text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        lines = [line.strip() for line in text.split("\n")]
        while lines and not lines[0]:
            lines.pop(0)
        while lines and not lines[-1]:
            lines.pop()
        return "\n".join(lines)


def html_to_text(html: str, *, url_shorten_threshold: int | None = None) -> str:
    """Convert an HTML body to readable text (the body door).

    Args:
        html: The HTML body.
        url_shorten_threshold: Standalone urls longer than this become
            ``[link](url)``; the configured ``emails_url_shorten_threshold``
            when omitted.

    Returns:
        The text; on a parser failure, the tags stripped and entities decoded.
    """
    if not html:
        return ""
    if url_shorten_threshold is None:
        from src.core.config import settings

        url_shorten_threshold = settings.emails_url_shorten_threshold
    converter = HTMLToTextConverter(url_shorten_threshold=url_shorten_threshold)
    try:
        converter.feed(html)
        return converter.get_text()
    except Exception as exc:
        # html.parser raises on a handful of malformed inputs; a body is never
        # lost to its parser, so the tags are stripped instead. The markup is
        # third-party content: only the failure's type is logged.
        logger.debug("html_to_text_parser_failed", error_type=type(exc).__name__)
        return unescape(_HTML_TAG_RE.sub(" ", html)).strip()


def strip_html_to_line(html: str, *, max_length: int) -> str:
    """Flatten HTML to one capped line (the snippet door).

    Args:
        html: The HTML (or plain text) to flatten.
        max_length: Characters kept.

    Returns:
        Tags removed, entities decoded, whitespace collapsed, capped.
    """
    text = unescape(_HTML_TAG_RE.sub(" ", html))
    return re.sub(r"\s+", " ", text).strip()[:max_length]


__all__ = ["HTMLToTextConverter", "html_to_text", "strip_html_to_line"]
