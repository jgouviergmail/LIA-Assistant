"""
Scheduled task for reminder notifications.

Runs every minute to check for pending reminders that need to be sent.

Flow (ADR-304 — no transaction is ever open while a model, a push service or
a channel answers):
1. Release the claims a crashed worker left PROCESSING past the stale timeout
2. Claim ONE due reminder (FOR UPDATE SKIP LOCKED → PROCESSING, committed)
3. Notify it:
   a. Generate personalized message via LLM (includes creation date/time)
   b. Record the occurrence that rings, so every surface can offer to
      postpone it (ADR-268 amendment 2026-11-16) — never a gate: a failed
      record sends the reminder with nothing to press, and is counted
   c. Deliver it: push, external channels, real time (``reminder_delivery``)
   d. Archive message in conversation
4. Settle it in a transaction of its own: ask the recurrence what to arm
   next — an instant RE-ARMS the reminder, `None` DELETES it. A single
   occurrence answers `None` once consumed, so "delete after notification"
   is that one rule, not a branch beside it.
5. Repeat, up to REMINDER_NOTIFICATION_BATCH_LIMIT reminders per tick, then
   purge a batch of fired occurrences whose snooze window closed — in a session
   of its own, never a gate either.

Metrics:
- background_job_duration_seconds{job_name="reminder_notification"}
- background_job_errors_total{job_name="reminder_notification"}
- reminder_firings_unrecorded_total (``metrics_reminders``)
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog

from src.core.config import settings
from src.core.constants import (
    REMINDER_MESSAGE_MAX_TOKENS,
    REMINDER_NOTIFICATION_MESSAGE_TYPE,
)
from src.core.constants import (
    REMINDER_NOTIFICATION_BATCH_LIMIT as REMINDER_BATCH_LIMIT,
)
from src.core.conversation_publication import CurrentPrimaryPublication
from src.core.i18n import get_language_name, normalize_language
from src.core.i18n_dates import format_elapsed, format_short_stamp, neutral_persona
from src.core.i18n_proactive import ProactiveMessages
from src.core.llm_usage import LLMBillingRecord
from src.core.recurrence import RecurrenceSpec, describe
from src.domains.agents.prompts.prompt_loader import (
    load_prompt,
)

# CRITICAL: Import Reminder model at module level to register it with SQLAlchemy
# before any database query is executed. This fixes the mapper initialization error:
# "expression 'Reminder' failed to locate a name" when User.reminders relationship
# is resolved during the first DB query.
from src.domains.reminders.models import Reminder  # noqa: F401
from src.infrastructure.cache.pricing_cache import capture_pricing_snapshot, get_cached_cost_usd_eur
from src.infrastructure.llm.message_text import coerce_content_to_text
from src.infrastructure.llm.output_truncation import is_output_truncated
from src.infrastructure.llm.token_capture import TokenCaptureHandler
from src.infrastructure.llm.usage_metadata import (
    reasoning_tokens_of,
)
from src.infrastructure.observability.metrics import (
    background_job_duration_seconds,
    background_job_errors_total,
)
from src.infrastructure.observability.metrics_reminders import reminder_firings_unrecorded_total
from src.infrastructure.scheduler.reminder_delivery import (
    deliver_reminder,
    get_localized_title,
    publish_reminder,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.domains.reminders.firings import FiringOffer
    from src.domains.reminders.repository import ReminderRepository

logger = structlog.get_logger(__name__)

# Maximum retries before marking as failed
MAX_RETRIES = 3


class ReminderMessageResult:
    """Result of reminder message generation with token usage."""

    def __init__(
        self,
        message: str,
        tokens_in: int = 0,
        tokens_out: int = 0,
        tokens_cache: int = 0,
        model_name: str = "",
        tokens_cache_write: int = 0,
        billing_records: tuple[LLMBillingRecord, ...] = (),
        billing_capture: TokenCaptureHandler | None = None,
        run_id: str | None = None,
    ):
        self.message = message
        self.tokens_in = tokens_in
        self.tokens_out = tokens_out
        self.tokens_cache = tokens_cache
        self.model_name = model_name
        # The part of ``tokens_in`` Claude wrote to its prompt cache (ADR-306).
        self.tokens_cache_write = tokens_cache_write
        self.billing_records = billing_records
        self.billing_capture = billing_capture
        self.run_id = run_id


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
    run_id: str | None = None,
    postponed: bool = False,
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
        postponed: The reminder is a copy the person postponed when it rang
            (ADR-268 amendment 2026-11-16): it is coming BACK, and the message
            must not present it as a request just made.

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
    if postponed:
        origin_context = load_prompt("reminder_origin_postponed", version="v1")
    elif recurrence is not None and recurrence.freq != "once":
        origin_context = load_prompt("reminder_origin_recurring", version="v1").format(
            schedule_human=describe(recurrence, language)
        )
    else:
        origin_context = load_prompt("reminder_origin_once", version="v1").format(
            created_at_text=created_at_text, elapsed_text=elapsed_text
        )

    template = load_prompt("reminder_prompt", version="v1")

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
        user_language=get_language_name(language),
        psyche_context=psyche_block,
        origin_context=origin_context,
    )
    if user_model_block:
        system_prompt += "\n\n" + user_model_block

    capture: TokenCaptureHandler | None = None
    operation_run_id = run_id or f"reminder_message_{uuid.uuid4().hex[:8]}"
    requested_model = "unknown"
    try:
        # The response slot, asked for a SHORT answer: no reasoning where the
        # model can stop, and the answer budget only there. Until 2026-09-12
        # this was a bare ``max_tokens=150`` on the slot as configured, which
        # on a model that thinks by default bought 150 tokens of chain of
        # thought and an empty answer (measured on deepseek-flash, 3 of 3).
        # The slot streams by design; usage_metadata is present on the
        # aggregated result because every streaming-capable provider requests
        # it explicitly (PROVIDER_USAGE_CAPABILITIES, ADR-220).
        from src.core.llm_config_helper import short_answer_config

        llm = get_llm(
            "response",
            config_override=short_answer_config(
                "response", max_tokens=REMINDER_MESSAGE_MAX_TOKENS, temperature=0.7
            ),
        )

        from src.infrastructure.llm.invoke_helpers import enrich_config_with_node_metadata

        invoke_config = enrich_config_with_node_metadata(None, "reminder_notification")
        from time import time

        from src.infrastructure.llm.usage_metadata import model_name_of
        from src.infrastructure.proactive.tracking import capture_spend_on_failure

        requested_model = model_name_of(llm) or "unknown"
        started_at = time()
        pricing_snapshot = capture_pricing_snapshot()
        capture = TokenCaptureHandler(requested_model)
        invoke_config["callbacks"] = [capture]
        try:
            owner = UUID(user_id) if user_id is not None else None
        except ValueError, TypeError:
            owner = None
        async with capture_spend_on_failure(
            capture,
            user_id=owner,
            task_type="reminder",
            target_id=operation_run_id,
            model_name=requested_model,
            source="scheduled",
            run_id=operation_run_id,
        ):
            response = await llm.ainvoke(system_prompt, config=invoke_config)
            capture.ensure_response_record(
                response,
                model_name=requested_model,
                started_at=started_at,
                snapshot=pricing_snapshot,
            )
            # Gemini 3.x returns content as list[dict] blocks; coerce to text so the
            # reminder message is the actual text, not a Python repr of the blocks.
            message = coerce_content_to_text(response.content).strip()

            # ONE reader for every provider's usage shape (usage_metadata.py): the
            # local copy this replaced read ``response_metadata["model"]`` -- a
            # key LangChain never sets -- and the raw ``cached_tokens`` rather than
            # the normalised ``input_token_details.cache_read``, so every reminder
            # was billed to an unnamed model at zero with no cache credit.
            records = capture.get_billing_records(requested_model)
            from src.infrastructure.llm.usage_metadata import UsageTokens

            tokens = UsageTokens(
                capture.tokens_in,
                capture.tokens_out,
                capture.tokens_cache,
                capture.tokens_cache_write,
            )
            model_name = records[-1].model_name if records else requested_model

            # An empty answer is not a message, and a cut one is not either
            # (ADR-275: a truncation is a refusal, never a rescue). The written
            # sentence goes out instead -- and the spend that DID happen is kept.
            if not message or is_output_truncated(response):
                logger.warning(
                    "reminder_message_empty",
                    model_name=model_name,
                    truncated=is_output_truncated(response),
                    tokens_out=tokens.completion,
                    reasoning_tokens=reasoning_tokens_of(response),
                    fallback=True,
                )
                message = ProactiveMessages.reminder_fallback_body(
                    created_at_text, reminder_content, language
                )

            return ReminderMessageResult(
                message=message,
                tokens_in=tokens.prompt,
                tokens_out=tokens.completion,
                tokens_cache=tokens.cached,
                model_name=model_name,
                tokens_cache_write=tokens.cache_write,
                billing_records=records,
                billing_capture=capture,
                run_id=operation_run_id,
            )

    except Exception as e:
        logger.warning(
            "reminder_message_generation_failed",
            error=str(e),
            fallback=True,
        )
        records = capture.get_billing_records(requested_model) if capture else ()
        return ReminderMessageResult(
            message=ProactiveMessages.reminder_fallback_body(
                created_at_text, reminder_content, language
            ),
            tokens_in=capture.tokens_in if capture else 0,
            tokens_out=capture.tokens_out if capture else 0,
            tokens_cache=capture.tokens_cache if capture else 0,
            tokens_cache_write=capture.tokens_cache_write if capture else 0,
            model_name=records[-1].model_name if records else "",
            billing_records=records,
            billing_capture=capture,
            run_id=operation_run_id,
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
                with_vectors=False,
            )

        # Return as list[dict] for backward compatibility with callers; the
        # vectors never left the database (latency lot 5)
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


async def _account_reminder_spend(
    db: AsyncSession | None,
    *,
    reminder_id: str,
    user_id: UUID,
    run_id: str,
    conversation_id: UUID | None,
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
        db: The caller's session, or None for settlement before delivery.
        reminder_id: Reminder being notified, for the log line.
        user_id: Account to bill.
        run_id: Pre-generated run id, already injected into the archived
            message's metadata — it must be reused, not regenerated, or the
            message and its cost stop pointing at each other.
        conversation_id: The archive's conversation, if already known.
        result: The generated message and its token usage.

    Returns:
        The call's cost in euros, for the archived message's metadata.
    """
    from src.infrastructure.scheduler.reminder_billing import account_reminder_spend

    return await account_reminder_spend(
        db,
        reminder_id=reminder_id,
        user_id=user_id,
        run_id=run_id,
        conversation_id=conversation_id,
        result=result,
        cost_calculator=get_cached_cost_usd_eur,
    )


