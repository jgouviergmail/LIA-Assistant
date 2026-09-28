"""A feed's items, normalised into what the newsroom stores.

Feeds are written by many hands and each one is wrong somewhere: HTML inside a
summary, relative links, tracking parameters, no date, a date in the future,
the same story twice under two GUIDs, a feed declared UTF-8 that is not. This
module turns one feed body into bounded, plain-text items with a stable
identity:

- ``item_key`` — the item's identity inside its feed (its GUID, else its
  canonical link), hashed so it fits an index whatever its length;
- ``fingerprint`` — the same STORY across outlets (a normalised title), a hint
  the editor may use to group coverage; never used to drop anything;
- ``published_at`` — the item's date in UTC, never later than the fetch
  (a feed dated tomorrow is a feed with a wrong clock, and « the newest »
  must not be decided by a lie).

Pure and synchronous (feedparser is CPU work): the collector calls it through
``asyncio.to_thread``.
"""

from __future__ import annotations

import calendar
import hashlib
import html
import io
import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import feedparser

from src.domains.radio.constants import URL_MAX_BYTES

#: Bounds of what an item may carry into the store.
TITLE_MAX_CHARS: Final[int] = 300
SUMMARY_MAX_CHARS: Final[int] = 1500

# A '<' in prose cannot consume the next tag (and repeated openers must
# remain linear). Decode references only AFTER stripping real markup.
_TAG_RE: Final[re.Pattern[str]] = re.compile(r"<[A-Za-z/!][^<>]*>")
#: Every control character (C0, DEL, C1) read as a space: PostgreSQL refuses NUL
#: in a text, and no reader wants the others — one of them in one item would
#: make the whole feed's stories a batch the database refuses.
CONTROL_CHARACTERS: Final[dict[int, str]] = dict.fromkeys((*range(0x20), *range(0x7F, 0xA0)), " ")
_WS_RE: Final[re.Pattern[str]] = re.compile(r"\s+")
#: Query parameters that only say where a click came from.
_TRACKING_PREFIXES: Final[tuple[str, ...]] = ("utm_", "at_", "fbclid", "gclid", "mc_")


@dataclass(frozen=True, slots=True)
class ParsedItem:
    """One normalised item of a feed.

    Attributes:
        item_key: Identity inside the feed (hashed GUID or canonical link).
        url: The canonical article URL (http/https only).
        title: Plain text, bounded.
        summary: Plain text, bounded (may be empty).
        published_at: UTC, never after the fetch.
        fingerprint: A normalised title, the same story across outlets.
    """

    item_key: str
    url: str
    title: str
    summary: str
    published_at: datetime
    fingerprint: str


def plain_text(value: str, limit: int) -> str:
    """HTML to one line of plain text, unescaped, bounded at a word boundary.

    Args:
        value: Raw feed text (may hold tags and entities).
        limit: Maximum characters.

    Returns:
        The text, ending in an ellipsis when it was cut.
    """
    unescaped = html.unescape(_TAG_RE.sub(" ", value)).translate(CONTROL_CHARACTERS)
    text = _WS_RE.sub(" ", unescaped).strip()
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0].rstrip(" ,;:")
    return cut + "…"


def canonical_url(link: str, base: str) -> str | None:
    """An absolute http(s) URL without tracking parameters or fragment.

    Args:
        link: The item's link (may be relative).
        base: The feed's URL, to resolve a relative link against.

    Returns:
        The canonical URL, or ``None`` when it is not a web URL (a control
        character included: no request can carry it) or is longer
        than the newsroom keeps (:data:`URL_MAX_BYTES`).
    """
    absolute = urljoin(base, link.strip())
    parts = urlsplit(absolute)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None
    query = urlencode(
        [
            (key, value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
            if not key.lower().startswith(_TRACKING_PREFIXES)
        ]
    )
    url = urlunsplit((parts.scheme, parts.netloc.lower(), parts.path, query, ""))
    if any(ord(char) in CONTROL_CHARACTERS for char in url):
        return None
    return url if len(url.encode("utf-8")) <= URL_MAX_BYTES else None


def fingerprint(title: str) -> str:
    """The same story under two outlets' punctuation, case and accents."""
    folded = unicodedata.normalize("NFKD", title.casefold())
    letters = "".join(c for c in folded if not unicodedata.combining(c))
    words = re.findall(r"\w+", letters)
    return " ".join(words)[:200]


def _published(entry: Any, fetched_at: datetime) -> datetime:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return fetched_at
    try:
        stamp = datetime.fromtimestamp(calendar.timegm(parsed), tz=UTC)
    except OverflowError, OSError, ValueError:
        return fetched_at
    return min(stamp, fetched_at)


def _summary_source(entry: Any) -> str:
    """The summary, else the entry's content (an Atom feed may carry only that)."""
    summary = entry.get("summary")
    if summary:
        return str(summary)
    contents = entry.get("content") or []
    return str(contents[0].get("value") or "") if contents else ""


def _key(entry: Any, url: str) -> str:
    identity = str(entry.get("id") or entry.get("guid") or url).strip() or url
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:40]


def parse_feed(content: bytes, *, feed_url: str, fetched_at: datetime) -> list[ParsedItem]:
    """Normalise every usable entry in a bounded feed body.

    Args:
        content: The raw body (encoding sniffed by feedparser).
        feed_url: The feed's URL (resolves relative links).
        fetched_at: When it was read (aware), the ceiling of every date.

    Returns:
        The usable items: a web link and a title each, deduplicated by key.
        A body that is not a feed yields no item rather than an error.
    """
    # A stream, never the bytes themselves: handed bytes, feedparser first tries
    # them as a FILE PATH (measured: a body reading ``/srv/x.xml`` yields that
    # local file's items), so a hostile server could make the newsroom read disk.
    parsed = feedparser.parse(io.BytesIO(content))
    items: list[ParsedItem] = []
    seen: set[str] = set()
    for entry in parsed.entries:
        url = canonical_url(str(entry.get("link") or ""), feed_url)
        title = plain_text(str(entry.get("title") or ""), TITLE_MAX_CHARS)
        if url is None or not title:
            continue
        key = _key(entry, url)
        if key in seen:
            continue
        seen.add(key)
        summary = plain_text(_summary_source(entry), SUMMARY_MAX_CHARS)
        items.append(
            ParsedItem(
                item_key=key,
                url=url,
                title=title,
                summary=summary if summary != title else "",
                published_at=_published(entry, fetched_at),
                fingerprint=fingerprint(title),
            )
        )
    return items


__all__ = [
    "CONTROL_CHARACTERS",
    "SUMMARY_MAX_CHARS",
    "TITLE_MAX_CHARS",
    "ParsedItem",
    "canonical_url",
    "fingerprint",
    "parse_feed",
    "plain_text",
]
