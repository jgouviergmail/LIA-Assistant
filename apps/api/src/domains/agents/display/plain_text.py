"""Rich assistant content → plain text, for surfaces that cannot render markup.

The assistant's reply is authored as *rich* content: an HTML document wrapped
in ``<div class="lia-response">`` when the user's display mode is ``html``,
server-rendered data cards and interactive widgets appended post-LLM, Markdown
otherwise. Every surface that renders the text verbatim — the TTS engine, FCM
push bodies (the service worker passes ``body`` straight to
``showNotification``), toast previews, plain-text channels — must flatten that
markup first, or the user hears tags read aloud and reads ``<div
class="lia-response">`` on their lock screen.

This module owns the *detection* half as well, and that is the point of it
existing: :func:`html_to_text` ends with ``re.sub(r"<[^>]+>", "", text)``,
which would happily delete ``"< 5 and y >"`` from the prose
``"x < 5 and y > 3"``. Stripping therefore runs only when genuine HTML element
tags are present, so the helpers are safe to apply unconditionally at any
entry point.

``html_to_text`` is imported lazily so this module keeps no import-time
dependency on the display package — that is what lets ``infrastructure``
callers import it at module level without inverting the layer graph.

It owns the MARKDOWN half for the same reason. A surface that renders neither
vocabulary renders both literally, and the two arrive together: a HITL
confirmation is Markdown written by our own renderer around a value that may be
HTML written by a mail client. :func:`markdown_to_plain_text` runs both, in that
order, and is the ONE door for such a surface — a ticket comment, where
``**Titre**`` and ``<br/>`` were read out exactly as typed (ADR-276, lot 13).
"""

import re

# Recognised HTML element tags emitted by the response/display layer.
_TAGS = (
    r"div|p|span|style|script|h[1-6]|ul|ol|li|table|thead|tbody|tr|td|th"
    r"|a|strong|em|b|i|blockquote|code|pre"
)
_OPEN_TAG_RE = re.compile(rf"<({_TAGS})\b[^>]*>", re.IGNORECASE)
_CLOSE_TAG_RE = re.compile(rf"</({_TAGS})\s*>", re.IGNORECASE)
_VOID_TAG_RE = re.compile(r"<(?:br|hr|img)\b[^>]*/?>", re.IGNORECASE)
# ``<tag attr="value">`` — an attribute is a signal prose never produces, and it
# is what keeps a *truncated* document (opening tags, no closing ones) detected.
_ATTR_TAG_RE = re.compile(rf"""<(?:{_TAGS})\s+[a-z-]+\s*=\s*["']""", re.IGNORECASE)

# Material Symbols icons render as <span class="material-symbols-outlined">NAME
# </span>, where NAME is a LIGATURE IDENTIFIER ("event", "mail", "star") that the
# font turns into a glyph — it is never prose. ``html_to_text`` keeps element
# text, so without this the icon name leaks into the flattened output: a data
# card became "event Déjeuner avec Marie 12:30" on a lock screen, and the TTS
# engine read "event" aloud before the sentence. Dropped whole, content included.
#
# The body is ``[^<]*``, not ``.*?``: an icon's text is a bare ligature name and
# cannot contain '<', so this is both exact and unable to swallow neighbouring
# markup when a span is left unclosed. Either quote style is accepted — the
# server renders double quotes, but the pattern must not silently miss an icon
# over a quoting detail.
_ICON_SPAN_RE = re.compile(
    r"""<span[^>]*class=["'][^"']*material-symbols-outlined[^"']*["'][^>]*>[^<]*</span\s*>""",
    re.IGNORECASE,
)


