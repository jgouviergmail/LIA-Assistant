"""Usage-accounting contract for streamed LLM calls (ADR-220, ex-F1).

An OpenAI-compatible provider only emits the ``usage`` object on a streamed
response when the request asks for it. LIA asked for it on two provider
branches (openai, qwen) and forgot the third (deepseek) — the exact branch the
reference seed puts the three streamed slots on. Production kept accounting
only because DeepSeek currently sends usage unrequested; nothing in the repo
guarded that generosity (zero tests mentioned ``stream_usage`` or
``stream_options`` before this file).

What must hold:
- every chat provider declared ``stream_usage_flag`` in
  ``PROVIDER_USAGE_CAPABILITIES`` actually receives ``stream_usage=True`` from
  the adapter — the registry is behavior, not documentation;
- the one ``excluded`` provider (perplexity: end-user key) deliberately does
  NOT request usage — a later "completion" of the list would bill LIA for
  spend it does not carry. Ollama LEFT this group on 2026-09-05 (ADR-220
  amendment, ADR-267 -- native client, usage on every response): it runs locally at 0 EUR, but a streamed call whose usage is
  never asked for raises ``LLMCallsWithoutUsage`` on every turn, for a spend
  that does exist and is simply free;
- the registry covers every chat provider (ADR-085 boot assert);
- the langchain contracts this relies on stay true on the installed packages:
  ``stream_usage=True`` drives ``_should_stream_usage`` (applied only to
  streamed requests, so DashScope's rejection of ``stream_options`` on
  ``stream=false`` cannot recur), and the auto-enable stays OFF whenever a
  ``base_url`` is set (the condition that made the omission silent).
"""

from __future__ import annotations

from typing import get_args
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.language_models.chat_models import BaseChatModel

from src.domains.llm_config.constants import PROVIDER_USAGE_CAPABILITIES
from src.infrastructure.llm.providers.adapter import ProviderAdapter, ProviderType

try:
    import langchain_deepseek  # noqa: F401

    HAS_DEEPSEEK = True
except ImportError:  # pragma: no cover - optional dependency
    HAS_DEEPSEEK = False

skip_if_no_deepseek = pytest.mark.skipif(
    not HAS_DEEPSEEK, reason="langchain-deepseek not installed (optional dependency)"
)


def _apply_settings(mock_settings_module: MagicMock, mock_settings_class: object) -> None:
    """Mirror the conftest settings object onto the patched adapter settings."""
    for attr in dir(mock_settings_class):
        if not attr.startswith("_"):
            setattr(mock_settings_module, attr, getattr(mock_settings_class, attr))


# ============================================================================
# Registry completeness (ADR-085: the declaration cannot drift from the code)
# ============================================================================


class TestProviderUsageCapabilitiesRegistry:
    def test_every_chat_provider_is_declared(self) -> None:
        """A chat provider without a usage-accounting declaration must not exist."""
        assert set(PROVIDER_USAGE_CAPABILITIES) == set(get_args(ProviderType))

    def test_values_are_bounded(self) -> None:
        assert set(PROVIDER_USAGE_CAPABILITIES.values()) <= {
            "stream_usage_flag",
            "native",
            "excluded",
        }

    def test_boot_validation_passes_on_current_registry(self) -> None:
        from src.core.bootstrap import validate_provider_usage_capabilities

        validate_provider_usage_capabilities()

    def test_boot_validation_fails_on_missing_provider(self) -> None:
        from src.core import bootstrap

        with patch.dict(PROVIDER_USAGE_CAPABILITIES, clear=False) as patched:
            del patched["deepseek"]
            with pytest.raises(RuntimeError, match="deepseek"):
                bootstrap.validate_provider_usage_capabilities()


# ============================================================================
# Adapter behavior: the declaration IS what the adapter does
# ============================================================================


@patch("src.infrastructure.llm.providers.adapter.init_chat_model")
@patch("src.infrastructure.llm.providers.adapter.settings")
class TestAdapterRequestsUsage:
    def _create(self, provider: str, model: str, mock_init: MagicMock) -> MagicMock:
        mock_llm = MagicMock(spec=BaseChatModel)
        mock_init.return_value = mock_llm
        ProviderAdapter.create_llm(
            provider=provider,  # type: ignore[arg-type]
            model=model,
            temperature=0.7,
            max_tokens=1000,
            streaming=True,
            llm_type="response",
        )
        return mock_init

    @pytest.mark.parametrize(
        ("provider", "model"),
        [("openai", "gpt-4-turbo"), ("qwen", "qwen3.5-plus")],
    )
    def test_stream_usage_flag_providers_request_usage(
        self,
        mock_settings_module: MagicMock,
        mock_init: MagicMock,
        mock_settings_class: object,
        provider: str,
        model: str,
    ) -> None:
        _apply_settings(mock_settings_module, mock_settings_class)
        mock_init = self._create(provider, model, mock_init)
        kwargs = mock_init.call_args.kwargs

        assert kwargs["stream_usage"] is True
        # The old shape injected stream_options into EVERY request via
        # model_kwargs — including non-streamed ones, which DashScope rejects.
        # stream_usage is applied per-request by _should_stream_usage, only
        # when streaming, so model_kwargs must stay clean.
        assert "stream_options" not in kwargs.get("model_kwargs", {})

    @pytest.mark.parametrize(
        ("provider", "model"),
        [("perplexity", "sonar-pro")],
    )
    def test_excluded_providers_do_not_request_usage(
        self,
        mock_settings_module: MagicMock,
        mock_init: MagicMock,
        mock_settings_class: object,
        provider: str,
        model: str,
    ) -> None:
        """perplexity (end-user key) stays excluded."""
        _apply_settings(mock_settings_module, mock_settings_class)
        mock_init = self._create(provider, model, mock_init)
        kwargs = mock_init.call_args.kwargs

        assert "stream_usage" not in kwargs
        assert "stream_options" not in kwargs.get("model_kwargs", {})

    def test_declaration_matches_adapter_for_openai_compatible_providers(
        self,
        mock_settings_module: MagicMock,
        mock_init: MagicMock,
        mock_settings_class: object,
    ) -> None:
        """The registry row and the emitted kwargs agree, provider by provider."""
        _apply_settings(mock_settings_module, mock_settings_class)
        models = {
            "openai": "gpt-4-turbo",
            "qwen": "qwen3.5-plus",
            "perplexity": "sonar-pro",
        }
        for provider, model in models.items():
            mock_init.reset_mock()
            self._create(provider, model, mock_init)
            requested = mock_init.call_args.kwargs.get("stream_usage") is True
            declared = PROVIDER_USAGE_CAPABILITIES[provider] == "stream_usage_flag"
            assert requested == declared, provider


