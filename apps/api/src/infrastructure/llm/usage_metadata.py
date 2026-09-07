"""Reading what a model call actually used — once, for every caller.

``usage_metadata`` carries the same three numbers in two spellings. OpenAI puts
the cache count under ``input_token_details.cache_read`` and includes it in
``input_tokens``; Anthropic publishes ``cache_read_input_tokens`` at the top
level. Both mean the same thing, and the billable non-cached count is
``input_tokens - cached`` in either case.

Seven copies of that arithmetic existed when this module was written
(2026-09-07), and they disagreed. Only one — the briefing's — read the
Anthropic spelling, and only that one clamped the subtraction at zero. The
other six, on an Anthropic model, attributed the cached tokens to full price
and could compute a NEGATIVE prompt count when a provider reported the two
fields inconsistently.

That is what a duplicated rule costs: not the extra lines, but the six versions
that stopped being the same rule. This module is the one implementation; the
tests pin both spellings and the clamp.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, NamedTuple


class UsageTokens(NamedTuple):
    """One call's token counts, normalised across providers.

    Attributes:
        prompt: Billable prompt tokens, cache EXCLUDED.
        completion: Tokens the model produced.
        cached: Prompt tokens served from the provider's cache, priced apart.
    """

    prompt: int
    completion: int
    cached: int

    @property
    def is_empty(self) -> bool:
        """True when the call reports no billable tokens at all."""
        return self.prompt == 0 and self.completion == 0 and self.cached == 0


def tokens_from_usage_metadata(usage_metadata: Mapping[str, Any] | None) -> UsageTokens:
    """Normalise a provider's usage metadata into three comparable counts.

    Args:
        usage_metadata: The mapping a LangChain message carries, or None.

    Returns:
        The normalised counts; all zero when nothing usable was reported.
    """
    if not usage_metadata:
        return UsageTokens(0, 0, 0)

    raw_input = _as_int(usage_metadata.get("input_tokens"))
    completion = _as_int(usage_metadata.get("output_tokens"))

    details = usage_metadata.get("input_token_details")
    detailed_cache = _as_int(details.get("cache_read")) if isinstance(details, Mapping) else 0
    # Anthropic publishes the same count at the top level. Reading only the
    # OpenAI spelling is what made six of the seven previous copies attribute
    # cached tokens to full price on every Anthropic model.
    cached = detailed_cache or _as_int(usage_metadata.get("cache_read_input_tokens"))

    # Clamped: a provider reporting the two fields inconsistently must not
    # produce a negative prompt count that then flows into a price.
    return UsageTokens(prompt=max(raw_input - cached, 0), completion=completion, cached=cached)


def tokens_from_response(response: object) -> UsageTokens:
    """Normalise the usage metadata carried by a model response.

    Args:
        response: Any object that may expose ``usage_metadata`` (a LangChain
            ``AIMessage``, typically). Anything else reads as no usage.

    Returns:
        The normalised counts.
    """
    usage = getattr(response, "usage_metadata", None)
    return tokens_from_usage_metadata(usage if isinstance(usage, Mapping) else None)


def tokens_from_callback(handler: object) -> UsageTokens:
    """Total usage collected by a ``UsageMetadataCallbackHandler``.

    The handler keys its dict by model name, so a call that fell back to a
    second model reports two entries; they are summed, because the question the
    ledger asks is « what did this call cost », not « which model answered ».

    Written because the hand-rolled loop that read this handler summed
    ``input_tokens`` and ``output_tokens`` and ignored the cache entirely — an
    eighth variant of the arithmetic this module exists to hold once.

    Args:
        handler: The callback handler, or anything exposing ``usage_metadata``.

    Returns:
        The summed, normalised counts.
    """
    collected = getattr(handler, "usage_metadata", None)
    if not isinstance(collected, Mapping):
        return UsageTokens(0, 0, 0)
    prompt = completion = cached = 0
    for entry in collected.values():
        if not isinstance(entry, Mapping):
            continue
        usage = tokens_from_usage_metadata(entry)
        prompt += usage.prompt
        completion += usage.completion
        cached += usage.cached
    return UsageTokens(prompt, completion, cached)


def model_name_of(llm: object) -> str | None:
    """The model a client is configured with, or None when it will not say.

    LangChain spells this ``model_name`` on some clients and ``model`` on
    others. Seven call sites read it before this helper existed, with three
    different fallbacks — ``""``, ``"unknown"`` and ``None`` — so the same
    unnamed model reached a price lookup as an empty string in one place and
    as the literal string "unknown" in another.

    Args:
        llm: The chat client.

    Returns:
        The model name, or None when neither attribute carries one.
    """
    for attribute in ("model_name", "model"):
        value = getattr(llm, attribute, None)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _as_int(value: object) -> int:
    """Coerce a reported count to a non-negative int, defensively.

    Providers have returned ``None``, floats and strings here. A raise would
    take down the call this only meant to measure.

    Args:
        value: Whatever the provider put in the field.

    Returns:
        The count, or 0 when it cannot be read.
    """
    if value is None or isinstance(value, bool):
        # A bool is an int in Python; a provider sending `true` here means
        # nothing countable, and reading it as 1 would invent a token.
        return 0
    if isinstance(value, int | float):
        return max(int(value), 0)
    if isinstance(value, str):
        try:
            return max(int(float(value)), 0)
        except ValueError:
            return 0
    return 0


__all__ = [
    "UsageTokens",
    "model_name_of",
    "tokens_from_callback",
    "tokens_from_response",
    "tokens_from_usage_metadata",
]
