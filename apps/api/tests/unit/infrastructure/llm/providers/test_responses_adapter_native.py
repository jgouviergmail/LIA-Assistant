"""Unit tests for the native Responses-API adapter (post-ResponsesLLM migration).

Covers the surface that survived the migration to native ``ChatOpenAI``:
- ``is_responses_api_eligible`` model gating;
- ``_extract_static_prefix`` (dynamic-marker cutoff);
- ``compute_prompt_cache_key`` (stable, prefix-driven, system-only);
- ``create_responses_llm`` builds a ``ChatOpenAICached`` configured for the
  Responses API (+ reasoning summary when an effort is set).
No network / no LLM call.
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from src.infrastructure.llm.providers.responses_adapter import (
    ChatOpenAICached,
    _extract_static_prefix,
    compute_prompt_cache_key,
    create_responses_llm,
    is_responses_api_eligible,
)


class TestEligibility:
    def test_eligible_models(self) -> None:
        assert is_responses_api_eligible("gpt-5-mini")
        assert is_responses_api_eligible("gpt-4.1")
        assert is_responses_api_eligible("o3-mini")

    def test_ineligible_legacy_models(self) -> None:
        assert not is_responses_api_eligible("gpt-4o")
        assert not is_responses_api_eligible("gpt-4-turbo")
        assert not is_responses_api_eligible("gpt-3.5-turbo")


class TestStaticPrefix:
    def test_cuts_at_dynamic_marker(self) -> None:
        from src.core.constants import DYNAMIC_CONTEXT_MARKER

        content = f"STATIC INSTRUCTIONS HERE{DYNAMIC_CONTEXT_MARKER}volatile user stuff"
        assert _extract_static_prefix(content) == "STATIC INSTRUCTIONS HERE"

    def test_no_marker_returns_full_trimmed(self) -> None:
        assert _extract_static_prefix("  just static  ") == "just static"

    def test_capped_length(self) -> None:
        big = "x" * 20000
        assert len(_extract_static_prefix(big)) == 8192


class TestComputeCacheKey:
    def test_stable_for_same_static_prefix(self) -> None:
        from src.core.constants import DYNAMIC_CONTEXT_MARKER

        msgs_a = [
            SystemMessage(content=f"ROUTER PROMPT{DYNAMIC_CONTEXT_MARKER}ctx A"),
            HumanMessage(content="question A"),
        ]
        msgs_b = [
            SystemMessage(content=f"ROUTER PROMPT{DYNAMIC_CONTEXT_MARKER}ctx B totally different"),
            HumanMessage(content="question B"),
        ]
        # Same static prefix + different dynamic/user content → SAME cache key.
        assert compute_prompt_cache_key(msgs_a, "gpt-5-mini") == compute_prompt_cache_key(
            msgs_b, "gpt-5-mini"
        )

    def test_differs_for_different_static_prefix(self) -> None:
        a = [SystemMessage(content="PROMPT TYPE A")]
        b = [SystemMessage(content="PROMPT TYPE B")]
        assert compute_prompt_cache_key(a, "gpt-5-mini") != compute_prompt_cache_key(
            b, "gpt-5-mini"
        )

    def test_no_system_message_falls_back_to_model(self) -> None:
        key1 = compute_prompt_cache_key([HumanMessage(content="hi")], "gpt-5-mini")
        key2 = compute_prompt_cache_key([HumanMessage(content="different")], "gpt-5-mini")
        # Falls back to model-based grouping → stable regardless of user text.
        assert key1 == key2
        assert len(key1) == 32


class TestCreateResponsesLLM:
    def test_standard_model_config(self) -> None:
        llm = create_responses_llm("gpt-4.1", api_key="sk-test", temperature=0.5, top_p=0.9)
        assert isinstance(llm, ChatOpenAICached)
        assert llm.model_name == "gpt-4.1"
        assert llm.use_responses_api is True
        # Sampling params applied for non-reasoning use.
        assert llm.temperature == 0.5

    def test_reasoning_model_enables_summary(self) -> None:
        llm = create_responses_llm("gpt-5-mini", api_key="sk-test", reasoning_effort="low")
        assert isinstance(llm, ChatOpenAICached)
        # Reasoning config carries summary=auto so thinking can be streamed.
        assert llm.reasoning == {"effort": "low", "summary": "auto"}
