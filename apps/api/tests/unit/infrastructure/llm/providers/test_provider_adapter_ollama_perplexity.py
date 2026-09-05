"""Ollama (native client, ADR-267) and Perplexity through ``ProviderAdapter``.

Production, 2026-09-05: the ``response`` slot moved to ``ollama / qwen3.8:27b``
and every turn died at instantiation --

    ValidationError: 1 validation error for ChatOpenAI
    reasoning_effort  Input should be a valid string
    [input_value=ReasoningIntent(level='none', ...)]

The Ollama branch of the OpenAI-compatible shim never routed ``reasoning_effort``
through the ADR-245 seam; neither did Perplexity's. Ollama is now a NATIVE
provider (``langchain-ollama``): the intent reaches the server as ``think``
through the seam, the ladder being the one the server declared at discovery
(``thinking`` capability), the output cap travels as ``num_predict``, the
context window as ``num_ctx``, and usage comes back on every response.
"""

from __future__ import annotations

import json
import os
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.language_models.chat_models import BaseChatModel

from src.core.constants import OLLAMA_BASE_URL_ENV
from src.core.reasoning_intent import ReasoningIntent
from src.infrastructure.llm.model_capabilities_cache import ModelCapabilitiesCache
from src.infrastructure.llm.model_profiles import ModelProfile
from src.infrastructure.llm.providers.adapter import ProviderAdapter
from src.infrastructure.llm.reasoning.profiles import ollama_declared_ladder

pytestmark = pytest.mark.unit

_URL = "http://ollama.local:11434"
_THINKING = "qwen3.8:27b"
_PLAIN = "llama3.2"


def _apply_settings(mock_settings_module: MagicMock, mock_settings_class: object) -> None:
    for attr in dir(mock_settings_class):
        if not attr.startswith("_"):
            setattr(mock_settings_module, attr, getattr(mock_settings_class, attr))
    mock_settings_module.ollama_num_ctx = None


def _ollama_key(url: str | None):  # type: ignore[no-untyped-def]
    """Patch the DB-cache reading of the Ollama URL, the source production used."""
    from src.domains.llm_config.cache import LLMConfigOverrideCache

    return patch.object(
        LLMConfigOverrideCache,
        "get_api_key",
        side_effect=lambda provider: url if provider == "ollama" else None,
    )


def _discovered(model: str, thinking: bool) -> ModelProfile:
    return ModelProfile(
        model_id=model,
        is_reasoning_model=thinking,
        reasoning_enum_values=list(ollama_declared_ladder(thinking)),
        capability_provenance="discovered",
    )


@pytest.fixture(autouse=True)
def _reset_capabilities():  # type: ignore[no-untyped-def]
    ModelCapabilitiesCache.reset()
    ModelCapabilitiesCache.merge_discovered(
        "ollama",
        {_THINKING: _discovered(_THINKING, True), _PLAIN: _discovered(_PLAIN, False)},
    )
    yield
    ModelCapabilitiesCache.reset()


def _create_ollama(
    mock_chat: MagicMock, model: str = _THINKING, url: str | None = _URL, **overrides: Any
) -> dict[str, Any]:
    from langchain_ollama.chat_models import ChatOllama as _RealChatOllama

    mock_chat.return_value = MagicMock(spec=BaseChatModel)
    mock_chat.model_fields = _RealChatOllama.model_fields
    params: dict[str, Any] = {
        "provider": "ollama",
        "model": model,
        "temperature": 0.3,
        "max_tokens": 1000,
        "streaming": True,
        "llm_type": "response",
    }
    params.update(overrides)
    with _ollama_key(url):
        ProviderAdapter.create_llm(**params)
    return dict(mock_chat.call_args.kwargs)


