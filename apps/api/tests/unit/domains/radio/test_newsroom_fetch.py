"""Every hop validated, every body bounded, robots.txt honoured — without touching the network."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine

import httpx
import pytest

from src.domains.agents.web_fetch.url_validator import UrlValidationResult
from src.domains.radio.constants import ETAG_MAX_CHARS, LAST_MODIFIED_MAX_CHARS
from src.domains.radio.newsroom import fetch as fetch_module
from src.domains.radio.newsroom.fetch import (
    NEWSROOM_USER_AGENT,
    FetchOutcome,
    FetchResult,
    fetch_public,
)
from src.domains.radio.newsroom.robots import RobotsCache

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def no_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    """Validate without DNS: any host containing ``internal`` is a private address."""

    async def fake_validate(url: str) -> UrlValidationResult:
        if "internal" in url:
            return UrlValidationResult(valid=False, url=url, error="blocked")
        return UrlValidationResult(valid=True, url=url)

    monkeypatch.setattr(fetch_module, "validate_url", fake_validate)


Handler = (
    Callable[[httpx.Request], httpx.Response]
    | Callable[[httpx.Request], Coroutine[None, None, httpx.Response]]
)


def client(handler: Handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


class TestFetch:
    async def test_a_body_comes_back_with_its_validators(self) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            headers = {"ETag": '"v2"', "Content-Type": "text/html; charset=ISO-8859-1"}
            return httpx.Response(200, content=b"<rss/>", headers=headers)

        async with client(handler) as c:
            result = await fetch_public(c, "https://feeds.example.org/rss", max_bytes=1000)
        assert (result.outcome, result.content, result.etag) == (FetchOutcome.OK, b"<rss/>", '"v2"')
        assert result.charset == "iso-8859-1"
        assert seen[0].headers["User-Agent"] == NEWSROOM_USER_AGENT

    async def test_a_validator_that_cannot_be_sent_back_is_not_kept(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"x", headers=[(b"ETag", "é".encode("latin-1"))])

        async with client(handler) as c:
            result = await fetch_public(c, "https://f.example.org/rss", max_bytes=10)
        assert (result.outcome, result.etag) == (FetchOutcome.OK, None)

    @pytest.mark.parametrize(
        ("header", "bound"), [("ETag", ETAG_MAX_CHARS), ("Last-Modified", LAST_MODIFIED_MAX_CHARS)]
    )
    async def test_a_validator_too_long_to_be_filed_is_not_kept(
        self, header: str, bound: int
    ) -> None:
        """Its column holds ``bound`` characters: a longer one would fail the feed's
        every reading — kept by nobody, sent by nobody."""
        longest, too_long = "v" * bound, "v" * (bound + 1)

        async def fetch(value: str) -> FetchResult:
            def handler(request: httpx.Request) -> httpx.Response:
                return httpx.Response(200, content=b"x", headers={header: value})

            async with client(handler) as c:
                return await fetch_public(c, "https://f.example.org/rss", max_bytes=10)

        kept = {"ETag": "etag", "Last-Modified": "last_modified"}[header]
        assert getattr(await fetch(longest), kept) == longest
        assert getattr(await fetch(too_long), kept) is None

    async def test_an_unchanged_feed_costs_a_304(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.headers["If-None-Match"] == '"v1"'
            return httpx.Response(304)

        async with client(handler) as c:
            result = await fetch_public(c, "https://f.example.org/rss", max_bytes=10, etag='"v1"')
        assert result.outcome is FetchOutcome.NOT_MODIFIED
        assert result.etag == '"v1"'

    async def test_a_redirect_to_a_private_address_is_blocked(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(302, headers={"Location": "http://metadata.internal/latest"})

        async with client(handler) as c:
            result = await fetch_public(c, "https://f.example.org/rss", max_bytes=100)
        assert result.outcome is FetchOutcome.BLOCKED
        assert "internal" in result.final_url

    async def test_a_relative_redirect_is_followed(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/old":
                return httpx.Response(301, headers={"Location": "/new"})
            return httpx.Response(200, content=b"ok")

        async with client(handler) as c:
            result = await fetch_public(c, "https://f.example.org/old", max_bytes=100)
        assert (result.outcome, result.final_url) == (FetchOutcome.OK, "https://f.example.org/new")

    async def test_a_url_no_request_can_carry_is_blocked(self) -> None:
        async with client(lambda _r: httpx.Response(200)) as c:
            result = await fetch_public(c, "https://f.example.org/a\x00b", max_bytes=100)
        assert result.outcome is FetchOutcome.BLOCKED

    async def test_a_redirect_loop_stops(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(302, headers={"Location": str(request.url)})

        async with client(handler) as c:
            result = await fetch_public(c, "https://f.example.org/loop", max_bytes=100)
        assert result.outcome is FetchOutcome.TOO_MANY_REDIRECTS

    async def test_a_body_past_the_ceiling_is_abandoned(self) -> None:
        async with client(lambda _r: httpx.Response(200, content=b"x" * 5000)) as c:
            result = await fetch_public(c, "https://f.example.org/big", max_bytes=1000)
        assert result.outcome is FetchOutcome.TOO_LARGE
        assert result.content == b""

    @pytest.mark.parametrize("status", [302, 403, 404, 500])  # 302 without a Location
    async def test_an_http_error_is_an_outcome(self, status: int) -> None:
        async with client(lambda _r: httpx.Response(status)) as c:
            result = await fetch_public(c, "https://f.example.org/x", max_bytes=100)
        assert (result.outcome, result.status) == (FetchOutcome.HTTP_ERROR, status)

    async def test_a_network_failure_is_an_outcome(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused")

        async with client(handler) as c:
            result = await fetch_public(c, "https://f.example.org/x", max_bytes=100)
        assert result.outcome is FetchOutcome.NETWORK_ERROR


ROBOTS = b"""User-agent: *
Disallow: /private/

