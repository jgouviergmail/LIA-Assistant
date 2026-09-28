"""A site a listener adds to their newsroom: the feed it serves, found safely (ADR-324).

A person names a SITE, not a feed URL (« bellingcat.com »). The site is read
through the newsroom's own fetch — every hop validated against private
addresses, the body bounded — and its robots.txt, and the feed kept is the
FIRST that parses with at least one entry among: the address itself (it may BE
a feed), the feeds its page advertises, the conventional paths its publishing
system serves. What was found is DESCRIBED — its title, the language it
declares, how many entries it carries — so the settings show the person what
they are about to add before anything is stored.

Every way this can fail is named, because each asks the person for something
different: an address with nothing public behind it, a site that does not
answer, a site whose robots.txt closes it to the newsroom, a site that serves
no feed.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

import httpx

from src.domains.radio.newsroom.discovery import FeedDescription, candidate_feeds, describe_feed
from src.domains.radio.newsroom.fetch import FetchOutcome, fetch_public, public_url
from src.domains.radio.newsroom.robots import RobotsCache, RobotsVerdict

#: Candidate feeds tried at most for one site (each is a bounded fetch).
CANDIDATES_TRIED_MAX: Final[int] = 6


class DiscoveryOutcome(StrEnum):
    """How looking for a site's feed ended — a bounded vocabulary (an API error key)."""

    FOUND = "found"
    #: Nothing public to reach: a private or reserved address, a name that
    #: resolves to nothing (a typo), or no address at all — the validator
    #: answers these alike, and so does the person's next step (check the address).
    NOT_PUBLIC = "not_public"
    #: The site did not answer (nor did its robots.txt).
    UNREACHABLE = "unreachable"
    #: Its robots.txt closes the page, or every candidate feed, to the newsroom.
    FORBIDDEN = "forbidden"
    #: It answered, and serves no feed with an entry.
    NO_FEED = "no_feed"


@dataclass(frozen=True, slots=True)
class Discovery:
    """What looking for a site's feed found.

    Attributes:
        outcome: How it ended.
        feed_url: The feed's URL, when one was found.
        description: What the feed says of itself, when one was found.
    """

    outcome: DiscoveryOutcome
    feed_url: str | None = None
    description: FeedDescription | None = None


def with_scheme(address: str) -> str:
    """The address a person typed, with a scheme when they typed none."""
    stripped = address.strip()
    return stripped if "://" in stripped else f"https://{stripped}"


async def discover_feed(
    client: httpx.AsyncClient, address: str, *, robots: RobotsCache, max_bytes: int
) -> Discovery:
    """The feed a site serves.

    Args:
        client: The caller's HTTP client (it owns the pool).
        address: What the person typed.
        robots: The newsroom's robots.txt cache.
        max_bytes: The largest body read (a page or a feed).

    Returns:
        The feed and its description, or why there is none; never an exception
        for a network or HTTP failure.
    """
    url = await public_url(with_scheme(address))
    if url is None:
        return Discovery(DiscoveryOutcome.NOT_PUBLIC)
    verdict = await robots.verdict(client, url)
    if verdict is RobotsVerdict.UNREADABLE:
        return Discovery(DiscoveryOutcome.UNREACHABLE)
    if verdict is RobotsVerdict.DISALLOWED:
        return Discovery(DiscoveryOutcome.FORBIDDEN)
    page = await fetch_public(client, url, max_bytes=max_bytes)
    if page.outcome is FetchOutcome.BLOCKED:
        return Discovery(DiscoveryOutcome.NOT_PUBLIC)
    if page.outcome is not FetchOutcome.OK:
        return Discovery(DiscoveryOutcome.UNREACHABLE)
    itself = describe_feed(page.content)
    if itself is not None:
        return Discovery(DiscoveryOutcome.FOUND, page.final_url, itself)
    return await _first_feed(
        client,
        candidate_feeds(page.content, page.final_url)[:CANDIDATES_TRIED_MAX],
        robots=robots,
        max_bytes=max_bytes,
    )


async def _first_feed(
    client: httpx.AsyncClient, candidates: Sequence[str], *, robots: RobotsCache, max_bytes: int
) -> Discovery:
    """The first candidate that is a feed; FORBIDDEN when robots.txt closed every one of them."""
    read = 0
    for candidate in candidates:
        if not await robots.allows(client, candidate):
            continue
        read += 1
        result = await fetch_public(client, candidate, max_bytes=max_bytes)
        if result.outcome is not FetchOutcome.OK:
            continue
        described = describe_feed(result.content)
        if described is not None:
            return Discovery(DiscoveryOutcome.FOUND, result.final_url, described)
    closed = bool(candidates) and read == 0
    return Discovery(DiscoveryOutcome.FORBIDDEN if closed else DiscoveryOutcome.NO_FEED)


__all__ = [
    "CANDIDATES_TRIED_MAX",
    "Discovery",
    "DiscoveryOutcome",
    "discover_feed",
    "with_scheme",
]
