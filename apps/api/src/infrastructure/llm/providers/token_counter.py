"""
Token counting abstraction for multi-provider support.

Provides provider-specific token counting implementations:
- OpenAI: tiktoken (exact tokenization)
- Anthropic: Official Anthropic SDK count_tokens()
- DeepSeek: tiktoken with cl100k_base encoding (compatible)
- Perplexity: tiktoken (uses OpenAI models underneath)
- Ollama: Estimation-based (no official tokenizer API)
"""

from typing import Protocol

from src.domains.llm_config.cache import LLMConfigOverrideCache
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


class TokenCounter(Protocol):
    """Protocol for provider-specific token counting."""

    def count(self, text: str, model: str) -> int:
        """
        Count tokens in text for given model.

        Args:
            text: Input text to tokenize
            model: Model name (for provider-specific encoding selection)

        Returns:
            int: Number of tokens
        """
        ...


class OpenAITokenCounter:
    """
    Token counter for OpenAI models using tiktoken.

    Uses model-specific encodings:
    - gpt-4.1-mini, gpt-4-turbo: o200k_base
    - gpt-4, gpt-3.5-turbo: cl100k_base
    - gpt-3: p50k_base
    """

    def count(self, text: str, model: str) -> int:
        """Count tokens using tiktoken with model-specific encoding."""
        try:
            import tiktoken

            try:
                # Try to get encoding for specific model
                encoding = tiktoken.encoding_for_model(model)
            except KeyError:
                # Fallback to cl100k_base (GPT-4/GPT-3.5 encoding)
                logger.debug(
                    "tiktoken_model_not_found",
                    model=model,
                    fallback="o200k_base",
                )
                encoding = tiktoken.get_encoding("o200k_base")

            return len(encoding.encode(text))

        except ImportError:
            logger.warning(
                "tiktoken_not_installed", msg="tiktoken not installed, falling back to estimation"
            )
            return len(text) // 4  # Rough estimation
        except Exception as e:
            logger.error(
                "tiktoken_error",
                model=model,
                error=str(e),
                exc_info=True,
            )
            return len(text) // 4  # Fallback estimation


class AnthropicTokenCounter:
    """
    Token counter for Anthropic models using official SDK.

    Uses Anthropic's messages.count_tokens() method for accurate counting
    with model-specific tokenizers.
    """

    def count(self, text: str, model: str) -> int:
        """Count tokens using Anthropic SDK with model-specific tokenization."""
        try:
            from anthropic import Anthropic  # type: ignore[import-not-found]

            api_key = LLMConfigOverrideCache.get_api_key("anthropic")
            if not api_key:
                logger.warning(
                    "anthropic_token_counter_no_key",
                    msg="No Anthropic API key in DB, falling back to tiktoken estimation",
                )
                raise ImportError("No Anthropic API key configured")
            client = Anthropic(api_key=api_key)

            # Normalize model name - ensure it starts with "claude"
            # Fallback to claude-sonnet-4-5 if model is not a Claude model
            normalized_model = model if model.startswith("claude") else "claude-sonnet-4-5"

            # FIXED: Use messages.count_tokens with model parameter
            # The simple count_tokens() method does not support model-specific tokenization
            token_count = client.messages.count_tokens(
                model=normalized_model,
                messages=[{"role": "user", "content": text}],
            ).input_tokens

            return token_count

        except ImportError:
            logger.warning(
                "anthropic_sdk_not_installed",
                msg="anthropic SDK not installed, falling back to estimation",
            )
            return len(text) // 4  # Rough estimation
        except Exception as e:
            logger.error(
                "anthropic_count_tokens_error",
                model=model,
                error=str(e),
                exc_info=True,
            )
            return len(text) // 4  # Fallback estimation


class DeepSeekTokenCounter:
    """
    Token counter for DeepSeek models.

    DeepSeek uses tiktoken-compatible encoding (cl100k_base).
    Falls back to estimation if tiktoken is not available.
    """

    def count(self, text: str, model: str) -> int:
        """Count tokens using tiktoken cl100k_base encoding."""
        try:
            import tiktoken

            # DeepSeek uses cl100k_base encoding (same as GPT-4)
            encoding = tiktoken.get_encoding("cl100k_base")
            return len(encoding.encode(text))

        except ImportError:
            logger.warning(
                "tiktoken_not_installed_deepseek",
                msg="tiktoken not installed, falling back to estimation",
            )
            return len(text) // 4  # Rough estimation
        except Exception as e:
            logger.error(
                "tiktoken_error_deepseek",
                model=model,
                error=str(e),
                exc_info=True,
            )
            return len(text) // 4  # Fallback estimation


class PerplexityTokenCounter:
    """
    Token counter for Perplexity models.

    Perplexity uses OpenAI models underneath, so we use tiktoken
    with cl100k_base encoding.
    """

    def count(self, text: str, model: str) -> int:
        """Count tokens using tiktoken cl100k_base encoding."""
        try:
            import tiktoken

            # Perplexity uses OpenAI models (GPT-4-based)
            encoding = tiktoken.get_encoding("cl100k_base")
            return len(encoding.encode(text))

        except ImportError:
            logger.warning(
                "tiktoken_not_installed_perplexity",
                msg="tiktoken not installed, falling back to estimation",
            )
            return len(text) // 4  # Rough estimation
        except Exception as e:
            logger.error(
                "tiktoken_error_perplexity",
                model=model,
                error=str(e),
                exc_info=True,
            )
            return len(text) // 4  # Fallback estimation


class EstimationTokenCounter:
    """
    Fallback token counter using character-based estimation.

    Rule of thumb: ~4 characters per token (rough average for English text).
    Used for Ollama and as a fallback when specific tokenizers fail.
    """

    def count(self, text: str, model: str) -> int:
        """Estimate tokens using 4 characters per token."""
        return len(text) // 4


def get_token_counter(provider: str) -> TokenCounter:
    """
    Factory function for token counters.

    Args:
        provider: Provider name (openai, anthropic, deepseek, perplexity, ollama)

    Returns:
        TokenCounter: Appropriate token counter for the provider

    Example:
        >>> counter = get_token_counter("anthropic")
        >>> tokens = counter.count("Hello, world!", "claude-sonnet-4-5")
    """
    counters: dict[str, TokenCounter] = {
        "openai": OpenAITokenCounter(),
        "anthropic": AnthropicTokenCounter(),
        "deepseek": DeepSeekTokenCounter(),
        "perplexity": PerplexityTokenCounter(),
        "gemini": EstimationTokenCounter(),
        "ollama": EstimationTokenCounter(),
    }

    return counters.get(provider, EstimationTokenCounter())
