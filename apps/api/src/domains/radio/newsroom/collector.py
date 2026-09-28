"""One pass of the newsroom: the feeds that are due, what is new in them, the articles.

The collector runs on the scheduler's leader for the whole instance — the
catalogue's feeds and the sites people added — and is the newsroom's only
writer. It calls no model: nothing it does is billed to anyone.

A pass is bounded: how many feeds it reads, how many articles it opens, how long
it may take — a slow outlet delays the next pass, never the antenna. Each feed
keeps its own pace: a conditional request once its interval has passed, the
interval doubled after each failure up to a ceiling, so a dead feed costs one
request an hour rather than one a pass. robots.txt is honoured for a feed and
for every article, and one outlet's articles are opened one after the other,
never all at once. An article that could not be read for a passing reason (the
network, a 5xx, a 429) is tried again at a later pass, a bounded number of
times; one that answered for good (a 4xx, no article in the page) is not. A
feed that answers with no usable item — a page where the feed used to be — is
a failed reading like any other: it backs off, and its old validators are kept
so a later 304 cannot pass it for healthy.
Parsing and extraction are CPU work (feedparser, lxml): each runs in a thread.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final, Protocol
from urllib.parse import urlsplit
from uuid import UUID

import httpx
import structlog

from src.domains.radio.newsroom.catalogue import CATALOGUE, CatalogueFeed
from src.domains.radio.newsroom.fetch import FetchOutcome, FetchResult, fetch_public
from src.domains.radio.newsroom.fulltext import extract_article
from src.domains.radio.newsroom.parse import ParsedItem, parse_feed
from src.domains.radio.newsroom.robots import RobotsCache

logger = structlog.get_logger(__name__)

#: The status a feed records when its robots.txt forbids us (beside the fetch outcomes).
DISALLOWED: Final = "disallowed"
#: The status of a feed whose body held no usable item (not a feed any more).
EMPTY: Final = "empty"
#: The status of a feed whose reading broke, or whose stories could not be filed.
UNFILED: Final = "unfiled"


@dataclass(frozen=True, slots=True)
class FeedState:
    """A feed as the newsroom last left it.

    Attributes:
        feed_id: The feed.
        url: Where it is read.
        full_text: Whether its articles are worth opening.
        etag: The validator its server last gave.
        last_modified: The other validator.
        last_read_at: When it was last read (aware), or None if never.
        failures: Failed readings in a row.
    """

    feed_id: UUID
    url: str
    full_text: bool
    etag: str | None
    last_modified: str | None
    last_read_at: datetime | None
    failures: int


@dataclass(frozen=True, slots=True)
class FeedReading:
    """What one reading of a feed ended in.

    Attributes:
        status: A fetch outcome, :data:`DISALLOWED` or :data:`EMPTY`.
        succeeded: Whether the feed answered (a 304 did).
        etag: The validator to send next time.
        last_modified: The other validator.
    """

    status: str
    succeeded: bool
    etag: str | None
    last_modified: str | None


@dataclass(frozen=True, slots=True)
class TextJob:
    """An article waiting to be read.

    Attributes:
        item_id: The stored item.
        url: The article.
        attempts: Readings already tried.
    """

    item_id: UUID
    url: str
    attempts: int


class NewsroomStore(Protocol):
    """Where the newsroom keeps its feeds and their items."""

    async def sync_catalogue(self, feeds: Sequence[CatalogueFeed]) -> None:
        """Make the stored catalogue the shipped one (added, updated, removed)."""
        ...

    async def feed_states(self, *, listened_since: datetime) -> list[FeedState]:
        """The feeds read for someone: the catalogue while anyone listened since
        the instant, a listener's own sites while they did."""
        ...

    async def record_reading(self, feed_id: UUID, reading: FeedReading, *, now: datetime) -> None:
        """File a reading: its status, validators and failure count."""
        ...

    async def add_items(
        self, feed_id: UUID, items: Sequence[ParsedItem], *, full_text: bool
    ) -> int:
        """Keep the items not already known; return how many were new."""
        ...

    async def text_jobs(self, *, limit: int) -> list[TextJob]:
        """Articles waiting to be read, the newest first."""
        ...

    async def record_text(self, item_id: UUID, text: str | None, *, final: bool) -> None:
        """File an article's text; ``None`` and not final means « try again later »."""
        ...

    async def purge(self, *, published_before: datetime) -> int:
        """Remove the items published before an instant; return how many."""
        ...


@dataclass(frozen=True, slots=True)
class CollectorLimits:
    """The bounds of one pass (settings, read by the caller).

    Attributes:
        feeds_per_pass: Feeds read at most.
        texts_per_pass: Articles opened at most.
        feed_interval_s: Seconds between two readings of a healthy feed.
        backoff_max_s: The longest wait after failures.
        feed_max_bytes: The largest feed body accepted.
        page_max_bytes: The largest article page accepted.
        text_attempts_max: Readings of an article before giving up.
        retention_s: How long an item is kept after publication.
        concurrency: Requests in flight at once.
        pass_timeout_s: The longest a pass may run.
        listener_window_s: Feeds are read for the listeners of this window —
            never for nobody.
    """

    feeds_per_pass: int
    texts_per_pass: int
    feed_interval_s: float
    backoff_max_s: float
    feed_max_bytes: int
    page_max_bytes: int
    text_attempts_max: int
    retention_s: float
    concurrency: int
    pass_timeout_s: float
    listener_window_s: float


