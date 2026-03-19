"""
Unit tests for Ollama dynamic model discovery.

Tests discover_ollama_models() with real capability fetching via /api/show.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.infrastructure.llm.providers.ollama_discovery import (
    _fetch_model_capabilities,
    clear_ollama_model_cache,
    discover_ollama_models,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

OLLAMA_TAGS_RESPONSE = {
    "models": [
        {
            "name": "qwen3:14b-q4_K_M",
            "size": 9276198565,
            "details": {
                "family": "qwen3",
                "parameter_size": "14.8B",
                "quantization_level": "Q4_K_M",
            },
        },
        {
            "name": "gemma3:27b-it-q4_K_M",
            "size": 17396936941,
            "details": {
                "family": "gemma3",
                "parameter_size": "27.4B",
            },
        },
        {
            "name": "nomic-embed-text:latest",
            "size": 274302450,
            "details": {
                "family": "nomic-bert",
                "parameter_size": "137M",
            },
        },
        {
            "name": "deepseek-r1:14b-qwen-distill-q4_K_M",
            "size": 8988112209,
            "details": {
                "family": "qwen2",
                "parameter_size": "14.8B",
            },
        },
    ]
}

# /api/show responses per model (capabilities from the real Ollama API)
SHOW_RESPONSES = {
    "qwen3:14b-q4_K_M": {"capabilities": ["completion", "tools", "thinking"]},
    "gemma3:27b-it-q4_K_M": {"capabilities": ["completion", "vision"]},
    "nomic-embed-text:latest": {"capabilities": ["embedding"]},
    "deepseek-r1:14b-qwen-distill-q4_K_M": {"capabilities": ["completion", "thinking"]},
}


@pytest.fixture(autouse=True)
def _clear_cache():
    """Ensure fresh cache state for each test."""
    clear_ollama_model_cache()
    yield
    clear_ollama_model_cache()


def _mock_response(json_data: dict, status_code: int = 200) -> httpx.Response:
    """Create a mock httpx.Response."""
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.json.return_value = json_data
    response.raise_for_status = MagicMock()
    if status_code >= 400:
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=response
        )
    return response


def _make_mock_client(tags_response: dict, show_responses: dict | None = None) -> AsyncMock:
    """Create a mock httpx.AsyncClient that handles GET /api/tags and POST /api/show."""
    mock_client = AsyncMock()

    async def mock_get(url: str) -> httpx.Response:
        return _mock_response(tags_response)

    async def mock_post(url: str, json: dict | None = None) -> httpx.Response:
        if show_responses and json:
            model_name = json.get("name", "")
            data = show_responses.get(model_name, {"capabilities": []})
            return _mock_response(data)
        return _mock_response({"capabilities": []})

    mock_client.get = mock_get
    mock_client.post = mock_post
    return mock_client


# ---------------------------------------------------------------------------
# discover_ollama_models tests
# ---------------------------------------------------------------------------


class TestDiscoverOllamaModels:
    """Tests for discover_ollama_models()."""

    @pytest.mark.asyncio
    async def test_success_with_real_capabilities(self):
        """Should return models with capabilities from /api/show."""
        mock_client = _make_mock_client(OLLAMA_TAGS_RESPONSE, SHOW_RESPONSES)

        with (
            patch(
                "src.infrastructure.llm.providers.ollama_discovery._resolve_ollama_base_url",
                return_value="http://localhost:11434",
            ),
            patch("httpx.AsyncClient") as mock_cls,
        ):
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            models = await discover_ollama_models()

        assert len(models) == 4

        # qwen3 — tools + thinking
        qwen3 = models[0]
        assert qwen3.name == "qwen3:14b-q4_K_M"
        assert "tools" in qwen3.capabilities
        assert "thinking" in qwen3.capabilities

        # gemma3 — vision only (no tools!)
        gemma3 = models[1]
        assert gemma3.name == "gemma3:27b-it-q4_K_M"
        assert "vision" in gemma3.capabilities
        assert "tools" not in gemma3.capabilities

        # nomic — embedding only
        nomic = models[2]
        assert nomic.name == "nomic-embed-text"  # :latest stripped
        assert nomic.capabilities == ["embedding"]

        # deepseek-r1 — thinking (no tools)
        r1 = models[3]
        assert "thinking" in r1.capabilities
        assert "tools" not in r1.capabilities

    @pytest.mark.asyncio
    async def test_strips_latest_tag(self):
        """Should strip ':latest' from model names."""
        response_data = {
            "models": [
                {"name": "llama3.1:latest", "details": {"parameter_size": "8B", "family": "llama"}}
            ]
        }
        mock_client = _make_mock_client(
            response_data, {"llama3.1:latest": {"capabilities": ["completion", "tools"]}}
        )

        with (
            patch(
                "src.infrastructure.llm.providers.ollama_discovery._resolve_ollama_base_url",
                return_value="http://localhost:11434",
            ),
            patch("httpx.AsyncClient") as mock_cls,
        ):
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            models = await discover_ollama_models()

        assert len(models) == 1
        assert models[0].name == "llama3.1"

    @pytest.mark.asyncio
    async def test_keeps_specific_tags(self):
        """Should preserve non-':latest' tags like ':70b' or ':8b-instruct'."""
        response_data = {
            "models": [
                {"name": "llama3.2:70b", "details": {"parameter_size": "70B", "family": "llama"}},
                {
                    "name": "mistral:8b-instruct",
                    "details": {"parameter_size": "8B", "family": "mistral"},
                },
            ]
        }
        mock_client = _make_mock_client(response_data)

        with (
            patch(
                "src.infrastructure.llm.providers.ollama_discovery._resolve_ollama_base_url",
                return_value="http://localhost:11434",
            ),
            patch("httpx.AsyncClient") as mock_cls,
        ):
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            models = await discover_ollama_models()

        assert models[0].name == "llama3.2:70b"
        assert models[1].name == "mistral:8b-instruct"

    @pytest.mark.asyncio
    async def test_timeout(self):
        """Should return empty list on timeout."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timed out"))

        with (
            patch(
                "src.infrastructure.llm.providers.ollama_discovery._resolve_ollama_base_url",
                return_value="http://localhost:11434",
            ),
            patch("httpx.AsyncClient") as mock_cls,
        ):
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            models = await discover_ollama_models()

        assert models == []

    @pytest.mark.asyncio
    async def test_unreachable(self):
        """Should return empty list when Ollama server is unreachable."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))

        with (
            patch(
                "src.infrastructure.llm.providers.ollama_discovery._resolve_ollama_base_url",
                return_value="http://localhost:11434",
            ),
            patch("httpx.AsyncClient") as mock_cls,
        ):
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            models = await discover_ollama_models()

        assert models == []

    @pytest.mark.asyncio
    async def test_cache_hit(self):
        """Second call within TTL should return cached results without HTTP."""
        call_count = 0

        async def counting_get(url: str) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return _mock_response(OLLAMA_TAGS_RESPONSE)

        mock_client = _make_mock_client(OLLAMA_TAGS_RESPONSE, SHOW_RESPONSES)
        mock_client.get = counting_get

        with (
            patch(
                "src.infrastructure.llm.providers.ollama_discovery._resolve_ollama_base_url",
                return_value="http://localhost:11434",
            ),
            patch("httpx.AsyncClient") as mock_cls,
        ):
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            models1 = await discover_ollama_models()
            models2 = await discover_ollama_models()

        assert models1 == models2
        assert call_count == 1  # Only one /api/tags call

    @pytest.mark.asyncio
    async def test_no_url(self):
        """Should return empty list when no Ollama URL is configured."""
        with patch(
            "src.infrastructure.llm.providers.ollama_discovery._resolve_ollama_base_url",
            return_value=None,
        ):
            models = await discover_ollama_models()

        assert models == []

    @pytest.mark.asyncio
    async def test_deduplicates_latest_and_plain(self):
        """Should deduplicate when both 'model' and 'model:latest' exist."""
        response_data = {
            "models": [
                {"name": "llama3.1:latest", "details": {"parameter_size": "8B", "family": "llama"}},
                {"name": "llama3.1", "details": {"parameter_size": "8B", "family": "llama"}},
            ]
        }
        mock_client = _make_mock_client(response_data)

        with (
            patch(
                "src.infrastructure.llm.providers.ollama_discovery._resolve_ollama_base_url",
                return_value="http://localhost:11434",
            ),
            patch("httpx.AsyncClient") as mock_cls,
        ):
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            models = await discover_ollama_models()

        assert len(models) == 1
        assert models[0].name == "llama3.1"

    @pytest.mark.asyncio
    async def test_show_error_returns_empty_capabilities(self):
        """If /api/show fails for a model, capabilities should be empty (not crash)."""
        response_data = {
            "models": [
                {
                    "name": "broken-model:latest",
                    "details": {"family": "test", "parameter_size": "1B"},
                }
            ]
        }

        async def failing_post(url: str, json: dict | None = None) -> httpx.Response:
            raise httpx.TimeoutException("show timed out")

        mock_client = _make_mock_client(response_data)
        mock_client.post = failing_post

        with (
            patch(
                "src.infrastructure.llm.providers.ollama_discovery._resolve_ollama_base_url",
                return_value="http://localhost:11434",
            ),
            patch("httpx.AsyncClient") as mock_cls,
        ):
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            models = await discover_ollama_models()

        assert len(models) == 1
        assert models[0].name == "broken-model"
        assert models[0].capabilities == []


# ---------------------------------------------------------------------------
# _fetch_model_capabilities tests
# ---------------------------------------------------------------------------


class TestFetchModelCapabilities:
    """Tests for _fetch_model_capabilities()."""

    @pytest.mark.asyncio
    async def test_returns_capabilities(self):
        """Should return capabilities list from /api/show response."""
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(
            return_value=_mock_response({"capabilities": ["completion", "tools", "vision"]})
        )
        caps = await _fetch_model_capabilities(mock_client, "http://localhost:11434", "test-model")
        assert caps == ["completion", "tools", "vision"]

    @pytest.mark.asyncio
    async def test_returns_empty_on_error(self):
        """Should return empty list on HTTP error."""
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
        caps = await _fetch_model_capabilities(mock_client, "http://localhost:11434", "test-model")
        assert caps == []

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_capabilities_field(self):
        """Should return empty list when response has no capabilities field."""
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(
            return_value=_mock_response({"license": "MIT", "template": "..."})
        )
        caps = await _fetch_model_capabilities(mock_client, "http://localhost:11434", "test-model")
        assert caps == []
