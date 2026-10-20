"""Pure external-content envelope shared by tools and direct source readers."""

import re
import unicodedata

from src.core.constants import (
    EXTERNAL_CONTENT_CLOSE_TAG,
    EXTERNAL_CONTENT_OPEN_TAG,
    EXTERNAL_CONTENT_WARNING,
)

#: Brackets a model reads as a tag's opening one: ASCII, fullwidth, small form.
_OPENING_BRACKETS = "<" + chr(0xFF1C) + chr(0xFE64)
_OPENING_BRACKET_PATTERN = re.compile("[" + re.escape(_OPENING_BRACKETS) + "]")
#: How far after a bracket the tag name is looked for — wide enough for a name
#: padded with invisible characters. Bounded: the escape stays linear.
_TAG_WINDOW_CHARS = 256
_WRAPPER_TAG_NAME = EXTERNAL_CONTENT_OPEN_TAG.lstrip("<")


def _names_the_wrapper(window: str) -> bool:
    """Whether a bracket followed by ``window`` reads as the wrapper's tag.

    Read as a model reads it: compatibility forms folded (NFKC), case folded,
    blanks and format characters (zero-width, bidi) skipped, a leading slash
    of any width skipped. Compared character by character and abandoned at
    the first one that differs — ``<em>`` costs two characters, measured: a
    whole-window normalisation took 1.2 s on 40 000 characters of ``<e``.

    Args:
        window: The characters right after the bracket.

    Returns:
        True when they spell the wrapper's tag name, opening or closing.
    """
    matched = 0
    for char in window:
        if unicodedata.category(char) == "Cf":
            continue
        for folded in unicodedata.normalize("NFKC", char).casefold():
            if folded.isspace() or (folded == "/" and matched == 0):
                continue
            if folded != _WRAPPER_TAG_NAME[matched]:
                return False
            matched += 1
            if matched == len(_WRAPPER_TAG_NAME):
                return True
    return False


def _escape_tags(content: str) -> str:
    """Neutralise every bracket that would open or close the wrapper, however spelled.

    The escape knew one spelling, and a model reads ``</EXTERNAL_CONTENT>``, a
    fullwidth bracket or a zero-width split as the same tag (point 4). Each
    bracket is judged on a short window after it: one search over the content
    and a bounded look at each bracket, linear by construction (ADR-326).

    Args:
        content: Third-party text about to be wrapped.

    Returns:
        The text, every such bracket written ``&lt;``.
    """
    parts: list[str] = []
    start = 0
    for match in _OPENING_BRACKET_PATTERN.finditer(content):
        index = match.start()
        if _names_the_wrapper(content[index + 1 : index + 1 + _TAG_WINDOW_CHARS]):
            parts.append(content[start:index])
            parts.append("&lt;")
            start = index + 1
    parts.append(content[start:])
    return "".join(parts)


#: Longest source name kept in the opening tag: a URL is rarely longer, and
#: a stranger's file name that is has nothing more to say.
_SOURCE_ATTRIBUTE_MAX_CHARS = 512
_ATTRIBUTE_ESCAPES = {'"': "&quot;", "<": "&lt;", ">": "&gt;"}


def _safe_attribute(value: str) -> str:
    """A source name that stays INSIDE its attribute, on one line, bounded.

    A source name is a stranger's text too — a mail attachment's file name, a
    page title — so a quote, an angle bracket or a line break in it must not
    close the tag or land a line before the untrusted warning.
    """
    one_line = " ".join(value.split())
    escaped = "".join(_ATTRIBUTE_ESCAPES.get(char, char) for char in one_line)
    return escaped[:_SOURCE_ATTRIBUTE_MAX_CHARS]


def wrap_external_content(
    content: str,
    source_url: str,
    source_type: str = "web_page",
) -> str:
    """Wrap untrusted external content with safety markers.

    Adds XML-like tags and an UNTRUSTED warning that instructs the LLM
    to treat the enclosed content as data only.

    Args:
        content: The raw external content to wrap.
        source_url: URL or identifier of the content source.
        source_type: Type of content (e.g., "web_page", "search_synthesis", "search_snippet").

    Returns:
        Wrapped content string with safety markers.
    """
    if not content:
        return content

    escaped_content = _escape_tags(content)
    safe_source_url = _safe_attribute(source_url)

    return (
        f'{EXTERNAL_CONTENT_OPEN_TAG} source="{safe_source_url}" type="{source_type}">'
        f"\n{EXTERNAL_CONTENT_WARNING}\n"
        f"{escaped_content}\n"
        f"{EXTERNAL_CONTENT_CLOSE_TAG}"
    )
