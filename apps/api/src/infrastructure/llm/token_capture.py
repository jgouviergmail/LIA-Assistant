"""Shared token-usage capture callback for structured-output LLM calls.

``get_structured_output`` (the structured-output chokepoint) returns only the
parsed Pydantic model — the raw ``AIMessage`` and its usage metadata never
reach the caller. Paths that must track their spend (proactive tasks:
heartbeat, open-loop extraction, telephony return synthesis) attach this
handler to the ``RunnableConfig`` callbacks and read the counters after the
call.

Consolidates the two historical private copies (``heartbeat/prompts.py`` and
``agents/services/open_loop_extractor.py``) which each read a *different*
surface of the ``LLMResult``:

- per-generation ``message.usage_metadata`` (LangChain-canonical, populated
  by every chat-model integration) — preferred;
- response-level ``llm_output["token_usage"]`` (OpenAI-compatible aggregate)
  — fallback only, so a provider populating both is never double-counted.

Counters are *raw provider-reported* values; cache-aware billing adjustments
(e.g. subtracting cached tokens from the billable input) belong to the caller.
"""

from __future__ import annotations

from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult


def _cache_read_tokens(meta: dict[str, Any]) -> int:
    """Cache-read count from ``usage_metadata`` (flat or nested-details shape)."""
    flat = meta.get("cache_read_input_tokens", 0)
    if flat:
        return int(flat)
    details = meta.get("input_token_details") or {}
    return int(details.get("cache_read", 0) or 0)


def _generation_usage(response: LLMResult) -> tuple[int, int, int, bool]:
    """Sum per-generation ``message.usage_metadata`` (LangChain-canonical surface).

    Returns:
        ``(tokens_in, tokens_out, tokens_cache, found)`` — ``found`` is False
        when no generation carried usage metadata at all.
    """
    tokens_in = tokens_out = tokens_cache = 0
    found = False
    for generation_list in response.generations:
        for gen in generation_list:
            msg = getattr(gen, "message", None)
            meta = getattr(msg, "usage_metadata", None) if msg is not None else None
            if not meta:
                continue
            found = True
            tokens_in += int(meta.get("input_tokens", 0) or 0)
            tokens_out += int(meta.get("output_tokens", 0) or 0)
            tokens_cache += _cache_read_tokens(meta)
    return tokens_in, tokens_out, tokens_cache, found


def _aggregate_usage(response: LLMResult) -> tuple[int, int, int]:
    """Usage from ``llm_output["token_usage"]`` (OpenAI-compatible aggregate)."""
    llm_output = getattr(response, "llm_output", None) or {}
    token_usage = llm_output.get("token_usage") or {}
    details = token_usage.get("prompt_tokens_details") or {}
    return (
        int(token_usage.get("prompt_tokens", 0) or 0),
        int(token_usage.get("completion_tokens", 0) or 0),
        int(details.get("cached_tokens", 0) or 0),
    )


class TokenCaptureHandler(BaseCallbackHandler):
    """Accumulate token usage across every LLM call of one invocation.

    Attach a fresh instance per logical operation (the counters accumulate
    across retries too — retried attempts are paid, so they belong in the
    spend). Thread-safety is not needed: LangChain fires callbacks on the
    invoking loop.
    """

    def __init__(self) -> None:
        super().__init__()
        self.tokens_in: int = 0
        self.tokens_out: int = 0
        self.tokens_cache: int = 0

    @property
    def has_usage(self) -> bool:
        """True when the provider reported any token usage at all."""
        return bool(self.tokens_in or self.tokens_out or self.tokens_cache)

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        """Extract token usage from the LLM response (both known surfaces)."""
        tokens_in, tokens_out, tokens_cache, found = _generation_usage(response)
        if not found:
            # Fallback surface, reached only when NO generation carried
            # usage_metadata — the two surfaces can never double-count.
            tokens_in, tokens_out, tokens_cache = _aggregate_usage(response)
        self.tokens_in += tokens_in
        self.tokens_out += tokens_out
        self.tokens_cache += tokens_cache
