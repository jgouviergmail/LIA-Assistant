"""
Utility for extracting token usage metadata from LangChain LLMResult.

Centralizes the 3-strategy extraction logic used by multiple callbacks.
This eliminates code duplication and provides a single source of truth
for token metadata extraction.
"""

from typing import TYPE_CHECKING, NamedTuple

import structlog
from langchain_core.outputs import LLMResult

from src.core.field_names import FIELD_MODEL_NAME

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

logger = structlog.get_logger(__name__)


class TokenUsage(NamedTuple):
    """Token usage extracted from LLMResult."""

    input_tokens: int
    output_tokens: int
    cached_tokens: int
    model_name: str


class TokenExtractor:
    """
    Utility class for extracting token usage from LangChain LLMResult.

    Uses a 3-strategy fallback approach to handle different LangChain versions
    and LLM providers:
    1. AIMessage.usage_metadata (modern API, preferred)
    2. llm_output dict (legacy API)
    3. LLM instance model_name attribute (fallback)

    Example:
        >>> extractor = TokenExtractor()
        >>> usage = extractor.extract(llm_result)
        >>> print(f"Tokens: {usage.input_tokens} in, {usage.output_tokens} out")
    """

    @staticmethod
    def extract(response: LLMResult, llm: "BaseChatModel | None" = None) -> TokenUsage | None:
        """
        Extract token usage and model name from LLMResult.

        Uses 3-strategy extraction with fallbacks:
        1. Modern: AIMessage.usage_metadata + response_metadata
        2. Legacy: llm_output dict
        3. Fallback: LLM instance attributes

        Args:
            response: LLMResult from LLM call completion
            llm: Optional LLM instance for fallback model name extraction

        Returns:
            TokenUsage namedtuple with extracted values, or None if no usage found

        Example:
            >>> extractor = TokenExtractor()
            >>> usage = extractor.extract(llm_result, llm_instance)
            >>> if usage:
            ...     print(f"Model: {usage.model_name}, Tokens: {usage.input_tokens}")
        """
        input_tokens = 0
        output_tokens = 0
        cached_tokens = 0
        model_name = "unknown"
        usage_dict = None

        # Strategy 1: Extract from AIMessage.usage_metadata (modern LangChain API)
        # This is the preferred method as of 2025
        if response.generations and response.generations[0]:
            first_gen = response.generations[0][0]

            # Extract usage_metadata from message
            if hasattr(first_gen, "message") and hasattr(first_gen.message, "usage_metadata"):
                usage_dict = first_gen.message.usage_metadata
                if usage_dict:
                    raw_input_tokens = usage_dict.get("input_tokens", 0)
                    output_tokens = usage_dict.get("output_tokens", 0)

                    # Extract cached tokens from input_token_details
                    # Both OpenAI and Anthropic populate this via langchain:
                    #   - cache_read: tokens read from cache (discounted pricing)
                    #   - cache_creation: tokens written to cache (Anthropic only, 125% pricing)
                    input_details = usage_dict.get("input_token_details", {})
                    if input_details:
                        cached_tokens = input_details.get("cache_read", 0) or 0
                        cache_creation = input_details.get("cache_creation", 0) or 0
                        if cache_creation > 0:
                            logger.info(
                                "token_cache_creation_detected",
                                cache_creation_tokens=cache_creation,
                                cache_read_tokens=cached_tokens,
                                msg="Cache write detected — subsequent identical prefixes will be cache hits",
                            )

                    # Both OpenAI and Anthropic include cached tokens in input_tokens total.
                    # Subtract cache_read to get non-cached input tokens for pricing.
                    # (cache_creation stays in input_tokens — priced at input rate, close to
                    # Anthropic's 125% actual rate but acceptable approximation)
                    input_tokens = raw_input_tokens - cached_tokens

            # Extract model name from response_metadata
            if hasattr(first_gen, "message") and hasattr(first_gen.message, "response_metadata"):
                response_metadata = first_gen.message.response_metadata
                if response_metadata:
                    model_name = response_metadata.get(FIELD_MODEL_NAME, "unknown")

        # Strategy 2: Fallback to llm_output (legacy LangChain API)
        if not usage_dict or model_name == "unknown":
            llm_output = response.llm_output or {}

            # Extract usage from llm_output
            if not usage_dict:
                usage_dict = llm_output.get("usage_metadata") or llm_output.get("token_usage")
                if usage_dict:
                    input_tokens = usage_dict.get("input_tokens", 0) or usage_dict.get(
                        "prompt_tokens", 0
                    )
                    output_tokens = usage_dict.get("output_tokens", 0) or usage_dict.get(
                        "completion_tokens", 0
                    )
                    # Legacy cached tokens field
                    cached_tokens = usage_dict.get("cached_tokens", 0)

            # Extract model name from llm_output
            if model_name == "unknown":
                model_name = llm_output.get(FIELD_MODEL_NAME, "unknown")

        # Strategy 3: Fallback to LLM instance attributes
        if model_name == "unknown" and llm:
            model_name = getattr(llm, "model_name", "unknown")

        # Return None if no usage found
        if not usage_dict:
            logger.debug("token_extraction_no_usage", msg="No usage metadata found in LLMResult")
            return None

        return TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
            model_name=model_name,
        )