@skip_if_no_deepseek
@patch("src.infrastructure.llm.providers._deepseek_patched.ChatDeepSeekPatched")
@patch("src.infrastructure.llm.providers.adapter.settings")
def test_provider_config_escape_hatch_wins_over_the_default(
    mock_settings_module: MagicMock,
    mock_chat_deepseek: MagicMock,
    mock_settings_class: object,
) -> None:
    """An explicit ``stream_usage`` in provider_config overrides the default.

    Same precedence rule as ``timeout`` (ADR-221): the advanced JSON escape
    hatch wins over the resolved slot value. Before this pin, a
    ``{"stream_usage": ...}`` in provider_config CRASHED the deepseek branch
    (TypeError: multiple values for keyword 'stream_usage') and was silently
    overwritten on the qwen/openai branches.
    """
    import json

    _apply_settings(mock_settings_module, mock_settings_class)
    mock_chat_deepseek.return_value = MagicMock(spec=BaseChatModel)

    ProviderAdapter.create_llm(
        provider="deepseek",
        model="deepseek-v4-flash",
        temperature=0.5,
        max_tokens=4000,
        streaming=True,
        llm_type="response",
        provider_config=json.dumps({"stream_usage": False}),
    )

    assert mock_chat_deepseek.call_args.kwargs["stream_usage"] is False


@skip_if_no_deepseek
@patch("src.infrastructure.llm.providers._deepseek_patched.ChatDeepSeekPatched")
@patch("src.infrastructure.llm.providers.adapter.settings")
def test_deepseek_requests_usage(
    mock_settings_module: MagicMock,
    mock_chat_deepseek: MagicMock,
    mock_settings_class: object,
) -> None:
    """The branch F1 identified as missing now requests usage explicitly."""
    _apply_settings(mock_settings_module, mock_settings_class)
    mock_chat_deepseek.return_value = MagicMock(spec=BaseChatModel)

    for model, streaming in (("deepseek-v4-flash", True), ("deepseek-chat", False)):
        mock_chat_deepseek.reset_mock()
        ProviderAdapter.create_llm(
            provider="deepseek",
            model=model,
            temperature=0.5,
            max_tokens=4000,
            streaming=streaming,
            llm_type="response",
        )
        # Unconditional on purpose: _should_stream_usage only applies it to
        # streamed requests, so non-streamed calls are unaffected — and a slot
        # LangGraph force-streams internally still gets its usage counted.
        assert mock_chat_deepseek.call_args.kwargs["stream_usage"] is True


# ============================================================================
# langchain contracts on the INSTALLED packages (what made F1 silent)
# ============================================================================


class TestLangchainStreamUsageContract:
    def test_stream_usage_true_drives_should_stream_usage(self) -> None:
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(
            model="gpt-4-turbo",
            api_key="test-key",
            base_url="https://example.invalid/v1",
            stream_usage=True,
        )
        assert llm._should_stream_usage() is True
        # Not injected into every request body: model_kwargs stays clean, the
        # flag is added by _stream/_astream only (DashScope stream=false safe).
        assert "stream_options" not in llm.model_kwargs

    def test_auto_enable_stays_off_with_explicit_base_url(self) -> None:
        """The condition that made F1 silent, pinned on the installed package.

        langchain-openai only auto-enables stream_usage when NO base_url /
        client override is set. LIA always sets base_url, so an adapter branch
        that forgets the flag gets no fallback — this is why the omission
        shipped. If langchain ever changes this, the pin tells us.
        """
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(
            model="gpt-4-turbo",
            api_key="test-key",
            base_url="https://example.invalid/v1",
        )
        assert llm._should_stream_usage() is False

    @skip_if_no_deepseek
    def test_chat_deepseek_honors_stream_usage(self) -> None:
        from src.infrastructure.llm.providers._deepseek_patched import ChatDeepSeekPatched

        llm = ChatDeepSeekPatched(
            model="deepseek-v4-flash",
            api_key="test-key",
            api_base="https://api.deepseek.com",
            stream_usage=True,
        )
        assert llm._should_stream_usage() is True
