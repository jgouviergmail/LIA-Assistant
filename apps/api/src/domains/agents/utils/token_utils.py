"""
Token counting utilities for LLM operations.

Provides functions for counting tokens in text and messages using tiktoken.
Centralizes all token-related operations for consistency and maintainability.
"""

import tiktoken
from langchain_core.messages import BaseMessage

from src.core.config import get_settings
from src.core.field_names import FIELD_TOTAL
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


def count_tokens(text: str, encoding_name: str | None = None) -> int:
    """
    Count tokens in text using tiktoken encoding.

    Args:
        text: Text to count tokens for.
        encoding_name: Tiktoken encoding name (default: from settings.token_encoding_name).

    Returns:
        Number of tokens.

    Example:
        >>> count_tokens("Hello, world!")
        3
        >>> count_tokens("Bonjour le monde !")
        5

    Note:
        Falls back to rough estimation (4 chars per token) if tiktoken fails.
    """
    if encoding_name is None:
        encoding_name = settings.token_encoding_name
    try:
        encoding = tiktoken.get_encoding(encoding_name)
        return len(encoding.encode(text))
    except Exception as e:
        logger.warning(
            "token_counting_failed_fallback",
            error=str(e),
            encoding=encoding_name,
        )
        # Fallback: rough estimation (4 chars per token for Latin scripts)
        return len(text) // 4


def count_messages_tokens(messages: list[BaseMessage], encoding_name: str | None = None) -> int:
    """
    Count total tokens in a list of messages.

    Sums token counts across all message contents.

    Args:
        messages: List of LangChain messages.
        encoding_name: Tiktoken encoding name (default: from settings.token_encoding_name).

    Returns:
        Total token count across all messages.

    Example:
        >>> from langchain_core.messages import HumanMessage, AIMessage
        >>> messages = [HumanMessage(content="Hello"), AIMessage(content="Hi there!")]
        >>> count_messages_tokens(messages)
        6

    Note:
        Only counts message content, not metadata or tool_calls.
        For precise LLM billing, use OpenAI's native token counter.
    """
    if encoding_name is None:
        encoding_name = settings.token_encoding_name
    total = 0
    for msg in messages:
        content = msg.content or ""
        total += count_tokens(str(content), encoding_name)

    return total


def count_state_tokens(state: dict, encoding_name: str | None = None) -> dict[str, int]:
    """
    Count tokens in MessagesState for diagnostics and monitoring.

    Provides detailed breakdown of token usage across state fields:
    - messages: Total tokens in all messages
    - agent_results: Total tokens in agent results data
    - routing_history: Total tokens in router decisions

    Args:
        state: MessagesState dictionary.
        encoding_name: Tiktoken encoding name (default: from settings.token_encoding_name).

    Returns:
        Dictionary with token counts per field.

    Example:
        >>> token_counts = count_state_tokens(state)
        >>> print(f"Total state tokens: {sum(token_counts.values())}")
        >>> # Output: {"messages": 12500, "agent_results": 3200, "routing_history": 450}

    Note:
        Useful for identifying memory bloat and optimizing state management.
    """
    if encoding_name is None:
        encoding_name = settings.token_encoding_name

    counts = {
        "messages": 0,
        "agent_results": 0,
        "routing_history": 0,
        FIELD_TOTAL: 0,
    }

    # Count messages tokens
    messages = state.get("messages", [])
    counts["messages"] = count_messages_tokens(messages, encoding_name)

    # Count agent_results tokens (approximate)
    agent_results = state.get("agent_results", {})
    for _key, result in agent_results.items():
        result_str = str(result)
        counts["agent_results"] += count_tokens(result_str, encoding_name)

    # Count routing_history tokens (approximate)
    routing_history = state.get("routing_history", [])
    for decision in routing_history:
        decision_str = str(decision)
        counts["routing_history"] += count_tokens(decision_str, encoding_name)

    # Total
    counts[FIELD_TOTAL] = sum(counts.values())

    logger.debug(
        "count_state_tokens",
        token_counts=counts,
        encoding=encoding_name,
    )

    return counts


def estimate_cost(
    input_tokens: int,
    output_tokens: int,
    model: str = "gpt-4.1-mini",
) -> dict[str, float]:
    """
    Estimate LLM API cost based on token counts and model pricing.

    Uses approximate pricing as of 2025. For exact pricing, use the LLM pricing service.

    Args:
        input_tokens: Number of input tokens.
        output_tokens: Number of output tokens.
        model: Model identifier (e.g., "gpt-4.1-mini", "gpt-4.1-mini-mini").

    Returns:
        Dictionary with cost breakdown in USD.

    Example:
        >>> cost = estimate_cost(input_tokens=1000, output_tokens=500, model="gpt-4.1-mini")
        >>> print(f"Total cost: ${cost['total']:.4f}")
        Total cost: $0.0015

    Note:
        This is a rough estimate. For production cost tracking, use the
        LLM pricing service with real-time pricing data.

    Pricing (approximate, 2025):
        - gpt-4.1-nano: $0.10/1M input, $0.40/1M output
        - gpt-4.1-mini: $0.15/1M input, $0.60/1M output
        - gpt-4.1-mini-mini: $0.15/1M input, $0.60/1M output
        - gpt-4.1: $2.50/1M input, $10/1M output
    """
    # Approximate pricing (USD per 1M tokens)
    pricing = {
        "gpt-4.1-nano": {"input": 0.10, "output": 0.40},
        "gpt-4.1-mini": {"input": 0.15, "output": 0.60},
        "gpt-4.1-mini-mini": {"input": 0.15, "output": 0.60},
        "gpt-4.1": {"input": 2.50, "output": 10.00},
    }

    model_pricing = pricing.get(model, {"input": 0.15, "output": 0.60})  # Default: gpt-4.1-mini

    input_cost = (input_tokens / 1_000_000) * model_pricing["input"]
    output_cost = (output_tokens / 1_000_000) * model_pricing["output"]
    total_cost = input_cost + output_cost

    return {
        "input_cost": round(input_cost, 6),
        "output_cost": round(output_cost, 6),
        FIELD_TOTAL: round(total_cost, 6),
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }


def get_encoding_for_model(model: str) -> str:
    """
    Get appropriate tiktoken encoding for a model.

    Maps model names to their corresponding tiktoken encodings.

    Args:
        model: Model identifier (e.g., "gpt-4.1-mini", "gpt-3.5-turbo").

    Returns:
        Tiktoken encoding name.

    Example:
        >>> encoding = get_encoding_for_model("gpt-4.1-mini")
        >>> encoding
        'o200k_base'

    Encoding mapping:
        - GPT-4.1, gpt-4.1-mini: o200k_base (2024+ models)
        - GPT-4: cl100k_base (2023 models)
        - GPT-3.5: cl100k_base
    """
    if any(model_prefix in model for model_prefix in ["gpt-4.1", "gpt-4.1-mini"]):
        return "o200k_base"  # Latest GPT-4 models (2024+)
    elif "gpt-4" in model or "gpt-3.5" in model:
        return "cl100k_base"  # Older GPT-4 and GPT-3.5 models
    else:
        # Default to latest encoding
        logger.warning(
            "unknown_model_using_default_encoding",
            model=model,
            default_encoding="o200k_base",
        )
        return "o200k_base"


__all__ = [
    "count_messages_tokens",
    "count_state_tokens",
    "count_tokens",
    "estimate_cost",
    "get_encoding_for_model",
]
