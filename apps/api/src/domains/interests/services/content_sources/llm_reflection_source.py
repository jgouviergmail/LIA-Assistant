"""
LLM Reflection Content Source for Interest Notifications.

Generates original AI insights and reflections on topics when other
sources (Brave Search, Perplexity) are not available or don't provide
suitable content. Acts as a fallback source.

Features:
- Original AI-generated content
- No external API dependencies (uses configured LLM)
- Always available (fallback)
- Token tracking via TrackingContext

References:
    - Prompt: prompts/v1/interest_llm_reflection_prompt.txt
"""

import uuid
from datetime import UTC, datetime
from uuid import UUID

from langchain_core.messages import AIMessage

from src.core.config import settings
from src.core.i18n_types import get_language_name
from src.core.llm_config_helper import get_llm_config_for_agent
from src.domains.agents.prompts import load_prompt
from src.domains.interests.services.content_sources.base import ContentResult
from src.infrastructure.llm import get_llm
from src.infrastructure.llm.invoke_helpers import invoke_with_instrumentation
from src.infrastructure.llm.token_utils import extract_llm_tokens
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


class LLMReflectionContentSource:
    """
    LLM-based content source for interest notifications (fallback).

    Generates original insights and reflections by:
    1. Using configured LLM with reflection prompt
    2. Generating engaging content about the topic
    3. No external dependencies - always available

    Used as fallback when Wikipedia and Perplexity don't find content.

    Example:
        >>> source = LLMReflectionContentSource()
        >>> result = await source.generate(
        ...     topic="machine learning",
        ...     user_language="fr",
        ... )
        >>> if result:
        ...     print(result.content)
    """

    source_name: str = "llm_reflection"

    def __init__(self) -> None:
        """Initialize LLM reflection content source."""
        self._prompt_template: str | None = None

    def _get_prompt(self) -> str:
        """
        Load the LLM reflection prompt from file.

        Returns:
            Prompt template string
        """
        if self._prompt_template is None:
            self._prompt_template = str(load_prompt("interest_llm_reflection_prompt"))
        return self._prompt_template

    async def generate(
        self,
        topic: str,
        user_language: str,
        existing_embeddings: list[list[float]] | None = None,
        user_id: str | None = None,
        category: str | None = None,
    ) -> ContentResult | None:
        """
        Generate content using LLM reflection.

        Creates an original insight or reflection about the topic using
        the configured LLM model.

        Args:
            topic: Interest topic to generate content for
            user_language: User's language code
            existing_embeddings: Not used (dedup handled at generator level)
            user_id: Optional user ID for token tracking
            category: Optional interest category for context

        Returns:
            ContentResult with LLM-generated reflection, or None if failed
        """
        try:
            logger.debug(
                "llm_reflection_source_generating",
                topic=topic,
                language=user_language,
                user_id=user_id,
            )

            current_datetime = datetime.now(tz=UTC).strftime("%d/%m/%Y %H:%M")

            prompt = self._get_prompt().format(
                interest_topic=topic,
                interest_category=category or "general",
                user_language=get_language_name(user_language),
                current_datetime=current_datetime,
            )

            llm = get_llm("interest_content")

            session_id = f"llm_reflection_{uuid.uuid4().hex[:8]}"

            result = await invoke_with_instrumentation(
                llm=llm,
                llm_type="interest_llm_reflection",
                messages=prompt,
                session_id=session_id,
                user_id=user_id or "system",
            )

            content = result.content if isinstance(result.content, str) else str(result.content)

            if not content or len(content.strip()) < 20:
                logger.debug(
                    "llm_reflection_source_empty_content",
                    topic=topic,
                    content_length=len(content) if content else 0,
                )
                return None

            content = content.strip()
            if len(content) > 500:
                content = content[:500] + "..."

            # Extract token usage from LLM response
            tokens_in, tokens_out = extract_llm_tokens(result)

            if user_id:
                await self._persist_tokens(
                    user_id=user_id,
                    session_id=session_id,
                    result=result,
                    model_name=get_llm_config_for_agent(settings, "interest_content").model,
                )

            logger.info(
                "llm_reflection_source_content_generated",
                topic=topic,
                content_length=len(content),
                language=user_language,
                user_id=user_id,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
            )

            return ContentResult(
                content=content,
                source=self.source_name,
                raw_content=content,
                citations=[],
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                metadata={
                    "model": get_llm_config_for_agent(settings, "interest_content").model,
                    "language": user_language,
                    "category": category or "general",
                    "generated_at": current_datetime,
                },
            )

        except Exception as e:
            logger.warning(
                "llm_reflection_source_generation_failed",
                topic=topic,
                user_id=user_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            return None

    async def _persist_tokens(
        self,
        user_id: str,
        session_id: str,
        result: AIMessage,
        model_name: str,
    ) -> None:
        """
        Persist token usage from LLM reflection to database.

        Args:
            user_id: User ID for statistics
            session_id: Session ID for tracking
            result: AIMessage with usage_metadata
            model_name: LLM model used
        """
        from src.domains.chat.service import TrackingContext

        try:
            usage_metadata = getattr(result, "usage_metadata", None)
            if not usage_metadata:
                return

            raw_input_tokens = usage_metadata.get("input_tokens", 0)
            output_tokens = usage_metadata.get("output_tokens", 0)

            input_details = usage_metadata.get("input_token_details", {})
            cached_tokens = input_details.get("cache_read", 0) if input_details else 0
            input_tokens = raw_input_tokens - cached_tokens

            if input_tokens == 0 and output_tokens == 0:
                return

            run_id = f"llm_reflection_{uuid.uuid4().hex[:12]}"

            async with TrackingContext(
                run_id=run_id,
                user_id=UUID(user_id),
                session_id=session_id,
                conversation_id=None,
                auto_commit=False,
            ) as tracker:
                await tracker.record_node_tokens(
                    node_name="interest_llm_reflection",
                    model_name=model_name,
                    prompt_tokens=input_tokens,
                    completion_tokens=output_tokens,
                    cached_tokens=cached_tokens,
                )
                await tracker.commit()

            logger.debug(
                "llm_reflection_tokens_persisted",
                user_id=user_id,
                run_id=run_id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )

        except Exception as e:
            logger.error(
                "llm_reflection_tokens_persistence_failed",
                user_id=user_id,
                error=str(e),
            )

    def is_available(self, user_id: str | None = None) -> bool:
        """
        Check if LLM reflection source is available.

        LLM reflection is always available as it uses the configured LLM
        without external dependencies.

        Args:
            user_id: Not used (LLM doesn't need per-user auth)

        Returns:
            Always True
        """
        return True

    async def close(self) -> None:
        """Cleanup resources (no-op for LLM source)."""
        pass
