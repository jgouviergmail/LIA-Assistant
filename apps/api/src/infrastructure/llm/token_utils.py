"""Utilities for extracting token usage from LangChain LLM responses.

Provides a single, reusable function for extracting input/output token counts
from AIMessage objects across all LLM providers (OpenAI, Anthropic, Google, etc.).
"""

from typing import Any


def extract_llm_tokens(result: Any) -> tuple[int, int]:
    """Extract token usage from a LangChain AIMessage response.

    Tries ``usage_metadata`` first (standard for OpenAI/Anthropic via LangChain
    ≥0.2), then falls back to ``response_metadata.token_usage`` for providers
    that use the older format.

    Args:
        result: A LangChain AIMessage or similar object with token metadata.

    Returns:
        Tuple of (tokens_in, tokens_out). Both 0 if unavailable.
    """
    # Primary: usage_metadata (LangChain ≥0.2 standard for OpenAI/Anthropic)
    usage = getattr(result, "usage_metadata", None)
    if usage:
        return usage.get("input_tokens", 0), usage.get("output_tokens", 0)

    # Fallback: response_metadata.token_usage (some providers)
    resp_meta = getattr(result, "response_metadata", None)
    if resp_meta:
        token_usage = resp_meta.get("token_usage") or resp_meta.get("usage", {})
        if token_usage:
            return (
                token_usage.get("prompt_tokens", 0) or token_usage.get("input_tokens", 0),
                token_usage.get("completion_tokens", 0) or token_usage.get("output_tokens", 0),
            )

    return 0, 0
