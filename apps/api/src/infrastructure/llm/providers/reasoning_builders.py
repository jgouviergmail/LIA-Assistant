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

from src.core.constants import ANTHROPIC_MIN_THINKING_BUDGET_TOKENS
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
    """Anthropic extended-thinking config, per model family.

    Verified against Anthropic docs (2026-05) for the managed models:

    - **Adaptive** (opus-4-6, sonnet-4-6): ``reasoning_widget='enum'``. The effort
      enum carries an ``"off"`` sentinel. ``"off"`` → no thinking (``{}``); any other
      value → ``thinking={"type":"adaptive"}`` + ``effort=<value>`` (effort guides the
      adaptive thinking depth, and also overall token spend).
    - **Manual** (opus-4-5, haiku-4-5): ``reasoning_widget='toggle_budget'``.
      ``enabled=False`` → no thinking (``{}``); ``enabled=True`` →
      ``thinking={"type":"enabled","budget_tokens":<budget or min>}``.

    ``langchain_anthropic`` 1.4.0 accepts both ``thinking`` and ``effort`` constructor
    kwargs (verified). When the returned dict contains a ``thinking`` key, the adapter
    omits ``temperature``/``top_p`` — Anthropic rejects custom sampling while extended
    thinking is enabled (API constraint). reasoning_stream does NOT inject thinking:
    the streamed reasoning comes solely from this config-driven setup.
    """
    if value is None:
        return {}
    if isinstance(value, ReasoningEffortEnum):
        # Adaptive family (opus-4-6 / sonnet-4-6): 'off' disables thinking.
        if value.effort == "off":
            return {}
        return {"thinking": {"type": "adaptive"}, "effort": value.effort}
    if isinstance(value, ReasoningEffortToggleBudget):
        # Manual family (opus-4-5 / haiku-4-5): explicit budget_tokens thinking.
        if not value.enabled:
            return {}
        budget = value.budget if value.budget is not None else ANTHROPIC_MIN_THINKING_BUDGET_TOKENS
        return {"thinking": {"type": "enabled", "budget_tokens": budget}}
    raise RuntimeError(
        f"Anthropic {model}: reasoning_effort must be ReasoningEffortEnum or "
        f"ReasoningEffortToggleBudget, got {type(value).__name__}. "
        "Validation upstream is broken."
    )


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

    ``include_thoughts=True`` is set alongside the thinking config so the
    configured thoughts are actually surfaced in the response stream (Gemini
    computes thoughts but omits them unless asked). This is config-driven — the
    live reasoning stream no longer injects it. When reasoning is not configured
    (``value is None``) we return ``{}`` so no thoughts are requested.
    """
    if value is None:
        return {}
    if isinstance(value, ReasoningEffortBudget):
        return {"thinking_budget": value.budget, "include_thoughts": True}
    if isinstance(value, ReasoningEffortEnum):
        return {"thinking_level": value.effort, "include_thoughts": True}
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
