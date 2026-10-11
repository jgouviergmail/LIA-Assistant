"""Linear HTML-markup detection shared by rich text and saved-answer projections."""

import re

# Recognised HTML element tags emitted by the response/display layer.
_TAGS = (
    r"div|p|span|style|script|h[1-6]|ul|ol|li|table|thead|tbody|tr|td|th"
    r"|a|strong|em|b|i|blockquote|code|pre"
)
_OPEN_TAG_RE = re.compile(rf"<({_TAGS})\b[^<>]*>", re.IGNORECASE)
_CLOSE_TAG_RE = re.compile(rf"</({_TAGS})\s*>", re.IGNORECASE)
_VOID_TAG_RE = re.compile(r"<(?:br|hr|img)\b[^<>]*/?>", re.IGNORECASE)
# ``<tag attr="value">`` — an attribute is a signal prose never produces, and it
# is what keeps a *truncated* document (opening tags, no closing ones) detected.
_ATTR_TAG_RE = re.compile(rf"""<(?:{_TAGS})\s+[a-z-]+\s*=\s*["']""", re.IGNORECASE)


def looks_like_html(text: str) -> bool:
    """Cheaply detect genuine HTML markup (not a bare '<' in prose or code).

    Guards :func:`strip_html_if_markup`, whose stripper ends with
    ``re.sub(r"<[^<>]+>", "", text)`` and would otherwise delete chunks of prose.
    Merely spotting a lone ``<tag`` is not enough: single-letter element names
    collide with ordinary comparisons and generics, so ``"if x<a and b>c"``,
    ``"count<b et total>i"`` and ``"vector<i> v; map<p,tr> m;"`` were all
    detected as HTML and silently mutilated ("if xc", "counti", "vector v").

    Markup is therefore accepted on three signals, any of which suffices:

    1. a **matched pair** — the same tag name opened and closed;
    2. a **void element** (``<br>``, ``<hr>``, ``<img>``), which never closes;
    3. a **tag carrying an attribute** (``<div class="…">``), which prose does
       not produce — this is what keeps a truncated document, all opening tags
       and no closing ones, correctly detected.

    Implemented as full scans plus a set intersection rather than a
    backreference (``<(tag)…>.*?</\\1>``): the backreference form is
    super-linear on a run of unclosed opening tags (24 KB of ``<p>`` cost
    448 ms), and this runs synchronously on the event loop.

    Args:
        text: Candidate text, possibly containing markup.

    Returns:
        True when the text carries genuine HTML markup.
    """
    if not text:
        return False
    opened = {name.lower() for name in _OPEN_TAG_RE.findall(text)}
    if opened and opened & {name.lower() for name in _CLOSE_TAG_RE.findall(text)}:
        return True
    return bool(_VOID_TAG_RE.search(text)) or bool(_ATTR_TAG_RE.search(text))