async def process_pending_reminders() -> dict[str, Any]:
    """Notify every reminder that is due, one claimed at a time (ADR-304).

    1. Releases the claims a crashed worker left PROCESSING past the stale
       timeout (``recover_stale_processing``).
    2. Claims ONE due reminder — ``FOR UPDATE SKIP LOCKED`` then PROCESSING,
       committed at once, so no row stays locked while it is notified.
    3. Notifies it holding no transaction: the message is generated, pushed,
       sent to the external channels, archived and published, each read or
       write in a short session of its own.
    4. Settles it in a transaction of its own, conditioned on the claim still
       standing: re-armed on its next instant, deleted when nothing follows
       (``rearm_after`` answering None), released on a temporary skip, retried
       — or its occurrence abandoned — on failure.

    It used to lock the whole batch (up to 100 rows) and keep one transaction
    open through every model call and every push of that batch.

    Returns:
        Stats dict with processed, notified, failed, skipped counts.
    """
    start_time = time.perf_counter()
    job_name = "reminder_notification"
    stats: dict[str, Any] = {"processed": 0, "notified": 0, "failed": 0, "skipped": 0}

    try:
        from src.domains.reminders.repository import ReminderRepository
        from src.infrastructure.database.session import get_db_context

        async with get_db_context() as db:
            await ReminderRepository(db).recover_stale_processing(
                settings.reminder_processing_stale_timeout_minutes
            )

        for _ in range(REMINDER_BATCH_LIMIT):
            reminder = await _claim_next_due()
            if reminder is None:
                break
            stats["processed"] += 1
            counter = await _notify_and_settle(reminder)
            if counter is not None:
                stats[counter] += 1

        await _purge_closed_windows()

        duration = time.perf_counter() - start_time
        background_job_duration_seconds.labels(job_name=job_name).observe(duration)
        if stats["processed"]:
            logger.info(
                "reminder_notification_completed", **stats, duration_seconds=round(duration, 3)
            )
        return stats

    except Exception as e:
        background_job_errors_total.labels(job_name=job_name).inc()
        duration = time.perf_counter() - start_time
        background_job_duration_seconds.labels(job_name=job_name).observe(duration)
        logger.error(
            "reminder_notification_failed",
            error=str(e),
            error_type=type(e).__name__,
            duration_seconds=round(duration, 3),
        )
        raise


