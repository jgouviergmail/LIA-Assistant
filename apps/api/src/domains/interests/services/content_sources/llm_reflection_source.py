"""
LLM Reflection Content Source for Interest Notifications.

Generates original AI insights and reflections on topics when other
sources (Brave Search, Perplexity) are not available or don't provide
suitable content. Acts as a fallback source.

Features:
- Original AI-generated content
- No external API dependencies (uses configured LLM)
- Always available (fallback)
- Its tokens travel with the content (``ContentResult.tokens_in/out``) and are
  billed ONCE, by the run that asked for it: the interest sweep and the
  heartbeat enrichment both add them to what they hand the runner. Billing them
  here too, under a run of its own, charged every reflection twice (measured on
  dev 2026-09-27, ADR-263 amendment 2026-09-27).

References:
    - Prompt: prompts/v1/interest_llm_reflection_prompt.txt
"""

import uuid
from datetime import UTC, datetime
from time import time

from src.core.i18n import get_language_name
from src.domains.agents.prompts import load_prompt
from src.domains.interests.services.content_sources.base import ContentResult
from src.infrastructure.cache.pricing_cache import capture_pricing_snapshot
from src.infrastructure.llm import get_llm
from src.infrastructure.llm.invoke_helpers import invoke_with_instrumentation
from src.infrastructure.llm.token_capture import TokenCaptureHandler
from src.infrastructure.llm.usage_metadata import model_name_of
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
            model_name = model_name_of(llm) or "unknown"
            started_at = time()
            pricing_snapshot = capture_pricing_snapshot()

            session_id = f"llm_reflection_{uuid.uuid4().hex[:8]}"
            capture = TokenCaptureHandler(model_name)
            from langchain_core.runnables import RunnableConfig

            from src.infrastructure.proactive.tracking import (
                ambient_run_id,
                bill_captured_usage,
                capture_spend_on_failure,
            )

            try:
                owner = uuid.UUID(str(user_id)) if user_id is not None else None
            except ValueError, TypeError:
                owner = None

            async with capture_spend_on_failure(
                capture,
                user_id=owner,
                task_type="interest_generation",
                target_id=topic,
                model_name=model_name,
                source="proactive",
                run_id=ambient_run_id(),
            ):
                result = await invoke_with_instrumentation(
                    llm=llm,
                    llm_type="interest_llm_reflection",
                    messages=prompt,
                    session_id=session_id,
                    user_id=user_id or "system",
                    config=RunnableConfig(callbacks=[capture]),
                )
                capture.ensure_response_record(
                    result, model_name=model_name, started_at=started_at, snapshot=pricing_snapshot
                )
                content = result.text
                records = capture.get_billing_records(model_name)

                if not content or len(content.strip()) < 20:
                    logger.debug(
                        "llm_reflection_source_empty_content",
                        topic=topic,
                        content_length=len(content) if content else 0,
                    )
                    await bill_captured_usage(
                        capture,
                        user_id=owner,
                        task_type="interest_generation",
                        target_id=topic,
                        model_name=model_name,
                        source="proactive",
                        run_id=ambient_run_id(),
                        failed=True,
                        llm_type="interest_content",
                    )
                    return None

                content = content.strip()
                if len(content) > 500:
                    content = content[:500] + "..."
                paid_result = ContentResult(
                    content=content,
                    raw_content=content,
                    source=self.source_name,
                    tokens_in=capture.tokens_in,
                    tokens_out=capture.tokens_out,
                    tokens_cache=capture.tokens_cache,
                    tokens_cache_write=capture.tokens_cache_write,
                    billing_records=records,
                    billing_capture=capture,
                    metadata={
                        "model": records[-1].model_name if records else model_name,
                        "language": user_language,
                        "category": category or "general",
                        "generated_at": current_datetime,
                    },
                )
                logger.info(
                    "llm_reflection_source_content_generated",
                    topic_length=len(topic),
                    content_length=len(content),
                    language=user_language,
                    user_id=user_id,
                    tokens_in=capture.tokens_in,
                    tokens_out=capture.tokens_out,
                )
                return paid_result

        except Exception as e:
            logger.warning(
                "llm_reflection_source_generation_failed",
                topic_length=len(topic),
                user_id=user_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            return None

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