User-agent: LIA-Radio
Disallow: /no-radio/
"""


class TestRobots:
    async def test_the_rules_for_our_agent_are_honoured(self) -> None:
        async with client(lambda _r: httpx.Response(200, content=ROBOTS)) as c:
            cache = RobotsCache()
            assert await cache.allows(c, "https://site.example.org/articles/1") is True
            assert await cache.allows(c, "https://site.example.org/no-radio/1") is False

    async def test_no_robots_file_allows_everything(self) -> None:
        async with client(lambda _r: httpx.Response(404)) as c:
            assert await RobotsCache().allows(c, "https://site.example.org/private/1") is True

    @pytest.mark.parametrize("status", [429, 500, 503])
    async def test_doubt_never_reads_a_page(self, status: int) -> None:
        async with client(lambda _r: httpx.Response(status)) as c:
            assert await RobotsCache().allows(c, "https://site.example.org/a") is False

    async def test_robots_is_read_once_per_origin_until_it_expires(self) -> None:
        reads: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            reads.append(str(request.url))
            return httpx.Response(200, content=ROBOTS)

        now = [1000.0]
        async with client(handler) as c:
            cache = RobotsCache(clock=lambda: now[0])
            await cache.allows(c, "https://site.example.org/a")
            await cache.allows(c, "https://site.example.org/b")
            assert reads == ["https://site.example.org/robots.txt"]
            now[0] += 25 * 3600
            await cache.allows(c, "https://site.example.org/c")
            assert len(reads) == 2

    async def test_a_burst_of_checks_reads_robots_once(self) -> None:
        reads: list[str] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            reads.append(str(request.url))
            await asyncio.sleep(0)  # let the other checks run meanwhile
            return httpx.Response(200, content=ROBOTS)

        async with client(handler) as c:
            cache = RobotsCache()
            verdicts = await asyncio.gather(
                *(cache.allows(c, f"https://site.example.org/a/{n}") for n in range(5))
            )
        assert verdicts == [True] * 5
        assert len(reads) == 1

    async def test_a_non_web_url_is_never_allowed(self) -> None:
        async with client(lambda _r: httpx.Response(200, content=b"")) as c:
            assert await RobotsCache().allows(c, "ftp://site.example.org/a") is False
