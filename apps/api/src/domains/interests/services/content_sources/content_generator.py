"""
Interest Content Generator - Orchestrates content sources.

Coordinates multiple content sources (Brave Search, Perplexity, LLM) with
intelligent fallback and deduplication logic for interest notifications.

Architecture:
    InterestContentGenerator
           |
    [ContentSourceStrategy Protocol]
           |
    +------+------+------+
    |      |      |      |
  Brave  Perplexity  LLM  (fallback)

Flow:
1. Shuffle primary sources (Brave, Perplexity) randomly
2. Try each source until content is generated
3. Check deduplication against recent notifications
4. Fall back to LLM reflection if needed
5. If all content is duplicate, retry once with a diversity angle

References:
    - Pattern: Strategy Pattern with fallback chain
"""

import random
from dataclasses import dataclass, replace
from typing import Any

from src.core.config import settings
from src.core.constants import INTEREST_CONTENT_DIVERSITY_ANGLES
from src.domains.interests.helpers import normalize_language_code
from src.domains.interests.services.content_sources.base import (
    ContentGenerationContext,
    ContentResult,
    ContentSourceStrategy,
)
from src.domains.interests.services.content_sources.brave_source import (
    BraveSearchContentSource,
)
from src.domains.interests.services.content_sources.llm_reflection_source import (
    LLMReflectionContentSource,
)
from src.domains.interests.services.content_sources.perplexity_source import (
    PerplexityContentSource,
)
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


@dataclass
class GenerationResult:
    """
    Result from content generation orchestration.

    Attributes:
        success: Whether content was successfully generated
        content_result: The generated content (if success)
        source_tried: List of sources attempted
        source_used: The source that produced the content
        dedup_skipped: Whether content was skipped due to deduplication
        error: Error message if generation failed
    """

    success: bool
    content_result: ContentResult | None = None
    sources_tried: list[str] | None = None
    source_used: str | None = None
    dedup_skipped: bool = False
    error: str | None = None


