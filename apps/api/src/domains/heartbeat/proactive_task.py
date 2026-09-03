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

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import structlog

from src.core.config import get_settings
from src.core.constants import HEARTBEAT_ENRICHMENT_CONTEXT_ID
from src.domains.habits.presence import last_seen_at
from src.domains.heartbeat.context_aggregator import ContextAggregator
from src.domains.heartbeat.habit_context import should_defer_tick_for_rhythm
from src.domains.heartbeat.prompts import (
    generate_heartbeat_message,
    get_heartbeat_decision,
)
from src.domains.heartbeat.schemas import HeartbeatTarget
from src.domains.push_channels.wake import WakePayload
from src.infrastructure.database import get_db_context
from src.infrastructure.observability.metrics_registry import heartbeat_enrichment_total
from src.infrastructure.proactive.base import ContentSource, ProactiveTaskResult

logger = structlog.get_logger(__name__)


def _as_uuid(value: str | None) -> UUID | None:
    """Read a notification identifier, or admit it is not one.

    ``generate_content`` always produces a UUID, so the ``None`` return is
    reserved for results built elsewhere — older callers and test fakes. It is
    a real degradation, not a detail: the row then gets a generated id that no
    archived card points at, so its feedback buttons would resolve to nothing.
    Hence the warning rather than a silent fallback.

    Args:
        value: The result's ``target_id``.

    Returns:
        The parsed UUID, or ``None`` when the value cannot be one.
    """
    if value is None:
        return None
    try:
        return UUID(value)
    except ValueError:
        logger.warning(
            "heartbeat_target_id_not_a_uuid",
            reason="audit row will not be reachable from its archived card",
        )
        return None


