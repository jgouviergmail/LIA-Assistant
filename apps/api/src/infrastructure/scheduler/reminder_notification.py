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
   f. DELETE reminder from database (one-shot behavior)

Metrics:
- background_job_duration_seconds{job_name="reminder_notification"}
- background_job_errors_total{job_name="reminder_notification"}
- reminder_notifications_sent_total{status="success"|"failed"}
"""

import json
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog

from src.core.config import settings
from src.core.field_names import (
    FIELD_COST_EUR,
    FIELD_TOKENS_CACHE,
    FIELD_TOKENS_IN,
    FIELD_TOKENS_OUT,
)
from src.domains.agents.prompts.prompt_loader import load_prompt_with_fallback

# CRITICAL: Import Reminder model at module level to register it with SQLAlchemy
# before any database query is executed. This fixes the mapper initialization error:
# "expression 'Reminder' failed to locate a name" when User.reminders relationship
# is resolved during the first DB query.
from src.domains.reminders.models import Reminder  # noqa: F401
from src.infrastructure.observability.metrics import (
    background_job_duration_seconds,
    background_job_errors_total,
)

logger = structlog.get_logger(__name__)

# Maximum retries before marking as failed
MAX_RETRIES = 3


def get_localized_title(language: str) -> str:
    """Get localized notification title."""
    titles = {
        "fr": "Rappel",
        "en": "Reminder",
        "es": "Recordatorio",
        "de": "Erinnerung",
        "it": "Promemoria",
        "zh": "提醒",
    }
    return titles.get(language, "Reminder")


def truncate_for_notification(text: str, max_length: int = 150) -> str:
    """Truncate text for notification body."""
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


def format_elapsed_time(elapsed: timedelta, language: str) -> str:
    """Format elapsed time in human-readable form."""
    days = elapsed.days
    hours = elapsed.seconds // 3600
    minutes = (elapsed.seconds % 3600) // 60

    if language == "fr":
        if days > 1:
            return f"il y a {days} jours"
        elif days == 1:
            return "hier"
        elif hours > 0:
            return f"il y a {hours} heure{'s' if hours > 1 else ''}"
        elif minutes > 0:
            return f"il y a {minutes} minute{'s' if minutes > 1 else ''}"
        else:
            return "il y a quelques instants"
    else:
        if days > 1:
            return f"{days} days ago"
        elif days == 1:
            return "yesterday"
        elif hours > 0:
            return f"{hours} hour{'s' if hours > 1 else ''} ago"
        elif minutes > 0:
            return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
        else:
            return "just now"


def format_creation_datetime(created_at: datetime, user_timezone: str, language: str) -> str:
    """
    Format the creation datetime for display in the notification message.

    Args:
        created_at: When the reminder was created (UTC)
        user_timezone: User's timezone
        language: User's language

    Returns:
        Formatted string like "le 27/12 à 15:30" or "on 12/27 at 3:30 PM"
    """
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(user_timezone)
    local_dt = created_at.astimezone(tz)

    if language == "fr":
        return f"le {local_dt.strftime('%d/%m')} à {local_dt.strftime('%H:%M')}"
    else:
        return f"on {local_dt.strftime('%m/%d')} at {local_dt.strftime('%I:%M %p')}"


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

    Returns:
        ReminderMessageResult with message and token usage info
    """
    from zoneinfo import ZoneInfo

    from src.infrastructure.llm.factory import get_llm

    # Calculate elapsed time
    now = datetime.now(UTC)
    elapsed = now - created_at
    elapsed_text = format_elapsed_time(elapsed, language)

    # Format creation datetime for the message
    created_at_text = format_creation_datetime(created_at, user_timezone, language)

    # Get current time in user timezone
    tz = ZoneInfo(user_timezone)
    now_local = now.astimezone(tz)
    trigger_text = now_local.strftime("%H:%M")

    # Build personality context
    if personality and hasattr(personality, "system_prompt"):
        persona_prompt = personality.system_prompt
    else:
        if language == "fr":
            persona_prompt = "Tu es un assistant amical et efficace."
        else:
            persona_prompt = "You are a friendly and efficient assistant."

    # Build memory context
    memory_section = ""
    if memories:
        memory_lines = [f"- {m.get('content', '')}" for m in memories[:5]]
        memory_context = "\n".join(memory_lines)
        if language == "fr":
            memory_section = f"MÉMOIRES PERTINENTES :\n{memory_context}"
        else:
            memory_section = f"RELEVANT MEMORIES:\n{memory_context}"

    # Load prompt template using the standard loader
    fallback_prompt = f"""{persona_prompt}

It's time to remind the user about: {reminder_content}
The user asked for this reminder {elapsed_text} ({created_at_text}).
Generate a short, natural message in {language}.
"""

    template = load_prompt_with_fallback(
        "reminder_prompt",
        version="v1",
        fallback_content=fallback_prompt,
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
    )

    try:
        # Use the response LLM with custom settings for short message generation
        # Disable streaming to get usage_metadata in response
        # Type-safe config override using LLMConfig TypedDict
        from src.domains.agents.graphs.base_agent_builder import LLMConfig

        llm_config: LLMConfig = {"temperature": 0.7, "max_tokens": 150}
        llm = get_llm("response", config_override=llm_config)

        from src.infrastructure.llm.invoke_helpers import enrich_config_with_node_metadata

        invoke_config = enrich_config_with_node_metadata(None, "reminder_notification")
        response = await llm.ainvoke(system_prompt, config=invoke_config)
        raw_content = response.content
        if isinstance(raw_content, list):
            # Handle list of content blocks
            message = " ".join(str(c) for c in raw_content).strip()
        else:
            message = str(raw_content).strip()

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
        if language == "fr":
            fallback_msg = f"C'est l'heure ! Rappel ({created_at_text}) : {reminder_content}"
        else:
            fallback_msg = f"It's time! Reminder ({created_at_text}): {reminder_content}"

        return ReminderMessageResult(message=fallback_msg)


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
        from src.domains.agents.context.store import get_tool_context_store

        store = await get_tool_context_store()

        results = await store.asearch(
            (user_id, "memories"),
            query=reminder_content[:500],
            limit=5,
        )

        # Filter by score using centralized constant
        from src.core.constants import INITIATIVE_MEMORY_MIN_SCORE

        return [r.value for r in results if getattr(r, "score", 1.0) >= INITIATIVE_MEMORY_MIN_SCORE]

    except Exception as e:
        logger.warning(
            "reminder_memory_search_failed",
            user_id=user_id,
            error=str(e),
        )
        return []


