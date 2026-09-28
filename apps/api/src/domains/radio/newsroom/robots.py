"""robots.txt, honoured for every page the newsroom reads.

A site says what a crawler may read; the newsroom asks before reading an
article page (feeds are published FOR syndication, articles are not). One
parsed robots.txt per origin, kept a day; a site whose robots.txt cannot be
read right now (timeout, 5xx, 429) is treated as a refusal for an hour — doubt
never reads a page. A robots.txt that does not exist (any other 4xx) allows
everything, as RFC 9309 says.

The cache is per process and bounded: the collector runs on the scheduler
leader, and a worker validating a person's new feed keeps its own few entries.
Loads are serialised, so concurrent checks on one origin read its robots.txt
once — a burst of article fetches must not become a burst of robots.txt ones.
"""

from __future__ import annotations

import asyncio
import time
import urllib.robotparser
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Final
from urllib.parse import urlparse

import httpx

from src.domains.radio.newsroom.fetch import NEWSROOM_USER_AGENT, FetchOutcome, fetch_public

#: How long a read robots.txt is trusted.
_ALLOW_TTL_S: Final[float] = 24 * 3600.0
#: How long an unreadable robots.txt counts as a refusal.
_DOUBT_TTL_S: Final[float] = 3600.0
#: The largest robots.txt read.
_ROBOTS_MAX_BYTES: Final[int] = 512 * 1024
#: Origins remembered at most (least recently used out).
_MAX_ORIGINS: Final[int] = 512


class RobotsVerdict(StrEnum):
    """What robots.txt says of one URL."""

    ALLOWED = "allowed"
    DISALLOWED = "disallowed"
    #: robots.txt could not be read right now — a refusal, for an hour (a site
    #: that does not answer for its robots.txt does not answer for its pages).
    UNREADABLE = "unreadable"


@dataclass(frozen=True, slots=True)
class _Entry:
    parser: urllib.robotparser.RobotFileParser | None  # None = refuse everything
    expires_at: float


def _origin(url: str) -> str | None:
    parts = urlparse(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None
    return f"{parts.scheme}://{parts.netloc}"


class RobotsCache:
    """The parsed robots.txt of the origins the newsroom reads.

    Args:
        clock: A monotonic clock in seconds (injected by tests).
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._entries: OrderedDict[str, _Entry] = OrderedDict()
        self._load_lock = asyncio.Lock()

    def _fresh(self, origin: str) -> _Entry | None:
        entry = self._entries.get(origin)
        return entry if entry is not None and entry.expires_at > self._clock() else None

    async def allows(self, client: httpx.AsyncClient, url: str) -> bool:
        """Whether the newsroom may read ``url``.

        Args:
            client: The caller's HTTP client.
            url: The page to read.

        Returns:
            True when robots.txt allows our user agent; False when it forbids
            it, when the URL is not a web URL, or while robots.txt is unreadable.
        """
        return await self.verdict(client, url) is RobotsVerdict.ALLOWED

    async def verdict(self, client: httpx.AsyncClient, url: str) -> RobotsVerdict:
        """What robots.txt says of ``url`` — why a page may not be read, when it may not.

        Args:
            client: The caller's HTTP client.
            url: The page to read.

        Returns:
            ``ALLOWED``; ``DISALLOWED`` when robots.txt forbids our user agent or
            the URL is not a web URL; ``UNREADABLE`` while robots.txt cannot be read.
        """
        origin = _origin(url)
        if origin is None:
            return RobotsVerdict.DISALLOWED
        entry = self._fresh(origin)
        if entry is None:
            async with self._load_lock:
                entry = self._fresh(origin) or await self._load(client, origin)
                self._remember(origin, entry)
        else:
            self._entries.move_to_end(origin)
        if entry.parser is None:
            return RobotsVerdict.UNREADABLE
        if entry.parser.can_fetch(NEWSROOM_USER_AGENT, url):
            return RobotsVerdict.ALLOWED
        return RobotsVerdict.DISALLOWED

    def _remember(self, origin: str, entry: _Entry) -> None:
        self._entries[origin] = entry
        self._entries.move_to_end(origin)
        while len(self._entries) > _MAX_ORIGINS:
            self._entries.popitem(last=False)

    async def _load(self, client: httpx.AsyncClient, origin: str) -> _Entry:
        result = await fetch_public(client, f"{origin}/robots.txt", max_bytes=_ROBOTS_MAX_BYTES)
        now = self._clock()
        parser = urllib.robotparser.RobotFileParser()
        if result.outcome is FetchOutcome.OK:
            # RFC 9309: robots.txt is UTF-8, whatever the header says.
            parser.parse(result.content.decode("utf-8", errors="replace").splitlines())
            return _Entry(parser, now + _ALLOW_TTL_S)
        status = result.status or 0
        if result.outcome is FetchOutcome.HTTP_ERROR and 400 <= status < 500 and status != 429:
            parser.parse([])  # no robots.txt: everything is allowed
            return _Entry(parser, now + _ALLOW_TTL_S)
        return _Entry(None, now + _DOUBT_TTL_S)


__all__ = ["RobotsCache", "RobotsVerdict"]
