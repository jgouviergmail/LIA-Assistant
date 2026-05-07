"""Unit tests for ChatDeepSeekPatched — reasoning_content round-trip.

Validates that our local subclass injects ``reasoning_content`` from
``AIMessage.additional_kwargs`` back into the request payload's assistant
messages, satisfying the DeepSeek V4 API requirement on multi-turn flows
with tool calls.

See ``_deepseek_patched.py`` for the rationale (issue #37178, PR #37179).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from src.infrastructure.llm.providers._deepseek_patched import ChatDeepSeekPatched


@pytest.mark.unit
class TestChatDeepSeekPatchedRoundTrip:
    """``_get_request_payload`` must echo prior ``reasoning_content`` back."""

    def _make_llm(self) -> ChatDeepSeekPatched:
        # The underlying ``openai.OpenAI`` client always requires a non-empty
        # api_key at construction time, even when api_base is overridden.
        return ChatDeepSeekPatched(
            model="deepseek-v4-flash",
            api_base="https://example.invalid/v1",
            api_key="sk-test",
        )

    def test_reasoning_content_injected_when_present(self) -> None:
        llm = self._make_llm()
        messages = [
            HumanMessage(content="What's the weather?"),
            AIMessage(
                content="It is sunny.",
                additional_kwargs={"reasoning_content": "User asked weather → call tool."},
            ),
            HumanMessage(content="And tomorrow?"),
        ]

        payload = llm._get_request_payload(messages)

        assistant_msgs = [m for m in payload["messages"] if m["role"] == "assistant"]
        assert len(assistant_msgs) == 1
        assert assistant_msgs[0]["reasoning_content"] == "User asked weather → call tool."

    def test_no_injection_when_additional_kwargs_empty(self) -> None:
        """Backward-compat: V3 deepseek-chat without thinking adds nothing."""
        llm = self._make_llm()
        messages = [
            HumanMessage(content="hi"),
            AIMessage(content="hello"),  # no additional_kwargs
        ]

        payload = llm._get_request_payload(messages)

        assistant_msgs = [m for m in payload["messages"] if m["role"] == "assistant"]
        assert len(assistant_msgs) == 1
        assert "reasoning_content" not in assistant_msgs[0]

    def test_no_injection_when_reasoning_content_is_none(self) -> None:
        """``additional_kwargs`` with explicit None must not produce a key."""
        llm = self._make_llm()
        messages = [
            AIMessage(content="prior", additional_kwargs={"reasoning_content": None}),
        ]

        payload = llm._get_request_payload(messages)
        assistant_msgs = [m for m in payload["messages"] if m["role"] == "assistant"]
        assert "reasoning_content" not in assistant_msgs[0]

    def test_multiple_ai_messages_aligned_in_order(self) -> None:
        """Each AIMessage maps to its corresponding payload assistant message."""
        llm = self._make_llm()
        messages = [
            SystemMessage(content="You are helpful."),
            HumanMessage(content="Q1"),
            AIMessage(
                content="A1",
                additional_kwargs={"reasoning_content": "thought-1"},
            ),
            HumanMessage(content="Q2"),
            AIMessage(
                content="A2",
                additional_kwargs={"reasoning_content": "thought-2"},
            ),
            HumanMessage(content="Q3"),
        ]

        payload = llm._get_request_payload(messages)

        assistant_msgs = [m for m in payload["messages"] if m["role"] == "assistant"]
        assert [m["reasoning_content"] for m in assistant_msgs] == ["thought-1", "thought-2"]

    def test_partial_reasoning_content_only_injected_when_present(self) -> None:
        """A mix of reasoning / no-reasoning AI messages keeps alignment."""
        llm = self._make_llm()
        messages = [
            HumanMessage(content="Q1"),
            AIMessage(content="A1"),  # no reasoning_content
            HumanMessage(content="Q2"),
            AIMessage(
                content="A2",
                additional_kwargs={"reasoning_content": "thought-2"},
            ),
        ]

        payload = llm._get_request_payload(messages)

        assistant_msgs = [m for m in payload["messages"] if m["role"] == "assistant"]
        assert "reasoning_content" not in assistant_msgs[0]
        assert assistant_msgs[1]["reasoning_content"] == "thought-2"

    def test_tool_messages_do_not_shift_alignment(self) -> None:
        """ToolMessage between AI turns must not break the AI-message indexing."""
        llm = self._make_llm()
        messages = [
            HumanMessage(content="What's the weather in Paris?"),
            AIMessage(
                content="",
                additional_kwargs={"reasoning_content": "Need to call get_weather."},
                tool_calls=[
                    {
                        "name": "get_weather",
                        "args": {"city": "Paris"},
                        "id": "call_1",
                        "type": "tool_call",
                    }
                ],
            ),
            ToolMessage(content="sunny, 20C", tool_call_id="call_1"),
            AIMessage(
                content="It's sunny in Paris, 20°C.",
                additional_kwargs={"reasoning_content": "Got result, format reply."},
            ),
        ]

        payload = llm._get_request_payload(messages)

        assistant_msgs = [m for m in payload["messages"] if m["role"] == "assistant"]
        assert len(assistant_msgs) == 2
        assert assistant_msgs[0]["reasoning_content"] == "Need to call get_weather."
        assert assistant_msgs[1]["reasoning_content"] == "Got result, format reply."

    def test_parent_payload_unchanged_for_non_assistant_messages(self) -> None:
        """The patch must not mutate user/system/tool messages."""
        llm = self._make_llm()
        messages = [
            SystemMessage(content="sys"),
            HumanMessage(content="hi"),
            AIMessage(
                content="bye",
                additional_kwargs={"reasoning_content": "thought"},
            ),
        ]

        payload = llm._get_request_payload(messages)

        # Only assistant messages should ever carry reasoning_content
        for m in payload["messages"]:
            if m["role"] != "assistant":
                assert "reasoning_content" not in m


@pytest.mark.unit
class TestChatDeepSeekPatchedIntegrationWithAdapter:
    """Smoke check: the adapter wires ChatDeepSeekPatched, not bare ChatDeepSeek."""

    def test_create_deepseek_llm_uses_patched_subclass(self) -> None:
        from src.infrastructure.llm.providers.adapter import ProviderAdapter

        with patch(
            "src.infrastructure.llm.providers.adapter._require_api_key",
            return_value="sk-test",
        ):
            llm = ProviderAdapter._create_deepseek_llm(
                model="deepseek-v4-flash",
                temperature=0.5,
                max_tokens=4096,
                streaming=False,
            )

        assert isinstance(llm, ChatDeepSeekPatched)

    def test_v4_thinking_disabled_when_reasoning_effort_off(self) -> None:
        """reasoning_effort={"effort":"off"} → extra_body.thinking.type=disabled.

        Updated 2026-05-06: the legacy 6-level UI scale (none/minimal/low/medium/
        high/xhigh) was replaced by the 3-value enum (off/high/max) per the
        philosophy A "raw truth" decision. The DeepSeek adapter delegates to
        ``build_deepseek_v4_reasoning`` which produces the correct API shape.
        """
        from src.core.reasoning_types import ReasoningEffortEnum
        from src.infrastructure.llm.providers.adapter import ProviderAdapter

        with patch(
            "src.infrastructure.llm.providers.adapter._require_api_key",
            return_value="sk-test",
        ):
            llm = ProviderAdapter._create_deepseek_llm(
                model="deepseek-v4-pro",
                temperature=0.5,
                max_tokens=4096,
                streaming=False,
                reasoning_effort=ReasoningEffortEnum(effort="off"),
            )

        assert llm.extra_body == {"thinking": {"type": "disabled"}}

    def test_v4_thinking_enabled_high(self) -> None:
        """reasoning_effort={"effort":"high"} → thinking enabled + top-level effort=high.

        Per the DeepSeek V4 API spec, ``reasoning_effort`` is a TOP-LEVEL
        request field (sibling of ``messages`` / ``model``), NOT nested in
        ``extra_body``. ``extra_body`` only carries ``thinking={type:...}``.
        The legacy adapter erroneously merged both into ``extra_body``.
        """
        from src.core.reasoning_types import ReasoningEffortEnum
        from src.infrastructure.llm.providers.adapter import ProviderAdapter

        with patch(
            "src.infrastructure.llm.providers.adapter._require_api_key",
            return_value="sk-test",
        ):
            llm = ProviderAdapter._create_deepseek_llm(
                model="deepseek-v4-flash",
                temperature=0.5,
                max_tokens=4096,
                streaming=False,
                reasoning_effort=ReasoningEffortEnum(effort="high"),
            )

        # extra_body now only carries the thinking toggle.
        assert llm.extra_body == {"thinking": {"type": "enabled"}}
        # reasoning_effort lives at the top-level kwargs of the LLM client.
        assert getattr(llm, "reasoning_effort", None) == "high"

    def test_v4_thinking_enabled_max(self) -> None:
        """reasoning_effort={"effort":"max"} → thinking enabled + top-level effort=max."""
        from src.core.reasoning_types import ReasoningEffortEnum
        from src.infrastructure.llm.providers.adapter import ProviderAdapter

        with patch(
            "src.infrastructure.llm.providers.adapter._require_api_key",
            return_value="sk-test",
        ):
            llm = ProviderAdapter._create_deepseek_llm(
                model="deepseek-v4-pro",
                temperature=0.5,
                max_tokens=4096,
                streaming=False,
                reasoning_effort=ReasoningEffortEnum(effort="max"),
            )

        assert llm.extra_body == {"thinking": {"type": "enabled"}}
        assert getattr(llm, "reasoning_effort", None) == "max"

    def test_v3_legacy_models_unaffected_by_v4_logic(self) -> None:
        """deepseek-chat/deepseek-reasoner: no extra_body injection."""
        from src.infrastructure.llm.providers.adapter import ProviderAdapter

        with patch(
            "src.infrastructure.llm.providers.adapter._require_api_key",
            return_value="sk-test",
        ):
            llm = ProviderAdapter._create_deepseek_llm(
                model="deepseek-chat",
                temperature=0.5,
                max_tokens=4096,
                streaming=False,
                reasoning_effort="medium",  # ignored for V3
            )

        # V3 deepseek-chat: extra_body should be empty (no thinking-mode injection)
        # Pydantic default for unset extra_body is {} on BaseChatOpenAI
        assert llm.extra_body in (None, {})


@pytest.mark.unit
class TestIsV4ThinkingEnabledDetection:
    """``_is_v4_thinking_enabled`` correctly classifies V3/V4 + thinking states."""

    def _make_llm(self, model: str, extra_body: dict | None = None) -> ChatDeepSeekPatched:
        kwargs: dict = {
            "model": model,
            "api_base": "https://example.invalid/v1",
            "api_key": "sk-test",
        }
        if extra_body is not None:
            kwargs["extra_body"] = extra_body
        return ChatDeepSeekPatched(**kwargs)

    def test_v4_default_no_extra_body_treated_as_thinking_on(self) -> None:
        """V4 default API state is thinking enabled — be safe and assume ON."""
        from src.infrastructure.llm.structured_output import _is_v4_thinking_enabled

        llm = self._make_llm("deepseek-v4-flash")
        assert _is_v4_thinking_enabled(llm) is True

    def test_v4_thinking_explicitly_enabled(self) -> None:
        from src.infrastructure.llm.structured_output import _is_v4_thinking_enabled

        llm = self._make_llm(
            "deepseek-v4-pro",
            extra_body={"thinking": {"type": "enabled"}, "reasoning_effort": "high"},
        )
        assert _is_v4_thinking_enabled(llm) is True

    def test_v4_thinking_explicitly_disabled(self) -> None:
        from src.infrastructure.llm.structured_output import _is_v4_thinking_enabled

        llm = self._make_llm(
            "deepseek-v4-flash",
            extra_body={"thinking": {"type": "disabled"}},
        )
        assert _is_v4_thinking_enabled(llm) is False

    def test_v3_chat_never_v4_thinking(self) -> None:
        from src.infrastructure.llm.structured_output import _is_v4_thinking_enabled

        llm = self._make_llm("deepseek-chat")
        assert _is_v4_thinking_enabled(llm) is False

    def test_v3_reasoner_never_v4_thinking(self) -> None:
        """V3 R1 has its own reasoning, but does NOT match the V4 thinking path."""
        from src.infrastructure.llm.structured_output import _is_v4_thinking_enabled

        llm = self._make_llm("deepseek-reasoner")
        assert _is_v4_thinking_enabled(llm) is False

    def test_non_deepseek_llm_returns_false(self) -> None:
        """Helper must not crash on arbitrary BaseChatModel — returns False."""
        from src.infrastructure.llm.structured_output import _is_v4_thinking_enabled

        class _DummyLLM:
            model_name = "gpt-4.1-mini"
            extra_body = None

        assert _is_v4_thinking_enabled(_DummyLLM()) is False  # type: ignore[arg-type]


@pytest.mark.unit
class TestGetBaseUrl:
    """``_get_base_url`` correctly resolves env var with default fallback."""

    def test_perplexity_default_when_env_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.infrastructure.llm.providers.adapter import _get_base_url

        monkeypatch.delenv("PERPLEXITY_BASE_URL", raising=False)
        assert _get_base_url("perplexity") == "https://api.perplexity.ai"

    def test_qwen_default_when_env_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.infrastructure.llm.providers.adapter import _get_base_url

        monkeypatch.delenv("QWEN_BASE_URL", raising=False)
        assert _get_base_url("qwen") == "https://dashscope-us.aliyuncs.com/compatible-mode/v1"

    def test_perplexity_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.infrastructure.llm.providers.adapter import _get_base_url

        monkeypatch.setenv("PERPLEXITY_BASE_URL", "https://api.perplexity.eu/v1")
        assert _get_base_url("perplexity") == "https://api.perplexity.eu/v1"

    def test_qwen_env_override_to_china_region(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.infrastructure.llm.providers.adapter import _get_base_url

        cn_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
        monkeypatch.setenv("QWEN_BASE_URL", cn_url)
        assert _get_base_url("qwen") == cn_url

    def test_empty_env_value_falls_back_to_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """An empty string in env should be treated as unset (fall back to default)."""
        from src.infrastructure.llm.providers.adapter import _get_base_url

        monkeypatch.setenv("PERPLEXITY_BASE_URL", "")
        assert _get_base_url("perplexity") == "https://api.perplexity.ai"

    def test_whitespace_only_env_value_falls_back_to_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Whitespace-only env value (a common copy-paste mistake) falls back."""
        from src.infrastructure.llm.providers.adapter import _get_base_url

        monkeypatch.setenv("QWEN_BASE_URL", "   ")
        assert _get_base_url("qwen") == "https://dashscope-us.aliyuncs.com/compatible-mode/v1"

    def test_unknown_provider_raises_value_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A provider with no registered default must raise — fail-loud, not silent."""
        from src.infrastructure.llm.providers.adapter import _get_base_url

        monkeypatch.delenv("UNKNOWN_BASE_URL", raising=False)
        with pytest.raises(ValueError, match="No default base_url registered"):
            _get_base_url("unknown")
