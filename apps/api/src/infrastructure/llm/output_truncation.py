"""One reading of « the provider stopped at its output budget » (ADR-275).

Five adapters spell it five ways, and until 2026-09-08 none of them was read:
a payload cut by ``max_tokens`` reached ``json_recovery``, which closes an open
structure mechanically, and the shortened object validated — a report missing
its last sections was rendered, stored and announced complete (measured: of 100
cuts of a valid document payload, 12 report cuts and 14 deck cuts validated as
SHORTER documents). When the repair did not validate, the call was retried
three times with the same prompt, which cannot complete what the budget cut.

The predicate reads the provider's own verdict, never the shape of the text.
Each shape was read in the installed adapter and is pinned by a fixture in
``tests/unit/infrastructure/llm/test_output_truncation.py``.
"""

from __future__ import annotations

from typing import Any, NoReturn

import structlog

from src.infrastructure.llm.message_text import coerce_content_to_text
from src.infrastructure.llm.structured_output_errors import StructuredOutputTruncatedError

logger = structlog.get_logger(__name__)

#: ``finish_reason`` values meaning « output budget exhausted »: OpenAI chat
#: completions (and the OpenAI-compatible DeepSeek / Perplexity) say ``length``;
#: langchain-google-genai forwards the enum name ``MAX_TOKENS``.
_FINISH_REASONS_TRUNCATED: frozenset[str] = frozenset({"length", "MAX_TOKENS"})


def is_output_truncated(message: Any) -> bool:
    """Whether the provider itself reports the answer as cut at its output budget.

    Args:
        message: The raw ``AIMessage`` — anything carrying ``response_metadata``.

    Returns:
        True on a budget stop; False on every other stop, on missing or
        unusable metadata, and on anything that is not a message. Doubt never
        invents a refusal: only an explicit provider verdict counts.
    """
    metadata = getattr(message, "response_metadata", None)
    if not isinstance(metadata, dict):
        return False
    if metadata.get("finish_reason") in _FINISH_REASONS_TRUNCATED:
        return True
    if metadata.get("stop_reason") == "max_tokens":  # Anthropic
        return True
    if metadata.get("done_reason") == "length":  # Ollama
        return True
    details = metadata.get("incomplete_details")  # OpenAI Responses API
    return (
        metadata.get("status") == "incomplete"
        and isinstance(details, dict)
        and details.get("reason") == "max_output_tokens"
    )


def raise_truncated(raw_message: Any, provider: str, schema_name: str) -> NoReturn:
    """Refuse a payload the provider reports as cut — before any rescue shortens it.

    Args:
        raw_message: The raw ``AIMessage`` the provider returned.
        provider: Provider name (logging and error payload).
        schema_name: Target schema name.

    Raises:
        StructuredOutputTruncatedError: Always.
    """
    raw_text = coerce_content_to_text(getattr(raw_message, "content", None) or "")
    logger.warning(
        "structured_output_truncated",
        provider=provider,
        schema=schema_name,
        raw_chars=len(raw_text),
    )
    raise StructuredOutputTruncatedError(
        f"Structured output for {schema_name} was cut at the provider's output budget",
        provider=provider,
        schema_name=schema_name,
        raw_output=raw_text[:2000] or None,
    )
