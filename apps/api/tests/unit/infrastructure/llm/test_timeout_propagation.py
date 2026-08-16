"""The admin-visible timeout is the timeout the client applies (ADR-221, ex-F2).

``timeout_seconds`` existed end to end — admin dialog, API validation,
``llm_config_overrides`` column, ``LLMAgentConfig`` resolution, 57 defaults —
and then NOTHING read it: neither the factory nor the adapter passed it to any
client. The value the operator could edit was not the value the system
applied; the applied ones (a subset of ``asyncio.wait_for`` sites fed by env
vars) were invisible in the UI. Mirror image of the ADR-184 doctrine: a value
the producer can write but the system does not apply is a trap.

Contract (ADR-221):
- the resolved ``timeout_seconds`` reaches every provider client as its
  per-attempt transport timeout (the ``timeout`` alias is accepted by all
  four installed SDKs — verified: openai, anthropic, gemini, deepseek);
- the existing ``asyncio.wait_for`` barriers are UNCHANGED: they remain the
  user-experience bound on graph nodes and may be tighter (the chat response
  barrier stays at 60s while the client default protects the same slot's
  barrier-less callers, e.g. the reminder notification);
- defaults raised where 30 days of production latency said the old value
  would cut calls that succeed today (p99 measured 2026-08-16);
- ``router_llm_timeout_seconds`` is gone: defined for years, read nowhere —
  the router node makes no direct LLM call (QueryAnalyzer does the work).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from langchain_core.language_models.chat_models import BaseChatModel

from src.domains.llm_config.constants import LLM_DEFAULTS
from src.infrastructure.llm.factory import get_llm
from src.infrastructure.llm.providers.adapter import ProviderAdapter

try:
    import langchain_deepseek  # noqa: F401

    HAS_DEEPSEEK = True
except ImportError:  # pragma: no cover - optional dependency
    HAS_DEEPSEEK = False


def _apply_settings(mock_settings_module: MagicMock, mock_settings_class: object) -> None:
    for attr in dir(mock_settings_class):
        if not attr.startswith("_"):
            setattr(mock_settings_module, attr, getattr(mock_settings_class, attr))


class TestFactoryPropagatesTimeout:
    @patch("src.infrastructure.llm.factory.ProviderAdapter")
    def test_resolved_timeout_reaches_the_adapter(self, mock_adapter: MagicMock) -> None:
        mock_adapter.create_llm.return_value = MagicMock(spec=BaseChatModel)

        get_llm("response")

        kwargs = mock_adapter.create_llm.call_args.kwargs
        assert kwargs["timeout_seconds"] == LLM_DEFAULTS["response"].timeout_seconds


@patch("src.infrastructure.llm.providers.adapter.init_chat_model")
@patch("src.infrastructure.llm.providers.adapter.settings")
class TestAdapterAppliesTimeout:
    @pytest.mark.parametrize(
        ("provider", "model"),
        [
            ("openai", "gpt-4-turbo"),
            ("anthropic", "claude-sonnet-4-5"),
            ("qwen", "qwen3.5-plus"),
            ("perplexity", "sonar-pro"),
            ("ollama", "llama3.1"),
            ("gemini", "gemini-2.5-flash"),
        ],
    )
    def test_timeout_reaches_every_client(
        self,
        mock_settings_module: MagicMock,
        mock_init: MagicMock,
        mock_settings_class: object,
        provider: str,
        model: str,
    ) -> None:
        _apply_settings(mock_settings_module, mock_settings_class)
        mock_init.return_value = MagicMock(spec=BaseChatModel)

        with patch(
            "src.infrastructure.llm.providers.adapter.ProviderAdapter._create_gemini_llm"
        ) as mock_gemini:
            mock_gemini.return_value = MagicMock(spec=BaseChatModel)
            ProviderAdapter.create_llm(
                provider=provider,  # type: ignore[arg-type]
                model=model,
                temperature=0.7,
                max_tokens=1000,
                streaming=False,
                llm_type="planner",
                timeout_seconds=45.0,
            )
            target = mock_gemini if provider == "gemini" else mock_init

        assert target.call_args.kwargs["timeout"] == 45.0

    def test_absent_timeout_sets_nothing(
        self,
        mock_settings_module: MagicMock,
        mock_init: MagicMock,
        mock_settings_class: object,
    ) -> None:
        """No configured value → the SDK default applies, no stray kwarg."""
        _apply_settings(mock_settings_module, mock_settings_class)
        mock_init.return_value = MagicMock(spec=BaseChatModel)

        ProviderAdapter.create_llm(
            provider="openai",
            model="gpt-4-turbo",
            temperature=0.7,
            max_tokens=1000,
            streaming=False,
            llm_type="planner",
        )

        assert "timeout" not in mock_init.call_args.kwargs


@pytest.mark.skipif(not HAS_DEEPSEEK, reason="langchain-deepseek not installed")
@patch("src.infrastructure.llm.providers._deepseek_patched.ChatDeepSeekPatched")
@patch("src.infrastructure.llm.providers.adapter.settings")
def test_timeout_reaches_deepseek(
    mock_settings_module: MagicMock,
    mock_chat_deepseek: MagicMock,
    mock_settings_class: object,
) -> None:
    _apply_settings(mock_settings_module, mock_settings_class)
    mock_chat_deepseek.return_value = MagicMock(spec=BaseChatModel)

    ProviderAdapter.create_llm(
        provider="deepseek",
        model="deepseek-v4-flash",
        temperature=0.5,
        max_tokens=4000,
        streaming=True,
        llm_type="response",
        timeout_seconds=120.0,
    )

    assert mock_chat_deepseek.call_args.kwargs["timeout"] == 120.0


class TestDefaultsHoldAgainstProduction:
    """Defaults vs 30 days of production p99 (measured 2026-08-16).

    Applying a client timeout below the observed tail would cut calls that
    succeed today — the exact A2.R regression class. Each raised value is
    pinned WITH its measurement so the next reader knows what it protects.
    """

    @pytest.mark.parametrize(
        ("llm_type", "minimum", "p99_measured"),
        [
            ("response", 120.0, 47.4),
            ("planner", 90.0, 44.7),
            ("heartbeat_decision", 120.0, 59.7),  # + 2 calls beyond 60s in 30d
            ("interest_content", 120.0, 60.0),  # + 1 call beyond 60s in 30d
            ("open_loop_extraction", 90.0, 35.1),
            ("memory_reference_extraction", 45.0, 15.3),
        ],
    )
    def test_raised_defaults(self, llm_type: str, minimum: float, p99_measured: float) -> None:
        default = LLM_DEFAULTS[llm_type].timeout_seconds
        assert default is not None and default >= minimum
        assert default >= 2 * p99_measured * 0.9  # ~2× the measured tail

    def test_every_slot_declares_a_timeout(self) -> None:
        missing = [t for t, cfg in LLM_DEFAULTS.items() if cfg.timeout_seconds is None]
        assert missing == [], f"slots without a client timeout: {missing}"


class TestDeadSettingRemoved:
    def test_router_llm_timeout_seconds_is_gone(self) -> None:
        from src.core.config import settings

        assert not hasattr(settings, "router_llm_timeout_seconds")

    def test_response_barrier_still_exists(self) -> None:
        """The wait_for barrier keeps its setting — ADR-221 leaves it in place."""
        from src.core.config import settings

        assert settings.response_llm_timeout_seconds > 0
