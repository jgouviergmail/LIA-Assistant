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

The counters are in the ONE reader's buckets (``usage_metadata.py``, ADR-306):
``tokens_in`` is the billable input with the cache reads REMOVED, priced apart
through ``tokens_cache``, and ``tokens_cache_write`` is the part of
``tokens_in`` Claude wrote to its prompt cache. They used to be the RAW
provider values while four of the five callers priced ``tokens_cache`` on top,
so every cached token was billed twice there.
"""

from __future__ import annotations

from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from src.infrastructure.llm.usage_metadata import (
    UsageTokens,
    sum_usage,
    tokens_from_usage_metadata,
)


def _generation_usage(response: LLMResult) -> UsageTokens | None:
    """Sum per-generation ``message.usage_metadata`` (LangChain-canonical surface).

    Returns:
        The summed reading, or ``None`` when no generation carried usage
        metadata at all.
    """
    readings = [
        tokens_from_usage_metadata(meta)
        for generation_list in response.generations
        for gen in generation_list
        if (meta := getattr(getattr(gen, "message", None), "usage_metadata", None))
    ]
    return sum_usage(readings) if readings else None


def _aggregate_usage(response: LLMResult) -> UsageTokens:
    """Usage from ``llm_output["token_usage"]`` (OpenAI-compatible aggregate).

    Its ``prompt_tokens`` includes the cached ones, like ``input_tokens`` does,
    so it goes through the same reader under the LangChain spelling.
    """
    llm_output = getattr(response, "llm_output", None) or {}
    token_usage = llm_output.get("token_usage") or {}
    details = token_usage.get("prompt_tokens_details") or {}
    return tokens_from_usage_metadata(
        {
            "input_tokens": token_usage.get("prompt_tokens"),
            "output_tokens": token_usage.get("completion_tokens"),
            "input_token_details": {"cache_read": details.get("cached_tokens")},
        }
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
        self.tokens_cache_write: int = 0

    @property
    def has_usage(self) -> bool:
        """True when the provider reported any token usage at all."""
        return bool(self.tokens_in or self.tokens_out or self.tokens_cache)

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        """Extract token usage from the LLM response (both known surfaces)."""
        # Fallback surface, reached only when NO generation carried
        # usage_metadata — the two surfaces can never double-count.
        usage = _generation_usage(response) or _aggregate_usage(response)
        self.tokens_in += usage.prompt
        self.tokens_out += usage.completion
        self.tokens_cache += usage.cached
        self.tokens_cache_write += usage.cache_write
