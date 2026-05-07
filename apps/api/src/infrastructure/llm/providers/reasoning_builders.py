"""Per-provider translators from validated ReasoningEffortValue to provider
constructor kwargs.

Philosophy A — raw truth: NO coercion happens here. Validation already ran
upstream (Pydantic + ``reasoning_validation.validate_reasoning_effort``).
Any shape mismatch in this module indicates a bug in seed / matrix /
service / cache invalidation: raise RuntimeError to fail loud.

Each function returns a dict of kwargs to merge into the provider's LLM
client constructor (e.g. ``ChatAnthropic(**common_kwargs, **reasoning_kwargs)``).
For DeepSeek V4 / Qwen, the dict carries ``extra_body`` which the upstream
adapter merges into the request payload.
"""

from __future__ import annotations

from typing import Any

from src.core.reasoning_types import (
    ReasoningEffortBudget,
    ReasoningEffortEnum,
    ReasoningEffortToggleBudget,
    ReasoningEffortValue,
)


def build_openai_reasoning(value: ReasoningEffortValue, model: str) -> dict[str, Any]:
    """OpenAI o-series + GPT-5.x reasoning models."""
    if value is None:
        return {}
    if not isinstance(value, ReasoningEffortEnum):
        raise RuntimeError(
            f"OpenAI {model}: reasoning_effort must be ReasoningEffortEnum, "
            f"got {type(value).__name__}. Validation upstream is broken."
        )
    return {"reasoning_effort": value.effort}


def build_anthropic_reasoning(value: ReasoningEffortValue, model: str) -> dict[str, Any]:
    """Anthropic Claude 4.5+ effort enum.

    Verified: ``langchain_anthropic.chat_models.ChatAnthropic`` accepts an
    ``effort`` constructor kwarg and merges it into the native API as
    ``output_config.effort`` (cf. langchain-anthropic 1.3.5
    chat_models.py:899-918, 1186-1197). The previous code used
    ``additional_kwargs["effort"]`` — that is a LangChain *messages* kwarg
    convention, NOT a constructor-level field, so the value was silently
    dropped at the API call. This is the bug fix.
    """
    if value is None:
        return {}
    if not isinstance(value, ReasoningEffortEnum):
        raise RuntimeError(
            f"Anthropic {model}: reasoning_effort must be ReasoningEffortEnum, "
            f"got {type(value).__name__}. Validation upstream is broken."
        )
    return {"effort": value.effort}


def build_deepseek_v4_reasoning(value: ReasoningEffortValue, model: str) -> dict[str, Any]:
    """DeepSeek V4 thinking mode.

    UI exposes ``["off", "high", "max"]`` (philosophy A — the 3 effective
    behaviors per DeepSeek's published docs, where ``low`` and ``medium``
    are silently mapped to ``high`` server-side). This builder maps:
    - ``off``  → ``extra_body.thinking={"type":"disabled"}``
    - ``high`` → ``extra_body.thinking={"type":"enabled"}`` + ``reasoning_effort="high"``
    - ``max``  → ``extra_body.thinking={"type":"enabled"}`` + ``reasoning_effort="max"``
    """
    if value is None:
        return {}
    if not isinstance(value, ReasoningEffortEnum):
        raise RuntimeError(
            f"DeepSeek V4 {model}: reasoning_effort must be ReasoningEffortEnum, "
            f"got {type(value).__name__}. Validation upstream is broken."
        )
    if value.effort == "off":
        return {"extra_body": {"thinking": {"type": "disabled"}}}
    return {
        "extra_body": {"thinking": {"type": "enabled"}},
        "reasoning_effort": value.effort,
    }


def build_gemini_reasoning(value: ReasoningEffortValue, model: str) -> dict[str, Any]:
    """Gemini 2.5 (budget_int) and Gemini 3.x (enum thinking_level).

    No silent ``medium → low`` mapping — the matrix exposes only what each
    model accepts.
    """
    if value is None:
        return {}
    if isinstance(value, ReasoningEffortBudget):
        return {"thinking_budget": value.budget}
    if isinstance(value, ReasoningEffortEnum):
        return {"thinking_level": value.effort}
    raise RuntimeError(
        f"Gemini {model}: unexpected reasoning_effort shape "
        f"{type(value).__name__}. Validation upstream is broken."
    )


def build_qwen_reasoning(value: ReasoningEffortValue, model: str) -> dict[str, Any]:
    """Qwen3 hybrid thinking (toggle + numeric budget).

    No legacy enum-string-to-budget mapping. The UI uses widget=toggle_budget
    and stores ``{"enabled": bool, "budget": int|None}`` directly.
    """
    if value is None:
        return {}
    if not isinstance(value, ReasoningEffortToggleBudget):
        raise RuntimeError(
            f"Qwen {model}: reasoning_effort must be ReasoningEffortToggleBudget, "
            f"got {type(value).__name__}. Validation upstream is broken."
        )
    extra: dict[str, Any] = {"enable_thinking": value.enabled}
    if value.enabled and value.budget is not None:
        extra["thinking_budget"] = value.budget
    return {"extra_body": extra}


def build_perplexity_reasoning(value: ReasoningEffortValue, model: str) -> dict[str, Any]:
    """Perplexity sonar-deep-research only (the others have widget=none)."""
    if value is None:
        return {}
    if not isinstance(value, ReasoningEffortEnum):
        raise RuntimeError(
            f"Perplexity {model}: reasoning_effort must be ReasoningEffortEnum, "
            f"got {type(value).__name__}. Validation upstream is broken."
        )
    return {"reasoning_effort": value.effort}


def build_ollama_reasoning(value: ReasoningEffortValue, model: str) -> dict[str, Any]:
    """Ollama OpenAI-compatible bridge (passthrough). For the project's
    catalogue (llama3.2, mistral) this is a no-op since both models have
    widget=none in the matrix."""
    if value is None:
        return {}
    if not isinstance(value, ReasoningEffortEnum):
        raise RuntimeError(
            f"Ollama {model}: reasoning_effort must be ReasoningEffortEnum, "
            f"got {type(value).__name__}. Validation upstream is broken."
        )
    return {"reasoning_effort": value.effort}


__all__ = [
    "build_anthropic_reasoning",
    "build_deepseek_v4_reasoning",
    "build_gemini_reasoning",
    "build_ollama_reasoning",
    "build_openai_reasoning",
    "build_perplexity_reasoning",
    "build_qwen_reasoning",
]