@patch("src.infrastructure.llm.providers.ollama_chat.ChatOllamaTraced")
@patch("src.infrastructure.llm.providers.adapter.settings")
class TestOllamaNative:
    def test_the_native_client_is_used_not_the_openai_shim(
        self, mock_settings_module: MagicMock, mock_chat: MagicMock, mock_settings_class: object
    ) -> None:
        _apply_settings(mock_settings_module, mock_settings_class)
        with patch("src.infrastructure.llm.providers.adapter.init_chat_model") as init_chat:
            kwargs = _create_ollama(mock_chat)
        init_chat.assert_not_called()
        assert kwargs["model"] == _THINKING
        assert kwargs["base_url"] == _URL
        assert kwargs["num_predict"] == 1000
        assert kwargs["temperature"] == 0.3

    @pytest.mark.parametrize(
        "stored",
        [_URL, _URL + "/", _URL + "/v1", _URL + "/v1/"],
    )
    def test_every_url_shape_reaches_the_client_as_the_server_root(
        self,
        mock_settings_module: MagicMock,
        mock_chat: MagicMock,
        mock_settings_class: object,
        stored: str,
    ) -> None:
        """Operators typed the former ``/v1`` suffix; the native API lives at the root."""
        _apply_settings(mock_settings_module, mock_settings_class)
        assert _create_ollama(mock_chat, url=stored)["base_url"] == _URL

    @pytest.mark.parametrize(
        ("level", "expected"),
        [
            ("none", False),
            ("low", "low"),
            ("medium", "medium"),
            ("high", "high"),
            ("max", "max"),
            # Coerced onto Ollama's vocabulary by the seam (ties break upward).
            ("minimal", "low"),
            ("xhigh", "max"),
        ],
    )
    def test_the_stored_intent_reaches_a_thinking_model_as_think(
        self,
        mock_settings_module: MagicMock,
        mock_chat: MagicMock,
        mock_settings_class: object,
        level: str,
        expected: Any,
    ) -> None:
        _apply_settings(mock_settings_module, mock_settings_class)
        kwargs = _create_ollama(mock_chat, reasoning_effort=ReasoningIntent(level=level))  # type: ignore[arg-type]
        assert kwargs["reasoning"] == expected
        assert not any(isinstance(v, ReasoningIntent) for v in kwargs.values())

    def test_provider_default_on_a_thinking_model_makes_the_server_default_explicit(
        self, mock_settings_module: MagicMock, mock_chat: MagicMock, mock_settings_class: object
    ) -> None:
        """``reasoning=True`` is what lets langchain-ollama SEPARATE the trace
        (``reasoning_content``) instead of dropping it; the server would think anyway."""
        _apply_settings(mock_settings_module, mock_settings_class)
        assert _create_ollama(mock_chat)["reasoning"] is True
        kwargs = _create_ollama(mock_chat, reasoning_effort=ReasoningIntent())
        assert kwargs["reasoning"] is True

    @pytest.mark.parametrize("level", ["none", "medium", "high", "provider_default"])
    def test_a_model_that_cannot_think_never_receives_a_positive_level(
        self,
        mock_settings_module: MagicMock,
        mock_chat: MagicMock,
        mock_settings_class: object,
        level: str,
    ) -> None:
        """The server refuses ``think=<level>`` on a model without the capability
        (400) and accepts ``think=false`` on every model: the declared ladder
        ``("none",)`` coerces every depth to the switch-off, and nothing is
        made explicit when nothing was asked."""
        _apply_settings(mock_settings_module, mock_settings_class)
        kwargs = _create_ollama(
            mock_chat, model=_PLAIN, reasoning_effort=ReasoningIntent(level=level)  # type: ignore[arg-type]
        )
        if level == "provider_default":
            assert "reasoning" not in kwargs
        else:
            assert kwargs["reasoning"] is False

    def test_a_catalogue_row_alone_never_asserts_thinking(
        self, mock_settings_module: MagicMock, mock_chat: MagicMock, mock_settings_class: object
    ) -> None:
        """Only the SERVER's word justifies ``think=true``.

        The four static Ollama rows in the seed are guesses an admin can edit,
        and asserting thinking on a model without the capability is a 400 on
        every call. Absent the server's word LIA sends nothing.
        """
        _apply_settings(mock_settings_module, mock_settings_class)
        ModelCapabilitiesCache.reset()
        ModelCapabilitiesCache._cache = {
            _THINKING: ModelProfile(
                model_id=_THINKING, is_reasoning_model=True, capability_provenance="verified"
            )
        }
        ModelCapabilitiesCache._provider_by_model = {_THINKING: "ollama"}
        assert "reasoning" not in _create_ollama(mock_chat)

    def test_an_undiscovered_tag_sends_no_think_at_all(
        self, mock_settings_module: MagicMock, mock_chat: MagicMock, mock_settings_class: object
    ) -> None:
        """No declaration, no claim: the pre-ADR-267 behaviour, and never a 400."""
        _apply_settings(mock_settings_module, mock_settings_class)
        kwargs = _create_ollama(
            mock_chat, model="unknown-tag:latest", reasoning_effort=ReasoningIntent(level="high")
        )
        assert "reasoning" not in kwargs

    def test_a_legacy_stored_shape_goes_through_the_seam_too(
        self, mock_settings_module: MagicMock, mock_chat: MagicMock, mock_settings_class: object
    ) -> None:
        """An instance that has not run the ADR-245 migration still stores dicts."""
        _apply_settings(mock_settings_module, mock_settings_class)
        assert _create_ollama(mock_chat, reasoning_effort={"effort": "off"})["reasoning"] is False

    def test_num_ctx_is_the_number_the_discovery_published(
        self, mock_settings_module: MagicMock, mock_chat: MagicMock, mock_settings_class: object
    ) -> None:
        """What LIA accounts with (``max_input_tokens`` of the discovered profile,
        read by the compaction threshold) is what LIA requests."""
        _apply_settings(mock_settings_module, mock_settings_class)
        # The fixture's discovered profiles carry ModelProfile's default window.
        assert _create_ollama(mock_chat)["num_ctx"] == 8192
        kwargs = _create_ollama(mock_chat, provider_config=json.dumps({"num_ctx": 4096}))
        assert kwargs["num_ctx"] == 4096  # the escape hatch wins

    def test_an_undiscovered_tag_falls_back_to_the_setting_then_to_nothing(
        self, mock_settings_module: MagicMock, mock_chat: MagicMock, mock_settings_class: object
    ) -> None:
        _apply_settings(mock_settings_module, mock_settings_class)
        with patch("src.infrastructure.llm.providers.ollama_chat.logger") as log:
            assert _create_ollama(mock_chat, model="unknown-tag:latest")["num_ctx"] is None
        assert any(c.args[0] == "ollama_context_window_unknown" for c in log.warning.call_args_list)
        mock_settings_module.ollama_num_ctx = 16384
        assert _create_ollama(mock_chat, model="unknown-tag:latest")["num_ctx"] == 16384

    def test_the_slot_timeout_reaches_the_http_client(
        self, mock_settings_module: MagicMock, mock_chat: MagicMock, mock_settings_class: object
    ) -> None:
        """ADR-221: the per-slot transport timeout is the timeout the client applies."""
        _apply_settings(mock_settings_module, mock_settings_class)
        kwargs = _create_ollama(mock_chat, timeout_seconds=42.0)
        assert kwargs["client_kwargs"] == {"timeout": 42.0}
        kwargs = _create_ollama(
            mock_chat,
            timeout_seconds=42.0,
            provider_config=json.dumps({"client_kwargs": {"timeout": 5, "verify": False}}),
        )
        assert kwargs["client_kwargs"] == {"timeout": 5, "verify": False}

    def test_penalties_the_client_cannot_express_are_dropped(
        self, mock_settings_module: MagicMock, mock_chat: MagicMock, mock_settings_class: object
    ) -> None:
        _apply_settings(mock_settings_module, mock_settings_class)
        kwargs = _create_ollama(mock_chat, top_p=0.9, frequency_penalty=0.5, presence_penalty=0.2)
        assert kwargs["top_p"] == 0.9
        assert "frequency_penalty" not in kwargs
        assert "presence_penalty" not in kwargs

    def test_escape_hatch_keys_the_client_defines_pass_and_others_are_reported(
        self, mock_settings_module: MagicMock, mock_chat: MagicMock, mock_settings_class: object
    ) -> None:
        """``ChatOllama`` ignores unknown fields in silence; the adapter does not."""
        _apply_settings(mock_settings_module, mock_settings_class)
        with patch("src.infrastructure.llm.providers.ollama_chat.logger") as log:
            kwargs = _create_ollama(
                mock_chat,
                provider_config=json.dumps(
                    {"keep_alive": "10m", "top_k": 40, "num_predcit": 5, "stream_usage": True}
                ),
            )
        assert kwargs["keep_alive"] == "10m"
        assert kwargs["top_k"] == 40
        assert "num_predcit" not in kwargs
        assert "stream_usage" not in kwargs
        reported = [
            c
            for c in log.warning.call_args_list
            if c.args[0] == "ollama_provider_config_keys_ignored"
        ]
        assert reported and reported[0].kwargs["keys"] == ["num_predcit", "stream_usage"]

    def test_the_credential_placeholder_stays_searchable(
        self, mock_settings_module: MagicMock, mock_chat: MagicMock, mock_settings_class: object
    ) -> None:
        """No URL anywhere: the failure names ``NOT_CONFIGURED``, not a mangled URL."""
        _apply_settings(mock_settings_module, mock_settings_class)
        env = {k: v for k, v in os.environ.items() if k != OLLAMA_BASE_URL_ENV}
        with patch.dict(os.environ, env, clear=True):
            kwargs = _create_ollama(mock_chat, url=None)
        assert kwargs["base_url"] == "NOT_CONFIGURED"


