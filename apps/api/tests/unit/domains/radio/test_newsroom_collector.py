"""One pass of the newsroom: due feeds, new items, articles — polite and bounded."""

from __future__ import annotations

import asyncio
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from uuid import UUID, uuid4

import httpx
import pytest

from src.domains.agents.web_fetch.url_validator import UrlValidationResult
from src.domains.radio.newsroom import fetch as fetch_module
from src.domains.radio.newsroom.catalogue import CatalogueFeed
from src.domains.radio.newsroom.collector import (
    DISALLOWED,
    EMPTY,
    CollectorLimits,
    FeedReading,
    FeedState,
    PassReport,
    TextJob,
    collect_pass,
    due_feeds,
)
from src.domains.radio.newsroom.parse import ParsedItem
from src.domains.radio.newsroom.robots import RobotsCache

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 26, 9, 0, tzinfo=UTC)
LIMITS = CollectorLimits(
    feeds_per_pass=10,
    texts_per_pass=10,
    feed_interval_s=900,
    backoff_max_s=3600,
    feed_max_bytes=100_000,
    page_max_bytes=100_000,
    text_attempts_max=3,
    retention_s=48 * 3600,
    concurrency=4,
    pass_timeout_s=5,
    listener_window_s=7 * 86400,
)
ARTICLE = (
    "<html><body><article>"
    + "".join(
        f"<p>Paragraph {n} of a long enough article about the rain. " * 3 + "</p>" for n in range(8)
    )
    + "</article></body></html>"
).encode()


@pytest.fixture(autouse=True)
def no_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_validate(url: str) -> UrlValidationResult:
        return UrlValidationResult(valid=True, url=url)

    monkeypatch.setattr(fetch_module, "validate_url", fake_validate)


def rss(host: str, count: int) -> bytes:
    items = "".join(
        f"<item><title>Story {n} at {host}</title><link>https://{host}/a/{n}</link>"
        f"<guid>{host}-{n}</guid><description>Summary {n}</description></item>"
        for n in range(count)
    )
    return f'<?xml version="1.0"?><rss version="2.0"><channel><title>{host}</title>{items}</channel></rss>'.encode()


def feed(
    host: str,
    *,
    full_text: bool = True,
    etag: str | None = None,
    last_modified: str | None = None,
    last_read_at: datetime | None = None,
    failures: int = 0,
) -> FeedState:
    return FeedState(
        feed_id=uuid4(),
        url=f"https://{host}/rss",
        full_text=full_text,
        etag=etag,
        last_modified=last_modified,
        last_read_at=last_read_at,
        failures=failures,
    )


@dataclass
class FakeNewsroom:
    """The store port, in memory — with a pause in ``add_items`` so writers interleave."""

    feeds: list[FeedState] = field(default_factory=list)
    jobs: list[TextJob] = field(default_factory=list)
    readings: dict[UUID, FeedReading] = field(default_factory=dict)
    items: dict[UUID, list[ParsedItem]] = field(default_factory=dict)
    texts: dict[UUID, tuple[str | None, bool]] = field(default_factory=dict)
    purged_before: datetime | None = None
    synced: int = 0
    listened_since: datetime | None = None

    async def sync_catalogue(self, feeds: Sequence[CatalogueFeed]) -> None:
        self.synced += 1

    async def feed_states(self, *, listened_since: datetime) -> list[FeedState]:
        self.listened_since = listened_since
        return list(self.feeds)

    async def record_reading(self, feed_id: UUID, reading: FeedReading, *, now: datetime) -> None:
        self.readings[feed_id] = reading

    async def add_items(
        self, feed_id: UUID, items: Sequence[ParsedItem], *, full_text: bool
    ) -> int:
        await asyncio.sleep(0)  # a database round trip: siblings run meanwhile
        known = self.items.setdefault(feed_id, [])
        fresh = [item for item in items if item.item_key not in {k.item_key for k in known}]
        known.extend(fresh)
        return len(fresh)

    async def text_jobs(self, *, limit: int) -> list[TextJob]:
        return self.jobs[:limit]

    async def record_text(self, item_id: UUID, text: str | None, *, final: bool) -> None:
        self.texts[item_id] = (text, final)

    async def purge(self, *, published_before: datetime) -> int:
        self.purged_before = published_before
        return 2