@dataclass(frozen=True, slots=True)
class PassReport:
    """What one pass did — counts only (a metric, a log line)."""

    feeds_read: int
    feeds_failed: int
    items_new: int
    texts_ready: int
    texts_unavailable: int
    purged: int
    cut: bool


@dataclass(slots=True)
class _Tally:
    feeds_read: int = 0
    feeds_failed: int = 0
    items_new: int = 0
    texts_ready: int = 0
    texts_unavailable: int = 0
    purged: int = 0

    def report(self, *, cut: bool) -> PassReport:
        return PassReport(
            feeds_read=self.feeds_read,
            feeds_failed=self.feeds_failed,
            items_new=self.items_new,
            texts_ready=self.texts_ready,
            texts_unavailable=self.texts_unavailable,
            purged=self.purged,
            cut=cut,
        )


def next_reading_at(
    state: FeedState, *, interval_s: float, backoff_max_s: float
) -> datetime | None:
    """When a feed is next due: None when never read (due now).

    The interval, doubled after each failure in a row, never past the ceiling.
    """
    if state.last_read_at is None:
        return None
    wait = min(interval_s * 2 ** min(state.failures, 32), max(interval_s, backoff_max_s))
    return state.last_read_at + timedelta(seconds=wait)


def _is_due(state: FeedState, *, now: datetime, limits: CollectorLimits) -> bool:
    at = next_reading_at(
        state, interval_s=limits.feed_interval_s, backoff_max_s=limits.backoff_max_s
    )
    return at is None or at <= now


def due_feeds(
    states: Sequence[FeedState], *, now: datetime, limits: CollectorLimits
) -> list[FeedState]:
    """The feeds to read this pass: never-read ones first, then the longest-waiting, bounded."""
    due = [state for state in states if _is_due(state, now=now, limits=limits)]
    due.sort(key=lambda state: (state.last_read_at is not None, state.last_read_at or now))
    return due[: limits.feeds_per_pass]


def _transient(result: FetchResult) -> bool:
    if result.outcome is FetchOutcome.NETWORK_ERROR:
        return True
    return result.status is not None and (result.status >= 500 or result.status == 429)


async def _read_feed(
    client: httpx.AsyncClient,
    robots: RobotsCache,
    feed: FeedState,
    *,
    now: datetime,
    max_bytes: int,
) -> tuple[FeedReading, list[ParsedItem]]:
    if not await robots.allows(client, feed.url):
        return FeedReading(DISALLOWED, False, feed.etag, feed.last_modified), []
    result = await fetch_public(
        client, feed.url, max_bytes=max_bytes, etag=feed.etag, last_modified=feed.last_modified
    )
    if result.outcome is FetchOutcome.NOT_MODIFIED:
        return FeedReading(result.outcome.value, True, feed.etag, feed.last_modified), []
    if result.outcome is not FetchOutcome.OK:
        return FeedReading(result.outcome.value, False, feed.etag, feed.last_modified), []
    items = await asyncio.to_thread(
        parse_feed, result.content, feed_url=result.final_url, fetched_at=now
    )
    if not items:
        return FeedReading(EMPTY, False, feed.etag, feed.last_modified), []
    return FeedReading(result.outcome.value, True, result.etag, result.last_modified), items


async def _read_article(
    client: httpx.AsyncClient, robots: RobotsCache, job: TextJob, limits: CollectorLimits
) -> tuple[str | None, bool]:
    """The article's text (or None), and whether that answer is final."""
    if not await robots.allows(client, job.url):
        return None, True
    result = await fetch_public(client, job.url, max_bytes=limits.page_max_bytes)
    if result.outcome is FetchOutcome.OK:
        text = await asyncio.to_thread(extract_article, result.content, charset=result.charset)
        return text, True
    return None, not _transient(result) or job.attempts + 1 >= limits.text_attempts_max


def _by_origin(jobs: Sequence[TextJob]) -> list[list[TextJob]]:
    groups: dict[str, list[TextJob]] = {}
    for job in jobs:
        groups.setdefault(urlsplit(job.url).netloc, []).append(job)
    return list(groups.values())


def _kept_since(now: datetime, limits: CollectorLimits) -> datetime:
    """The oldest publication the newsroom keeps — the purge's line and the filing's.

    A feed keeps listing stories long after the purge removed them: filed again,
    they came back « new » at every pass, their articles downloaded again
    (measured 2026-09-26: 164 purged, then 165 « new » five minutes later).
    """
    return now - timedelta(seconds=limits.retention_s)


