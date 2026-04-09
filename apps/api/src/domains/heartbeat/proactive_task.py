"""
Heartbeat Proactive Task implementation.

Implements the ProactiveTask Protocol for heartbeat autonome notifications.
Key design: the LLM decision is in select_target() (not generate_content()),
so that a "skip" correctly maps to "no_target" in the runner (not "content_failed").

Two-phase LLM approach:
1. select_target(): Context aggregation + LLM decision (structured output)
2. generate_content(): Message rewrite with user personality + language
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import structlog

from src.core.config import get_settings
from src.domains.heartbeat.context_aggregator import ContextAggregator
from src.domains.heartbeat.prompts import (
    generate_heartbeat_message,
    get_heartbeat_decision,
)
from src.domains.heartbeat.schemas import HeartbeatTarget
from src.infrastructure.database import get_db_context
from src.infrastructure.proactive.base import ContentSource, ProactiveTaskResult

logger = structlog.get_logger(__name__)


class HeartbeatProactiveTask:
    """Proactive task for heartbeat autonome notifications.

    Implements the ProactiveTask protocol to:
    1. Aggregate context from multiple sources (calendar, weather, interests, etc.)
    2. Let LLM decide if notification is warranted (structured output)
    3. Generate personalized message with user's personality and language
    4. Record audit trail and store conversational context
    """

    task_type: str = "heartbeat"

    async def check_eligibility(
        self,
        user_id: UUID,
        user_settings: dict[str, Any],
        now: datetime,
    ) -> bool:
        """Check task-specific eligibility.

        Common checks (time window, quota, cooldown) are handled by
        EligibilityChecker. This only checks heartbeat-specific conditions.
        """
        return bool(user_settings.get("heartbeat_enabled", False))

    async def select_target(
        self,
        user_id: UUID,
    ) -> HeartbeatTarget | None:
        """Aggregate context and run LLM decision.

        Returns HeartbeatTarget if LLM decides to notify, None if skip.
        When None, the runner records "no_target" (semantically correct).
        """
        try:
            settings = get_settings()

            async with get_db_context() as db:
                from src.domains.auth.models import User

                user = await db.get(User, user_id)
                if not user:
                    return None

                # Early-exit: skip if user inactive for too long (save tokens)
                inactive_days = getattr(settings, "heartbeat_inactive_skip_days", 7)
                if user.last_login:
                    last_login = user.last_login
                    # Defensive: ensure timezone-aware for safe subtraction
                    if last_login.tzinfo is None:
                        last_login = last_login.replace(tzinfo=UTC)
                    days_since = (datetime.now(UTC) - last_login).days
                    if days_since > inactive_days:
                        logger.debug(
                            "heartbeat_skip_inactive_user",
                            user_id=str(user_id),
                            days_inactive=days_since,
                        )
                        return None

                # Aggregate context from all sources in parallel
                aggregator = ContextAggregator(db)
                context = await aggregator.aggregate(user_id, user)

            if not context.has_meaningful_context():
                logger.debug(
                    "heartbeat_skip_no_context",
                    user_id=str(user_id),
                    failed_sources=context.failed_sources,
                )
                return None

            # LLM Decision (structured output, cheap model)
            user_language = getattr(user, "language", settings.default_language)
            decision, tok_in, tok_out, tok_cache = await get_heartbeat_decision(
                context, user_language=user_language
            )

            if decision.action == "skip":
                logger.info(
                    "heartbeat_llm_skip",
                    user_id=str(user_id),
                    reason=decision.reason[:200],
                    tokens_in=tok_in,
                    tokens_out=tok_out,
                )
                # Track decision tokens even for skips — they cost money and must
                # appear in the dashboard/user statistics. Without this, skip tokens
                # are silently lost since the runner only calls track_proactive_tokens()
                # on successful dispatches.
                await self._track_skip_tokens(user_id, tok_in, tok_out, tok_cache)
                return None

            return HeartbeatTarget(
                context=context,
                decision=decision,
                decision_tokens_in=tok_in,
                decision_tokens_out=tok_out,
                decision_tokens_cache=tok_cache,
            )

        except Exception as e:
            logger.error(
                "heartbeat_select_target_failed",
                user_id=str(user_id),
                error=str(e),
                error_type=type(e).__name__,
            )
            return None

    async def generate_content(
        self,
        user_id: UUID,
        target: HeartbeatTarget,
        user_language: str,
    ) -> ProactiveTaskResult:
        """Generate the final notification message.

        Only called when LLM decided to notify (target is not None).
        Rewrites the decision's message_draft with personality and language.
        """
        personality = await self._get_user_personality(user_id)

        # Use the message_draft from the decision phase
        draft = target.decision.message_draft or target.decision.reason

        message, msg_tok_in, msg_tok_out, msg_tok_cache = await generate_heartbeat_message(
            message_draft=draft,
            context=target.context,
            user_language=user_language,
            personality_instruction=personality,
            user_id=user_id,
        )

        # Aggregate tokens: decision + message phases
        total_in = target.decision_tokens_in + msg_tok_in
        total_out = target.decision_tokens_out + msg_tok_out
        total_cache = target.decision_tokens_cache + msg_tok_cache

        from src.core.llm_config_helper import get_llm_config_for_agent

        settings = get_settings()
        model_name = get_llm_config_for_agent(settings, "heartbeat_message").model

        return ProactiveTaskResult(
            success=True,
            content=message,
            source=ContentSource.HEARTBEAT,
            target_id=f"heartbeat_{uuid4().hex[:8]}",
            tokens_in=total_in,
            tokens_out=total_out,
            tokens_cache=total_cache,
            model_name=model_name,
            metadata={
                "priority": target.decision.priority,
                "sources_used": target.decision.sources_used,
                "decision_reason": target.decision.reason,
            },
        )

    async def on_feedback(
        self,
        user_id: UUID,
        target: Any,
        feedback: str,
    ) -> None:
        """Handle user feedback.

        For heartbeat, feedback is managed directly via the router
        (PATCH /heartbeat/notifications/{id}/feedback) since we have
        the notification ID in the database. The Protocol on_feedback()
        is not used here.
        """

    async def on_notification_sent(
        self,
        user_id: UUID,
        target: HeartbeatTarget,
        result: ProactiveTaskResult,
    ) -> None:
        """Record audit trail and store conversational context.

        1. Create HeartbeatNotification record (immutable audit)
        2. Write lightweight summary to LangGraph Store for conversational
           continuity (write-only v1 — read integration in future iteration)
        """
        # 1. Create audit record via repository
        async with get_db_context() as db:
            from src.domains.heartbeat.repository import HeartbeatNotificationRepository

            repo = HeartbeatNotificationRepository(db)
            await repo.create(
                user_id=user_id,
                run_id=result.target_id or f"heartbeat_{uuid4().hex[:8]}",
                content=result.content or "",
                content_hash=hashlib.sha256((result.content or "").encode()).hexdigest(),
                sources_used=json.dumps(result.metadata.get("sources_used", [])),
                decision_reason=result.metadata.get("decision_reason"),
                priority=result.metadata.get("priority", "low"),
                tokens_in=result.tokens_in,
                tokens_out=result.tokens_out,
                model_name=result.model_name,
            )
            await db.commit()

        # 2. Store summary in LangGraph Store for conversational continuity
        try:
            from src.domains.agents.context.store import get_tool_context_store

            store = await get_tool_context_store()
            await store.aput(
                (str(user_id), "heartbeat_context"),
                key="last_heartbeat",
                value={
                    "content": (result.content or "")[:200],
                    "sources": result.metadata.get("sources_used", []),
                    "sent_at": datetime.now(UTC).isoformat(),
                },
            )
        except Exception:
            # Non-critical: conversational continuity is a bonus
            logger.debug(
                "heartbeat_store_write_failed",
                user_id=str(user_id),
            )

    async def _track_skip_tokens(
        self,
        user_id: UUID,
        tokens_in: int,
        tokens_out: int,
        tokens_cache: int,
    ) -> None:
        """Track decision phase tokens when the LLM decides to skip.

        Without this, skip decision tokens are silently lost because
        the runner's track_proactive_tokens() only runs after successful dispatch.
        """
        if tokens_in == 0 and tokens_out == 0:
            return

        try:
            from src.core.llm_config_helper import get_llm_config_for_agent
            from src.infrastructure.proactive.tracking import track_proactive_tokens

            settings = get_settings()
            model_name = get_llm_config_for_agent(settings, "heartbeat_decision").model

            await track_proactive_tokens(
                user_id=user_id,
                task_type="heartbeat",
                target_id=f"heartbeat_skip_{uuid4().hex[:8]}",
                conversation_id=None,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                tokens_cache=tokens_cache,
                model_name=model_name,
            )
        except Exception as e:
            # Non-fatal: token tracking failure shouldn't prevent the skip
            logger.warning(
                "heartbeat_skip_token_tracking_failed",
                user_id=str(user_id),
                error=str(e),
            )

    async def _get_user_personality(self, user_id: UUID) -> str | None:
        """Get user's personality instruction for content presentation.

        Follows the same pattern as InterestProactiveTask._get_user_personality().
        """
        try:
            async with get_db_context() as db:
                from src.domains.personalities.service import PersonalityService

                service = PersonalityService(db)
                return await service.get_prompt_instruction_for_user(user_id)
        except Exception as e:
            logger.warning(
                "heartbeat_get_personality_failed",
                user_id=str(user_id),
                error=str(e),
            )
            return None
