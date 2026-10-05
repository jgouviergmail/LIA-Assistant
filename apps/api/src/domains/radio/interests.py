"""A listener's interests as stories (ADR-324 decision 40).

What the listener cares about is searched on the web and what comes back is filed as
stories of their own interest row, so every news programme can draw from the sources
OR from the interests with the same shortlists, the same aired ledger and the same
article page. This module is the pure part:

- a search result becomes a story exactly as a feed item would have: a canonical web
  URL, a bounded plain-text title and summary, the story's fingerprint across outlets,
  a date never later than when it was found (:func:`interest_story`);
- the topics the start read are searched, each at most once while its last search is
  fresh, and every search is one consultation of the listener's own key — ``failed``
  when it failed, and then not marked, so the next session tries again
  (:func:`refresh_interest_stories`);
- the desk reads those stories under a bound of their own, the most the searches can
  file within its horizon, so no story the listener's key paid for is ever cut
  (:func:`interest_stories_max`).

What searches, what remembers a search and what files a story are ports: the listener's
own connectors, Redis and the repository.
"""

from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from time import perf_counter
from typing import Protocol
from urllib.parse import urlsplit

import structlog

from src.domains.radio.constants import OUTLET_MAX_CHARS
from src.domains.radio.newsroom.parse import (
    SUMMARY_MAX_CHARS,
    TITLE_MAX_CHARS,
    canonical_url,
    fingerprint,
    plain_text,
)
from src.domains.radio.readers import ConsultationRecorder
from src.domains.shared.commercial_content import editorial_excerpt, is_commercial_content

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class InterestStory:
    """One article a search found, as the newsroom would have filed a feed item.

    Attributes:
        item_key: Its identity within the listener's interest row.
        url: The article (canonical).
        title: The headline.
        summary: What the search said it reports (may be empty).
        outlet: The outlet that published it.
        published_at: When it was published — when it was found, when unknown.
        fingerprint: The same story across outlets.
    """

    item_key: str
    url: str
    title: str
    summary: str
    outlet: str
    published_at: datetime
    fingerprint: str


def interest_story(
    *,
    url: str,
    title: str,
    summary: str,
    outlet: str,
    published_at: datetime | None,
    found_at: datetime,
) -> InterestStory | None:
    """One search result as a story, or ``None`` when it is no web article.

    Args:
        url: The result's address.
        title: Its headline (may hold markup).
        summary: What the search says it reports (may hold markup).
        outlet: The outlet the search names (may be empty).
        published_at: Its date, when the search gives one (aware).
        found_at: When it was found (aware), the ceiling of every date.

    Returns:
        The story, or ``None`` for an address the newsroom would not keep or an
        empty headline.
    """
    if is_commercial_content(title, summary=summary):
        return None
    canonical = canonical_url(url, url)
    headline = plain_text(title, TITLE_MAX_CHARS)
    if canonical is None or not headline:
        return None
    text = plain_text(editorial_excerpt(summary), SUMMARY_MAX_CHARS)
    site = (urlsplit(canonical).hostname or "").removeprefix("www.")
    return InterestStory(
        item_key=hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:40],
        url=canonical,
        title=headline,
        summary=text if text != headline else "",
        outlet=plain_text(outlet, OUTLET_MAX_CHARS) or site[:OUTLET_MAX_CHARS],
        published_at=min(published_at, found_at) if published_at is not None else found_at,
        fingerprint=fingerprint(headline),
    )


class InterestSearch(Protocol):
    """Searches the web for one interest with the listener's own key."""

    #: The consultation section a search is filed under (``brave``, ``perplexity``).
    section: str

    async def search(self, topic: str, *, language: str, found_at: datetime) -> list[InterestStory]:
        """The recent articles about ``topic``; raises when the search failed."""
        ...


class SearchMarks(Protocol):
    """Which topics were searched recently enough to reuse what was found."""

    async def fresh(self, topic: str) -> bool:
        """Whether the topic's last search is still fresh."""
        ...

    async def mark(self, topic: str) -> None:
        """The topic was just searched."""
        ...


def interest_stories_max(
    *, topics: int, stories_per_search: int, fresh_s: int, horizon_s: int
) -> int:
    """The most stories the searches can have filed within a desk's horizon.

    Each topic is searched at most once per freshness window, and a story is never dated
    after it was found, so within any horizon a topic is searched at most
    ``horizon_s // fresh_s + 1`` times, each search filing at most ``stories_per_search``
    new stories. Read under this bound, every story a search filed reaches the desk while
    the interests stay the same.

    Args:
        topics: The most topics a start reads.
        stories_per_search: The most stories one search keeps.
        fresh_s: How long a topic's search stays fresh (seconds, positive).
        horizon_s: The oldest story the desk reads (seconds).

    Returns:
        The bound; 0 when no topic is read.
    """
    return topics * stories_per_search * (horizon_s // fresh_s + 1)


async def refresh_interest_stories(
    topics: Sequence[str],
    *,
    search: InterestSearch,
    marks: SearchMarks,
    file: Callable[[Sequence[InterestStory]], Awaitable[int]],
    record: ConsultationRecorder,
    language: str,
    now: datetime,
    max_age_s: int,
) -> int:
    """Search the interests the start read that were not searched lately, and file what
    they found.

    Args:
        topics: The listener's interests the start read, strongest first — already
            bounded there (``RADIO_INTEREST_TOPICS_MAX``), the count the writer is told.
        search: The listener's own search.
        marks: Which topics were searched lately.
        file: Files stories, returns how many were new.
        record: Files each search as a consultation of the listener's key.
        language: The listener's language (the search's).
        now: The instant (aware).
        max_age_s: The oldest story a news programme may air: an older one is
            never filed (the purge would take it before any programme could).

    Returns:
        How many new stories were filed.
    """
    filed = 0
    oldest = now - timedelta(seconds=max_age_s)
    for topic in [topic.strip() for topic in topics if topic.strip()]:
        if await marks.fresh(topic):
            continue
        started = perf_counter()
        succeeded = False
        try:
            stories = await search.search(topic, language=language, found_at=now)
            succeeded = True
        except Exception as exc:  # noqa: BLE001 — one blind search, never the session
            logger.warning(
                "radio_interest_search_failed",
                section=search.section,
                error_type=type(exc).__name__,
            )
            continue
        finally:
            section = frozenset({search.section})
            record(
                opened=section if succeeded else frozenset(),
                failed=frozenset() if succeeded else section,
                duration_ms=int((perf_counter() - started) * 1000),
            )
        filed += await file([story for story in stories if story.published_at >= oldest])
        await marks.mark(topic)
    return filed


__all__ = [
    "InterestSearch",
    "InterestStory",
    "SearchMarks",
    "interest_stories_max",
    "interest_story",
    "refresh_interest_stories",
]
