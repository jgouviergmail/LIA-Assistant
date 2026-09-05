"""What ``/api/show`` says becomes the runtime's profile (ADR-267)."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.core.constants import (
    CAPABILITY_PROVENANCE_DISCOVERED,
    OLLAMA_DISCOVERED_MAX_OUTPUT_TOKENS,
    OLLAMA_NUM_CTX_DEFAULT_CAP,
)
from src.infrastructure.llm.model_capabilities_cache import ModelCapabilitiesCache
from src.infrastructure.llm.providers.ollama_discovery import (
    OllamaModelInfo,
    _fetch_model_capabilities,
    build_discovered_profile,
    clear_ollama_model_cache,
    refresh_ollama_capabilities,
)
from src.infrastructure.llm.reasoning.profiles import ollama_declared_ladder

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _reset() -> Generator[None]:
    clear_ollama_model_cache()
    ModelCapabilitiesCache.reset()
    yield
    clear_ollama_model_cache()
    ModelCapabilitiesCache.reset()


def _info(name: str, caps: list[str], context_length: int | None = None) -> OllamaModelInfo:
    return OllamaModelInfo(
        name=name, size="27.3B", family="qwen35", capabilities=caps, context_length=context_length
    )


class TestBuildDiscoveredProfile:
    def test_a_thinking_model_declares_the_full_ladder(self) -> None:
        with patch("src.infrastructure.llm.providers.ollama_discovery.settings") as settings:
            settings.ollama_num_ctx = None
            profile = build_discovered_profile(
                _info("qwen3.8:27b", ["completion", "vision", "tools", "thinking"], 262144)
            )
        assert profile.model_id == "qwen3.8:27b"
        assert profile.is_reasoning_model is True
        assert profile.reasoning_enum_values == list(ollama_declared_ladder(True))
        assert profile.supports_tool_calling is True
        assert profile.supports_vision is True
        assert profile.supports_structured_output is True
        assert profile.kind == "chat"
        assert profile.capability_provenance == CAPABILITY_PROVENANCE_DISCOVERED
        # The number LIA will REQUEST: the model maximum capped by the default cap.
        assert profile.max_input_tokens == OLLAMA_NUM_CTX_DEFAULT_CAP
        assert profile.max_output_tokens == OLLAMA_DISCOVERED_MAX_OUTPUT_TOKENS
        assert profile.metadata["ollama_context_length"] == 262144

    def test_a_plain_model_declares_the_switch_off_only(self) -> None:
        with patch("src.infrastructure.llm.providers.ollama_discovery.settings") as settings:
            settings.ollama_num_ctx = None
            profile = build_discovered_profile(
                _info("gemma4:26b", ["completion", "vision"], 131072)
            )
        assert profile.is_reasoning_model is False
        assert profile.reasoning_enum_values == ["none"]
        assert profile.supports_tool_calling is False

    def test_the_penalties_the_native_client_cannot_express_are_declared_unsupported(
        self,
    ) -> None:
        with patch("src.infrastructure.llm.providers.ollama_discovery.settings") as settings:
            settings.ollama_num_ctx = None
            profile = build_discovered_profile(_info("m", ["completion"]))
        assert profile.supports_frequency_penalty is False
        assert profile.supports_presence_penalty is False
        assert profile.supports_temperature is True
        assert profile.supports_top_p is True

    def test_the_requested_context_window_wins_over_the_model_maximum(self) -> None:
        """What LIA asks for (``num_ctx``) is what the server allocates; the
        model's maximum is only the fallback when nothing is asked."""
        with patch("src.infrastructure.llm.providers.ollama_discovery.settings") as settings:
            settings.ollama_num_ctx = 32768
            profile = build_discovered_profile(_info("m", ["completion"], 262144))
        assert profile.max_input_tokens == 32768

    def test_no_context_length_requests_the_default_cap(self) -> None:
        """The server clamps to the model's real limit; LIA still asks explicitly."""
        with patch("src.infrastructure.llm.providers.ollama_discovery.settings") as settings:
            settings.ollama_num_ctx = None
            profile = build_discovered_profile(_info("m", ["completion"], None))
        assert profile.max_input_tokens == OLLAMA_NUM_CTX_DEFAULT_CAP

    def test_a_small_model_maximum_is_not_inflated_to_the_cap(self) -> None:
        with patch("src.infrastructure.llm.providers.ollama_discovery.settings") as settings:
            settings.ollama_num_ctx = None
            profile = build_discovered_profile(_info("m", ["completion"], 8192))
        assert profile.max_input_tokens == 8192

    def test_an_embedding_model_is_not_a_chat_model(self) -> None:
        with patch("src.infrastructure.llm.providers.ollama_discovery.settings") as settings:
            settings.ollama_num_ctx = None
            profile = build_discovered_profile(_info("nomic-embed-text", ["embedding"]))
        assert profile.kind == "embedding"
        assert profile.supports_structured_output is False

    def test_the_context_window_reader_trusts_a_discovered_profile(self) -> None:
        """``discovered`` is not ``declared``: the reader must believe the server."""
        from src.core.llm_config_helper import get_effective_context_window

        with patch("src.infrastructure.llm.providers.ollama_discovery.settings") as settings:
            settings.ollama_num_ctx = 32768
            ModelCapabilitiesCache.merge_discovered(
                "ollama",
                {
                    "qwen3.8:27b": build_discovered_profile(
                        _info("qwen3.8:27b", ["completion"], 262144)
                    )
                },
            )
        assert get_effective_context_window("qwen3.8:27b") == 32768