class InterestContentGenerator:
    """
    Orchestrates content generation from multiple sources.

    Manages the content generation pipeline:
    1. Primary sources (Brave Search, Perplexity) - tried in random order
    2. Fallback source (LLM reflection) - used if primary sources fail
    3. Deduplication - checks against recent notification embeddings

    Example:
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
        ...     print(f"Source: {result.source_used}")
    """

    def __init__(self) -> None:
        """Initialize content generator with all sources."""
        self._brave_source = BraveSearchContentSource()
        self._perplexity_source = PerplexityContentSource()
        self._llm_source = LLMReflectionContentSource()

        self._primary_sources: list[ContentSourceStrategy] = [
            self._brave_source,
            self._perplexity_source,
        ]

    async def generate(
        self,
        context: ContentGenerationContext,
    ) -> GenerationResult:
        """
        Generate content for an interest using available sources.

        Tries sources in random order (primary first, then fallback),
        with deduplication check against recent notifications. If all sources
        produce duplicate content, retries once with a diversity angle appended
        to the topic (e.g., "Films de SF : perspectives futures").

        Args:
            context: Generation context with interest details and user info

        Returns:
            GenerationResult with content or error information
        """
        sources_tried: list[str] = []

        try:
            logger.debug(
                "content_generation_starting",
                interest_id=context.interest_id,
                topic=context.topic,
                user_id=context.user_id,
                language=context.user_language,
            )

            # First attempt with original topic
            result = await self._try_all_sources(context, sources_tried)

            if result is not None:
                return result

            # All sources returned duplicate content — retry with diversity angle
            angle = self._pick_diversity_angle(context.user_language)
            if angle is None:
                return GenerationResult(
                    success=False,
                    sources_tried=sources_tried,
                    dedup_skipped=True,
                    error="All generated content was duplicate",
                )

            angled_topic = self._apply_angle_to_topic(context.topic, angle)

            logger.info(
                "content_generation_diversity_retry",
                original_topic=context.topic,
                angled_topic=angled_topic,
                angle=angle,
                user_id=context.user_id,
            )

            angled_context = replace(context, topic=angled_topic)

            retry_result = await self._try_all_sources(
                angled_context, sources_tried, retry_label=angle
            )

            if retry_result is not None:
                return retry_result

            # Retry also produced only duplicates
            logger.warning(
                "content_generation_diversity_retry_failed",
                topic=context.topic,
                angle=angle,
                user_id=context.user_id,
            )

            return GenerationResult(
                success=False,
                sources_tried=sources_tried,
                dedup_skipped=True,
                error="All generated content was duplicate (including diversity retry)",
            )

        except Exception as e:
            logger.error(
                "content_generation_error",
                topic=context.topic,
                user_id=context.user_id,
                error=str(e),
                error_type=type(e).__name__,
            )

            return GenerationResult(
                success=False,
                sources_tried=sources_tried,
                error=str(e),
            )

    async def _try_all_sources(
        self,
        context: ContentGenerationContext,
        sources_tried: list[str],
        retry_label: str | None = None,
    ) -> GenerationResult | None:
        """
        Try all sources (primary + fallback) for content generation.

        Args:
            context: Generation context with interest details and user info
            sources_tried: Mutable list to track which sources were attempted
            retry_label: If set, annotates source names (e.g., "brave(retry:angle)")

        Returns:
            GenerationResult(success=True) if non-duplicate content found.
            GenerationResult(success=False) if no source produced content at all
                (genuine generation failure — no retry useful).
            None if at least one source produced content but ALL were duplicates
                (caller should retry with diversity angle).
        """
        had_duplicate = False
        suffix = f"(retry:{retry_label})" if retry_label else ""

        primary_sources = self._get_shuffled_primary_sources(context.user_id)

        for source in primary_sources:
            source_name = source.source_name
            sources_tried.append(f"{source_name}{suffix}")

            if not source.is_available(context.user_id):
                logger.debug(
                    "content_source_not_available",
                    source=source_name,
                    user_id=context.user_id,
                )
                continue

            content = await self._try_source(source, context)

            if content is None:
                logger.debug(
                    "content_source_no_result",
                    source=source_name,
                    topic=context.topic,
                )
                continue

            if self._is_duplicate(content, context.recent_notification_embeddings):
                logger.debug(
                    "content_source_duplicate_detected",
                    source=source_name,
                    topic=context.topic,
                )
                had_duplicate = True
                continue

            logger.info(
                "content_generation_success_primary",
                source=source_name,
                topic=context.topic,
                content_length=len(content.content),
                user_id=context.user_id,
            )

            return GenerationResult(
                success=True,
                content_result=content,
                sources_tried=sources_tried,
                source_used=source_name,
            )

        # Try LLM fallback
        sources_tried.append(f"{self._llm_source.source_name}{suffix}")

        logger.debug(
            "content_generation_trying_fallback",
            topic=context.topic,
            user_id=context.user_id,
            primary_sources_tried=len(primary_sources),
        )

        content = await self._try_source(self._llm_source, context)

        if content is not None:
            if self._is_duplicate(content, context.recent_notification_embeddings):
                logger.debug(
                    "content_generation_fallback_duplicate",
                    topic=context.topic,
                    user_id=context.user_id,
                )
                # At least LLM produced content but it was duplicate
                return None

            logger.info(
                "content_generation_success_fallback",
                topic=context.topic,
                content_length=len(content.content),
                user_id=context.user_id,
            )

            return GenerationResult(
                success=True,
                content_result=content,
                sources_tried=sources_tried,
                source_used=self._llm_source.source_name,
            )

        # No source produced content at all
        if had_duplicate:
            # Some primary source had content but it was duplicate, LLM produced nothing
            return None

        logger.warning(
            "content_generation_all_sources_failed",
            topic=context.topic,
            user_id=context.user_id,
            sources_tried=sources_tried,
        )

        return GenerationResult(
            success=False,
            sources_tried=sources_tried,
            error="All content sources failed to generate content",
        )

    def _get_shuffled_primary_sources(self, user_id: str) -> list:
        """
        Get primary sources in randomized order.

        Shuffles primary sources (Brave, Perplexity) to ensure
        variety in content and avoid always hitting the same API first.

        Args:
            user_id: User ID for logging

        Returns:
            Shuffled list of primary content sources
        """
        sources = list(self._primary_sources)
        random.shuffle(sources)

        logger.debug(
            "content_sources_order",
            order=[s.source_name for s in sources],
            user_id=user_id,
        )

        return sources

    async def _try_source(
        self, source: Any, context: ContentGenerationContext
    ) -> ContentResult | None:
        """
        Try to generate content from a single source.

        All sources accept user_id. LLM reflection additionally needs category.
        Generates embedding for the content for deduplication.

        Args:
            source: Content source to try
            context: Generation context

        Returns:
            ContentResult if successful, None otherwise
        """
        try:
            kwargs: dict[str, Any] = {
                "topic": context.topic,
                "user_language": context.user_language,
                "existing_embeddings": context.recent_notification_embeddings,
                "user_id": context.user_id,
            }
            # category is specific to LLM reflection
            if source.source_name == "llm_reflection":
                kwargs["category"] = context.category

            result: ContentResult | None = await source.generate(**kwargs)

            # Generate embedding for deduplication check
            if result and not result.embedding:
                result.embedding = self._generate_content_embedding(result.content)

            return result

        except Exception as e:
            logger.warning(
                "content_source_exception",
                source=source.source_name,
                topic=context.topic,
                error=str(e),
                error_type=type(e).__name__,
            )
            return None

    def _generate_content_embedding(self, content: str) -> list[float] | None:
        """
        Generate embedding for content using E5-small.

        Delegates to shared helper for consistency across interest domain.

        Args:
            content: Text content to embed

        Returns:
            384-dimensional embedding vector, or None if generation fails
        """
        from src.domains.interests.helpers import generate_interest_embedding

        return generate_interest_embedding(content)

    def _is_duplicate(
        self,
        content: ContentResult,
        recent_embeddings: list[list[float]] | None,
    ) -> bool:
        """
        Check if content is a duplicate of recent notifications.

        Uses embedding similarity to detect semantic duplicates.
        A duplicate is content that is too similar to something already sent.

        Args:
            content: Generated content to check
            recent_embeddings: Embeddings of recent notifications

        Returns:
            True if content is a duplicate, False otherwise
        """
        if not recent_embeddings:
            return False

        if not content.embedding:
            return False

        threshold = settings.interest_content_similarity_threshold

        from src.infrastructure.llm.local_embeddings import cosine_similarity

        max_similarity = 0.0
        for existing_embedding in recent_embeddings:
            similarity = cosine_similarity(content.embedding, existing_embedding)
            max_similarity = max(max_similarity, similarity)

            if similarity >= threshold:
                logger.info(
                    "content_duplicate_detected",
                    similarity=round(similarity, 3),
                    threshold=threshold,
                    source=content.source,
                    embeddings_compared=len(recent_embeddings),
                )
                return True

        logger.info(
            "content_dedup_passed",
            max_similarity=round(max_similarity, 3),
            threshold=threshold,
            source=content.source,
            embeddings_compared=len(recent_embeddings),
        )
        return False

    @staticmethod
    def _pick_diversity_angle(user_language: str) -> str | None:
        """
        Pick a random diversity angle for the given language.

        Uses INTEREST_CONTENT_DIVERSITY_ANGLES to select an angle that will
        be appended to the topic for a retry attempt, producing different
        search results and LLM output.

        Args:
            user_language: User's language code (e.g., "fr", "fr-FR")

        Returns:
            Random angle string, or None if no angles available
        """
        base_lang = normalize_language_code(user_language)
        angles = INTEREST_CONTENT_DIVERSITY_ANGLES.get(
            base_lang, INTEREST_CONTENT_DIVERSITY_ANGLES.get("en")
        )

        if not angles:
            return None

        return random.choice(angles)

    @staticmethod
    def _apply_angle_to_topic(topic: str, angle: str) -> str:
        """
        Append a diversity angle to a topic.

        Args:
            topic: Original interest topic
            angle: Diversity angle to append

        Returns:
            Modified topic string (e.g., "Films de SF : perspectives futures")
        """
        return f"{topic} : {angle}"

    async def close(self) -> None:
        """Cleanup all content sources."""
        await self._brave_source.close()
        await self._perplexity_source.close()
        await self._llm_source.close()

        logger.debug("content_generator_closed")
