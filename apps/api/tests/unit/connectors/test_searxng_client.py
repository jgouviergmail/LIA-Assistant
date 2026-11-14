"""The instance's SearXNG client (lot 18): what it asks, what it reads, how it fails.

SearXNG is a service the operator runs on the internal network: no key travels,
one rate-limit bucket serves the whole instance (the public engines it asks
throttle the server's address, never an account), and a refused or unreadable
search RAISES — the caller says it failed, it never reads « nothing found ».
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import pytest

from src.core.config import settings
from src.core.constants import SEARXNG_QUERY_MAX_CHARS
from src.domains.connectors.clients.searxng_client import SearXNGClient

pytestmark = pytest.mark.unit

_REAL_ASYNC_CLIENT = httpx.AsyncClient
BASE = "http://searxng:8080"


def _patches(handler):  # noqa: ANN001, ANN202
    transport = httpx.MockTransport(handler)

    def factory(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        kwargs.pop("transport", None)
        return _REAL_ASYNC_CLIENT(*args, transport=transport, **kwargs)

    return (
        patch("httpx.AsyncClient", new=factory),
        patch("asyncio.sleep", new=AsyncMock()),
    )


@pytest.fixture(autouse=True)
def _fresh_circuit_breaker():  # noqa: ANN202
    from src.infrastructure.resilience.circuit_breaker import CircuitBreakerRegistry

    CircuitBreakerRegistry.clear()
    yield
    CircuitBreakerRegistry.clear()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> SearXNGClient:
    monkeypatch.setattr(settings, "searxng_url", f"{BASE}/")
    return SearXNGClient(user_id=uuid4(), rate_limit_per_second=1000)


ANSWER = {
    "results": [
        {
            "url": "https://fr.wikipedia.org/wiki/Canberra",
            "title": "Canberra — Wikipédia",
            "content": "Canberra est la capitale fédérale de l'Australie.",
            "engines": ["google cse", "duckduckgo"],
            "publishedDate": None,
        },
        {
            "url": "https://www.tf1info.fr/x",
            "title": "Un train percute une voiture",
            "content": "Un TER a percuté une voiture.",
            "engines": ["bing news"],
            "metadata": "Il y a 20 heures | TF1 INFO",
        },
    ],
    "unresponsive_engines": [["brave", "Suspended: too many requests"]],
}


async def test_a_search_asks_json_in_the_persons_language_with_no_key(
    client: SearXNGClient,
) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=ANSWER)

    p1, p2 = _patches(handler)
    with p1, p2:
        answer = await client.search("capitale de l'Australie", language="fr")
        await client.close()

    request = seen[0]
    assert str(request.url).startswith(f"{BASE}/search?")
    assert request.url.params["format"] == "json"
    assert request.url.params["q"] == "capitale de l'Australie"
    assert request.url.params["language"] == "fr"
    assert "categories" not in request.url.params and "time_range" not in request.url.params
    assert "authorization" not in {name.lower() for name in request.headers}
    assert [result.url for result in answer.results] == [
        "https://fr.wikipedia.org/wiki/Canberra",
        "https://www.tf1info.fr/x",
    ]
    assert answer.results[1].metadata == "Il y a 20 heures | TF1 INFO"
    assert answer.unresponsive_engines == [("brave", "Suspended: too many requests")]


async def test_the_web_is_searched_unfiltered_whatever_the_instance_says(
    client: SearXNGClient,
) -> None:
    """No safe-search filter on the web nor the news: the owner's decision (ADR-382).

    Sent on every request, so an operator's ``settings.yml`` cannot filter LIA's searches.
    """
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=ANSWER)

    p1, p2 = _patches(handler)
    with p1, p2:
        await client.search("capitale de l'Australie", language="fr")
        await client.search("élections", language="fr", recency="day", news=True)
        await client.close()

    assert [request.url.params["safesearch"] for request in seen] == ["0", "0"]


async def test_news_and_recency_become_the_news_category_and_a_time_range(
    client: SearXNGClient,
) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"results": []})

    p1, p2 = _patches(handler)
    with p1, p2:
        answer = await client.search("grève", language="zh-CN", recency="week", news=True)
        await client.close()

    params = seen[0].url.params
    assert params["categories"] == "news" and params["time_range"] == "week"
    assert params["language"] == "zh-CN"  # the backend's canonical Chinese, accepted verbatim
    assert answer.results == []


async def test_an_overlong_query_is_cut_at_a_word_boundary_before_it_leaves(
    client: SearXNGClient,
) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"results": []})

    p1, p2 = _patches(handler)
    with p1, p2:
        await client.search("word " * 200, language="en")
        await client.close()

    sent = seen[0].url.params["q"]
    assert len(sent) <= SEARXNG_QUERY_MAX_CHARS and sent.endswith("word")


async def test_a_refused_search_raises_instead_of_reading_as_nothing_found(
    client: SearXNGClient,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "bad request"})

    p1, p2 = _patches(handler)
    with p1, p2, pytest.raises(httpx.HTTPStatusError):
        await client.search("anything", language="en")
    await client.close()


def test_the_whole_instance_shares_one_bucket(client: SearXNGClient) -> None:
    other = SearXNGClient(user_id=uuid4(), rate_limit_per_second=1000)

    assert client._get_rate_limit_key() == other._get_rate_limit_key()
    assert str(client.user_id) not in client._get_rate_limit_key()


def test_the_timeout_is_the_operators(
    client: SearXNGClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "http_timeout_searxng", 7.5)

    assert client._get_http_timeout() == 7.5


async def test_a_service_that_keeps_failing_is_refused_at_once(client: SearXNGClient) -> None:
    """The breaker opens on repeated failures: a turn stops waiting for a dead service."""
    from src.core.exceptions import ExternalServiceError

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    p1, p2 = _patches(handler)
    with p1, p2:
        for _ in range(20):
            try:
                await client.search("x", language="en")
            except httpx.HTTPStatusError:
                continue
            except ExternalServiceError:
                break
        else:
            pytest.fail("the breaker never opened")
        await client.close()


def test_it_is_no_api_key_client() -> None:
    """Its address is the operator's internal service, never a sandbox credential host."""
    from src.domains.connectors.clients.base_api_key_client import BaseAPIKeyClient

    assert not issubclass(SearXNGClient, BaseAPIKeyClient)
