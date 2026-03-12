"""
TokenCounterService: Pre-count tokens before LLM invocation.

This service provides accurate token counting to:
- Prevent context overflow before it happens
- Trigger progressive fallback strategies
- Track token usage metrics
- Optimize prompt composition

Architecture:
- Uses tiktoken for accurate OpenAI-compatible counting
- Caches tokenizer instance for performance
- Provides both counting and safety checks
- Integrates with Prometheus metrics
- Thresholds configurable via .env (Phase B)

Phase A - Planner Reliability Improvement
Created: 2025-11-18
Updated: 2025-12-10 (Phase B - Configurable thresholds)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog
import tiktoken
from langchain_core.messages import BaseMessage

from src.core.constants import (
    TOKEN_THRESHOLD_CRITICAL_DEFAULT,
    TOKEN_THRESHOLD_MAX_DEFAULT,
    TOKEN_THRESHOLD_SAFE_DEFAULT,
    TOKEN_THRESHOLD_WARNING_DEFAULT,
)
from src.infrastructure.observability.metrics_agents import (
    planner_fallback_triggered_total,
    planner_token_count,
)

if TYPE_CHECKING:
    from src.core.config import Settings

logger = structlog.get_logger(__name__)

# Re-export constants for backward compatibility
TOKEN_THRESHOLD_SAFE = TOKEN_THRESHOLD_SAFE_DEFAULT
TOKEN_THRESHOLD_WARNING = TOKEN_THRESHOLD_WARNING_DEFAULT
TOKEN_THRESHOLD_CRITICAL = TOKEN_THRESHOLD_CRITICAL_DEFAULT
TOKEN_THRESHOLD_MAX = TOKEN_THRESHOLD_MAX_DEFAULT


class FallbackLevel:
    """Fallback levels for progressive catalogue reduction."""

    FULL_CATALOGUE = "full_catalogue"  # All tools, full descriptions
    FILTERED_CATALOGUE = "filtered_catalogue"  # Detected domains only
    REDUCED_DESCRIPTIONS = "reduced_descriptions"  # Minimal descriptions
    PRIMARY_DOMAIN_ONLY = "primary_domain_only"  # Single domain
    SIMPLE_SEARCH = "simple_search"  # Minimal tools


class TokenCounterService:
    """
    Service for pre-counting tokens before LLM invocation.

    This service prevents context overflow by:
    - Pre-counting tokens for system prompt, catalogue, and messages
    - Determining appropriate fallback level
    - Tracking token usage metrics

    Thread Safety:
        Uses cached tiktoken encoder, safe for concurrent use.

    Example:
        counter = TokenCounterService()

        # Count tokens
        token_count = counter.count_prompt_tokens(
            system_prompt=prompt,
            catalogue_json=catalogue,
            messages=messages,
            user_query=query
        )

        # Check safety
        if not counter.is_safe_prompt(token_count):
            fallback_level = counter.get_fallback_level(token_count)
            # Apply fallback strategy
    """

    def __init__(self, model_name: str = "gpt-4", settings: Settings | None = None):
        """
        Initialize token counter service.

        Args:
            model_name: Model name for tokenizer selection.
                        Uses cl100k_base for GPT-4/Claude compatibility.
            settings: Optional Settings object for configurable thresholds.
                      If None, uses module-level defaults.
        """
        # Use configurable encoding from settings, or default to o200k_base
        encoding_name = settings.token_encoding_name if settings else "o200k_base"
        try:
            self.encoder = tiktoken.get_encoding(encoding_name)
        except Exception as e:
            logger.warning("token_counter_encoding_fallback", error=str(e), fallback="o200k_base")
            self.encoder = tiktoken.get_encoding("o200k_base")

        self.model_name = model_name
        self._cache: dict[int, int] = {}

        # Phase B: Configurable thresholds from settings
        if settings:
            self.threshold_safe = settings.token_threshold_safe
            self.threshold_warning = settings.token_threshold_warning
            self.threshold_critical = settings.token_threshold_critical
            self.threshold_max = settings.token_threshold_max
        else:
            self.threshold_safe = TOKEN_THRESHOLD_SAFE
            self.threshold_warning = TOKEN_THRESHOLD_WARNING
            self.threshold_critical = TOKEN_THRESHOLD_CRITICAL
            self.threshold_max = TOKEN_THRESHOLD_MAX

    def count_tokens(self, text: str) -> int:
        """
        Count tokens in a text string.

        Uses caching for repeated strings to improve performance.

        Args:
            text: Text to count tokens for

        Returns:
            Number of tokens
        """
        if not text:
            return 0

        # Check cache for common strings
        cache_key = hash(text) if len(text) < 10000 else None
        if cache_key and cache_key in self._cache:
            return self._cache[cache_key]

        try:
            token_count = len(self.encoder.encode(text))

            # Cache small strings
            if cache_key and len(self._cache) < 1000:
                self._cache[cache_key] = token_count

            return token_count
        except Exception as e:
            logger.warning("token_counter_encode_error", error=str(e), text_length=len(text))
            # Fallback: rough estimate (4 chars per token)
            return len(text) // 4

    def count_message_tokens(self, message: BaseMessage) -> int:
        """
        Count tokens in a LangChain message.

        Accounts for message overhead (role, formatting).

        Args:
            message: LangChain message object

        Returns:
            Number of tokens including overhead
        """
        content = message.content if isinstance(message.content, str) else str(message.content)
        base_tokens = self.count_tokens(content)

        # Add overhead for message formatting (role, etc.)
        # Approximately 4 tokens per message
        return base_tokens + 4

    def count_messages_tokens(self, messages: list[BaseMessage]) -> int:
        """
        Count tokens in a list of messages.

        Args:
            messages: List of LangChain messages

        Returns:
            Total token count
        """
        return sum(self.count_message_tokens(msg) for msg in messages)

    def count_prompt_tokens(
        self,
        system_prompt: str,
        catalogue_json: str,
        messages: list[BaseMessage],
        user_query: str,
    ) -> int:
        """
        Count total tokens for a complete planner prompt.

        Provides accurate pre-invocation token count including:
        - System prompt
        - Tool catalogue JSON
        - Conversation history
        - User query

        Args:
            system_prompt: System prompt template
            catalogue_json: JSON-formatted tool catalogue
            messages: Conversation history messages
            user_query: Current user query

        Returns:
            Total token count
        """
        # Count each component
        system_tokens = self.count_tokens(system_prompt)
        catalogue_tokens = self.count_tokens(catalogue_json)
        messages_tokens = self.count_messages_tokens(messages)
        query_tokens = self.count_tokens(user_query)

        # Add overhead for prompt structure
        overhead = 50  # Formatting, separators, etc.

        total = system_tokens + catalogue_tokens + messages_tokens + query_tokens + overhead

        logger.debug(
            "token_counter_prompt_counted",
            system_tokens=system_tokens,
            catalogue_tokens=catalogue_tokens,
            messages_tokens=messages_tokens,
            query_tokens=query_tokens,
            overhead=overhead,
            total=total,
        )

        return total

    def count_catalogue_tokens(self, catalogue: dict[str, Any]) -> int:
        """
        Count tokens for a tool catalogue.

        Useful for comparing catalogue sizes before/after filtering.

        Args:
            catalogue: Tool catalogue dictionary

        Returns:
            Token count for JSON representation
        """
        import json

        catalogue_json = json.dumps(catalogue, indent=2, ensure_ascii=False)
        return self.count_tokens(catalogue_json)

    def is_safe_prompt(
        self,
        token_count: int,
        max_tokens: int | None = None,
    ) -> bool:
        """
        Check if token count is within safe limits.

        Args:
            token_count: Total token count
            max_tokens: Maximum safe token count (default: from settings or 6000)

        Returns:
            True if token count is safe
        """
        threshold = max_tokens if max_tokens is not None else self.threshold_safe
        return token_count <= threshold

    def get_fallback_level(self, token_count: int) -> str:
        """
        Determine appropriate fallback level based on token count.

        Progressive fallback strategy (thresholds configurable via .env):
        - < threshold_safe: FULL_CATALOGUE (no reduction needed)
        - threshold_safe-threshold_warning: FILTERED_CATALOGUE (domain filtering)
        - threshold_warning-threshold_critical: REDUCED_DESCRIPTIONS (minimal descriptions)
        - threshold_critical-threshold_max: PRIMARY_DOMAIN_ONLY (single domain)
        - > threshold_max: SIMPLE_SEARCH (emergency minimal)

        Args:
            token_count: Total token count

        Returns:
            Fallback level constant
        """
        if token_count <= self.threshold_safe:
            return FallbackLevel.FULL_CATALOGUE
        elif token_count <= self.threshold_warning:
            return FallbackLevel.FILTERED_CATALOGUE
        elif token_count <= self.threshold_critical:
            return FallbackLevel.REDUCED_DESCRIPTIONS
        elif token_count <= self.threshold_max:
            return FallbackLevel.PRIMARY_DOMAIN_ONLY
        else:
            return FallbackLevel.SIMPLE_SEARCH

    def should_trigger_fallback(
        self,
        token_count: int,
        current_level: str = FallbackLevel.FULL_CATALOGUE,
    ) -> tuple[bool, str]:
        """
        Check if fallback should be triggered and return new level.

        Args:
            token_count: Total token count
            current_level: Current fallback level

        Returns:
            Tuple of (should_trigger, new_level)
        """
        new_level = self.get_fallback_level(token_count)

        # Define level order for comparison
        level_order = [
            FallbackLevel.FULL_CATALOGUE,
            FallbackLevel.FILTERED_CATALOGUE,
            FallbackLevel.REDUCED_DESCRIPTIONS,
            FallbackLevel.PRIMARY_DOMAIN_ONLY,
            FallbackLevel.SIMPLE_SEARCH,
        ]

        try:
            current_index = level_order.index(current_level)
            new_index = level_order.index(new_level)

            if new_index > current_index:
                # Track metric
                planner_fallback_triggered_total.labels(
                    from_level=current_level,
                    to_level=new_level,
                ).inc()

                logger.info(
                    "token_counter_fallback_triggered",
                    token_count=token_count,
                    from_level=current_level,
                    to_level=new_level,
                )

                return True, new_level
        except ValueError:
            pass

        return False, current_level

    def track_token_usage(
        self,
        token_count: int,
        domain_count: int,
        tool_count: int,
        run_id: str,
    ) -> None:
        """
        Track token usage metrics for observability.

        Sends metrics to Prometheus for:
        - Token distribution analysis
        - Fallback trigger patterns
        - Optimization opportunities

        Args:
            token_count: Total token count
            domain_count: Number of domains in catalogue
            tool_count: Number of tools in catalogue
            run_id: Unique run identifier
        """
        # Track histogram
        planner_token_count.observe(token_count)

        # Determine safety status
        fallback_level = self.get_fallback_level(token_count)
        is_safe = fallback_level == FallbackLevel.FULL_CATALOGUE

        logger.info(
            "token_counter_usage_tracked",
            run_id=run_id,
            token_count=token_count,
            domain_count=domain_count,
            tool_count=tool_count,
            fallback_level=fallback_level,
            is_safe=is_safe,
        )

    def clear_cache(self) -> None:
        """Clear the token count cache."""
        self._cache.clear()
        logger.debug("token_counter_cache_cleared")


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_token_counter_instance: TokenCounterService | None = None


def get_token_counter(settings: Settings | None = None) -> TokenCounterService:
    """
    Get singleton TokenCounterService instance.

    Args:
        settings: Optional Settings object for configurable thresholds.
                  Only used on first call (singleton creation).

    Returns:
        Shared TokenCounterService instance
    """
    global _token_counter_instance
    if _token_counter_instance is None:
        _token_counter_instance = TokenCounterService(settings=settings)
    return _token_counter_instance


def reset_token_counter() -> None:
    """
    Reset singleton instance (for testing or reconfiguration).
    """
    global _token_counter_instance
    _token_counter_instance = None


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "TokenCounterService",
    "FallbackLevel",
    "get_token_counter",
    "reset_token_counter",
    "TOKEN_THRESHOLD_SAFE",
    "TOKEN_THRESHOLD_WARNING",
    "TOKEN_THRESHOLD_CRITICAL",
    "TOKEN_THRESHOLD_MAX",
]