async def process_pending_reminders() -> dict[str, Any]:
    """
    Process pending reminders that are due for notification.

    This function:
    1. Gets and locks pending reminders (FOR UPDATE SKIP LOCKED)
    2. For each reminder, generates personalized message (with creation date)
    3. Sends FCM notification
    4. Archives message in conversation
    5. Publishes to Redis for SSE
    6. DELETES the reminder from database (one-shot behavior)

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

                    # 3. Load personality (optional)
                    personality = None
                    if user.personality_id:
                        try:
                            personality = await personality_service.get_by_id(user.personality_id)
                        except Exception:
                            pass  # Use default if personality not found

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
                        from src.domains.chat.repository import ChatRepository
                        from src.domains.conversations.service import ConversationService
                        from src.domains.llm.pricing_service import AsyncPricingService

                        conv_service = ConversationService()
                        conversation = await conv_service.get_or_create_conversation(
                            reminder.user_id, db
                        )

                        # Calculate cost if we have token usage
                        cost_eur = 0.0
                        if result.tokens_in > 0 or result.tokens_out > 0:
                            try:
                                pricing_service = AsyncPricingService(db)
                                cost_eur = await pricing_service.calculate_token_cost_at_date(
                                    model=result.model_name or "claude-3-5-haiku-latest",
                                    input_tokens=result.tokens_in,
                                    output_tokens=result.tokens_out,
                                    cached_tokens=result.tokens_cache,
                                    at_date=datetime.now(UTC),
                                )
                            except Exception as price_error:
                                logger.warning(
                                    "reminder_cost_calculation_failed",
                                    reminder_id=str(reminder.id),
                                    error=str(price_error),
                                )

                            # Store token summary
                            try:
                                chat_repo = ChatRepository(db)
                                await chat_repo.create_or_update_token_summary(
                                    run_id=run_id,
                                    user_id=reminder.user_id,
                                    session_id=f"reminder_{reminder.id}",
                                    conversation_id=conversation.id,
                                    summary_data={
                                        FIELD_TOKENS_IN: result.tokens_in,
                                        FIELD_TOKENS_OUT: result.tokens_out,
                                        FIELD_TOKENS_CACHE: result.tokens_cache,
                                        FIELD_COST_EUR: cost_eur,
                                    },
                                )
                            except Exception as token_error:
                                logger.warning(
                                    "reminder_token_summary_failed",
                                    reminder_id=str(reminder.id),
                                    error=str(token_error),
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

                    # 9. DELETE the reminder (one-shot behavior, no need to keep it)
                    await reminder_repo.delete(reminder)

                    stats["notified"] += 1

                    logger.info(
                        "reminder_notified_and_deleted",
                        reminder_id=str(reminder.id),
                        user_id=str(reminder.user_id),
                        fcm_success=fcm_result.success_count,
                        fcm_failed=fcm_result.failure_count,
                    )

                except Exception as e:
                    # Handle error with retry logic
                    reminder.retry_count += 1

                    if reminder.retry_count >= MAX_RETRIES:
                        # Delete failed reminder after max retries
                        await reminder_repo.delete(reminder)
                        stats["failed"] += 1
                        logger.error(
                            "reminder_failed_permanently_deleted",
                            reminder_id=str(reminder.id),
                            error=str(e),
                            retry_count=reminder.retry_count,
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
