"""
Content Source Strategy Protocol for Interest Notifications.

Defines the interface for content generation sources used by proactive
interest notifications. Implements the Strategy pattern for extensibility.

Available implementations:
- BraveSearchContentSource: Web search with recent news and citations (primary)
- PerplexityContentSource: AI-synthesized web search with citations (primary)
- LLMReflectionContentSource: AI-generated insights (fallback)

Architecture:
    InterestContentGenerator
           |
    [ContentSourceStrategy Protocol]
           |
    +------+------+------+
    |      |      |      |
  Brave  Perplexity  LLM  (future sources)

References:
    - Pattern: Strategy Pattern (GoF)
"""

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class ContentResult:
    """
    Result from a content source generation.

    Attributes:
        content: Generated content text (max ~500 chars recommended)
        source: Source identifier ("brave", "perplexity", "llm_reflection")
        raw_content: Original unprocessed content from the source
        citations: Source citations/URLs if available
        embedding: Content embedding for deduplication (384 dims, E5-small)
        metadata: Additional source-specific metadata
    """

    content: str
    source: str
    raw_content: str = ""
    citations: list[str] = field(default_factory=list)
    embedding: list[float] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate content result."""
        if not self.content:
            raise ValueError("Content cannot be empty")
        if not self.source:
            raise ValueError("Source cannot be empty")


@runtime_checkable
class ContentSourceStrategy(Protocol):
    """
    Protocol for content generation sources.

    Each implementation provides a different way to generate content
    for interest notifications:

    - BraveSearchContentSource: Web search with citations (primary)
    - PerplexityContentSource: AI-synthesized web search (primary)
    - LLMReflectionContentSource: AI-generated insights (fallback)

    Example:
        >>> class BraveSearchContentSource:
        ...     source_name = "brave"
        ...
        ...     async def generate(
        ...         self,
        ...         topic: str,
        ...         user_language: str,
        ...         existing_embeddings: list[list[float]] | None = None,
        ...         user_id: str | None = None,
        ...     ) -> ContentResult | None:
        ...         # Implementation
        ...         pass
        ...
        ...     def is_available(self, user_id: str | None = None) -> bool:
        ...         return user_id is not None  # Brave needs per-user API key
    """

    source_name: str
    """Unique identifier for this source (e.g., 'brave', 'perplexity')."""

    async def generate(
        self,
        topic: str,
        user_language: str,
        existing_embeddings: list[list[float]] | None = None,
    ) -> ContentResult | None:
        """
        Generate content for a given topic.

        Args:
            topic: Interest topic to generate content for
            user_language: User's language code (e.g., "fr", "en")
            existing_embeddings: Embeddings of recent notifications for dedup

        Returns:
            ContentResult with generated content, or None if generation failed
            or no relevant content found.

        Note:
            Implementations should:
            - Return None on failure (not raise exceptions)
            - Check for content similarity against existing_embeddings if provided
            - Log warnings/errors appropriately
            - Include citations when available
        """
        ...

    def is_available(self, user_id: str | None = None) -> bool:
        """
        Check if this source is available for use.

        Some sources (like Perplexity) require user-specific API keys.
        Others (like Wikipedia) are always available.

        Args:
            user_id: Optional user ID for sources requiring per-user auth

        Returns:
            True if the source can be used, False otherwise
        """
        ...


@dataclass
class ContentGenerationContext:
    """
    Context for content generation.

    Provides all necessary information for generating content for an interest.
    """

    interest_id: str
    topic: str
    category: str
    user_id: str
    user_language: str
    user_timezone: str = "UTC"
    personality_instruction: str | None = None
    recent_notification_embeddings: list[list[float]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
