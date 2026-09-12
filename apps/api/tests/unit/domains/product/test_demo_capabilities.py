"""The relay of the demonstrator's own capability list.

What must hold: the read asks the demonstrator's ORIGIN (the advertised link
points at a page), keeps only well-formed entries, is bounded and cached — a
negative answer included — and never raises: an unreadable demonstrator is
"unknown", which the page renders as "did not answer", never as an empty
"switched off" column.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.core import constants
from src.domains.product import demo_capabilities as relay

pytestmark = pytest.mark.unit

DEMO_LINK = "https://demo.example.org/register"
CONFIG_URL = "https://demo.example.org/api/v1/config"

PAYLOAD = {
    "features": {"journals_enabled": True},
    "capabilities": {
        "web_search": {"enabled": True, "family": "reach"},
        "meetings": {"enabled": False, "family": "media"},
    },
}


def _transport(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


def _answer(status: int = 200, body: object = PAYLOAD) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, content=json.dumps(body).encode(), request=request)

    return _transport(handler)


@pytest.fixture(autouse=True)
def _fresh_cache() -> None:
    relay.reset_cache()


class TestPublicConfigUrl:
    def test_keeps_the_origin_and_drops_the_page(self) -> None:
        assert relay.public_config_url(DEMO_LINK) == CONFIG_URL
        assert relay.public_config_url("https://demo.example.org/fr/register?x=1") == CONFIG_URL
        assert relay.public_config_url("http://localhost:8090/register") == (
            "http://localhost:8090/api/v1/config"
        )

    def test_refuses_what_is_not_an_http_url(self) -> None:
        assert relay.public_config_url("not a url") is None
        assert relay.public_config_url("ftp://demo.example.org") is None
        assert relay.public_config_url("") is None


class TestReadCapabilities:
    def test_keeps_well_formed_entries_and_drops_the_rest(self) -> None:
        read = relay.read_capabilities(
            {
                "capabilities": {
                    "web_search": {"enabled": True, "family": "reach"},
                    "broken": {"enabled": "yes", "family": "reach"},
                    "other": "nope",
                }
            }
        )
        assert read == {"web_search": {"enabled": True, "family": "reach"}}

    def test_answers_none_for_an_absent_or_empty_block(self) -> None:
        assert relay.read_capabilities({"features": {}}) is None
        assert relay.read_capabilities({"capabilities": {}}) is None
        assert relay.read_capabilities("text") is None
        assert relay.read_capabilities(None) is None


class TestFetch:
    async def test_asks_the_origin_and_relays_the_block(self) -> None:
        asked: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            asked.append(str(request.url))
            return httpx.Response(200, content=json.dumps(PAYLOAD).encode(), request=request)

        read = await relay.fetch_demo_capabilities(DEMO_LINK, transport=_transport(handler))
        assert asked == [CONFIG_URL]
        assert read == PAYLOAD["capabilities"]

    async def test_a_refusal_reads_as_unknown_never_raises(self) -> None:
        assert await relay.fetch_demo_capabilities(DEMO_LINK, transport=_answer(status=503)) is None

    async def test_a_non_lia_answer_reads_as_unknown(self) -> None:
        assert (
            await relay.fetch_demo_capabilities(
                DEMO_LINK, transport=_answer(body={"hello": "world"})
            )
            is None
        )

    async def test_a_network_failure_reads_as_unknown(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused", request=request)

        assert await relay.fetch_demo_capabilities(DEMO_LINK, transport=_transport(handler)) is None

    async def test_a_bad_link_asks_nothing(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise AssertionError("no request expected")

        assert (
            await relay.fetch_demo_capabilities("not a url", transport=_transport(handler)) is None
        )

    async def test_the_read_is_bounded_in_time(self) -> None:
        captured: dict[str, object] = {}

        class _Client:
            def __init__(self, **kwargs: object) -> None:
                captured.update(kwargs)

            async def __aenter__(self) -> _Client:
                return self

            async def __aexit__(self, *_: object) -> None:
                return None

            async def get(self, url: str) -> httpx.Response:
                return httpx.Response(
                    200,
                    content=json.dumps(PAYLOAD).encode(),
                    request=httpx.Request("GET", url),
                )

        with patch.object(relay.httpx, "AsyncClient", _Client):
            await relay.fetch_demo_capabilities(DEMO_LINK)
        assert captured["timeout"] == constants.DEMO_CAPABILITIES_FETCH_TIMEOUT_SECONDS
        assert captured["follow_redirects"] is False


class TestCache:
    async def test_a_second_read_within_the_ttl_asks_nothing(self) -> None:
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(str(request.url))
            return httpx.Response(200, content=json.dumps(PAYLOAD).encode(), request=request)

        clock = MagicMock(side_effect=[100.0, 100.0, 130.0])
        transport = _transport(handler)
        first = await relay.fetch_demo_capabilities(DEMO_LINK, transport=transport, now=clock)
        second = await relay.fetch_demo_capabilities(DEMO_LINK, transport=transport, now=clock)
        assert first == second == PAYLOAD["capabilities"]
        assert calls == [CONFIG_URL]

    async def test_a_negative_answer_is_cached_too(self) -> None:
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(str(request.url))
            raise httpx.ConnectError("refused", request=request)

        clock = MagicMock(side_effect=[100.0, 100.0, 130.0])
        transport = _transport(handler)
        assert (
            await relay.fetch_demo_capabilities(DEMO_LINK, transport=transport, now=clock) is None
        )
        assert (
            await relay.fetch_demo_capabilities(DEMO_LINK, transport=transport, now=clock) is None
        )
        assert calls == [CONFIG_URL], "an unreachable demonstrator is not re-asked on every load"

    async def test_the_cache_expires(self) -> None:
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(str(request.url))
            return httpx.Response(200, content=json.dumps(PAYLOAD).encode(), request=request)

        ttl = constants.DEMO_CAPABILITIES_CACHE_TTL_SECONDS
        # First read: one clock read (the store). Second: the cache check reads
        # the clock past the TTL, then the store reads it again.
        clock = MagicMock(side_effect=[100.0, 100.0 + ttl + 1, 100.0 + ttl + 1])
        transport = _transport(handler)
        await relay.fetch_demo_capabilities(DEMO_LINK, transport=transport, now=clock)
        await relay.fetch_demo_capabilities(DEMO_LINK, transport=transport, now=clock)
        assert calls == [CONFIG_URL, CONFIG_URL]


class TestTheLinkRouteRelaysIt:
    async def test_the_payload_carries_the_block_when_the_link_is_on(self) -> None:
        from src.domains.product.public_demo_link import PublicDemoLink, get_public_demo_link

        with (
            patch(
                "src.domains.product.public_demo_link.resolve_public_demo_link",
                AsyncMock(return_value=PublicDemoLink(enabled=True, url=DEMO_LINK)),
            ),
            patch(
                "src.domains.product.public_demo_link.fetch_demo_capabilities",
                AsyncMock(return_value=PAYLOAD["capabilities"]),
            ) as fetched,
        ):
            payload = await get_public_demo_link()
        fetched.assert_awaited_once_with(DEMO_LINK)
        assert payload.capabilities is not None
        assert payload.capabilities["meetings"].enabled is False
        assert payload.capabilities["web_search"].family == "reach"

    async def test_the_payload_says_unknown_when_the_demonstrator_did_not_answer(self) -> None:
        from src.domains.product.public_demo_link import PublicDemoLink, get_public_demo_link

        with (
            patch(
                "src.domains.product.public_demo_link.resolve_public_demo_link",
                AsyncMock(return_value=PublicDemoLink(enabled=True, url=DEMO_LINK)),
            ),
            patch(
                "src.domains.product.public_demo_link.fetch_demo_capabilities",
                AsyncMock(return_value=None),
            ),
        ):
            payload = await get_public_demo_link()
        assert payload.enabled is True
        assert payload.capabilities is None

    async def test_nothing_is_asked_while_the_link_is_off(self) -> None:
        from src.domains.product.public_demo_link import PublicDemoLink, get_public_demo_link

        with (
            patch(
                "src.domains.product.public_demo_link.resolve_public_demo_link",
                AsyncMock(return_value=PublicDemoLink()),
            ),
            patch(
                "src.domains.product.public_demo_link.fetch_demo_capabilities",
                AsyncMock(return_value=PAYLOAD["capabilities"]),
            ) as fetched,
        ):
            payload = await get_public_demo_link()
        fetched.assert_not_awaited()
        assert payload.capabilities is None