async def _purge_closed_windows() -> None:
    """Delete a batch of occurrences whose snooze window closed.

    Housekeeping, in a session of its own and AFTER the batch: a failure here is
    logged and left to the next tick — it must never keep a reminder from
    ringing (measured 2026-11-16: run in the recovery's transaction, a missing
    table stopped every reminder of the instance).
    """
    from src.domains.reminders.firing_service import ReminderFiringService
    from src.infrastructure.database.session import get_db_context

    try:
        async with get_db_context() as db:
            await ReminderFiringService(db).purge_expired(now=datetime.now(UTC))
    except Exception as error:
        logger.warning("reminder_firings_purge_failed", error_type=type(error).__name__)


async def _claim_next_due() -> Reminder | None:
    """Claim the next due reminder in a transaction committed at once."""
    from src.domains.reminders.repository import ReminderRepository
    from src.infrastructure.database.session import get_db_context

    async with get_db_context() as db:
        return await ReminderRepository(db).claim_next_due()


async def _settle(
    reminder_id: UUID,
    apply: Callable[[ReminderRepository, Reminder], Awaitable[datetime | None]],
) -> datetime | None:
    """Apply ``apply`` to the claimed row, in a transaction of its own.

    Conditioned on the claim still standing: a reminder its owner deleted
    meanwhile — or one released as stale and claimed again — is left alone.

    Returns:
        What ``apply`` answered (the next instant of a re-armed reminder).
    """
    from src.domains.reminders.repository import ReminderRepository
    from src.infrastructure.database.session import get_db_context

    async with get_db_context() as db:
        repo = ReminderRepository(db)
        reminder = await repo.get_processing_for_update(reminder_id)
        if reminder is None:
            logger.info("reminder_settlement_skipped_claim_gone", reminder_id=str(reminder_id))
            return None
        return await apply(repo, reminder)