@patch("src.infrastructure.llm.providers.adapter.init_chat_model")
@patch("src.infrastructure.llm.providers.adapter.settings")
class TestPerplexity:
    @pytest.mark.parametrize(
        ("model", "level", "expected"),
        [
            ("sonar-pro", "none", None),  # no reasoning family: nothing is sent
            ("sonar-pro", "medium", None),
            ("sonar-reasoning", "low", "low"),
            ("sonar-reasoning", "high", "high"),
            # ``none`` is not on the sonar-reasoning ladder and the tier has no
            # off switch: the runtime coerces upward to the nearest level.
            ("sonar-reasoning", "none", "low"),
            ("sonar-deep-research", "provider_default", None),
        ],
    )
    def test_the_stored_intent_goes_through_the_seam(
        self,
        mock_settings_module: MagicMock,
        mock_init: MagicMock,
        mock_settings_class: object,
        model: str,
        level: str,
        expected: str | None,
    ) -> None:
        _apply_settings(mock_settings_module, mock_settings_class)
        mock_init.return_value = MagicMock(spec=BaseChatModel)

        ProviderAdapter.create_llm(
            provider="perplexity",
            model=model,
            temperature=0.3,
            max_tokens=1000,
            streaming=False,
            llm_type="perplexity_agent",
            reasoning_effort=ReasoningIntent(level=level),  # type: ignore[arg-type]
        )

        kwargs = mock_init.call_args.kwargs
        assert kwargs.get("reasoning_effort") == expected
        assert not any(isinstance(v, ReasoningIntent) for v in kwargs.values())
        # End-user key: still excluded from usage accounting (ADR-220).
        assert "stream_usage" not in kwargs
