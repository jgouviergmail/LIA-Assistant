"""One function, one branch per family, replacing seven builders.

:func:`~src.core.reasoning_intent.intent_from_legacy` is re-exported here for
the callers that imported it from this module before it moved to ``core``:
``core`` must not import from ``infrastructure``, and ``LLMAgentConfig`` needs
the mapper to read the shapes still stored in the database. Wherever it lives,
there is exactly one of it -- the migration, the seed and the golden
equivalence proof must agree on what a stored value MEANT, and two copies
could not.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
from functools import cache
from typing import Any

import structlog

from src.core.constants import ANTHROPIC_MIN_THINKING_BUDGET_TOKENS
from src.core.reasoning_intent import ReasoningIntent, intent_from_legacy
from src.infrastructure.llm.reasoning.coerce import coerce
from src.infrastructure.llm.reasoning.profiles import ReasoningProfile
from src.infrastructure.observability.metrics_llm_config import llm_reasoning_coerced_total

logger = structlog.get_logger(__name__)

__all__ = ["honours_exclude_from_output", "intent_from_legacy", "kwargs_for", "translate"]

#: Output cap used only to probe a renderer's behaviour. Any positive value
#: works: the probe compares two renderings that share it.
_PROBE_OUTPUT_TOKENS = 4096

#: Level -> fraction of the model's output cap, for the families that express a
#: budget rather than a level. The ratios are the ones OpenRouter and Vercel
#: publish for the same mapping, so a level means comparable depth across
#: providers instead of meaning whatever each translator happened to choose.
_BUDGET_RATIO: dict[str, float] = {
    "minimal": 0.10,
    "low": 0.20,
    "medium": 0.50,
    "high": 0.80,
    "xhigh": 0.95,
    "max": 0.95,
}


#: ``provider_default`` is the identity, not a depth: it asks for nothing and
#: must never be rendered. Every renderer below returns the kwargs that remain
#: meaningful WITHOUT a depth -- an explicit budget, "keep the reasoning out of
#: the output" -- and nothing else. A renderer that forwarded the sentinel put
#: the literal string on the wire (``"effort": "provider_default"``), which is
#: not a value any provider accepts. Pinned by
#: ``test_translate_matrix.py::test_the_identity_sentinel_never_reaches_a_provider``.
_NO_DEPTH = "provider_default"


def _budget_for(level: str, max_output_tokens: int, floor: int) -> int:
    """Turn a level into a token budget, never below the provider's floor."""
    ratio = _BUDGET_RATIO.get(level)
    if ratio is None:
        return floor
    return max(int(max_output_tokens * ratio), floor)


def _render_openai(level: str, _intent: ReasoningIntent, _max_output: int) -> dict[str, Any]:
    return {} if level == _NO_DEPTH else {"reasoning_effort": level}


def _render_anthropic_adaptive(
    level: str, _intent: ReasoningIntent, _max_output: int
) -> dict[str, Any]:
    if level in (_NO_DEPTH, "none"):
        return {}
    return {"thinking": {"type": "adaptive"}, "effort": level}


def _render_anthropic_budget(
    level: str, intent: ReasoningIntent, max_output: int
) -> dict[str, Any]:
    if level == "none":
        return {}
    budget = intent.budget_tokens
    if budget is None:
        if level == _NO_DEPTH:
            return {}
        budget = _budget_for(level, max_output, ANTHROPIC_MIN_THINKING_BUDGET_TOKENS)
    # An explicit budget IS a request to think, whatever the depth says.
    return {"thinking": {"type": "enabled", "budget_tokens": budget}}


def _render_gemini_level(level: str, intent: ReasoningIntent, _max_output: int) -> dict[str, Any]:
    if level == _NO_DEPTH:
        # No depth was asked for, so none is sent; the only thing left to say
        # is the caller's wish to keep the reasoning out of the response, and
        # it is said only when it was actually asked.
        return {"include_thoughts": False} if intent.exclude_from_output else {}
    return {"thinking_level": level, "include_thoughts": not intent.exclude_from_output}


def _render_gemini_budget(level: str, intent: ReasoningIntent, max_output: int) -> dict[str, Any]:
    budget = intent.budget_tokens
    if level == _NO_DEPTH:
        depthless: dict[str, Any] = {}
        if budget is not None:
            depthless["thinking_budget"] = budget
        if intent.exclude_from_output:
            depthless["include_thoughts"] = False
        return depthless
    if budget is None:
        budget = 0 if level == "none" else int(max_output * _BUDGET_RATIO.get(level, 0.5))
    return {"thinking_budget": budget, "include_thoughts": not intent.exclude_from_output}


def _render_deepseek_toggle(
    level: str, _intent: ReasoningIntent, _max_output: int
) -> dict[str, Any]:
    if level == _NO_DEPTH:
        return {}
    if level == "none":
        return {"extra_body": {"thinking": {"type": "disabled"}}}
    return {"extra_body": {"thinking": {"type": "enabled"}}, "reasoning_effort": level}


def _render_qwen_toggle_budget(
    level: str, intent: ReasoningIntent, _max_output: int
) -> dict[str, Any]:
    if level == "none":
        return {"extra_body": {"enable_thinking": False}}
    if level == _NO_DEPTH and intent.budget_tokens is None:
        return {}
    # An explicit budget IS a request to think, whatever the depth says.
    extra: dict[str, Any] = {"enable_thinking": True}
    if intent.budget_tokens is not None:
        extra["thinking_budget"] = intent.budget_tokens
    return {"extra_body": extra}


def _render_perplexity(level: str, _intent: ReasoningIntent, _max_output: int) -> dict[str, Any]:
    return {} if level == _NO_DEPTH else {"reasoning_effort": level}