async def _release(_repo: ReminderRepository, reminder: Reminder) -> None:
    """Back to PENDING: a TEMPORARY skip must leave the reminder selectable.

    Left PROCESSING it would wait for the stale recovery; deleted, it would be
    lost for good — a budget window or a paused account is not a reason to
    destroy what the person asked for.
    """
    from src.domains.reminders.models import ReminderStatus

    reminder.status = ReminderStatus.PENDING.value


async def _drop(repo: ReminderRepository, reminder: Reminder) -> None:
    """Delete a reminder nobody can receive (its account is gone)."""
    await repo.delete(reminder)


async def _rearm_or_drop(repo: ReminderRepository, reminder: Reminder) -> datetime | None:
    """Re-arm on the next instant, or delete when nothing follows.

    ONE rule, no branch on "is this recurring": a single occurrence answers
    None here — which IS the historical one-shot behaviour — and a recurring
    one answers its next instant.
    """
    from src.domains.reminders.models import ReminderStatus
    from src.domains.reminders.service import next_arming

    next_at = next_arming(reminder)
    if next_at is None:
        await repo.delete(reminder)
        return None
    reminder.trigger_at = next_at
    reminder.status = ReminderStatus.PENDING.value
    # A row that SURVIVES its notification must forget its past failures:
    # `retry_count` was never reset because the row always died at this
    # point, so a recurring reminder would have deleted itself after three
    # failures spread over its whole life.
    reminder.retry_count = 0
    reminder.notification_error = None
    return next_at