class Web:
    """A MockTransport: feeds, articles, robots.txt, and who was asked what, when."""

    def __init__(self) -> None:
        self.pages: dict[str, httpx.Response] = {}
        self.delays: dict[str, float] = {}
        self.disallowed_hosts: set[str] = set()
        self.requests: list[str] = []
        self.in_flight: Counter[str] = Counter()
        self.peak: Counter[str] = Counter()

    async def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        host = request.url.host
        if request.url.path == "/robots.txt":
            rule = "Disallow: /" if host in self.disallowed_hosts else "Allow: /"
            return httpx.Response(200, text=f"User-agent: *\n{rule}\n")
        self.requests.append(url)
        self.in_flight[host] += 1
        self.peak[host] = max(self.peak[host], self.in_flight[host])
        try:
            await asyncio.sleep(self.delays.get(host, 0.01))
            return self.pages.get(url, httpx.Response(404))
        finally:
            self.in_flight[host] -= 1

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handler))


async def run(store: FakeNewsroom, web: Web, limits: CollectorLimits = LIMITS) -> PassReport:
    async with web.client() as client:
        return await collect_pass(store, client, RobotsCache(), now=NOW, limits=limits)


class TestDueFeeds:
    def test_a_feed_never_read_comes_first_then_the_longest_waiting(self) -> None:
        stale = feed("a.example", last_read_at=NOW - timedelta(hours=2))
        older = feed("b.example", last_read_at=NOW - timedelta(hours=5))
        new = feed("c.example")
        fresh = feed("d.example", last_read_at=NOW - timedelta(minutes=5))
        assert due_feeds([stale, fresh, older, new], now=NOW, limits=LIMITS) == [new, older, stale]

    @pytest.mark.parametrize(
        ("failures", "waited_min", "due"),
        [
            (0, 15, True),
            (1, 29, False),
            (1, 30, True),
            (2, 60, True),
            (40, 59, False),
            (40, 60, True),
        ],
    )
    def test_each_failure_doubles_the_wait_up_to_the_ceiling(
        self, failures: int, waited_min: int, due: bool
    ) -> None:
        state = feed(
            "a.example", failures=failures, last_read_at=NOW - timedelta(minutes=waited_min)
        )
        assert (due_feeds([state], now=NOW, limits=LIMITS) == [state]) is due

    def test_a_pass_reads_a_bounded_number_of_feeds(self) -> None:
        states = [feed(f"h{n}.example") for n in range(5)]
        assert len(due_feeds(states, now=NOW, limits=replace(LIMITS, feeds_per_pass=3))) == 3