class HeartbeatProactiveTask:
    """Proactive task for heartbeat autonome notifications.

    Implements the ProactiveTask protocol to:
    1. Aggregate context from multiple sources (calendar, weather, interests, etc.)
    2. Let LLM decide if notification is warranted (structured output)
    3. Generate personalized message with user's personality and language
    4. Record audit trail and store conversational context
    """

    task_type: str = "heartbeat"

    def __init__(self, wake: WakePayload | None = None) -> None:
        """Args:
        wake: The push wake being served (ADR-261), or None for a tick.
        """
        self.wake = wake

    async def check_eligibility(
        self,
        user_id: UUID,
        user_settings: dict[str, Any],
        now: datetime,
    ) -> bool:
        """Check task-specific eligibility.

        Common checks (time window, quota, cooldown) are handled by
        EligibilityChecker. This checks heartbeat-specific conditions, then
        the deterministic tick scoring (ADR-214 §11.2, own flag, default
        OFF): a tick outside the learned rhythm defers ONLY when a later
        same-day tick can land inside a learned window within the user's
        bounds — anti-starvation is the rule's core, and every failure path
        fails open to the current behavior.
        """
        if not user_settings.get("heartbeat_enabled", False):
            return False
        if await should_defer_tick_for_rhythm(user_id, user_settings, get_settings()):
            return False
        return True

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
                from src.domains.users.models import User

                user = await db.get(User, user_id)
                if not user:
                    return None

                # Early-exit: skip if user inactive for too long (save tokens)
                inactive_days = getattr(settings, "heartbeat_inactive_skip_days", 7)
                # ADR-214 amendment: a user who READS without logging in again
                # is not inactive (last_login alone silenced two accounts).
                last_seen = await last_seen_at(user)
                if last_seen is not None:
                    days_since = (datetime.now(UTC) - last_seen).days
                    if days_since > inactive_days:
                        logger.debug(
                            "heartbeat_skip_inactive_user",
                            user_id=str(user_id),
                            days_inactive=days_since,
                        )
                        return None

                # Aggregate context from all sources in parallel
                aggregator = ContextAggregator(db, wake=self.wake)
                context = await aggregator.aggregate(user_id, user)
                if self.wake is not None:
                    context.wake_trigger = self.wake.provider

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

            # Fail-open guard (ADR-135): interest_topic must be one of the
            # injected sample topics — anything else is dropped, never trusted.
            if decision.interest_topic is not None:
                sample_topics = {i.get("topic") for i in (context.trending_interests or [])}
                if decision.interest_topic not in sample_topics:
                    logger.warning(
                        "heartbeat_interest_topic_invalid",
                        user_id=str(user_id),
                        invalid_topic=decision.interest_topic[:50],
                    )
                    decision.interest_topic = None

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

    async def _resolve_interest_for_enrichment(
        self,
        user_id: UUID,
        topic: str,
    ) -> tuple[UUID | None, str, list[list[float]]]:
        """Resolve the stored interest behind an enrichment topic (ADR-135).

        Returns its category and the embeddings of its recent notifications so
        the fetched content is deduplicated exactly like the interest flow does
        (flow asymmetries are a recurring bug source). Best-effort: an
        unresolved topic simply yields no category and no embeddings.

        Args:
            user_id: User UUID.
            topic: Interest topic string from the decision.

        Returns:
            (interest_id or None, category, recent content embeddings).
        """
        settings = get_settings()
        try:
            async with get_db_context() as db:
                from src.domains.interests.repository import (
                    InterestNotificationRepository,
                    InterestRepository,
                )

                interest = await InterestRepository(db).get_by_user_and_topic_ci(user_id, topic)
                if interest is None:
                    return None, "", []

                recent = await InterestNotificationRepository(db).get_recent_for_interest(
                    interest_id=interest.id,
                    days=settings.interest_content_lookback_days,
                )
                embeddings = [n.content_embedding for n in recent if n.content_embedding]
                return interest.id, interest.category, embeddings
        except Exception as e:
            logger.warning(
                "heartbeat_enrichment_resolve_failed",
                user_id=str(user_id),
                topic=topic[:50],
                error=str(e),
                error_type=type(e).__name__,
            )
            return None, "", []

    async def _fetch_interest_facts(
        self,
        user_id: UUID,
        topic: str,
        user_language: str,
    ) -> tuple[str, list[str], int, int] | None:
        """Fetch real, fresh content for an interest-centered heartbeat (ADR-135).

        Reuses the interest content pipeline (Perplexity/Brave/Wikipedia) under
        a hard timeout so the notification can propose something concrete
        instead of a vague exhortation. Fail-open by contract: any failure
        returns None and the message is generated from the plain draft.

        Args:
            user_id: User UUID (the content sources resolve per-user API keys).
            topic: Interest topic the decision centered on.
            user_language: User's language code.

        Returns:
            (facts_text, citations, tokens_in, tokens_out) or None.
        """
        from src.domains.interests.services.content_sources import (
            ContentGenerationContext,
            InterestContentGenerator,
        )

        settings = get_settings()
        if not settings.heartbeat_interest_enrichment_enabled:
            heartbeat_enrichment_total.labels(outcome="disabled").inc()
            return None

        interest_id, category, recent_embeddings = await self._resolve_interest_for_enrichment(
            user_id, topic
        )

        generator = InterestContentGenerator()
        try:
            generation = await asyncio.wait_for(
                generator.generate(
                    ContentGenerationContext(
                        interest_id=(
                            str(interest_id)
                            if interest_id is not None
                            else HEARTBEAT_ENRICHMENT_CONTEXT_ID
                        ),
                        topic=topic,
                        category=category,
                        user_id=str(user_id),
                        user_language=user_language,
                        recent_notification_embeddings=recent_embeddings,
                    )
                ),
                timeout=settings.heartbeat_enrichment_timeout_seconds,
            )
        except Exception as e:
            # Fail-open by contract: enrichment is a bonus, never a blocker.
            logger.warning(
                "heartbeat_enrichment_failed",
                user_id=str(user_id),
                topic=topic[:50],
                error=str(e),
                error_type=type(e).__name__,
            )
            heartbeat_enrichment_total.labels(outcome="error").inc()
            return None
        finally:
            await generator.close()

        if not generation.success or generation.content_result is None:
            logger.info(
                "heartbeat_enrichment_empty",
                user_id=str(user_id),
                topic=topic[:50],
                sources_tried=generation.sources_tried,
            )
            heartbeat_enrichment_total.labels(outcome="empty").inc()
            return None

        content_result = generation.content_result
        logger.info(
            "heartbeat_enrichment_succeeded",
            user_id=str(user_id),
            topic=topic[:50],
            source=content_result.source,
            citations_count=len(content_result.citations),
        )
        heartbeat_enrichment_total.labels(outcome="success").inc()
        return (
            content_result.content,
            content_result.citations,
            content_result.tokens_in,
            content_result.tokens_out,
        )

    async def generate_content(
        self,
        user_id: UUID,
        target: HeartbeatTarget,
        user_language: str,
    ) -> ProactiveTaskResult:
        """Generate the final notification message.

        Only called when LLM decided to notify (target is not None).
        Rewrites the decision's message_draft with personality and language.
        When the decision centers on an interest (ADR-135), real facts are
        fetched first so the message proposes something concrete, and the
        sources are appended as clickable links.
        """
        personality = await self._get_user_personality(user_id)

        # Use the message_draft from the decision phase
        draft = target.decision.message_draft or target.decision.reason

        facts_block: str | None = None
        citations: list[str] = []
        enrich_tok_in = 0
        enrich_tok_out = 0
        interest_topic = target.decision.interest_topic
        if interest_topic:
            facts = await self._fetch_interest_facts(user_id, interest_topic, user_language)
            if facts is not None:
                facts_block, citations, enrich_tok_in, enrich_tok_out = facts

        message, msg_tok_in, msg_tok_out, msg_tok_cache = await generate_heartbeat_message(
            message_draft=draft,
            context=target.context,
            user_language=user_language,
            personality_instruction=personality,
            user_id=user_id,
            facts_block=facts_block,
        )

        if citations:
            from src.domains.interests.sources import build_sources_block

            message += build_sources_block(
                citations=citations,
                language=user_language,
                max_links=get_settings().interest_sources_max_links,
            )

        # Aggregate tokens: decision + message + enrichment phases
        total_in = target.decision_tokens_in + msg_tok_in + enrich_tok_in
        total_out = target.decision_tokens_out + msg_tok_out + enrich_tok_out
        total_cache = target.decision_tokens_cache + msg_tok_cache

        from src.core.llm_config_helper import get_llm_config_for_agent

        settings = get_settings()
        model_name = get_llm_config_for_agent(settings, "heartbeat_message").model

        return ProactiveTaskResult(
            success=True,
            content=message,
            source=ContentSource.HEARTBEAT,
            # The audit row's primary key, decided HERE because the dispatcher
            # writes this value into the archived card's `metadata.target_id`
            # BEFORE `on_notification_sent` gets to insert the row — and the
            # feedback route (`PATCH /heartbeat/notifications/{id}`) resolves
            # the notification by exactly that value. A synthetic
            # `heartbeat_<hex>` string used to live here: parseable by nothing,
            # it made every vote from the chat a 422 the frontend swallows.
            target_id=str(uuid4()),
            tokens_in=total_in,
            tokens_out=total_out,
            tokens_cache=total_cache,
            model_name=model_name,
            metadata={
                "priority": target.decision.priority,
                "sources_used": target.decision.sources_used,
                "decision_reason": target.decision.reason,
                "interest_topic": interest_topic,
                "citations": citations,
                # P5 — loop ids surfaced this cycle, consumed by the
                # post-notification cooldown bump (on_notification_sent).
                "open_loop_ids": [
                    ol["id"] for ol in (target.context.open_loops or []) if ol.get("id")
                ],
                # ADR-214 — the missed-routine candidate surfaced this cycle,
                # consumed by the post-notification offer bookkeeping.
                "habit_offer_id": (
                    ((target.context.habits or {}).get("missed_routine") or {}).get("habit_id")
                ),
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

    def _trigger(self) -> str:
        """What woke this decision (ADR-261): a push notification or the tick."""
        return "push" if self.wake is not None else "tick"

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
        #
        # Identity, and the two joins that depend on it:
        #  - `id` IS `result.target_id` (a UUID by construction, see
        #    generate_content): the archived card carries that value, so the
        #    feedback route and `mark_proactive_feedback_submitted` both land
        #    on this row instead of matching nothing;
        #  - `run_id` is the TOKEN-TRACKING run the runner injected into the
        #    metadata before dispatch. The column documents itself as "Unique
        #    ID linking to token tracking"; storing the target_id here left
        #    `message_token_summary` unjoinable for every heartbeat.
        notification_id = _as_uuid(result.target_id)
        async with get_db_context() as db:
            from src.domains.heartbeat.repository import HeartbeatNotificationRepository

            repo = HeartbeatNotificationRepository(db)
            await repo.create(
                notification_id=notification_id,
                user_id=user_id,
                # `run_id` is UNIQUE: the fallback must stay unique too, hence
                # the notification's own identifier rather than a constant.
                run_id=str(result.metadata.get("run_id") or result.target_id or uuid4()),
                content=result.content or "",
                content_hash=hashlib.sha256((result.content or "").encode()).hexdigest(),
                sources_used=json.dumps(result.metadata.get("sources_used", [])),
                decision_reason=result.metadata.get("decision_reason"),
                priority=result.metadata.get("priority", "low"),
                tokens_in=result.tokens_in,
                tokens_out=result.tokens_out,
                model_name=result.model_name,
                # ADR-214: persisted so the feedback route can bump the habit.
                habit_offer_id=_as_uuid(result.metadata.get("habit_offer_id")),
                trigger=self._trigger(),
            )

            # Unified mention ledger (ADR-135): an interest-centered heartbeat
            # counts as "subject served" for BOTH proactive flows' variety.
            # Eligibility queries exclude source='heartbeat' rows; selection
            # and rarity queries include them.
            interest_topic = result.metadata.get("interest_topic")
            if interest_topic:
                from src.domains.interests.repository import (
                    InterestNotificationRepository,
                    InterestRepository,
                )

                interest_repo = InterestRepository(db)
                interest = await interest_repo.get_by_user_and_topic_ci(user_id, interest_topic)
                if interest is not None:
                    await interest_repo.mark_notified(interest)

                    # Embed the served content so later fetches (either flow)
                    # deduplicate against it, exactly like the interest flow.
                    from src.domains.interests.helpers import generate_interest_embedding

                    content_embedding = None
                    if result.content:
                        content_embedding = await generate_interest_embedding(result.content)

                    ledger_repo = InterestNotificationRepository(db)
                    await ledger_repo.create(
                        user_id=user_id,
                        interest_id=interest.id,
                        run_id=f"hb_{result.target_id or uuid4().hex[:12]}",
                        content_hash=hashlib.sha256((result.content or "").encode()).hexdigest(),
                        source="heartbeat",
                        content_embedding=content_embedding,
                    )
                else:
                    logger.debug(
                        "heartbeat_ledger_topic_unresolved",
                        user_id=str(user_id),
                        topic=interest_topic[:50],
                    )

            # P5 — cooldown bump: only when the delivered notification actually
            # used the OPEN_LOOPS source (fetch-time bumping would suppress
            # loops the decision LLM chose to skip).
            await _bump_used_open_loops(db, user_id, result.metadata)

            # ADR-214 — offer bookkeeping: only when the delivered notification
            # actually used the HABITS source (same doctrine — exposing a
            # candidate the LLM skipped must not burn its cooldown).
            await _bump_offered_habit(db, user_id, result.metadata)

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


async def _bump_offered_habit(db: Any, user_id: UUID, metadata: dict[str, Any]) -> None:
    """Stamp the offer bookkeeping of the habit a delivered offer surfaced.

    ADR-214 stop rule: the offer date joins ``payload.offer_dates`` (bounded),
    and when the trailing offers reach the ignored threshold with no later
    occurrence, ``muted_until_reproof`` silences further offers until the
    routine re-occurs (a fresh promotion resets it). Only runs when the
    decision actually used the HABITS source.
    """
    habit_id = metadata.get("habit_offer_id")
    if "HABITS" not in metadata.get("sources_used", []) or not habit_id:
        return
    from src.core.config import settings as app_settings
    from src.domains.habits.models import UserHabit
    from src.domains.heartbeat.habit_context import (
        _ledger_occurrence_days,
        ignored_offer_count,
    )

    try:
        habit = await db.get(UserHabit, UUID(str(habit_id)))
    except ValueError:
        return
    if habit is None or habit.user_id != user_id:
        return
    # UTC calendar date on purpose: offer dates are compared against the
    # ledger's LOCAL dates and against a 7-day cooldown — the worst skew is
    # one day near midnight on an advisory bound, not worth a user fetch here.
    today_iso = datetime.now(UTC).date().isoformat()
    offer_dates = [str(d) for d in (habit.payload or {}).get("offer_dates") or []]
    offer_dates = sorted({*offer_dates, today_iso})[-5:]
    # New dict — never mutate JSONB in place.
    habit.payload = {**(habit.payload or {}), "offer_dates": offer_dates}
    # The stop rule counts offers with NO occurrence after them: an uptake
    # between two offers resets the run (the routine re-proved itself), so
    # the real ledger occurrences must weigh in, not an empty set.
    occurrences = await _ledger_occurrence_days(user_id, habit.key)
    if (
        ignored_offer_count(offer_dates, occurrences)
        >= app_settings.habits_deviation_stop_after_ignored
    ):
        habit.muted_until_reproof = True
    logger.info(
        "habit_offer_stamped",
        user_id=str(user_id),
        habit_id=str(habit_id),
        offers=len(offer_dates),
        muted=habit.muted_until_reproof,
    )


async def _bump_used_open_loops(db: Any, user_id: UUID, metadata: dict[str, Any]) -> None:
    """Bump the nudge cooldown for loops a delivered notification surfaced.

    Hoisted out of ``on_notification_sent`` (CC ratchet). Only runs when the
    decision actually used the OPEN_LOOPS source; malformed ids are skipped.
    """
    open_loop_ids = metadata.get("open_loop_ids") or []
    if "OPEN_LOOPS" not in metadata.get("sources_used", []) or not open_loop_ids:
        return
    from src.domains.open_loops.repository import OpenLoopRepository

    parsed_ids = []
    for raw_id in open_loop_ids:
        try:
            parsed_ids.append(UUID(str(raw_id)))
        except ValueError:
            continue
    if parsed_ids:
        await OpenLoopRepository(db).bump_nudged(parsed_ids, user_id=user_id)
        logger.info(
            "open_loops_nudge_bumped",
            user_id=str(user_id),
            count=len(parsed_ids),
        )
