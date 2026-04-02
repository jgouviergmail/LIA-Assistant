"""
Interest Proactive Task implementation.

Implements the ProactiveTask protocol for interest-based notifications.
Selects top weighted interests and generates content using the content sources.

Flow:
1. check_eligibility: Verify user has interests_enabled
2. select_target: Pick random interest from top 20%
3. generate_content: Use InterestContentGenerator
4. on_feedback: Update interest weights
5. on_notification_sent: Update last_notified_at

References:
    - Protocol: src/infrastructure/proactive/base.py
"""

import hashlib
import random
import uuid
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from src.core.config import settings
from src.core.i18n_types import get_language_name
from src.domains.interests.models import UserInterest
from src.domains.interests.repository import (
    InterestNotificationRepository,
    InterestRepository,
)
from src.domains.interests.services.content_sources import (
    ContentGenerationContext,
    InterestContentGenerator,
)
from src.infrastructure.database import get_db_context
from src.infrastructure.llm.token_utils import extract_llm_tokens
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.proactive.base import ContentSource, ProactiveTaskResult

logger = get_logger(__name__)


class InterestProactiveTask:
    """
    Proactive task for interest-based notifications.

    Implements the ProactiveTask protocol to:
    1. Check if user is eligible (interests_enabled)
    2. Select top weighted interest not in cooldown
    3. Generate content via Wikipedia/Perplexity/LLM
    4. Handle user feedback (thumbs up/down/block)

    Example:
        >>> task = InterestProactiveTask()
        >>> if await task.check_eligibility(user_id, settings, now):
        ...     target = await task.select_target(user_id)
        ...     if target:
        ...         result = await task.generate_content(user_id, target, "fr")
        ...         if result.success:
        ...             print(result.content)
    """

    task_type: str = "interest"

    def __init__(self) -> None:
        """Initialize interest proactive task."""
        self._content_generator: InterestContentGenerator | None = None

    def _get_content_generator(self) -> InterestContentGenerator:
        """Lazy initialization of content generator."""
        if self._content_generator is None:
            self._content_generator = InterestContentGenerator()
        return self._content_generator

    async def check_eligibility(
        self,
        user_id: UUID,
        user_settings: dict[str, Any],
        now: datetime,
    ) -> bool:
        """
        Check if user is eligible for interest notifications.

        Task-specific check: only verify interests_enabled setting.
        Common checks (timezone, quota, cooldown) handled by EligibilityChecker.

        Args:
            user_id: User UUID
            user_settings: User settings dict
            now: Current datetime in user's timezone

        Returns:
            True if interests_enabled is True
        """
        interests_enabled = user_settings.get("interests_enabled", False)

        if not interests_enabled:
            logger.debug(
                "interest_task_user_disabled",
                user_id=str(user_id),
            )
            return False

        logger.debug(
            "interest_task_eligible",
            user_id=str(user_id),
        )

        return True

    async def select_target(
        self,
        user_id: UUID,
    ) -> UserInterest | None:
        """
        Select an interest to notify about.

        Selection algorithm:
        1. Get all active interests
        2. Calculate effective weights (with decay)
        3. Filter out interests in cooldown
        4. Select top N% (configurable)
        5. Random selection from top N%

        Args:
            user_id: User UUID

        Returns:
            Selected UserInterest or None if no eligible interests
        """
        try:
            async with get_db_context() as db:
                repo = InterestRepository(db)

                top_interests = await repo.get_top_weighted_interests(
                    user_id=user_id,
                    top_percent=settings.interest_top_percent,
                    min_count=1,
                    exclude_in_cooldown=True,
                    cooldown_hours=settings.interest_per_topic_cooldown_hours,
                )

                if not top_interests:
                    logger.debug(
                        "interest_task_no_eligible_interests",
                        user_id=str(user_id),
                    )
                    return None

                selected_interest, weight = random.choice(top_interests)

                logger.info(
                    "interest_task_target_selected",
                    user_id=str(user_id),
                    interest_id=str(selected_interest.id),
                    topic=selected_interest.topic[:50],
                    weight=round(weight, 3),
                    candidates_count=len(top_interests),
                )

                return selected_interest

        except Exception as e:
            logger.error(
                "interest_task_select_target_failed",
                user_id=str(user_id),
                error=str(e),
                error_type=type(e).__name__,
            )
            return None

    async def generate_content(
        self,
        user_id: UUID,
        target: UserInterest,
        user_language: str,
    ) -> ProactiveTaskResult:
        """
        Generate content for the selected interest.

        Uses InterestContentGenerator with fallback chain:
        1. Wikipedia (encyclopedic facts)
        2. Perplexity (recent news, if API key configured)
        3. LLM reflection (fallback)

        Args:
            user_id: User UUID
            target: Selected UserInterest
            user_language: User's language code

        Returns:
            ProactiveTaskResult with generated content
        """
        try:
            # Get user's personality instruction for content presentation
            personality_instruction = await self._get_user_personality(user_id)

            recent_embeddings = await self._get_recent_notification_embeddings(
                user_id=user_id,
                interest_id=target.id,
            )

            context = ContentGenerationContext(
                interest_id=str(target.id),
                topic=target.topic,
                category=target.category,
                user_id=str(user_id),
                user_language=user_language,
                personality_instruction=personality_instruction,
                recent_notification_embeddings=recent_embeddings,
            )

            generator = self._get_content_generator()
            generation_result = await generator.generate(context)

            if not generation_result.success:
                logger.warning(
                    "interest_task_content_generation_failed",
                    user_id=str(user_id),
                    interest_id=str(target.id),
                    topic=target.topic[:50],
                    sources_tried=generation_result.sources_tried,
                    error=generation_result.error,
                )

                return ProactiveTaskResult.failure(
                    error=generation_result.error or "Content generation failed",
                    source=ContentSource.CUSTOM,
                )

            content_result = generation_result.content_result
            assert content_result is not None

            presented_content, presentation_tokens_in, presentation_tokens_out = (
                await self._present_content(
                    raw_content=content_result.content,
                    topic=target.topic,
                    category=target.category,
                    source=content_result.source,
                    citations=content_result.citations,
                    user_language=user_language,
                    personality_instruction=personality_instruction,
                    user_id=user_id,
                )
            )

            content_source = self._map_source(content_result.source)

            # Accumulate tokens from both phases: generation + presentation
            total_tokens_in = content_result.tokens_in + presentation_tokens_in
            total_tokens_out = content_result.tokens_out + presentation_tokens_out

            logger.info(
                "interest_task_content_generated",
                user_id=str(user_id),
                interest_id=str(target.id),
                topic=target.topic[:50],
                source=content_result.source,
                content_length=len(presented_content),
                tokens_in=total_tokens_in,
                tokens_out=total_tokens_out,
            )

            return ProactiveTaskResult(
                success=True,
                content=presented_content,
                source=content_source,
                target_id=str(target.id),
                tokens_in=total_tokens_in,
                tokens_out=total_tokens_out,
                model_name=settings.interest_content_llm_model,
                metadata={
                    "interest_topic": target.topic,
                    "interest_category": target.category,
                    "source": content_result.source,  # wikipedia, perplexity, or llm_reflection
                    "citations": content_result.citations,
                    "sources_tried": generation_result.sources_tried,
                    # Token info for frontend display
                    "tokens_in": total_tokens_in,
                    "tokens_out": total_tokens_out,
                    "model_name": settings.interest_content_llm_model,
                },
            )

        except Exception as e:
            logger.error(
                "interest_task_generate_content_failed",
                user_id=str(user_id),
                interest_id=str(target.id),
                error=str(e),
                error_type=type(e).__name__,
            )

            return ProactiveTaskResult.failure(
                error=str(e),
                source=ContentSource.CUSTOM,
            )

    async def _present_content(
        self,
        raw_content: str,
        topic: str,
        category: str,
        source: str,
        citations: list[str],
        user_language: str,
        personality_instruction: str | None = None,
        user_id: UUID | None = None,
    ) -> tuple[str, int, int]:
        """
        Format raw content for presentation using LLM.

        Uses the interest_content_prompt for natural formatting.

        Args:
            raw_content: Raw content from source
            topic: Interest topic
            category: Interest category
            source: Content source name
            citations: Source citations
            user_language: User's language
            personality_instruction: Assistant personality for content styling
            user_id: User UUID for psyche context injection

        Returns:
            Tuple of (formatted_content, tokens_in, tokens_out)
        """

        from src.core.llm_agent_config import LLMAgentConfig
        from src.domains.agents.prompts import load_prompt
        from src.domains.personalities.constants import DEFAULT_PERSONALITY_PROMPT
        from src.infrastructure.llm import get_llm
        from src.infrastructure.llm.invoke_helpers import invoke_with_instrumentation

        try:
            current_datetime = datetime.now(tz=UTC).strftime("%d/%m/%Y %H:%M")

            prompt = load_prompt("interest_content_prompt").format(
                personality_instruction=personality_instruction or DEFAULT_PERSONALITY_PROMPT,
                interest_topic=topic,
                interest_category=category,
                source_name=source,
                raw_content=raw_content,
                citations=", ".join(citations) if citations else "Aucune",
                user_language=get_language_name(user_language),
                current_datetime=current_datetime,
            )

            # Inject psyche context if user_id is available
            if user_id:
                try:
                    from src.domains.psyche.service import build_psyche_prompt_block

                    psyche_block = await build_psyche_prompt_block(
                        user_id=user_id, user_timezone=None
                    )
                    prompt += psyche_block
                except Exception:
                    pass  # Psyche injection is best-effort

            content_config = LLMAgentConfig(
                provider=settings.interest_content_llm_provider,
                model=settings.interest_content_llm_model,
                temperature=settings.interest_content_llm_temperature,
                max_tokens=settings.interest_content_llm_max_tokens,
                top_p=settings.interest_content_llm_top_p,
                frequency_penalty=settings.interest_content_llm_frequency_penalty,
                presence_penalty=settings.interest_content_llm_presence_penalty,
                reasoning_effort=settings.interest_content_llm_reasoning_effort,
            )

            llm = get_llm("response", config_override=content_config)

            result = await invoke_with_instrumentation(
                llm=llm,
                llm_type="interest_content_presentation",
                messages=prompt,
                session_id=f"interest_present_{uuid.uuid4().hex[:8]}",
                user_id="system",
            )

            presented = result.content if isinstance(result.content, str) else str(result.content)

            # Extract token usage from LLM response
            tokens_in, tokens_out = extract_llm_tokens(result)

            return presented.strip(), tokens_in, tokens_out

        except Exception as e:
            logger.warning(
                "interest_task_presentation_failed",
                error=str(e),
                fallback="raw_content",
            )
            return raw_content, 0, 0

    async def _get_recent_notification_embeddings(
        self,
        user_id: UUID,
        interest_id: UUID,
    ) -> list[list[float]]:
        """
        Get embeddings of recent notifications for deduplication.

        Args:
            user_id: User UUID
            interest_id: Interest UUID

        Returns:
            List of embedding vectors
        """
        try:
            async with get_db_context() as db:
                notif_repo = InterestNotificationRepository(db)
                lookback_days = getattr(settings, "interest_content_lookback_days", 30)
                recent = await notif_repo.get_recent_for_interest(
                    interest_id=interest_id,
                    days=lookback_days,
                )

                embeddings = []
                for notif in recent:
                    if notif.content_embedding:
                        embeddings.append(notif.content_embedding)

                logger.info(
                    "interest_dedup_embeddings_loaded",
                    user_id=str(user_id),
                    interest_id=str(interest_id),
                    lookback_days=lookback_days,
                    recent_notifications=len(recent),
                    embeddings_count=len(embeddings),
                )

                return embeddings

        except Exception as e:
            logger.warning(
                "interest_task_get_embeddings_failed",
                user_id=str(user_id),
                interest_id=str(interest_id),
                error=str(e),
            )
            return []

    async def _get_user_personality(self, user_id: UUID) -> str | None:
        """
        Get user's personality instruction for content presentation.

        Args:
            user_id: User UUID

        Returns:
            Personality prompt instruction or None if not found
        """
        try:
            async with get_db_context() as db:
                from src.domains.personalities.service import PersonalityService

                personality_service = PersonalityService(db)
                return await personality_service.get_prompt_instruction_for_user(user_id)

        except Exception as e:
            logger.warning(
                "interest_task_get_personality_failed",
                user_id=str(user_id),
                error=str(e),
            )
            return None

    def _map_source(self, source_name: str) -> ContentSource:
        """Map source name string to ContentSource enum."""
        mapping = {
            "wikipedia": ContentSource.WIKIPEDIA,
            "perplexity": ContentSource.PERPLEXITY,
            "llm_reflection": ContentSource.LLM_REFLECTION,
        }
        return mapping.get(source_name, ContentSource.CUSTOM)

    async def on_feedback(
        self,
        user_id: UUID,
        target: UserInterest,
        feedback: str,
    ) -> None:
        """
        Handle user feedback on the notification.

        Updates interest weights based on feedback:
        - thumbs_up: +2 positive_signals
        - thumbs_down: +2 negative_signals
        - block: status = BLOCKED

        Args:
            user_id: User UUID
            target: The interest that received feedback
            feedback: Feedback type
        """
        try:
            async with get_db_context() as db:
                repo = InterestRepository(db)

                interest = await repo.get_by_id(target.id)
                if not interest:
                    logger.warning(
                        "interest_task_feedback_interest_not_found",
                        user_id=str(user_id),
                        interest_id=str(target.id),
                    )
                    return

                await repo.apply_feedback(interest, feedback)
                await db.commit()

                logger.info(
                    "interest_task_feedback_applied",
                    user_id=str(user_id),
                    interest_id=str(target.id),
                    feedback=feedback,
                    new_positive=interest.positive_signals,
                    new_negative=interest.negative_signals,
                    new_status=interest.status,
                )

        except Exception as e:
            logger.error(
                "interest_task_feedback_failed",
                user_id=str(user_id),
                interest_id=str(target.id),
                feedback=feedback,
                error=str(e),
            )

    async def on_notification_sent(
        self,
        user_id: UUID,
        target: UserInterest,
        result: ProactiveTaskResult,
    ) -> None:
        """
        Called after notification is successfully sent.

        Updates:
        - Interest last_notified_at
        - Creates notification record for deduplication

        Args:
            user_id: User UUID
            target: The interest that was notified
            result: The content generation result
        """
        try:
            async with get_db_context() as db:
                interest_repo = InterestRepository(db)
                notif_repo = InterestNotificationRepository(db)

                interest = await interest_repo.get_by_id(target.id)
                if interest:
                    await interest_repo.mark_notified(interest)

                content_hash = ""
                content_embedding: list[float] | None = None

                if result.content:
                    content_hash = hashlib.sha256(result.content.encode("utf-8")).hexdigest()

                    # Generate embedding for deduplication of future content
                    from src.domains.interests.helpers import generate_interest_embedding

                    content_embedding = generate_interest_embedding(result.content)

                    if content_embedding:
                        logger.debug(
                            "interest_content_embedding_generated",
                            interest_id=str(target.id),
                            embedding_dim=len(content_embedding),
                        )

                run_id = f"interest_{target.id}_{uuid.uuid4().hex[:8]}"

                await notif_repo.create(
                    user_id=user_id,
                    interest_id=target.id,
                    run_id=run_id,
                    content_hash=content_hash,
                    source=result.source_name,
                    content_embedding=content_embedding,
                )

                await db.commit()

                logger.info(
                    "interest_task_notification_recorded",
                    user_id=str(user_id),
                    interest_id=str(target.id),
                    run_id=run_id,
                    source=result.source_name,
                )

        except Exception as e:
            logger.error(
                "interest_task_notification_record_failed",
                user_id=str(user_id),
                interest_id=str(target.id),
                error=str(e),
            )

    async def close(self) -> None:
        """Cleanup resources."""
        if self._content_generator:
            await self._content_generator.close()
            self._content_generator = None
