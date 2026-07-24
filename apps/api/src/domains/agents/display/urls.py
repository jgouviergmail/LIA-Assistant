"""
URL safety and URL building for the card layer.

Extracted from ``components/base.py`` (file-size ratchet): the helpers that
decide what may end up in an ``href``/``src`` form a cohesive unit, and one of
them — :func:`safe_url` — is the only thing standing between a payload URL and
a clickable link in the assistant's answer.

Re-exported by ``components/base.py`` so cards keep a single import surface.
"""

from __future__ import annotations

import html
import re
from urllib.parse import quote


def _escape(text: str) -> str:
    """Escape HTML special characters.

    Local to this module on purpose: ``components/base.py`` imports FROM here,
    so importing its ``escape_html`` back would close an import cycle.
    """
    return html.escape(text)


# A hex color, with or without the leading '#': #RGB / #RRGGBB / #RRGGBBAA.
_HEX_COLOR_RE = re.compile(r"^#?(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
# A bare CSS color keyword: "red", "dodgerblue". Digits/spaces/punctuation out.
_CSS_KEYWORD_RE = re.compile(r"^[a-zA-Z]+$")


def safe_css_color(color: str | None, *, default: str = "") -> str:
    """
    Return ``color`` normalised for an inline ``style`` attribute, else ``default``.

    Accepts a hex color (with or without the leading ``#`` — Google returns both)
    or a bare CSS color keyword. Everything else — a value carrying a quote, a
    semicolon, ``url(...)``, or an ``on*`` breakout — is rejected. Transit line
    colors reach the route card straight from the Google Routes API and are
    interpolated verbatim into ``style="... {color} ..."``; without this gate a
    ``"`` ends the attribute and the remainder injects an event handler.

    Args:
        color: Candidate color from external data (may be None).
        default: Value returned when the candidate is unsafe or empty.

    Returns:
        A hex color prefixed with ``#``, a lowercase-safe keyword, or ``default``.

    Example:
        >>> safe_css_color("#FF0000")
        '#FF0000'
        >>> safe_css_color("00aa00")
        '#00aa00'
        >>> safe_css_color("red")
        'red'
        >>> safe_css_color('#fff" onmouseover="alert(1)')
        ''
    """
    if not color:
        return default

    candidate = str(color).strip()

    if _HEX_COLOR_RE.match(candidate):
        return candidate if candidate.startswith("#") else f"#{candidate}"

    if _CSS_KEYWORD_RE.match(candidate):
        return candidate

    return default


# Schemes a card may put in an href/src. Everything else — javascript:, data:,
# vbscript:, file: — is dropped. HTML escaping alone does NOT protect these:
# "javascript:alert(1)" contains no character html.escape() touches.
_SAFE_URL_SCHEMES: tuple[str, ...] = ("http://", "https://", "mailto:", "tel:")

# Characters a browser strips (or ignores) BEFORE resolving the scheme, which
# would otherwise smuggle "java\tscript:..." past a naive prefix check.
_URL_IGNORABLE_CHARS_RE = re.compile(r"[\x00-\x20\x7f]")


def safe_url(url: str | None) -> str:
    """
    Escape a URL for an ``href``/``src`` attribute, dropping unsafe schemes.

    Card payloads carry URLs from places the user does not control: web-search
    results, Wikipedia, place websites, Drive links, arbitrary MCP servers and
    user-authored skills. HTML escaping makes such a value safe as TEXT but
    not as a URI: ``javascript:alert(1)`` survives escaping untouched and runs
    on click, in the application origin.

    Args:
        url: Raw URL from a payload (may be None).

    Returns:
        The HTML-escaped URL when its scheme is allowed (or when it is a
        site-relative path), and an empty string otherwise.

    Example:
        >>> safe_url("https://example.com/a?b=1&c=2")
        'https://example.com/a?b=1&amp;c=2'
        >>> safe_url("javascript:alert(1)")
        ''
    """
    if not url:
        return ""

    candidate = str(url).strip()
    normalised = _URL_IGNORABLE_CHARS_RE.sub("", candidate).lower()

    if normalised.startswith(_SAFE_URL_SCHEMES):
        return _escape(candidate)

    # Site-relative paths (the attachment proxy builds one) — but never the
    # protocol-relative "//host" form, which would leave the origin open.
    if normalised.startswith("/") and not normalised.startswith("//"):
        return _escape(candidate)

    return ""


def build_directions_url(destination: str) -> str:
    """
    Build a Google Maps Directions URL for the given destination.

    Uses Google Maps Directions API format which will automatically use
    the user's current location (GPS on mobile, or prompt on desktop).

    This is the centralized function for all address/location links across
    all card components to ensure consistent behavior.

    Args:
        destination: Address or location name to navigate to

    Returns:
        Google Maps Directions URL

    Example:
        >>> build_directions_url("123 Main St, Paris")
        'https://www.google.com/maps/dir/?api=1&destination=123%20Main%20St%2C%20Paris'
    """
    # str(): the destination reaches this helper from provider payloads and MCP
    # results, where a non-string would make quote() raise and cost the answer
    # every card (the render step catches TypeError globally).
    encoded_destination = quote(str(destination), safe="")
    return f"https://www.google.com/maps/dir/?api=1&destination={encoded_destination}"


def build_place_url(place_id: str | None = None, query: str | None = None) -> str:
    """
    Build a Google Maps Place URL to view a place's page (not directions).

    Args:
        place_id: Google Place ID (e.g., 'ChIJ...')
        query: Fallback search query (name + address) if no place_id

    Returns:
        Google Maps Place/Search URL

    Example:
        >>> build_place_url(place_id="ChIJN1t_tDeuEmsRUsoyG83frY4")
        'https://www.google.com/maps/place/?q=place_id:ChIJN1t_tDeuEmsRUsoyG83frY4'
        >>> build_place_url(query="Eiffel Tower, Paris")
        'https://www.google.com/maps/search/?api=1&query=Eiffel%20Tower%2C%20Paris'
    """
    if place_id:
        # Direct place page with place_id
        return f"https://www.google.com/maps/place/?q=place_id:{quote(str(place_id), safe='')}"
    elif query:
        # Search URL as fallback
        encoded_query = quote(str(query), safe="")
        return f"https://www.google.com/maps/search/?api=1&query={encoded_query}"
    return ""
