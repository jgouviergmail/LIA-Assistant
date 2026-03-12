"""
Content Sources for Interest Notifications.

This module provides multiple content sources for generating proactive
interest notifications. Uses the Strategy pattern for extensibility.

Available Sources:
- BraveSearchContentSource: Web search with recent news and citations (primary)
- PerplexityContentSource: AI-synthesized web search with citations (primary)
- LLMReflectionContentSource: AI-generated insights (fallback)

Main Components:
- ContentSourceStrategy: Protocol defining the source interface
- ContentResult: Result dataclass from content generation
- ContentGenerationContext: Context for generation requests
- InterestContentGenerator: Orchestrator coordinating all sources

Usage:
    >>> from src.domains.interests.services.content_sources import (
    ...     InterestContentGenerator,
    ...     ContentGenerationContext,
    ... )
    >>> generator = InterestContentGenerator()
    >>> context = ContentGenerationContext(
    ...     interest_id="uuid",
    ...     topic="machine learning",
    ...     category="technology",
    ...     user_id="user-uuid",
    ...     user_language="fr",
    ... )
    >>> result = await generator.generate(context)
    >>> if result.success:
    ...     print(result.content_result.content)

References:
    - Pattern: Strategy Pattern (GoF)
"""

from src.domains.interests.services.content_sources.base import (
    ContentGenerationContext,
    ContentResult,
    ContentSourceStrategy,
)
from src.domains.interests.services.content_sources.brave_source import (
    BraveSearchContentSource,
)
from src.domains.interests.services.content_sources.content_generator import (
    GenerationResult,
    InterestContentGenerator,
)
from src.domains.interests.services.content_sources.llm_reflection_source import (
    LLMReflectionContentSource,
)
from src.domains.interests.services.content_sources.perplexity_source import (
    PerplexityContentSource,
)

__all__ = [
    # Protocol and base classes
    "ContentSourceStrategy",
    "ContentResult",
    "ContentGenerationContext",
    # Orchestrator
    "InterestContentGenerator",
    "GenerationResult",
    # Individual sources
    "BraveSearchContentSource",
    "PerplexityContentSource",
    "LLMReflectionContentSource",
]
