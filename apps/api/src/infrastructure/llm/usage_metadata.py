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

A prompt-cache WRITE is the fourth number (ADR-306): it stays inside the
prompt count -- a written token is a prompt token -- and is reported apart
because a vendor may bill it above the input price. The count is the same fact
whoever reports it (langchain-anthropic and langchain-openai both fill the
generic ``cache_creation``); what a write COSTS is the tariff's to say
(``CachedModelPrice.cache_write_multiplier``), never this module's.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, NamedTuple

#: Where the written tokens are reported. langchain-anthropic fills the TTL
#: breakdown when the response carries one, and then sets the generic key to 0;
#: on the path LIA runs it reports the generic key alone (measured on Sonnet 5,
#: 2026-09-23). Summing the three counts each write once in either shape.
_CACHE_WRITE_KEYS = ("cache_creation", "ephemeral_5m_input_tokens", "ephemeral_1h_input_tokens")


class UsageTokens(NamedTuple):
    """One call's token counts, normalised across providers.

    Attributes:
        prompt: Billable prompt tokens, cache reads EXCLUDED.
        completion: Tokens the model produced.
        cached: Prompt tokens served from the provider's cache, priced apart.
        cache_write: The subset of ``prompt`` the provider wrote to its prompt
            cache. Its tariff says whether it owes more than the input price
            (Claude: the 5-minute write at 1.25x — LIA sets no ``ttl``, ADR-306).
    """

    prompt: int
    completion: int
    cached: int
    cache_write: int = 0

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
    if not isinstance(details, Mapping):
        details = {}
    detailed_cache = _as_int(details.get("cache_read"))
    # Anthropic publishes the same count at the top level. Reading only the
    # OpenAI spelling is what made six of the seven previous copies attribute
    # cached tokens to full price on every Anthropic model.
    cached = detailed_cache or _as_int(usage_metadata.get("cache_read_input_tokens"))

    # Clamped: a provider reporting the two fields inconsistently must not
    # produce a negative prompt count that then flows into a price.
    prompt = max(raw_input - cached, 0)
    written = sum(_as_int(details.get(key)) for key in _CACHE_WRITE_KEYS)
    return UsageTokens(
        prompt=prompt, completion=completion, cached=cached, cache_write=min(written, prompt)
    )


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
    readings = [tokens_from_usage_metadata(e) for e in collected.values() if isinstance(e, Mapping)]
    return sum_usage(readings)


def sum_usage(readings: Iterable[UsageTokens]) -> UsageTokens:
    """Add up the usage of several calls, field by field.

    Args:
        readings: One normalised reading per call.

    Returns:
        Their sum; all zero for no reading.
    """
    total = UsageTokens(0, 0, 0)
    for usage in readings:
        total = UsageTokens(
            prompt=total.prompt + usage.prompt,
            completion=total.completion + usage.completion,
            cached=total.cached + usage.cached,
            cache_write=total.cache_write + usage.cache_write,
        )
    return total


def reasoning_tokens_of(response: object) -> int:
    """How many of a response's output tokens were hidden reasoning.

    Read from the normalised ``output_token_details.reasoning`` a LangChain
    message carries; zero when the provider reports none. Diagnostic only --
    reasoning is already counted inside ``completion``, so this is never a
    billing quantity -- but it is the number that says why a capped answer
    came back empty (measured 2026-09-12: 150 requested, 150 of reasoning).

    Args:
        response: Any object that may expose ``usage_metadata``.

    Returns:
        The reasoning token count, or 0.
    """
    usage = getattr(response, "usage_metadata", None)
    if not isinstance(usage, Mapping):
        return 0
    details = usage.get("output_token_details")
    return _as_int(details.get("reasoning")) if isinstance(details, Mapping) else 0


def model_name_of_response(response: object) -> str | None:
    """The model a RESPONSE says it came from, or None when it does not say.

    The response-side twin of :func:`model_name_of`: LangChain spells it
    ``model_name`` in ``response_metadata`` on every chat model, and a few
    older adapters ``model``. Two call sites read it before this helper
    existed; one read ``model`` alone and billed every reminder to an unnamed
    model at zero.

    Args:
        response: Any object that may expose ``response_metadata``.

    Returns:
        The model name, or None.
    """
    metadata = getattr(response, "response_metadata", None)
    if not isinstance(metadata, Mapping):
        return None
    for key in ("model_name", "model"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


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
