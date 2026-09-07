"""
Scheduled task for reminder notifications.

Runs every minute to check for pending reminders that need to be sent.
Uses FOR UPDATE SKIP LOCKED to prevent concurrent processing.

Flow:
1. Get pending reminders due for notification (with lock)
2. For each reminder:
   a. Generate personalized message via LLM (includes creation date/time)
   b. Send FCM push notification
   c. Send via external channels (Telegram, etc.) if enabled
   d. Archive message in conversation
   e. Publish to Redis for SSE real-time
   f. Ask the recurrence what to arm next: an instant RE-ARMS the reminder,
      `None` DELETES it. A single occurrence answers `None` once consumed, so
      "delete after notification" is that one rule, not a branch beside it.

Metrics:
- background_job_duration_seconds{job_name="reminder_notification"}
- background_job_errors_total{job_name="reminder_notification"}
- reminder_notifications_sent_total{status="success"|"failed"}
"""

import json
import time
import uuid
from contextlib import suppress
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog

from src.core.config import settings
from src.core.i18n_dates import format_elapsed, format_short_stamp, neutral_persona
from src.core.i18n_proactive import ProactiveMessages
from src.core.recurrence import RecurrenceSpec, describe
from src.domains.agents.prompts.prompt_loader import (
    load_prompt,
    load_prompt_with_fallback,
)

