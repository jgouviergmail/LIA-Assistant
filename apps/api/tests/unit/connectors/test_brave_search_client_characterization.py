"""
Characterization tests for BraveSearchClient (public contract).

Pin the externally observable behavior of the client BEFORE its migration to
BaseAPIKeyClient (F2), so the migration can be proven behavior-preserving:
- search() returns the parsed dict on success, and **None on any error**
  (invalid endpoint, non-200 status, timeout after retries, unexpected
  exception) — callers rely on the None-on-error contract.
- Auth via the X-Subscription-Token header (raw key, no prefix).
- Query params: q, count (capped at 20 for web / 50 for news), search_lang,
  plus optional freshness/country.
- 429 responses are retried with backoff, then succeed.

Implementation-agnostic mocking: httpx.AsyncClient is patched to route through
a MockTransport, so the tests hold whether headers are set at client
construction (legacy) or per request (BaseAPIKeyClient).
"""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import pytest

from src.domains.connectors.clients.brave_search_client import BraveSearchClient

API_KEY = "BSA-test-key-1234567890"

# Captured BEFORE any patch — the factory must build the real class, not the
# patched name (otherwise it recurses on itself).
_REAL_ASYNC_CLIENT = httpx.AsyncClient


def _make_client_factory(handler):
    """Return an httpx.AsyncClient factory routing through MockTransport."""
    transport = httpx.MockTransport(handler)

    def factory(*args, **kwargs):
        kwargs.pop("transport", None)
        return _REAL_ASYNC_CLIENT(*args, transport=transport, **kwargs)

    return factory


def _patches(handler):
    """Patch AsyncClient (MockTransport) + asyncio.sleep (fast retries)."""
    return (
        patch("httpx.AsyncClient", new=_make_client_factory(handler)),
        patch("asyncio.sleep", new=AsyncMock()),
    )


@pytest.fixture(autouse=True)
def _fresh_circuit_breaker():
    """Isolate the process-global circuit-breaker registry between tests.

    Post-migration the client shares a per-service breaker; failure-path tests
    would otherwise open it and starve later tests (order-dependent failures).
    """
    from src.infrastructure.resilience.circuit_breaker import CircuitBreakerRegistry

    CircuitBreakerRegistry.clear()
    yield
    CircuitBreakerRegistry.clear()


@pytest.fixture
def client():
    """Brave client with a high rate limit (no throttling in tests)."""
    return BraveSearchClient(api_key=API_KEY, user_id=uuid4(), rate_limit_per_second=1000)


class TestBraveSearchSuccess:
    async def test_web_search_returns_parsed_dict(self, client):
        """Web search hits /web/search and returns the parsed JSON body."""
        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(200, json={"web": {"results": [{"title": "Python"}]}})

        p1, p2 = _patches(handler)
        with p1, p2:
            result = await client.search("python", endpoint="web", count=5)
            await client.close()

        assert result == {"web": {"results": [{"title": "Python"}]}}
        assert len(captured) == 1
        assert captured[0].url.path == "/res/v1/web/search"

    async def test_auth_header_is_raw_subscription_token(self, client):
        """The API key travels as a raw X-Subscription-Token header."""
        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(200, json={"web": {"results": []}})

        p1, p2 = _patches(handler)
        with p1, p2:
            await client.search("q")
            await client.close()

        assert captured[0].headers["X-Subscription-Token"] == API_KEY

    async def test_query_params_include_q_count_and_language(self, client):
        """q, count and search_lang are always sent."""
        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(200, json={"web": {"results": []}})

        p1, p2 = _patches(handler)
        with p1, p2:
            await client.search("hello world", count=7)
            await client.close()

        params = dict(captured[0].url.params)
        assert params["q"] == "hello world"
        assert params["count"] == "7"
        assert params["search_lang"] == "fr"  # constructor default

    async def test_count_is_capped_per_endpoint(self, client):
        """count is capped at 20 for web and 50 for news."""
        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            body = {"web": {"results": []}} if "/web/" in str(request.url) else {"results": []}
            return httpx.Response(200, json=body)

        p1, p2 = _patches(handler)
        with p1, p2:
            await client.search("q", endpoint="web", count=100)
            await client.search("q", endpoint="news", count=100)
            await client.close()

        assert dict(captured[0].url.params)["count"] == "20"
        assert dict(captured[1].url.params)["count"] == "50"

    async def test_optional_freshness_and_country_params(self, client):
        """freshness and country are only sent when provided."""
        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(200, json={"web": {"results": []}})

        p1, p2 = _patches(handler)
        with p1, p2:
            await client.search("q", freshness="pw", country="fr")
            await client.search("q")
            await client.close()

        with_optional = dict(captured[0].url.params)
        without_optional = dict(captured[1].url.params)
        assert with_optional["freshness"] == "pw"
        assert with_optional["country"] == "fr"
        assert "freshness" not in without_optional
        assert "country" not in without_optional

    async def test_news_endpoint_uses_news_path(self, client):
        """News search hits /news/search."""
        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(200, json={"results": [{"title": "News"}]})

        p1, p2 = _patches(handler)
        with p1, p2:
            result = await client.search("q", endpoint="news")
            await client.close()

        assert captured[0].url.path == "/res/v1/news/search"
        assert result == {"results": [{"title": "News"}]}


class TestBraveSearchNoneOnError:
    """The None-on-error contract callers rely on (`if not result: return []`)."""

    async def test_invalid_endpoint_returns_none_without_http_call(self, client):
        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(200, json={})

        p1, p2 = _patches(handler)
        with p1, p2:
            result = await client.search("q", endpoint="invalid")  # type: ignore[arg-type]
            await client.close()

        assert result is None
        assert captured == []

    async def test_auth_error_returns_none(self, client):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, text="Unauthorized")

        p1, p2 = _patches(handler)
        with p1, p2:
            result = await client.search("q")
            await client.close()

        assert result is None

    async def test_server_error_returns_none(self, client):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="boom")

        p1, p2 = _patches(handler)
        with p1, p2:
            result = await client.search("q")
            await client.close()

        assert result is None

    async def test_persistent_timeout_returns_none(self, client):
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            raise httpx.TimeoutException("timed out", request=request)

        p1, p2 = _patches(handler)
        with p1, p2:
            result = await client.search("q")
            await client.close()

        assert result is None
        assert calls["n"] >= 3  # retried before giving up

    async def test_rate_limited_then_success_retries(self, client):
        """A 429 is retried (with backoff) and the retry result is returned."""
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(429, headers={"Retry-After": "0"})
            return httpx.Response(200, json={"web": {"results": [{"title": "ok"}]}})

        p1, p2 = _patches(handler)
        with p1, p2:
            result = await client.search("q")
            await client.close()

        assert result == {"web": {"results": [{"title": "ok"}]}}
        assert calls["n"] == 2


class TestBraveClientLifecycle:
    async def test_close_is_idempotent(self, client):
        """close() can be called twice, including before any request."""
        await client.close()
        await client.close()

    async def test_user_id_none_is_supported(self):
        """The client works without a user_id (logging-only field)."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"web": {"results": []}})

        anonymous = BraveSearchClient(api_key=API_KEY, rate_limit_per_second=1000)
        p1, p2 = _patches(handler)
        with p1, p2:
            result = await anonymous.search("q")
            await anonymous.close()

        assert result == {"web": {"results": []}}
