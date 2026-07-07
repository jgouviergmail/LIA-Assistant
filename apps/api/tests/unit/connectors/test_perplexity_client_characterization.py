"""
Characterization tests for PerplexityClient (public contract).

Pin the externally observable behavior BEFORE the migration to
BaseAPIKeyClient (F4). This client RAISES on errors:
- 401 raises (invalid API key), message mentions the API key.
- 429 is retried with backoff, then the retry result is returned.
- Persistent network errors raise after retries.
Payload shape (model/messages/citations flags) and response parsing
(answer/citations/related_questions + empty-choices fallbacks) are pinned.
"""

from uuid import uuid4

import httpx
import pytest

from src.domains.connectors.clients.perplexity_client import PerplexityClient
from tests.unit.connectors.characterization_harness import transport_patches

API_KEY = "pplx-test-key-1234567890"

SEARCH_RESPONSE = {
    "choices": [{"message": {"content": "AI is progressing."}}],
    "citations": ["https://example.com/a"],
    "related_questions": ["What is AGI?"],
}


@pytest.fixture(autouse=True)
def _fresh_circuit_breaker():
    """Isolate the process-global circuit-breaker registry between tests."""
    from src.infrastructure.resilience.circuit_breaker import CircuitBreakerRegistry

    CircuitBreakerRegistry.clear()
    yield
    CircuitBreakerRegistry.clear()


@pytest.fixture
def client():
    """Perplexity client with a high rate limit (no throttling in tests)."""
    return PerplexityClient(api_key=API_KEY, user_id=uuid4(), rate_limit_per_second=1000)


class TestSearch:
    async def test_search_posts_chat_completions_payload(self, client):
        """search() POSTs to /chat/completions with the pinned payload shape."""
        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(200, json=SEARCH_RESPONSE)

        p1, p2 = transport_patches(handler)
        with p1, p2:
            await client.search(
                "latest AI news",
                search_recency_filter="week",
                return_related_questions=True,
                system_prompt="Current date: 2026-07-07",
            )
            await client.close()

        req = captured[0]
        assert req.method == "POST"
        assert req.url.path == "/chat/completions"
        assert req.headers["Authorization"] == f"Bearer {API_KEY}"

        import json as jsonlib

        payload = jsonlib.loads(req.content)
        assert payload["model"] == "sonar"
        assert payload["messages"][0] == {"role": "system", "content": "Current date: 2026-07-07"}
        assert payload["messages"][1] == {"role": "user", "content": "latest AI news"}
        assert payload["return_citations"] is True
        assert payload["return_related_questions"] is True
        assert payload["search_recency_filter"] == "week"

    async def test_search_parses_answer_citations_related(self, client):
        """search() maps the API response to the pinned result shape."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=SEARCH_RESPONSE)

        p1, p2 = transport_patches(handler)
        with p1, p2:
            result = await client.search("q")
            await client.close()

        assert result == {
            "answer": "AI is progressing.",
            "citations": ["https://example.com/a"],
            "related_questions": ["What is AGI?"],
            "query": "q",
            "model": "sonar",
        }

    async def test_search_empty_choices_fallback(self, client):
        """Empty choices → empty answer dict (quirk: no 'model' key here)."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"choices": []})

        p1, p2 = transport_patches(handler)
        with p1, p2:
            result = await client.search("q")
            await client.close()

        assert result == {
            "answer": "",
            "citations": [],
            "related_questions": [],
            "query": "q",
        }


class TestAsk:
    async def test_ask_payload_and_parsing(self, client):
        """ask() sends temperature + citations flag and parses the answer."""
        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": "42"}}], "citations": []},
            )

        p1, p2 = transport_patches(handler)
        with p1, p2:
            result = await client.ask("meaning of life?", temperature=0.5)
            await client.close()

        import json as jsonlib

        payload = jsonlib.loads(captured[0].content)
        assert payload["temperature"] == 0.5
        assert payload["return_citations"] is True
        assert result == {
            "answer": "42",
            "citations": [],
            "question": "meaning of life?",
            "model": "sonar",
        }


class TestErrorContract:
    """Perplexity raises on errors (callers catch broadly)."""

    async def test_invalid_api_key_raises_mentioning_api_key(self, client):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": "unauthorized"})

        p1, p2 = transport_patches(handler)
        with p1, p2:
            with pytest.raises(Exception, match="API key"):
                await client.search("q")
            await client.close()

    async def test_rate_limited_then_success_retries(self, client):
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(429, headers={"Retry-After": "0"})
            return httpx.Response(200, json=SEARCH_RESPONSE)

        p1, p2 = transport_patches(handler)
        with p1, p2:
            result = await client.search("q")
            await client.close()

        assert result["answer"] == "AI is progressing."
        assert calls["n"] == 2

    async def test_persistent_network_error_raises(self, client):
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            raise httpx.ConnectError("boom", request=request)

        p1, p2 = transport_patches(handler)
        with p1, p2:
            with pytest.raises(Exception):
                await client.search("q")
            await client.close()

        assert calls["n"] >= 3

    async def test_server_error_raises(self, client):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, text="unavailable")

        p1, p2 = transport_patches(handler)
        with p1, p2:
            with pytest.raises(Exception):
                await client.search("q")
            await client.close()


class TestHelpers:
    async def test_close_is_idempotent(self, client):
        await client.close()
        await client.close()

    def test_set_model_and_available_models(self, client):
        client.set_model("sonar-pro")
        assert client.model == "sonar-pro"
        models = PerplexityClient.get_available_models()
        assert {m["id"] for m in models} == {"sonar", "sonar-pro"}