# CRITICAL: Import Reminder model at module level to register it with SQLAlchemy
# before any database query is executed. This fixes the mapper initialization error:
# "expression 'Reminder' failed to locate a name" when User.reminders relationship
# is resolved during the first DB query.
from src.domains.reminders.models import Reminder  # noqa: F401
from src.infrastructure.cache.pricing_cache import get_cached_cost_usd_eur
from src.infrastructure.llm.message_text import coerce_content_to_text
from src.infrastructure.observability.metrics import (
    background_job_duration_seconds,
    background_job_errors_total,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

# Maximum retries before marking as failed
MAX_RETRIES = 3


def get_localized_title(language: str) -> str:
    """Localized push/channel title for a fired reminder.

    Delegates to the central proactive table. The inline dict that used to live
    here was keyed ``"zh"`` while ``User.language`` is backend-canonical
    ``"zh-CN"`` (see the column comment on ``users.language``), so the lookup
    never matched and every Chinese user received the English title on every
    reminder — the exact defect [ADR-131] centralized this table to eliminate,
    reproduced here for the third time.

    Args:
        language: Any locale spelling; normalized by the accessor.

    Returns:
        The localized title, English fallback.
    """
    from src.core.i18n_proactive import ProactiveMessages

    return ProactiveMessages.notification_title("reminder", language)


def truncate_for_notification(text: str, max_length: int = 150) -> str:
    """Truncate text for notification body."""
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


class ReminderMessageResult:
    """Result of reminder message generation with token usage."""

    def __init__(
        self,
        message: str,
        tokens_in: int = 0,
        tokens_out: int = 0,
        tokens_cache: int = 0,
        model_name: str = "",
    ):
        self.message = message
        self.tokens_in = tokens_in
        self.tokens_out = tokens_out
        self.tokens_cache = tokens_cache
        self.model_name = model_name


async def generate_reminder_message(
    original_message: str,
    reminder_content: str,
    created_at: datetime,
    user_timezone: str,
    personality: Any | None,
    memories: list[dict],
    language: str,
    user_id: str | None = None,
    recurrence: RecurrenceSpec | None = None,
) -> ReminderMessageResult:
    """
    Generate a personalized reminder message using LLM.

    Args:
        original_message: Original user request
        reminder_content: Extracted reminder content
        created_at: When the reminder was created
        user_timezone: User's timezone
        personality: User's personality preference (if any)
        memories: Relevant memories for context
        language: User's language
        recurrence: The reminder's schedule, so the message can tell a
            post-it from one occurrence of a series.
        user_id: User UUID string for psyche context injection

    Returns:
        ReminderMessageResult with message and token usage info
    """
    from zoneinfo import ZoneInfo

    from src.infrastructure.llm.factory import get_llm

    # Six languages, from the central table: these two fragments used to be
    # `if language == "fr": ... else: <English>`, so four readers out of six
    # got an English span inside a message otherwise in their own language.
    now = datetime.now(UTC)
    elapsed_text = format_elapsed(now - created_at, language)
    created_at_text = format_short_stamp(created_at, user_timezone, language)

    # Bounded before it spends: this model call runs on the DEPLOYMENT's
    # provider key, so both ceilings apply — the account's and the instance's.
    # Non-raising on purpose: the reminder still has to fire. It goes out with
    # its written sentence instead of a composed one, and says so as a skip
    # rather than as a generation failure, which is not what happened.
    from src.domains.usage_limits.enforcement import spend_blocked

    if await spend_blocked(user_id):
        return ReminderMessageResult(
            message=ProactiveMessages.reminder_fallback_body(
                created_at_text, reminder_content, language
            )
        )

    # Get current time in user timezone
    tz = ZoneInfo(user_timezone)
    now_local = now.astimezone(tz)
    trigger_text = now_local.strftime("%H:%M")

    # Build personality context
    if personality and hasattr(personality, "system_prompt"):
        persona_prompt = personality.system_prompt
    else:
        persona_prompt = neutral_persona(language)

    # Build memory context
    memory_section = ""
    if memories:
        memory_lines = [f"- {m.get('content', '')}" for m in memories[:5]]
        memory_context = "\n".join(memory_lines)
        header = ProactiveMessages.reminder_memory_header(language)
        memory_section = header + "\n" + memory_context

    # Load prompt template using the standard loader

    # What the message may say about its own origin. The SCHEDULING rule has
    # no branch on "is this recurring"; the WORDING does, and legitimately:
    # "you asked me three months ago" is right for a post-it and wrong on the
    # ninetieth morning of a daily reminder.
    if recurrence is not None and recurrence.freq != "once":
        origin_context = load_prompt("reminder_origin_recurring", version="v1").format(
            schedule_human=describe(recurrence, language)
        )
    else:
        origin_context = load_prompt("reminder_origin_once", version="v1").format(
            created_at_text=created_at_text, elapsed_text=elapsed_text
        )

    template = load_prompt_with_fallback(
        "reminder_prompt",
        version="v1",
        fallback_content=FALLBACK_REMINDER_PROMPT,
    )

    # Resolve psyche context before template formatting
    psyche_block = ""
    user_model_block = ""
    if user_id:
        # Psyche injection is best-effort
        with suppress(Exception):
            from src.domains.psyche.service import build_psyche_prompt_block

            psyche_block = await build_psyche_prompt_block(
                user_id=user_id, user_timezone=user_timezone
            )
        # Journal portrait injection is best-effort
        with suppress(Exception):
            from src.domains.journals.portrait_builder import (
                build_journal_user_model_block,
            )

            user_model_block = await build_journal_user_model_block(
                user_id=user_id, format="brief", flow="reminder"
            )

    system_prompt = template.format(
        persona_prompt=persona_prompt,
        original_message=original_message,
        reminder_content=reminder_content,
        elapsed_text=elapsed_text,
        created_at_text=created_at_text,
        trigger_text=trigger_text,
        memory_section=memory_section,
        user_language=language,
        psyche_context=psyche_block,
        origin_context=origin_context,
    )
    if user_model_block:
        system_prompt += "\n\n" + user_model_block

    try:
        # Use the response LLM with custom settings for short message generation.
        # The `response` slot streams by design; usage_metadata is present on
        # the aggregated result because every streaming-capable provider now
        # requests it explicitly (PROVIDER_USAGE_CAPABILITIES, ADR-220). The
        # historical "disable streaming to get usage_metadata" comment here
        # described an override that never existed (ex-F3).
        from src.domains.agents.graphs.base_agent_builder import LLMConfig

        llm_config: LLMConfig = {"temperature": 0.7, "max_tokens": 150}
        llm = get_llm("response", config_override=llm_config)

        from src.infrastructure.llm.invoke_helpers import enrich_config_with_node_metadata

        invoke_config = enrich_config_with_node_metadata(None, "reminder_notification")
        response = await llm.ainvoke(system_prompt, config=invoke_config)
        # Gemini 3.x returns content as list[dict] blocks; coerce to text so the
        # reminder message is the actual text, not a Python repr of the blocks.
        message = coerce_content_to_text(response.content).strip()

        # Extract token usage from response metadata
        tokens_in = 0
        tokens_out = 0
        tokens_cache = 0
        model_name = ""

        if hasattr(response, "usage_metadata") and response.usage_metadata:
            usage = response.usage_metadata
            tokens_in = int(usage.get("input_tokens", 0) or 0)
            tokens_out = int(usage.get("output_tokens", 0) or 0)
            cache_val = usage.get("cache_read_input_tokens") or usage.get("cached_tokens") or 0
            tokens_cache = int(cache_val) if isinstance(cache_val, int | float | str) else 0

        if hasattr(response, "response_metadata") and response.response_metadata:
            model_name = response.response_metadata.get("model", "")

        return ReminderMessageResult(
            message=message,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            tokens_cache=tokens_cache,
            model_name=model_name,
        )

    except Exception as e:
        logger.warning(
            "reminder_message_generation_failed",
            error=str(e),
            fallback=True,
        )
        # Fallback to simple message with creation date (no token usage)
        return ReminderMessageResult(
            message=ProactiveMessages.reminder_fallback_body(
                created_at_text, reminder_content, language
            )
        )


async def get_relevant_memories(user_id: str, reminder_content: str) -> list[dict]:
    """
    Search for relevant memories to personalize the reminder message.

    Args:
        user_id: User UUID as string
        reminder_content: Content to search for

    Returns:
        List of relevant memory dicts
    """
    try:
        from uuid import UUID

        from src.infrastructure.database.session import get_db_context
        from src.infrastructure.llm.memory_embeddings import get_memory_embeddings

        # Embed reminder content locally (not centralized — unique per reminder)
        embeddings = get_memory_embeddings()
        query_embedding = await embeddings.aembed_query(reminder_content[:500])

        if not query_embedding:
            return []

        from src.core.constants import INITIATIVE_MEMORY_MIN_SCORE

        async with get_db_context() as db:
            from src.domains.memories.repository import MemoryRepository

            repo = MemoryRepository(db)
            results = await repo.search_by_relevance(
                user_id=UUID(user_id),
                query_embedding=query_embedding,
                limit=5,
                min_score=INITIATIVE_MEMORY_MIN_SCORE,
            )

        # Return as list[dict] for backward compatibility with callers
        # Exclude embedding vector (1536 floats) to avoid unnecessary payload
        return [
            {
                "content": memory.content or "",
                "category": memory.category or "personal",
                "emotional_weight": memory.emotional_weight or 0,
                "trigger_topic": memory.trigger_topic or "",
                "usage_nuance": memory.usage_nuance or "",
                "importance": memory.importance or 0.7,
            }
            for memory, _score in results
        ]

    except Exception as e:
        logger.warning(
            "reminder_memory_search_failed",
            user_id=user_id,
            error=str(e),
        )
        return []


#: The net under `reminder_prompt.txt`, shaped exactly like it: PLACEHOLDERS
#: filled by the same `.format` call, never an f-string.
#:
#: Two defects this shape removes, both measured 2026-09-06 on the previous
#: inline version:
#:
#: - it interpolated the reader's own words into the template, so a reminder
#:   saying "payer la facture {montant}" turned a brace into a placeholder
#:   nobody could fill — `KeyError`, three retries, an abandoned occurrence;
#: - it stated when the reminder was set up unconditionally, contradicting
#:   `reminder_origin_recurring.txt`. What a message may say about its ORIGIN
#:   is decided there and arrives as `origin_context`; a net restates nothing.
FALLBACK_REMINDER_PROMPT = """{persona_prompt}

It's time to remind the user about: {reminder_content}
{origin_context}
Generate a short, natural message in {user_language}.
"""


async def _account_reminder_spend(
    db: AsyncSession,
    *,
    reminder_id: str,
    user_id: UUID,
    run_id: str,
    conversation_id: UUID,
    result: ReminderMessageResult,
) -> float:
    """Charge one reminder notification to the account it was written for.

    Until 2026-09-07 this path wrote only ``message_token_summary``. That row
    is a per-run aggregate and nothing else reads it for accounting, so the
    spend reached NONE of the three places that matter: no
    ``token_usage_logs`` row (so no Article-12 trace), no ``user_statistics``
    increment (so the account's own quota never moved) and no
    ``instance_daily_budget`` entry (so the deployment ceiling was blind to
    it). The irony measured at the same time: this path DOES consult the quota
    before spending — it read a counter it never fed.

    ``track_proactive_tokens`` is the funnel every other out-of-turn surface
    uses and it writes all four, so this is one call rather than a fourth
    hand-rolled variant.

    Args:
        db: The caller's session; the write joins its transaction.
        reminder_id: Reminder being notified, for the log line.
        user_id: Account to bill.
        run_id: Pre-generated run id, already injected into the archived
            message's metadata — it must be reused, not regenerated, or the
            message and its cost stop pointing at each other.
        conversation_id: Conversation the notification is archived in.
        result: The generated message and its token usage.

    Returns:
        The call's cost in euros, for the archived message's metadata.
    """
    from src.infrastructure.proactive.tracking import track_proactive_tokens

    if result.tokens_in <= 0 and result.tokens_out <= 0:
        return 0.0

    cost_eur = 0.0
    try:
        _cost_usd, cost_eur = get_cached_cost_usd_eur(
            model=result.model_name or "",
            prompt_tokens=result.tokens_in,
            completion_tokens=result.tokens_out,
            cached_tokens=result.tokens_cache,
        )
    except Exception as price_error:  # noqa: BLE001 — an unpriced call still happened
        logger.warning(
            "reminder_cost_calculation_failed",
            reminder_id=reminder_id,
            error=str(price_error),
        )

    await track_proactive_tokens(
        user_id=user_id,
        task_type="reminder",
        target_id=reminder_id,
        conversation_id=conversation_id,
        tokens_in=result.tokens_in,
        tokens_out=result.tokens_out,
        tokens_cache=result.tokens_cache,
        model_name=result.model_name,
        db=db,
        run_id=run_id,
        source="scheduled",
    )
    return float(cost_eur)


async def process_pending_reminders() -> dict[str, Any]:
    """
    Process pending reminders that are due for notification.

    This function:
    1. Gets and locks pending reminders (FOR UPDATE SKIP LOCKED)
    2. For each reminder, generates personalized message (with creation date)
    3. Sends FCM notification
    4. Archives message in conversation
    5. Publishes to Redis for SSE
    6. Re-arms the reminder on its next instant, or deletes it when the
       recurrence has none left (`rearm_after` answering `None`)

    Returns:
        Stats dict with processed, notified, failed counts
    """
    start_time = time.perf_counter()
    job_name = "reminder_notification"

    stats: dict[str, Any] = {
        "processed": 0,
        "notified": 0,
        "failed": 0,
        "skipped": 0,
    }

    try:
        from src.domains.notifications.service import FCMNotificationService
        from src.domains.personalities.service import PersonalityService
        from src.domains.reminders.models import ReminderStatus
        from src.domains.reminders.repository import ReminderRepository
        from src.domains.reminders.service import next_arming
        from src.domains.users.service import UserService
        from src.infrastructure.cache.redis import get_redis_cache
        from src.infrastructure.database.session import get_db_context

        async with get_db_context() as db:
            reminder_repo = ReminderRepository(db)

            # 1. Get and lock pending reminders
            reminders = await reminder_repo.get_and_lock_pending_reminders(limit=100)

            if not reminders:
                duration = time.perf_counter() - start_time
                background_job_duration_seconds.labels(job_name=job_name).observe(duration)
                return stats

            logger.info(
                "reminder_batch_started",
                count=len(reminders),
            )

            # Initialize services
            user_service = UserService(db)
            personality_service = PersonalityService(db)
            fcm_service = FCMNotificationService(db)

            for reminder in reminders:
                stats["processed"] += 1

                try:
                    # 1.5. Usage limit pre-check (skip early before any DB/LLM work)
                    from src.domains.usage_limits.service import UsageLimitService

                    if await UsageLimitService.is_user_blocked_for_llm(
                        reminder.user_id,
                        layer="reminder_notification",
                        extra_log_fields={"reminder_id": str(reminder.id)},
                    ):
                        # Release the lease: the block is TEMPORARY (a budget
                        # window), so the reminder must be selectable again on a
                        # later tick. Left in PROCESSING it would never be
                        # picked up (the query filters on PENDING) and never
                        # fire — a reminder lost with no error anywhere.
                        reminder.status = ReminderStatus.PENDING.value
                        stats["skipped"] += 1
                        continue

                    # 2. Load user context
                    user = await user_service.get_user_by_id(reminder.user_id)
                    if not user:
                        logger.warning(
                            "reminder_user_not_found",
                            reminder_id=str(reminder.id),
                            user_id=str(reminder.user_id),
                        )
                        stats["skipped"] += 1
                        # Delete orphan reminder
                        await reminder_repo.delete(reminder)
                        continue

                    # 2.5. Skip inactive users (deleted users also have is_active=False)
                    if not user.is_active:
                        logger.info(
                            "reminder_skipped_user_inactive",
                            reminder_id=str(reminder.id),
                            user_id=str(reminder.user_id),
                            is_active=user.is_active,
                        )
                        # Release the lease here too. Deactivation is
                        # reversible, so deleting would destroy a reminder the
                        # user may still want; a hard delete is the account
                        # purge's job (`user_data_map`: reminders are purged in
                        # full on erasure, and the FK cascades on user delete).
                        reminder.status = ReminderStatus.PENDING.value
                        stats["skipped"] += 1
                        continue

                    # 3. Load personality (optional)
                    personality = None
                    if user.personality_id:
                        # Use default if personality not found
                        with suppress(Exception):
                            personality = await personality_service.get_by_id(user.personality_id)

                    # 4. Search relevant memories (always enabled)
                    memories = await get_relevant_memories(
                        str(reminder.user_id),
                        reminder.content,
                    )

                    # 5. Generate personalized message (includes creation date)
                    result = await generate_reminder_message(
                        original_message=reminder.original_message,
                        reminder_content=reminder.content,
                        created_at=reminder.created_at,
                        user_timezone=reminder.user_timezone,
                        personality=personality,
                        memories=memories,
                        language=user.language or settings.default_language,
                        user_id=str(reminder.user_id),
                        recurrence=reminder.recurrence_spec,
                    )
                    # Always prefix with 🔔 emoji for reminders
                    message = f"🔔 {result.message}"

                    # Generate unique run_id for token tracking
                    run_id = f"reminder_{reminder.id}_{uuid.uuid4().hex[:8]}"

                    # 6. Send FCM notification
                    title = get_localized_title(user.language or settings.default_language)
                    body = truncate_for_notification(message, 150)

                    fcm_result = await fcm_service.send_reminder_notification(
                        user_id=reminder.user_id,
                        title=title,
                        body=body,
                        reminder_id=str(reminder.id),
                    )

                    # 6b. Send via external channels (Telegram, etc.)
                    if getattr(settings, "channels_enabled", False):
                        try:
                            from src.infrastructure.proactive.notification import (
                                send_notification_to_channels,
                            )

                            await send_notification_to_channels(
                                user_id=reminder.user_id,
                                title=title,
                                body=message,
                                task_type="reminder",
                                target_id=str(reminder.id),
                                db=db,
                            )
                        except Exception as ch_error:
                            logger.warning(
                                "reminder_channels_failed",
                                reminder_id=str(reminder.id),
                                error=str(ch_error),
                            )

                    # 7. Archive message in conversation with token tracking
                    try:
                        from src.domains.conversations.service import ConversationService

                        conv_service = ConversationService()
                        conversation = await conv_service.get_or_create_conversation(
                            reminder.user_id,
                            db,
                            language=user.language or settings.default_language,
                        )

                        cost_eur = await _account_reminder_spend(
                            db,
                            reminder_id=str(reminder.id),
                            user_id=reminder.user_id,
                            run_id=run_id,
                            conversation_id=conversation.id,
                            result=result,
                        )

                        # Archive message with run_id for token linking
                        await conv_service.archive_message(
                            conversation_id=conversation.id,
                            role="assistant",
                            content=message,
                            metadata={
                                "type": "reminder_notification",
                                "reminder_id": str(reminder.id),
                                "original_trigger_at": reminder.trigger_at.isoformat(),
                                "created_at": reminder.created_at.isoformat(),
                                "run_id": run_id,  # Link to token summary
                            },
                            db=db,
                        )

                        logger.debug(
                            "reminder_message_archived",
                            reminder_id=str(reminder.id),
                            conversation_id=str(conversation.id),
                            tokens_in=result.tokens_in,
                            tokens_out=result.tokens_out,
                            cost_eur=float(cost_eur),
                        )
                    except Exception as archive_error:
                        logger.warning(
                            "reminder_archive_failed",
                            reminder_id=str(reminder.id),
                            error=str(archive_error),
                        )

                    # 8. Publish to Redis for SSE real-time
                    try:
                        redis = await get_redis_cache()
                        if redis:
                            channel = f"user_notifications:{reminder.user_id}"
                            await redis.publish(
                                channel,
                                json.dumps(
                                    {
                                        "type": "reminder",
                                        "content": message,
                                        "reminder_id": str(reminder.id),
                                        "title": title,
                                    },
                                    ensure_ascii=False,
                                ),
                            )
                    except Exception as redis_error:
                        logger.warning(
                            "reminder_redis_publish_failed",
                            reminder_id=str(reminder.id),
                            error=str(redis_error),
                        )

                    # 9. Re-arm, or delete when nothing follows.
                    #
                    # ONE rule, no branch on "is this recurring": a single
                    # occurrence answers None here — which IS the historical
                    # one-shot behaviour — and a recurring one answers its
                    # next instant.
                    next_at = next_arming(reminder)
                    if next_at is None:
                        await reminder_repo.delete(reminder)
                    else:
                        reminder.trigger_at = next_at
                        reminder.status = ReminderStatus.PENDING.value
                        # A row that SURVIVES its notification must forget its
                        # past failures: `retry_count` was never reset because
                        # the row always died at this point, so a recurring
                        # reminder would have deleted itself after three
                        # failures spread over its whole life.
                        reminder.retry_count = 0
                        reminder.notification_error = None

                    stats["notified"] += 1

                    logger.info(
                        "reminder_notified",
                        reminder_id=str(reminder.id),
                        user_id=str(reminder.user_id),
                        rearmed_at=next_at.isoformat() if next_at else None,
                        fcm_success=fcm_result.success_count,
                        fcm_failed=fcm_result.failure_count,
                    )

                except Exception as e:
                    # Handle error with retry logic
                    reminder.retry_count += 1

                    if reminder.retry_count >= MAX_RETRIES:
                        # Give up on THIS occurrence, not on the series. A
                        # recurring reminder destroyed by three transient
                        # failures would take its whole schedule with it; a
                        # single occurrence has nothing after it and goes, as
                        # it always did.
                        next_at = next_arming(reminder)
                        if next_at is None:
                            await reminder_repo.delete(reminder)
                        else:
                            reminder.trigger_at = next_at
                            reminder.status = ReminderStatus.PENDING.value
                            reminder.retry_count = 0
                            reminder.notification_error = str(e)
                        stats["failed"] += 1
                        logger.error(
                            "reminder_occurrence_abandoned",
                            reminder_id=str(reminder.id),
                            error=str(e),
                            retry_count=MAX_RETRIES,
                            rearmed_at=next_at.isoformat() if next_at else None,
                        )
                    else:
                        # Revert to pending for retry
                        reminder.status = ReminderStatus.PENDING.value
                        reminder.notification_error = str(e)
                        logger.warning(
                            "reminder_retry_scheduled",
                            reminder_id=str(reminder.id),
                            error=str(e),
                            retry_count=reminder.retry_count,
                        )

            # Commit all changes
            await db.commit()

        # Track duration
        duration = time.perf_counter() - start_time
        background_job_duration_seconds.labels(job_name=job_name).observe(duration)

        logger.info(
            "reminder_notification_completed",
            **stats,
            duration_seconds=round(duration, 3),
        )

        return stats

    except Exception as e:
        # Track error
        background_job_errors_total.labels(job_name=job_name).inc()

        # Track duration even on error
        duration = time.perf_counter() - start_time
        background_job_duration_seconds.labels(job_name=job_name).observe(duration)

        logger.error(
            "reminder_notification_failed",
            error=str(e),
            error_type=type(e).__name__,
            duration_seconds=round(duration, 3),
        )
        raise