async def _notify_and_settle(reminder: Reminder) -> str | None:
    """Notify one claimed reminder and settle it; the counter it moves, if any."""
    try:
        return await _notify(reminder)
    except Exception as error:
        return await _settle_failure(reminder.id, error)


async def _settle_failure(reminder_id: UUID, error: Exception) -> str | None:
    """Retry the reminder, or abandon THIS occurrence past MAX_RETRIES.

    Returns:
        ``"failed"`` when the occurrence was abandoned, None on a retry.
    """
    from src.domains.reminders.models import ReminderStatus

    abandoned = False

    async def _apply(repo: ReminderRepository, reminder: Reminder) -> datetime | None:
        nonlocal abandoned
        reminder.retry_count += 1
        if reminder.retry_count < MAX_RETRIES:
            reminder.status = ReminderStatus.PENDING.value
            reminder.notification_error = str(error)
            logger.warning(
                "reminder_retry_scheduled",
                reminder_id=str(reminder.id),
                error=str(error),
                retry_count=reminder.retry_count,
            )
            return None
        # Give up on THIS occurrence, not on the series: a recurring reminder
        # destroyed by three transient failures would take its whole schedule
        # with it; a single occurrence has nothing after it and goes.
        abandoned = True
        next_at = await _rearm_or_drop(repo, reminder)
        if next_at is not None:
            reminder.notification_error = str(error)
        logger.error(
            "reminder_occurrence_abandoned",
            reminder_id=str(reminder.id),
            error=str(error),
            retry_count=MAX_RETRIES,
            rearmed_at=next_at.isoformat() if next_at else None,
        )
        return next_at

    await _settle(reminder_id, _apply)
    return "failed" if abandoned else None


async def _notify(reminder: Reminder) -> str:
    """Generate, deliver and archive one reminder, then settle it.

    Returns:
        ``"notified"`` or ``"skipped"``.
    """
    from src.domains.usage_limits.service import UsageLimitService

    if await UsageLimitService.is_user_blocked_for_llm(
        reminder.user_id,
        layer="reminder_notification",
        extra_log_fields={"reminder_id": str(reminder.id)},
    ):
        await _settle(reminder.id, _release)
        return "skipped"

    user, personality = await _load_owner(reminder)
    if user is None:
        logger.warning(
            "reminder_user_not_found",
            reminder_id=str(reminder.id),
            user_id=str(reminder.user_id),
        )
        await _settle(reminder.id, _drop)
        return "skipped"
    if not user.is_active:
        # Deactivation is reversible, so deleting would destroy a reminder the
        # person may still want; a hard delete is the account purge's job
        # (`user_data_map`: reminders are purged in full on erasure).
        logger.info(
            "reminder_skipped_user_inactive",
            reminder_id=str(reminder.id),
            user_id=str(reminder.user_id),
        )
        await _settle(reminder.id, _release)
        return "skipped"

    language = normalize_language(user.language)
    operation_run_id = f"reminder_{reminder.id}_{uuid.uuid4().hex[:8]}"
    result = await generate_reminder_message(
        original_message=reminder.original_message,
        reminder_content=reminder.content,
        # A postponed copy speaks of the request it carries, not of the press.
        created_at=reminder.first_asked_at or reminder.created_at,
        user_timezone=reminder.user_timezone,
        personality=personality,
        memories=await get_relevant_memories(str(reminder.user_id), reminder.content),
        language=language,
        user_id=str(reminder.user_id),
        recurrence=reminder.recurrence_spec,
        run_id=operation_run_id,
        postponed=reminder.first_asked_at is not None,
    )
    message = f"🔔 {result.message}"  # always the bell for a reminder
    title = get_localized_title(language)
    await _bill_before_delivery(reminder, result, operation_run_id)
    offer = await _record_firing(reminder)
    fcm_result = await deliver_reminder(
        reminder, title=title, message=message, language=language, offer=offer
    )
    await _archive(reminder, message=message, result=result, language=language, offer=offer)
    await publish_reminder(reminder, title=title, message=message, offer=offer)

    next_at = await _settle(reminder.id, _rearm_or_drop)
    logger.info(
        "reminder_notified",
        reminder_id=str(reminder.id),
        user_id=str(reminder.user_id),
        rearmed_at=next_at.isoformat() if next_at else None,
        fcm_success=fcm_result.success_count,
        fcm_failed=fcm_result.failure_count,
    )
    return "notified"