class TestPass:
    async def test_new_items_are_kept_and_counted_exactly(self) -> None:
        feeds = [feed(f"h{n}.example", full_text=False) for n in range(4)]
        store, web = FakeNewsroom(feeds=feeds), Web()
        for state in feeds:
            web.pages[state.url] = httpx.Response(200, content=rss(state.url.split("/")[2], 3))
        report = await run(store, web)
        assert report.items_new == 12  # four writers interleaved, none lost
        assert report.feeds_read == 4 and report.feeds_failed == 0
        assert store.synced == 1
        assert store.purged_before == NOW - timedelta(hours=48) and report.purged == 2
        # The feeds are read for the listeners of the window, never for nobody.
        assert store.listened_since == NOW - timedelta(days=7)

        again = await run(store, web)
        assert again.items_new == 0

    async def test_a_story_older_than_the_retention_is_never_filed(self) -> None:
        """A feed keeps listing what the purge removed: filed again, it came back
        « new » at every pass (measured 2026-09-26: 164 purged, then 165 « new »,
        their articles downloaded again) — one line, the purge's, decides both."""
        state = feed("a.example", full_text=False)
        store, web = FakeNewsroom(feeds=[state]), Web()
        retention = timedelta(seconds=LIMITS.retention_s)
        dated = {
            "Too old": NOW - retention - timedelta(seconds=1),
            "On the line": NOW - retention,
            "Fresh": NOW - timedelta(hours=2),
        }
        items = "".join(
            f"<item><title>{title}</title><link>https://a.example/{n}</link>"
            f"<guid>a-{n}</guid><pubDate>{format_datetime(at)}</pubDate></item>"
            for n, (title, at) in enumerate(dated.items())
        )
        web.pages[state.url] = httpx.Response(
            200,
            content=f'<?xml version="1.0"?><rss version="2.0"><channel><title>a</title>{items}</channel></rss>'.encode(),
        )
        report = await run(store, web)
        assert report.items_new == 2
        assert sorted(item.title for item in store.items[state.feed_id]) == ["Fresh", "On the line"]
        assert store.purged_before == NOW - retention

    async def test_recent_stories_at_the_end_of_a_large_feed_are_filed(self) -> None:
        state = feed("large.example", full_text=False)
        store, web = FakeNewsroom(feeds=[state]), Web()
        old = format_datetime(NOW - timedelta(days=3))
        recent = format_datetime(NOW - timedelta(hours=2))
        entries = "".join(
            f"<item><title>Old {n}</title><link>https://large.example/{n}</link>"
            f"<pubDate>{old}</pubDate></item>"
            for n in range(1_001)
        )
        entries += (
            "<item><title>Recent</title><link>https://large.example/recent</link>"
            f"<pubDate>{recent}</pubDate></item>"
        )
        web.pages[state.url] = httpx.Response(
            200,
            content=f"<rss><channel><title>Large feed</title>{entries}</channel></rss>".encode(),
        )
        report = await run(store, web, replace(LIMITS, feed_max_bytes=500_000))
        assert report.items_new == 1
        assert [item.title for item in store.items[state.feed_id]] == ["Recent"]

    async def test_an_unchanged_feed_keeps_its_validators(self) -> None:
        state = feed("a.example", etag='"v1"', last_modified="Fri, 25 Sep 2026 10:00:00 GMT")
        store, web = FakeNewsroom(feeds=[state]), Web()
        web.pages[state.url] = httpx.Response(304)
        await run(store, web)
        assert store.readings[state.feed_id] == FeedReading(
            "not_modified", True, '"v1"', "Fri, 25 Sep 2026 10:00:00 GMT"
        )

    async def test_a_feed_robots_txt_forbids_is_never_read(self) -> None:
        state = feed("closed.example")
        store, web = FakeNewsroom(feeds=[state]), Web()
        web.disallowed_hosts.add("closed.example")
        report = await run(store, web)
        assert web.requests == []
        assert store.readings[state.feed_id].status == DISALLOWED
        assert report.feeds_failed == 1

    async def test_a_page_where_the_feed_used_to_be_backs_off(self) -> None:
        """No usable item is a failure — and the old validators stay, so a later
        304 cannot pass the page for a healthy feed."""
        state = feed("moved.example", etag='"old"')
        store, web = FakeNewsroom(feeds=[state]), Web()
        web.pages[state.url] = httpx.Response(
            200, content=b"<html><body>We moved!</body></html>", headers={"ETag": '"page"'}
        )
        report = await run(store, web)
        assert store.readings[state.feed_id] == FeedReading(EMPTY, False, '"old"', None)
        assert report.feeds_failed == 1 and report.items_new == 0

    async def test_a_failing_feed_is_filed_as_failed(self) -> None:
        state = feed("down.example")
        store, web = FakeNewsroom(feeds=[state]), Web()
        report = await run(store, web)  # no page: 404
        assert store.readings[state.feed_id] == FeedReading("http_error", False, None, None)
        assert report.feeds_failed == 1


