"""What `/api/tags` already says, and what `/api/show` refuses to say (ADR-278).

Measured on Ollama 0.33.2, 2026-09-10, thirteen tags:

- ``/api/tags`` carries ``capabilities`` AND ``details.context_length`` for
  EVERY tag, cloud ones included;
- ``/api/show`` answers with capabilities and a ``model_info`` context length
  for local tags and for four of the eight cloud tags, and returns NOTHING for
  the other four (``kimi-k2.5:cloud``, ``glm-5:cloud``, ``deepseek-v3.2:cloud``,
  ``qwen3-vl:235b-instruct-cloud``).

Reading the silence of ``/api/show`` as a declaration is the defect this closes:
those four tags were published as unable to call tools, unable to think, and
capped at the local VRAM tier — and that profile WON over any catalogue row an
administrator could edit. Two of them declare 262 144 tokens of context in
``/api/tags``.

So the listing is read first and the per-model call is the FALLBACK, which also
removes thirteen HTTP round-trips from the boot path and from every opening of
the admin model list.

A cloud tag is recognised by ``remote_host`` / ``remote_model``, present in the
listing and absent on a local tag — never by a ``-cloud`` / ``:cloud`` suffix,
which is a naming convention rather than a contract.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.core.constants import OLLAMA_NUM_CTX_DEFAULT_CAP
from src.infrastructure.llm.providers.ollama_discovery import (
    OllamaModelInfo,
    build_discovered_profile,
    clear_ollama_model_cache,
    discover_ollama_models,
    requested_num_ctx,
)

pytestmark = pytest.mark.unit


# --- Real payload shapes, transcribed from the probe -------------------------

LOCAL_TAG: dict[str, Any] = {
    "name": "qwen3.8:27b",
    "details": {
        "family": "qwen35",
        "parameter_size": "27.3B",
        "context_length": 262144,
        "embedding_length": 5120,
    },
    "capabilities": ["completion", "tools", "thinking", "vision"],
}

BLIND_CLOUD_TAG: dict[str, Any] = {
    "name": "kimi-k2.5:cloud",
    "remote_host": "https://ollama.com:443",
    "remote_model": "kimi-k2.5",
    "details": {
        "family": "kimi",
        "parameter_size": "1T",
        "context_length": 262144,
    },
    "capabilities": ["completion", "tools", "thinking", "vision"],
}


def _tags(*entries: dict[str, Any]) -> dict[str, Any]:
    return {"models": list(entries)}


class _Response:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


class _Client:
    """An httpx stand-in that records whether `/api/show` was reached at all."""

    def __init__(self, tags: dict[str, Any], show: dict[str, Any] | None = None) -> None:
        self._tags = tags
        self._show = show or {}
        self.show_calls: list[str] = []

    async def __aenter__(self) -> _Client:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def get(self, url: str) -> _Response:
        assert url.endswith("/api/tags")
        return _Response(self._tags)

    async def post(self, url: str, json: dict[str, Any]) -> _Response:
        assert url.endswith("/api/show")
        self.show_calls.append(json["name"])
        return _Response(self._show)


@pytest.fixture(autouse=True)
def _clear_cache() -> Any:
    clear_ollama_model_cache()
    yield
    clear_ollama_model_cache()


def _discover(client: _Client) -> Any:
    with (
        patch(
            "src.infrastructure.llm.providers.ollama_discovery._resolve_ollama_base_url",
            return_value="http://ollama.test:11434",
        ),
        patch(
            "src.infrastructure.llm.providers.ollama_discovery.httpx.AsyncClient",
            return_value=client,
        ),
    ):
        return client


class TestTheListingIsTheFirstSource:
    @pytest.mark.asyncio
    async def test_a_tag_that_declares_itself_costs_no_second_call(self) -> None:
        client = _Client(_tags(LOCAL_TAG))
        _discover(client)
        with (
            patch(
                "src.infrastructure.llm.providers.ollama_discovery._resolve_ollama_base_url",
                return_value="http://ollama.test:11434",
            ),
            patch(
                "src.infrastructure.llm.providers.ollama_discovery.httpx.AsyncClient",
                return_value=client,
            ),
        ):
            models = await discover_ollama_models()

        assert client.show_calls == []
        assert models[0].capabilities == ["completion", "tools", "thinking", "vision"]
        assert models[0].context_length == 262144

    @pytest.mark.asyncio
    async def test_a_cloud_tag_keeps_what_the_listing_says(self) -> None:
        """The regression: `/api/show` answers NOTHING for this tag."""
        client = _Client(_tags(BLIND_CLOUD_TAG), show={})
        with (
            patch(
                "src.infrastructure.llm.providers.ollama_discovery._resolve_ollama_base_url",
                return_value="http://ollama.test:11434",
            ),
            patch(
                "src.infrastructure.llm.providers.ollama_discovery.httpx.AsyncClient",
                return_value=client,
            ),
        ):
            models = await discover_ollama_models()

        assert models[0].capabilities == ["completion", "tools", "thinking", "vision"]
        assert models[0].context_length == 262144
        assert models[0].is_cloud is True

    @pytest.mark.asyncio
    async def test_a_tag_the_listing_says_nothing_about_falls_back_to_show(self) -> None:
        bare = {"name": "mystery:latest", "details": {"family": "x"}}
        show = {
            "capabilities": ["completion", "tools"],
            "model_info": {"x.context_length": 8192},
        }
        client = _Client(_tags(bare), show=show)
        with (
            patch(
                "src.infrastructure.llm.providers.ollama_discovery._resolve_ollama_base_url",
                return_value="http://ollama.test:11434",
            ),
            patch(
                "src.infrastructure.llm.providers.ollama_discovery.httpx.AsyncClient",
                return_value=client,
            ),
        ):
            models = await discover_ollama_models()

        assert client.show_calls == ["mystery:latest"]
        assert models[0].capabilities == ["completion", "tools"]
        assert models[0].context_length == 8192


class TestACloudTagIsRecognisedByItsHostNotItsName:
    def test_a_remote_host_makes_a_tag_cloud(self) -> None:
        info = OllamaModelInfo(name="kimi-k2.5:cloud", remote_host="https://ollama.com:443")
        assert info.is_cloud is True

    def test_a_name_that_merely_says_cloud_does_not(self) -> None:
        """A suffix is a naming convention, never a contract."""
        info = OllamaModelInfo(name="my-cloudy-model:latest")
        assert info.is_cloud is False


class TestTheRequestedWindowKnowsWhereTheModelRuns:
    def test_a_local_tag_is_capped_by_the_vram_tier(self) -> None:
        assert requested_num_ctx(262144, is_cloud=False) == OLLAMA_NUM_CTX_DEFAULT_CAP

    def test_a_cloud_tag_keeps_its_whole_window(self) -> None:
        """There is no VRAM to protect on somebody else's machine."""
        assert requested_num_ctx(262144, is_cloud=True) == 262144

    def test_a_small_local_maximum_is_never_inflated(self) -> None:
        assert requested_num_ctx(4096, is_cloud=False) == 4096

    def test_an_unreported_window_still_asks_for_the_cap(self) -> None:
        """ADR-267's invariant: what LIA accounts with is what LIA REQUESTS.

        Asking for nothing is not neutral — the server then picks a VRAM tier
        (4k under 24 GiB) and truncates the beginning of a longer prompt in
        silence, which is the defect ADR-267 closed. The cap is the
        conservative request; the server clamps it down if the model is
        smaller, and says so."""
        assert requested_num_ctx(None, is_cloud=False) == OLLAMA_NUM_CTX_DEFAULT_CAP
        assert requested_num_ctx(None, is_cloud=True) == OLLAMA_NUM_CTX_DEFAULT_CAP
        assert requested_num_ctx(0, is_cloud=False) == OLLAMA_NUM_CTX_DEFAULT_CAP