def looks_like_html(text: str) -> bool:
    """Cheaply detect genuine HTML markup (not a bare '<' in prose or code).

    Guards :func:`strip_html_if_markup`, whose stripper ends with
    ``re.sub(r"<[^>]+>", "", text)`` and would otherwise delete chunks of prose.
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


def strip_html_if_markup(text: str) -> str:
    """Strip HTML to readable plain text, but only when markup is present.

    A no-op on Markdown and plain prose, so it is safe to apply unconditionally
    at any surface entry point without mangling normal replies.

    Icon spans are dropped whole beforehand — their text is a font ligature
    name, not content (see :data:`_ICON_SPAN_RE`).

    Args:
        text: Assistant content, possibly HTML.

    Returns:
        The text with markup flattened, or the input unchanged when it carries
        no recognised HTML element tag.
    """
    if not text or not looks_like_html(text):
        return text
    from src.domains.agents.display.components.base import html_to_text

    return html_to_text(_ICON_SPAN_RE.sub(" ", text), preserve_links=False)


#: ``[label](url)`` — the label is what a reader needs, the URL what they lose.
#: The target must be an http(s) URL with no space in it: ``[le devis](voir
#: plus bas)`` is prose, and flattening it would invent a link that is not one.
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
#: A fenced block's delimiter line, with or without a language tag.
_MD_FENCE_RE = re.compile(r"^[ \t]*(?:```|~~~)[^\n]*\n?", re.MULTILINE)
#: Emphasis, which always comes in pairs: bold, italic, strike-through, code.
#: ``_`` is deliberately absent — in the text these surfaces carry it lives
#: inside identifiers (``run_id``, ``in_progress``) far more often than around
#: emphasis, and stripping it there would corrupt the value being confirmed.
_MD_EMPHASIS_RE = re.compile(r"(\*\*|\*|~~|`)(?=\S)(.+?)(?<=\S)\1", re.DOTALL)
#: A heading's leading hashes, and a blockquote's mark.
_MD_HEADING_RE = re.compile(r"^[ \t]*#{1,6}[ \t]+", re.MULTILINE)
_MD_QUOTE_RE = re.compile(r"^[ \t]*>[ \t]?", re.MULTILINE)
#: An unordered list marker. A bullet REPLACES it rather than being dropped: a
#: list with no mark at all reads as prose that lost its punctuation.
_MD_BULLET_RE = re.compile(r"^([ \t]*)[-*+][ \t]+", re.MULTILINE)
#: A table's delimiter row (``|---|:--:|``). The header and the rows are data a
#: reader wants; this line only tells a renderer where the head stops, and it
#: must go BEFORE the bullet rule, which would read its dashes as a list.
_MD_TABLE_RULE_RE = re.compile(
    r"^[ \t]*\|?[ \t]*:?-{2,}:?[ \t]*(\|[ \t]*:?-*:?[ \t]*)*\|?[ \t]*$\n?", re.MULTILINE
)
#: Three line breaks or more — a gap nothing renders and every surface shows.
_MD_BLANK_RUN_RE = re.compile(r"\n{3,}")
#: ``<br>`` in any spelling: a line break someone wrote as markup.
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)


def markdown_links_to_plain(text: str) -> str:
    """Convert markdown links to "label (url)" for surfaces without markdown.

    FCM push bodies and Telegram (HTML parse_mode with escaping) would render
    raw markdown syntax; this keeps appended source links readable there
    (ADR-131). Chat archive and SSE keep the original markdown.

    Args:
        text: Content, possibly containing markdown links.

    Returns:
        The text with every markdown link flattened to "label (url)".
    """
    return _MD_LINK_RE.sub(r"\1 (\2)", text)


def markdown_to_plain_text(text: str) -> str:
    """Flatten Markdown *and* HTML into text a bare surface can render.

    For a surface that renders neither vocabulary — a ticket comment is a
    paragraph of escaped text — and where both arrive: LIA's own words are
    Markdown, and the value inside a HITL confirmation may be HTML written by
    somebody else's mail client. Line structure is PRESERVED (such a surface
    honours newlines); only the marks go.

    Order is load-bearing. ``<br/>`` becomes a real break BEFORE the HTML
    stripper runs, since a text whose only markup is ``<br/>`` would otherwise
    be flattened onto one line; the fences go before the emphasis, so a code
    fence's language tag is never mistaken for content; a table's delimiter row
    goes before the bullet rule, which would otherwise read its dashes as a
    list; and the emphasis pass runs twice, because a nested pair
    (``**a `b`**``) only becomes a pair of its own once the outer one is gone.

    Args:
        text: Content, possibly Markdown, possibly HTML, possibly both.

    Returns:
        The same text, marks removed and lines kept.
    """
    if not text:
        return text
    out = strip_html_if_markup(_BR_RE.sub("\n", text))
    out = _MD_FENCE_RE.sub("", out)
    out = _MD_HEADING_RE.sub("", out)
    out = _MD_QUOTE_RE.sub("", out)
    out = _MD_TABLE_RULE_RE.sub("", out)
    out = _MD_BULLET_RE.sub(r"\1• ", out)
    out = markdown_links_to_plain(out)
    out = _MD_EMPHASIS_RE.sub(r"\2", _MD_EMPHASIS_RE.sub(r"\2", out))
    return _MD_BLANK_RUN_RE.sub("\n\n", out).strip()