class TestArticles:
    async def test_one_outlet_is_read_one_article_at_a_time(self) -> None:
        jobs = [
            TextJob(uuid4(), f"https://{host}.example/a/{n}", 0)
            for host in ("slow", "other")
            for n in range(3)
        ]
        store, web = FakeNewsroom(jobs=jobs), Web()
        for job in jobs:
            web.pages[job.url] = httpx.Response(200, content=ARTICLE)
        report = await run(store, web)
        assert report.texts_ready == 6
        assert web.peak["slow.example"] == 1 and web.peak["other.example"] == 1
        assert all(text and final for text, final in store.texts.values())

    @pytest.mark.parametrize(
        ("response", "attempts", "final"),
        [
            (httpx.Response(503), 0, False),
            (httpx.Response(429), 1, False),
            (httpx.Response(503), 2, True),  # the last attempt
            (httpx.Response(404), 0, True),
            (httpx.Response(200, content=b"<html><p>Subscribe.</p></html>"), 0, True),
        ],
    )
    async def test_only_a_passing_failure_is_tried_again(
        self, response: httpx.Response, attempts: int, final: bool
    ) -> None:
        job = TextJob(uuid4(), "https://news.example/a/1", attempts)
        store, web = FakeNewsroom(jobs=[job]), Web()
        web.pages[job.url] = response
        report = await run(store, web)
        assert store.texts[job.item_id] == (None, final)
        assert report.texts_unavailable == (1 if final else 0)

    async def test_an_article_robots_txt_forbids_is_never_opened(self) -> None:
        job = TextJob(uuid4(), "https://closed.example/a/1", 0)
        store, web = FakeNewsroom(jobs=[job]), Web()
        web.disallowed_hosts.add("closed.example")
        await run(store, web)
        assert web.requests == [] and store.texts[job.item_id] == (None, True)


@dataclass
class BrittleNewsroom(FakeNewsroom):
    """A store that refuses to file one feed and one article (a constraint, a lost connection)."""

    refused: set[UUID] = field(default_factory=set)

    async def record_reading(self, feed_id: UUID, reading: FeedReading, *, now: datetime) -> None:
        if feed_id in self.refused:
            raise RuntimeError("the database refused the row")
        await super().record_reading(feed_id, reading, now=now)

    async def record_text(self, item_id: UUID, text: str | None, *, final: bool) -> None:
        if item_id in self.refused:
            raise RuntimeError("the database refused the row")
        await super().record_text(item_id, text, final=final)


class TestOneUnitNeverStopsThePass:
    """The newsroom serves every listener: a feed a listener added, or one row the
    database refuses, is that unit's failure — never the pass's, never the next one's."""

    async def test_a_feed_that_cannot_be_filed_is_counted_failed_and_the_others_land(
        self,
    ) -> None:
        broken, sound = feed("broken.example", full_text=False), feed(
            "sound.example", full_text=False
        )
        store, web = BrittleNewsroom(feeds=[broken, sound], refused={broken.feed_id}), Web()
        for state in (broken, sound):
            web.pages[state.url] = httpx.Response(200, content=rss(state.url.split("/")[2], 2))

        report = await run(store, web)

        assert set(store.readings) == {sound.feed_id} and report.items_new == 2
        assert (report.feeds_read, report.feeds_failed) == (1, 1)

    async def test_an_article_that_cannot_be_filed_never_stops_its_outlet(self) -> None:
        jobs = [TextJob(uuid4(), f"https://one.example/a/{n}", 0) for n in range(3)]
        store, web = BrittleNewsroom(jobs=jobs, refused={jobs[0].item_id}), Web()
        for job in jobs:
            web.pages[job.url] = httpx.Response(200, content=ARTICLE)

        report = await run(store, web)

        assert set(store.texts) == {jobs[1].item_id, jobs[2].item_id}
        assert report.texts_ready == 2 and not report.cut


async def test_a_pass_cut_by_its_bound_keeps_what_it_filed() -> None:
    quick, slow = feed("quick.example", full_text=False), feed("slow.example", full_text=False)
    store, web = FakeNewsroom(feeds=[quick, slow]), Web()
    web.pages[quick.url] = httpx.Response(200, content=rss("quick.example", 2))
    web.pages[slow.url] = httpx.Response(200, content=rss("slow.example", 2))
    web.delays["slow.example"] = 5.0
    report = await run(store, web, replace(LIMITS, pass_timeout_s=0.5))
    assert report.cut
    assert report.items_new == 2 and set(store.readings) == {quick.feed_id}