#: Family -> its renderer. A new provider with an unseen shape is one entry and
#: one small function; no existing family changes. The families deliberately
#: differ only in the kwargs they emit -- everything upstream (the ladder, the
#: coercion, the intent) is shared.
_RENDERERS: dict[str, Callable[[str, ReasoningIntent, int], dict[str, Any]]] = {
    "openai": _render_openai,
    "anthropic_adaptive": _render_anthropic_adaptive,
    "anthropic_budget": _render_anthropic_budget,
    "gemini_level": _render_gemini_level,
    "gemini_budget": _render_gemini_budget,
    "deepseek_toggle": _render_deepseek_toggle,
    "qwen_toggle_budget": _render_qwen_toggle_budget,
    "perplexity": _render_perplexity,
}


def _report_coercion(model: str, requested: str, applied: str) -> None:
    """Count and log a coercion, without ever letting observability break a call.

    The configured level was not on this model's ladder, so the runtime moved
    it. That is deliberate -- a stale configuration must not become an error --
    but it means the model is not doing what the admin asked, which has to be
    visible somewhere other than a reading of the code.
    """
    with suppress(Exception):
        llm_reasoning_coerced_total.labels(
            model=model, from_level=requested, to_level=applied
        ).inc()
    logger.info(
        "llm_reasoning_coerced",
        model=model,
        requested_level=requested,
        applied_level=applied,
    )


def translate(
    intent: ReasoningIntent,
    profile: ReasoningProfile,
    model: str,
    max_output_tokens: int,
) -> dict[str, Any]:
    """Render an intent as the provider kwargs its family expects.

    Args:
        intent: What the caller wants.
        profile: What the model can express.
        model: The model name, kept for renderers whose kwargs may name it.
        max_output_tokens: Used by the budget families to turn a level into a
            token count.

    Returns:
        The kwargs dict, empty when nothing should be sent -- which is the
        answer for a non-reasoning family and for ``provider_default``.
    """
    renderer = _RENDERERS.get(profile.family)
    if renderer is None:
        return {}
    if intent.level == _NO_DEPTH and intent.budget_tokens is None:
        # Nothing was asked -- unless the caller also asked to keep the
        # reasoning out of the response, which two families express on its own.
        # Swallowing that here is the published-vs-applied gap of ADR-184
        # pointing inwards: the widget offers the switch independently of the
        # depth, and the write path accepts it.
        if not (intent.exclude_from_output and honours_exclude_from_output(profile.family)):
            return {}
    level, was_coerced = coerce(intent.level, profile)
    if was_coerced:
        _report_coercion(model, intent.level, level)
    return renderer(level, intent, max_output_tokens)


@cache
def honours_exclude_from_output(family: str) -> bool:
    """Whether a family's renderer actually expresses ``exclude_from_output``.

    DERIVED, not declared: the answer is obtained by rendering the same level
    twice and comparing. A hand-maintained list of "the Gemini families" would
    be a second authority on the renderers, and the admin UI would keep
    offering a switch after the renderer stopped reading it -- exactly the
    published-vs-enforced gap ADR-184 closes.

    Args:
        family: A :data:`_RENDERERS` key.

    Returns:
        True when the two renderings differ, i.e. the flag reaches the provider.
    """
    renderer = _RENDERERS.get(family)
    if renderer is None:
        return False
    probe = "medium"
    kept = renderer(probe, ReasoningIntent(level=probe), _PROBE_OUTPUT_TOKENS)
    excluded = renderer(
        probe, ReasoningIntent(level=probe, exclude_from_output=True), _PROBE_OUTPUT_TOKENS
    )
    return kept != excluded


def kwargs_for(provider: str, model: str, stored: Any) -> dict[str, Any]:
    """The one seam the adapter calls, whatever the provider.

    Resolves the profile (deriving the family, narrowing the ladder with
    whatever the catalogue declares), reads the stored value as an intent and
    translates. Replaces six per-provider builder call sites scattered across
    ``adapter.py``.

    Args:
        provider: LIA provider id.
        model: LIA model name.
        stored: The configured ``reasoning_effort`` -- a legacy Pydantic shape,
            a plain dict, a :class:`ReasoningIntent`, or ``None``.

    Returns:
        The provider kwargs, empty when nothing should be sent. Never raises:
        an unknown model resolves to no family and produces no kwarg, where the
        previous builders raised ``RuntimeError`` on a shape mismatch.
    """
    from src.infrastructure.llm.model_capabilities_cache import ModelCapabilitiesCache
    from src.infrastructure.llm.reasoning.profiles import resolve_reasoning_profile

    if isinstance(stored, ReasoningIntent):
        intent = stored
    elif stored is None or isinstance(stored, dict):
        intent = intent_from_legacy(stored)
    else:
        dump = getattr(stored, "model_dump", None)
        intent = intent_from_legacy(dump() if callable(dump) else None)

    # Read the profile defensively: this runs on the LLM instantiation path,
    # and a cache entry shaped differently from ``ModelProfile`` -- a stand-in,
    # a future field rename -- must degrade to "the family's own ladder", never
    # raise an AttributeError inside a provider adapter.
    caps = ModelCapabilitiesCache.get(model)
    declared = getattr(caps, "reasoning_enum_values", None)
    ladder = tuple(declared) if declared else None
    max_output = getattr(caps, "max_output_tokens", None)
    usable_output = max_output if isinstance(max_output, int) and max_output > 0 else 4096
    profile = resolve_reasoning_profile(provider, model, model_levels=ladder)
    return translate(intent, profile, model, usable_output)