async def _feeds_phase(
    store: NewsroomStore,
    client: httpx.AsyncClient,
    robots: RobotsCache,
    *,
    now: datetime,
    limits: CollectorLimits,
    tally: _Tally,
) -> None:
    gate = asyncio.Semaphore(limits.concurrency)

    async def one(feed: FeedState) -> None:
        # One feed is one unit: a body that breaks the parser, a row the
        # database refuses — a site a listener added among them — is that feed's
        # failure, never the pass's. Its stories are filed BEFORE its reading,
        # so new validators are never kept for stories that were not: a failure
        # keeps the old ones, backs off, and reads the feed whole next time.
        try:
            async with gate:
                reading, items = await _read_feed(
                    client, robots, feed, now=now, max_bytes=limits.feed_max_bytes
                )
            floor = _kept_since(now, limits)
            kept = [item for item in items if item.published_at >= floor]
            added = (
                await store.add_items(feed.feed_id, kept, full_text=feed.full_text) if kept else 0
            )
        except Exception as exc:  # noqa: BLE001 — one feed's failure, never the pass's
            logger.warning(
                "radio_newsroom_feed_unfiled",
                feed_id=str(feed.feed_id),
                error_type=type(exc).__name__,
            )
            reading, added = FeedReading(UNFILED, False, feed.etag, feed.last_modified), 0
        try:
            await store.record_reading(feed.feed_id, reading, now=now)
        except Exception as exc:  # noqa: BLE001 — one feed's failure, never the pass's
            logger.warning(
                "radio_newsroom_reading_unfiled",
                feed_id=str(feed.feed_id),
                error_type=type(exc).__name__,
            )
            tally.feeds_failed += 1
            return
        if not reading.succeeded:
            tally.feeds_failed += 1
            return
        tally.feeds_read += 1
        tally.items_new += added

    listened_since = now - timedelta(seconds=limits.listener_window_s)
    states = await store.feed_states(listened_since=listened_since)
    async with asyncio.TaskGroup() as group:
        for feed in due_feeds(states, now=now, limits=limits):
            group.create_task(one(feed))


async def _texts_phase(
    store: NewsroomStore,
    client: httpx.AsyncClient,
    robots: RobotsCache,
    *,
    limits: CollectorLimits,
    tally: _Tally,
) -> None:
    gate = asyncio.Semaphore(limits.concurrency)

    async def outlet(jobs: list[TextJob]) -> None:
        # One outlet's articles one after the other: never a burst at one site.
        async with gate:
            for job in jobs:
                try:
                    text, final = await _read_article(client, robots, job, limits)
                    await store.record_text(job.item_id, text, final=final)
                except Exception as exc:  # noqa: BLE001 — one article's failure, never its outlet's
                    # Left pending: a later pass tries it again, within its attempts.
                    logger.warning(
                        "radio_newsroom_article_unfiled",
                        item_id=str(job.item_id),
                        error_type=type(exc).__name__,
                    )
                    continue
                if text is not None:
                    tally.texts_ready += 1
                elif final:
                    tally.texts_unavailable += 1

    jobs = await store.text_jobs(limit=limits.texts_per_pass)
    async with asyncio.TaskGroup() as group:
        for group_jobs in _by_origin(jobs):
            group.create_task(outlet(group_jobs))


async def collect_pass(
    store: NewsroomStore,
    client: httpx.AsyncClient,
    robots: RobotsCache,
    *,
    now: datetime,
    limits: CollectorLimits,
    catalogue: Sequence[CatalogueFeed] = CATALOGUE,
) -> PassReport:
    """Run one pass of the newsroom.

    Args:
        store: Where feeds and items are kept.
        client: The pass's HTTP client (the caller owns and closes it).
        robots: The process's robots.txt cache.
        now: The pass's instant (timezone-aware).
        limits: Its bounds.
        catalogue: The shipped feeds.

    Returns:
        What the pass did. A pass cut by its time bound keeps everything it
        filed before the cut.
    """
    started = time.perf_counter()
    tally = _Tally()
    tally.purged = await store.purge(published_before=_kept_since(now, limits))
    await store.sync_catalogue(catalogue)
    cut = False
    try:
        async with asyncio.timeout(limits.pass_timeout_s):
            await _feeds_phase(store, client, robots, now=now, limits=limits, tally=tally)
            await _texts_phase(store, client, robots, limits=limits, tally=tally)
    except TimeoutError:
        cut = True
    report = tally.report(cut=cut)
    logger.info(
        "radio_newsroom_pass",
        feeds_read=report.feeds_read,
        feeds_failed=report.feeds_failed,
        items_new=report.items_new,
        texts_ready=report.texts_ready,
        texts_unavailable=report.texts_unavailable,
        purged=report.purged,
        cut=report.cut,
        # What sizes ``RADIO_NEWSROOM_FEEDS_PER_PASS``: a pass must end well inside its bound.
        duration_s=round(time.perf_counter() - started, 1),
    )
    return report


__all__ = [
    "DISALLOWED",
    "EMPTY",
    "CollectorLimits",
    "FeedReading",
    "FeedState",
    "NewsroomStore",
    "PassReport",
    "TextJob",
    "collect_pass",
    "due_feeds",
    "next_reading_at",
]
