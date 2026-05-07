"""Unit tests for per-provider reasoning_builders.

Each builder must:
- Return {} for None input.
- Translate the validated ReasoningEffortValue to provider-native kwargs.
- Raise RuntimeError on shape mismatch (defensive — N1+N2 validation
  upstream should make this unreachable, but we test the safety net).
"""

from __future__ import annotations

import pytest

from src.core.reasoning_types import (
    ReasoningEffortBudget,
    ReasoningEffortEnum,
    ReasoningEffortToggleBudget,
)
from src.infrastructure.llm.providers.reasoning_builders import (
    build_anthropic_reasoning,
    build_deepseek_v4_reasoning,
    build_gemini_reasoning,
    build_ollama_reasoning,
    build_openai_reasoning,
    build_perplexity_reasoning,
    build_qwen_reasoning,
)

# ============================================================================
# build_openai_reasoning
# ============================================================================


@pytest.mark.unit
def test_openai_none_returns_empty() -> None:
    assert build_openai_reasoning(None, "gpt-5") == {}


@pytest.mark.unit
def test_openai_enum_passes_effort_through() -> None:
    assert build_openai_reasoning(ReasoningEffortEnum(effort="high"), "gpt-5") == {
        "reasoning_effort": "high"
    }


@pytest.mark.unit
def test_openai_wrong_shape_raises() -> None:
    with pytest.raises(RuntimeError):
        build_openai_reasoning(ReasoningEffortBudget(budget=1024), "gpt-5")


# ============================================================================
# build_anthropic_reasoning (FIX for langchain-anthropic constructor kwarg)
# ============================================================================


@pytest.mark.unit
def test_anthropic_none_returns_empty() -> None:
    assert build_anthropic_reasoning(None, "claude-opus-4.6") == {}


@pytest.mark.unit
def test_anthropic_enum_returns_constructor_kwarg() -> None:
    """Critical: must return ``effort=`` (constructor kwarg consumed by
    ChatAnthropic, mapped to native output_config.effort by langchain-
    anthropic 1.3.5), NOT additional_kwargs (which is silently dropped)."""
    result = build_anthropic_reasoning(ReasoningEffortEnum(effort="max"), "claude-opus-4.6")
    assert result == {"effort": "max"}
    # Negative assertion: ensure we didn't fall back to the broken pattern
    assert "additional_kwargs" not in result


@pytest.mark.unit
def test_anthropic_wrong_shape_raises() -> None:
    with pytest.raises(RuntimeError):
        build_anthropic_reasoning(ReasoningEffortBudget(budget=4096), "claude-opus-4.6")


# ============================================================================
# build_deepseek_v4_reasoning (3-value enum: off/high/max)
# ============================================================================


@pytest.mark.unit
def test_deepseek_v4_none_returns_empty() -> None:
    assert build_deepseek_v4_reasoning(None, "deepseek-v4-flash") == {}


@pytest.mark.unit
def test_deepseek_v4_off_disables_thinking() -> None:
    result = build_deepseek_v4_reasoning(ReasoningEffortEnum(effort="off"), "deepseek-v4-flash")
    assert result == {"extra_body": {"thinking": {"type": "disabled"}}}


@pytest.mark.unit
def test_deepseek_v4_high_enables_thinking_with_high_effort() -> None:
    result = build_deepseek_v4_reasoning(ReasoningEffortEnum(effort="high"), "deepseek-v4-flash")
    assert result == {
        "extra_body": {"thinking": {"type": "enabled"}},
        "reasoning_effort": "high",
    }


@pytest.mark.unit
def test_deepseek_v4_max_enables_thinking_with_max_effort() -> None:
    result = build_deepseek_v4_reasoning(ReasoningEffortEnum(effort="max"), "deepseek-v4-flash")
    assert result == {
        "extra_body": {"thinking": {"type": "enabled"}},
        "reasoning_effort": "max",
    }


@pytest.mark.unit
def test_deepseek_v4_wrong_shape_raises() -> None:
    with pytest.raises(RuntimeError):
        build_deepseek_v4_reasoning(ReasoningEffortBudget(budget=8192), "deepseek-v4-flash")


# ============================================================================
# build_gemini_reasoning (budget_int for 2.5, enum for 3.x)
# ============================================================================


@pytest.mark.unit
def test_gemini_none_returns_empty() -> None:
    assert build_gemini_reasoning(None, "gemini-2.5-flash") == {}


