"""Finding the feed of a site a person names.

A person adds « a site », not a feed URL: the page may BE a feed, advertise one
in its ``<link rel="alternate">`` tags (the RSS autodiscovery convention), or
advertise nothing while its publishing system serves one at a conventional
path (measured 2026-09-26: bellingcat.com advertises no feed, WordPress serves
it at ``/feed/``). Pure and synchronous: the caller fetches every candidate
safely and keeps the first that :func:`describe_feed` recognises
(:mod:`~src.domains.radio.newsroom.sources`).
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Final
from urllib.parse import urlsplit

import feedparser
from lxml import html as lxml_html
from lxml.etree import ParserError

from src.domains.radio.constants import LANGUAGE_TAG_MAX_CHARS
from src.domains.radio.newsroom.parse import canonical_url, plain_text

#: Feeds offered at most for one page (a site advertising dozens is a sitemap).
DISCOVERED_MAX: Final[int] = 10
#: Where common publishing systems serve their feed (WordPress, Ghost and
#: most static generators), tried when a page advertises none.
CONVENTIONAL_FEED_PATHS: Final[tuple[str, ...]] = (
    "/feed/",
    "/rss",
    "/rss.xml",
    "/feed.xml",
    "/atom.xml",
    "/index.xml",
)

#: The advertised types the parser reads (feedparser 6 reads no JSON Feed:
#: a site offering one offers RSS or Atom beside it).
_FEED_TYPES: Final[frozenset[str]] = frozenset({"application/rss+xml", "application/atom+xml"})
#: The longest feed title shown (a stranger wrote it).
FEED_TITLE_MAX_CHARS: Final[int] = 120


@dataclass(frozen=True, slots=True)
class FeedDescription:
    """What a feed says of itself, shown to the person before it is added.

    Attributes:
        title: Its own title, bounded (empty when it gives none).
        language: The language it declares, as written, when it declares one.
        entries: How many entries it carries now.
    """

    title: str
    language: str | None
    entries: int


def _is_language_tag(tag: str) -> bool:
    """A tag the station can file and read: ASCII letters, digits and separators, bounded."""
    return 0 < len(tag) <= LANGUAGE_TAG_MAX_CHARS and all(
        char.isascii() and (char.isalnum() or char in "-_") for char in tag
    )


def describe_feed(content: bytes) -> FeedDescription | None:
    """The feed a body is, or ``None`` when it is not a feed with at least one entry."""
    # A stream, never bytes: feedparser tries bytes as a local file path first.
    parsed = feedparser.parse(io.BytesIO(content))
    feed = parsed.get("feed")
    if not parsed.entries or not feed:
        return None
    title = plain_text(str(feed.get("title") or ""), FEED_TITLE_MAX_CHARS)
    tag = str(feed.get("language") or "").strip()
    language = tag if _is_language_tag(tag) else None
    return FeedDescription(title=title, language=language, entries=len(parsed.entries))


def advertised_feeds(page: bytes, base_url: str) -> list[str]:
    """The web feed URLs a page advertises, absolute, in page order, without repeats.

    Args:
        page: The page's HTML.
        base_url: The page's URL (resolves relative hrefs).

    Returns:
        Up to :data:`DISCOVERED_MAX` URLs; empty for a page that is not HTML.
    """
    try:
        tree = lxml_html.fromstring(page)
    except ParserError, ValueError:
        return []
    found: list[str] = []
    for link in tree.iter("link"):
        rel = (link.get("rel") or "").lower().split()
        kind = (link.get("type") or "").lower().strip()
        if "alternate" not in rel or kind not in _FEED_TYPES:
            continue
        url = canonical_url(link.get("href") or "", base_url)
        if url and url not in found:
            found.append(url)
            if len(found) >= DISCOVERED_MAX:
                break
    return found


def candidate_feeds(page: bytes, base_url: str) -> list[str]:
    """The URLs worth trying as the site's feed, most likely first.

    Args:
        page: The page's HTML.
        base_url: The page's URL.

    Returns:
        The advertised feeds; when there is none, the conventional paths on
        the page's origin.
    """
    advertised = advertised_feeds(page, base_url)
    if advertised:
        return advertised
    parts = urlsplit(base_url)
    origin = f"{parts.scheme}://{parts.netloc}"
    return [origin + path for path in CONVENTIONAL_FEED_PATHS]


__all__ = [
    "CONVENTIONAL_FEED_PATHS",
    "DISCOVERED_MAX",
    "FEED_TITLE_MAX_CHARS",
    "FeedDescription",
    "advertised_feeds",
    "candidate_feeds",
    "describe_feed",
]