class TestTheProfileCarriesWhatWasDiscovered:
    def test_a_blind_tag_publishes_no_profile_at_all(self) -> None:
        """Silence is not a declaration. A tag nobody could read stays UNKNOWN,
        which is the pre-ADR-267 behaviour, rather than being published as
        tool-less and thought-less — a profile that then WON over any catalogue
        row an administrator could edit."""
        assert build_discovered_profile(OllamaModelInfo(name="mystery:latest")) is None

    def test_a_cloud_tag_declares_its_own_window(self) -> None:
        profile = build_discovered_profile(
            OllamaModelInfo(
                name="kimi-k2.5:cloud",
                remote_host="https://ollama.com:443",
                capabilities=["completion", "tools", "thinking", "vision"],
                context_length=262144,
            )
        )

        assert profile is not None
        assert profile.max_input_tokens == 262144
        assert profile.supports_tool_calling is True
        assert profile.is_reasoning_model is True
        assert profile.supports_vision is True

    def test_a_local_tag_is_capped(self) -> None:
        profile = build_discovered_profile(
            OllamaModelInfo(
                name="qwen3.8:27b",
                capabilities=["completion", "tools", "thinking"],
                context_length=262144,
            )
        )

        assert profile is not None
        assert profile.max_input_tokens == OLLAMA_NUM_CTX_DEFAULT_CAP
        assert profile.metadata["ollama_is_cloud"] is False

    def test_an_embedding_tag_is_not_a_chat_model(self) -> None:
        profile = build_discovered_profile(
            OllamaModelInfo(
                name="nomic-embed-text:latest",
                capabilities=["embedding"],
                context_length=2048,
            )
        )

        assert profile is not None
        assert profile.kind == "embedding"


class TestAnUnreachableServerSaysNothing:
    @pytest.mark.asyncio
    async def test_no_url_discovers_nothing(self) -> None:
        with patch(
            "src.infrastructure.llm.providers.ollama_discovery._resolve_ollama_base_url",
            return_value=None,
        ):
            assert await discover_ollama_models() == []

    @pytest.mark.asyncio
    async def test_a_failing_listing_discovers_nothing(self) -> None:
        import httpx

        failing = AsyncMock()
        failing.__aenter__.return_value = failing
        failing.get.side_effect = httpx.ConnectError("refused")
        with (
            patch(
                "src.infrastructure.llm.providers.ollama_discovery._resolve_ollama_base_url",
                return_value="http://ollama.test:11434",
            ),
            patch(
                "src.infrastructure.llm.providers.ollama_discovery.httpx.AsyncClient",
                return_value=failing,
            ),
        ):
            assert await discover_ollama_models() == []