@pytest.mark.unit
def test_gemini_budget_returns_thinking_budget() -> None:
    result = build_gemini_reasoning(ReasoningEffortBudget(budget=16384), "gemini-2.5-flash")
    assert result == {"thinking_budget": 16384}


@pytest.mark.unit
def test_gemini_budget_passes_off_sentinel_through() -> None:
    """The validation step lets the off_sentinel through; the builder must
    forward it as-is to Gemini API (which interprets 0 as off)."""
    result = build_gemini_reasoning(ReasoningEffortBudget(budget=0), "gemini-2.5-flash")
    assert result == {"thinking_budget": 0}


@pytest.mark.unit
def test_gemini_budget_passes_dynamic_sentinel_through() -> None:
    result = build_gemini_reasoning(ReasoningEffortBudget(budget=-1), "gemini-2.5-flash")
    assert result == {"thinking_budget": -1}


@pytest.mark.unit
def test_gemini_enum_returns_thinking_level() -> None:
    """Gemini 3.x uses thinking_level (string enum)."""
    result = build_gemini_reasoning(ReasoningEffortEnum(effort="high"), "gemini-3-pro-preview")
    assert result == {"thinking_level": "high"}


@pytest.mark.unit
def test_gemini_no_silent_medium_to_low_mapping() -> None:
    """Regression: medium must NOT be silently rewritten to low (the previous
    adapter behavior was factually wrong per Gemini docs)."""
    result = build_gemini_reasoning(ReasoningEffortEnum(effort="medium"), "gemini-3-pro-preview")
    assert result == {"thinking_level": "medium"}


@pytest.mark.unit
def test_gemini_wrong_shape_raises() -> None:
    with pytest.raises(RuntimeError):
        build_gemini_reasoning(ReasoningEffortToggleBudget(enabled=True), "gemini-2.5-flash")


# ============================================================================
# build_qwen_reasoning (toggle_budget — direct passthrough, no enum mapping)
# ============================================================================


@pytest.mark.unit
def test_qwen_none_returns_empty() -> None:
    assert build_qwen_reasoning(None, "qwen3.5-plus") == {}


@pytest.mark.unit
def test_qwen_disabled_returns_enable_thinking_false() -> None:
    result = build_qwen_reasoning(ReasoningEffortToggleBudget(enabled=False), "qwen3.5-plus")
    assert result == {"extra_body": {"enable_thinking": False}}


@pytest.mark.unit
def test_qwen_enabled_with_budget() -> None:
    result = build_qwen_reasoning(
        ReasoningEffortToggleBudget(enabled=True, budget=4096), "qwen3.5-plus"
    )
    assert result == {"extra_body": {"enable_thinking": True, "thinking_budget": 4096}}


@pytest.mark.unit
def test_qwen_enabled_without_budget_omits_budget_kwarg() -> None:
    """When budget=None, omit thinking_budget so the model uses its default max."""
    result = build_qwen_reasoning(
        ReasoningEffortToggleBudget(enabled=True, budget=None), "qwen3.5-plus"
    )
    assert result == {"extra_body": {"enable_thinking": True}}
    assert "thinking_budget" not in result["extra_body"]


@pytest.mark.unit
def test_qwen_wrong_shape_raises() -> None:
    with pytest.raises(RuntimeError):
        build_qwen_reasoning(ReasoningEffortEnum(effort="high"), "qwen3.5-plus")


# ============================================================================
# build_perplexity_reasoning + build_ollama_reasoning (simple passthrough)
# ============================================================================


@pytest.mark.unit
def test_perplexity_passthrough() -> None:
    result = build_perplexity_reasoning(ReasoningEffortEnum(effort="medium"), "sonar-deep-research")
    assert result == {"reasoning_effort": "medium"}


@pytest.mark.unit
def test_perplexity_wrong_shape_raises() -> None:
    with pytest.raises(RuntimeError):
        build_perplexity_reasoning(ReasoningEffortBudget(budget=1024), "sonar-deep-research")


@pytest.mark.unit
def test_ollama_passthrough() -> None:
    result = build_ollama_reasoning(ReasoningEffortEnum(effort="low"), "llama3.2")
    assert result == {"reasoning_effort": "low"}


@pytest.mark.unit
def test_ollama_wrong_shape_raises() -> None:
    with pytest.raises(RuntimeError):
        build_ollama_reasoning(ReasoningEffortBudget(budget=2048), "llama3.2")
