"""A site a listener adds: the feed found, or why not — without touching the network."""

from __future__ import annotations

import httpx
import pytest

from src.domains.agents.web_fetch.url_validator import UrlValidationResult
from src.domains.radio.newsroom import fetch as fetch_module
from src.domains.radio.newsroom.robots import RobotsCache
from src.domains.radio.newsroom.sources import DiscoveryOutcome, discover_feed

pytestmark = pytest.mark.unit

RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Site news</title><language>fr-FR</language>
<item><title>One</title><link>https://site.example.org/1</link></item>
<item><title>Two</title><link>https://site.example.org/2</link></item>
</channel></rss>"""
ADVERTISING = b"""<html><head>
<link rel="alternate" type="application/rss+xml" href="/feed.xml">
</head><body>home</body></html>"""
SILENT = b"<html><head></head><body>home</body></html>"


@pytest.fixture(autouse=True)
def no_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    """Validate without DNS: any host containing ``internal`` is a private address."""

    async def fake_validate(url: str) -> UrlValidationResult:
        if "internal" in url:
            return UrlValidationResult(valid=False, url=url, error="blocked")
        return UrlValidationResult(valid=True, url=url, resolved_ips=("93.184.216.34",))

    monkeypatch.setattr(fetch_module, "validate_url", fake_validate)


class Site:
    """A fake site: path → (status, body); robots.txt answers 404 unless given."""

    def __init__(self, pages: dict[str, tuple[int, bytes]]) -> None:
        self.pages = pages
        self.requested: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requested.append(request.url.path)
        status, body = self.pages.get(request.url.path, (404, b""))
        return httpx.Response(status, content=body)


async def discover(site: Site, address: str) -> tuple[DiscoveryOutcome, str | None, str | None]:
    async with httpx.AsyncClient(transport=httpx.MockTransport(site.handler)) as client:
        found = await discover_feed(client, address, robots=RobotsCache(), max_bytes=100_000)
    title = found.description.title if found.description else None
    return found.outcome, found.feed_url, title


async def test_a_bare_site_name_leads_to_the_feed_its_page_advertises() -> None:
    site = Site({"/": (200, ADVERTISING), "/feed.xml": (200, RSS)})
    outcome, url, title = await discover(site, "site.example.org")
    assert (outcome, url, title) == (
        DiscoveryOutcome.FOUND,
        "https://site.example.org/feed.xml",
        "Site news",
    )


async def test_a_feed_address_is_its_own_feed_described() -> None:
    site = Site({"/rss": (200, RSS)})
    async with httpx.AsyncClient(transport=httpx.MockTransport(site.handler)) as client:
        found = await discover_feed(
            client, "https://site.example.org/rss", robots=RobotsCache(), max_bytes=100_000
        )
    assert found.outcome is DiscoveryOutcome.FOUND and found.description is not None
    assert (found.description.language, found.description.entries) == ("fr-FR", 2)


async def test_a_site_advertising_nothing_is_tried_where_feeds_usually_live() -> None:
    site = Site({"/": (200, SILENT), "/feed/": (200, RSS)})
    outcome, url, _ = await discover(site, "https://site.example.org/")
    assert (outcome, url) == (DiscoveryOutcome.FOUND, "https://site.example.org/feed/")


async def test_robots_txt_closing_the_site_means_not_a_page_is_read() -> None:
    site = Site({"/robots.txt": (200, b"User-agent: *\nDisallow: /\n"), "/": (200, ADVERTISING)})
    outcome, _, _ = await discover(site, "https://site.example.org/")
    assert outcome is DiscoveryOutcome.FORBIDDEN
    assert site.requested == ["/robots.txt"]


async def test_a_site_that_does_not_answer_is_unreachable_never_forbidden() -> None:
    site = Site({"/robots.txt": (503, b""), "/": (503, b"")})
    outcome, _, _ = await discover(site, "https://site.example.org/")
    assert outcome is DiscoveryOutcome.UNREACHABLE
    assert site.requested == ["/robots.txt"]


async def test_a_private_address_is_refused_before_anything_is_requested() -> None:
    site = Site({})
    outcome, _, _ = await discover(site, "http://intranet.internal/")
    assert outcome is DiscoveryOutcome.NOT_PUBLIC and site.requested == []


async def test_a_site_serving_no_feed_says_so() -> None:
    site = Site({"/": (200, SILENT)})
    outcome, url, _ = await discover(site, "https://site.example.org/")
    assert (outcome, url) == (DiscoveryOutcome.NO_FEED, None)