async def _bill_before_delivery(
    reminder: Reminder, result: ReminderMessageResult, run_id: str
) -> None:
    """Settle captured attempts before delivery can fail or be cancelled."""
    if getattr(result, "billing_capture", None) is not None:
        await _account_reminder_spend(
            None,
            reminder_id=str(reminder.id),
            user_id=reminder.user_id,
            run_id=run_id,
            conversation_id=None,
            result=result,
        )


async def _record_firing(reminder: Reminder) -> FiringOffer | None:
    """Record the occurrence about to ring, in a short session of its own.

    Never a gate: a reminder whose occurrence cannot be written still rings,
    with nothing to press, and the miss is counted.

    Returns:
        What the notification offers, or None when the record failed.
    """
    from src.domains.reminders.firing_service import ReminderFiringService
    from src.infrastructure.database.session import get_db_context

    try:
        async with get_db_context() as db:
            return await ReminderFiringService(db).record(reminder, fired_at=datetime.now(UTC))
    except Exception as error:
        reminder_firings_unrecorded_total.inc()
        logger.warning(
            "reminder_firing_unrecorded",
            reminder_id=str(reminder.id),
            error_type=type(error).__name__,
        )
        return None


async def _load_owner(reminder: Reminder) -> tuple[Any | None, Any | None]:
    """The reminder's owner and their personality, read in a short session."""
    from src.domains.personalities.service import PersonalityService
    from src.domains.users.service import UserService
    from src.infrastructure.database.session import get_db_context

    async with get_db_context() as db:
        user = await UserService(db).get_user_by_id(reminder.user_id)
        personality = None
        if user is not None and user.personality_id:
            # An unreadable personality falls back to the neutral voice.
            with suppress(Exception):
                personality = await PersonalityService(db).get_by_id(user.personality_id)
    return user, personality


async def _archive(
    reminder: Reminder,
    *,
    message: str,
    result: ReminderMessageResult,
    language: str,
    offer: FiringOffer | None = None,
) -> None:
    """Archive the notification in the person's conversation, with its cost.

    With an offer, the bubble names its occurrence and until when it can be
    postponed: the chat draws the « later » from them, nothing else.
    """
    from src.domains.conversations.service import ConversationService
    from src.infrastructure.database.session import get_db_context

    run_id = getattr(result, "run_id", None) or f"reminder_{reminder.id}_{uuid.uuid4().hex[:8]}"
    try:
        conv_service = ConversationService()
        async with get_db_context() as db:
            conversation = await conv_service.get_or_create_conversation(
                reminder.user_id, db, language=language
            )
            cost_eur = await _account_reminder_spend(
                db,
                reminder_id=str(reminder.id),
                user_id=reminder.user_id,
                run_id=run_id,
                conversation_id=conversation.id,
                result=result,
            )
            # Archive with run_id: the message and its token summary point at
            # each other.
            await conv_service.archive_message(
                conversation_id=CurrentPrimaryPublication(reminder.user_id),
                role="assistant",
                content=message,
                metadata={
                    "type": REMINDER_NOTIFICATION_MESSAGE_TYPE,
                    "reminder_id": str(reminder.id),
                    "original_trigger_at": reminder.trigger_at.isoformat(),
                    "created_at": reminder.created_at.isoformat(),
                    "run_id": run_id,
                    **(
                        {
                            "firing_id": str(offer.firing_id),
                            "snoozable_until": offer.snoozable_until.isoformat(),
                        }
                        if offer is not None
                        else {}
                    ),
                },
                db=db,
            )
        logger.debug(
            "reminder_message_archived",
            reminder_id=str(reminder.id),
            tokens_in=result.tokens_in,
            tokens_out=result.tokens_out,
            cost_eur=float(cost_eur),
        )
    except Exception as archive_error:
        logger.warning(
            "reminder_archive_failed", reminder_id=str(reminder.id), error=str(archive_error)
        )