class TestFetchModelCapabilities:
    async def test_reads_capabilities_and_context_length(self) -> None:
        response = MagicMock(spec=httpx.Response)
        response.raise_for_status = MagicMock()
        response.json.return_value = {
            "capabilities": ["completion", "thinking"],
            "model_info": {"general.architecture": "qwen35", "qwen35.context_length": 262144},
        }
        client = AsyncMock()
        client.post = AsyncMock(return_value=response)
        assert await _fetch_model_capabilities(client, "http://h:11434", "m") == (
            ["completion", "thinking"],
            262144,
        )

    async def test_degrades_per_model(self) -> None:
        client = AsyncMock()
        client.post = AsyncMock(side_effect=httpx.ConnectError("down"))
        assert await _fetch_model_capabilities(client, "http://h:11434", "m") == ([], None)


class TestRefreshOllamaCapabilities:
    async def test_publishes_every_discovered_model_to_the_cache(self) -> None:
        infos = [
            _info("qwen3.8:27b", ["completion", "tools", "thinking"], 262144),
            _info("gemma4:26b", ["completion"], 131072),
        ]
        with (
            patch(
                "src.infrastructure.llm.providers.ollama_discovery.discover_ollama_models",
                AsyncMock(return_value=infos),
            ),
            patch("src.infrastructure.llm.providers.ollama_discovery.settings") as settings,
        ):
            settings.ollama_num_ctx = None
            returned = await refresh_ollama_capabilities()
        assert returned == infos
        thinking = ModelCapabilitiesCache.get("qwen3.8:27b")
        plain = ModelCapabilitiesCache.get("gemma4:26b")
        assert thinking is not None and thinking.is_reasoning_model is True
        assert plain is not None and plain.reasoning_enum_values == ["none"]
        assert ModelCapabilitiesCache.get_provider("qwen3.8:27b") == "ollama"

    async def test_an_unreachable_server_clears_the_layer(self) -> None:
        ModelCapabilitiesCache.merge_discovered(
            "ollama", {"stale": build_discovered_profile(_info("stale", ["completion"]))}
        )
        with patch(
            "src.infrastructure.llm.providers.ollama_discovery.discover_ollama_models",
            AsyncMock(return_value=[]),
        ):
            assert await refresh_ollama_capabilities() == []
        assert ModelCapabilitiesCache.get("stale") is None
