"""
Scheduled task for executing scheduled actions.

Runs every 60s to check for due actions and execute them through the agent pipeline.
Uses FOR UPDATE SKIP LOCKED to prevent concurrent processing.

Flow (for each due action):
1. Guard: check no HITL interrupt pending on user's conversation
2. Execute via stream_chat_response(auto_approve_plan=True) with timeout
3. Dispatch notification (FCM + SSE, archive handled by stream_chat_response)
4. Recalculate next_trigger_at via CronTrigger
5. Mark success or failure (auto-disable after N consecutive failures)

Metrics:
- background_job_duration_seconds{job_name="scheduled_action_executor"}
- background_job_errors_total{job_name="scheduled_action_executor"}
"""

import asyncio
import json
import time
import uuid
from typing import Any

import structlog

from src.core.config import settings
from src.core.constants import (
    DEFAULT_USER_DISPLAY_TIMEZONE,
    SCHEDULED_ACTIONS_BATCH_SIZE,
    SCHEDULED_ACTIONS_EXECUTION_TIMEOUT_SECONDS,
    SCHEDULED_ACTIONS_MAX_CONSECUTIVE_FAILURES,
    SCHEDULED_ACTIONS_MAX_RETRIES,
    SCHEDULED_ACTIONS_RETRY_DELAY_SECONDS,
    SCHEDULED_ACTIONS_SESSION_PREFIX,
    SCHEDULED_ACTIONS_STALE_TIMEOUT_MINUTES,
    SCHEDULER_JOB_SCHEDULED_ACTION_EXECUTOR,
)

# CRITICAL: Import model at module level to register with SQLAlchemy metadata
from src.domains.scheduled_actions.models import ScheduledAction  # noqa: F401
from src.infrastructure.observability.metrics import (
    background_job_duration_seconds,
    background_job_errors_total,
)

logger = structlog.get_logger(__name__)


def _get_localized_title(language: str) -> str:
    """Get localized notification title for scheduled action results."""
    titles = {
        "fr": "Action planifiée",
        "en": "Scheduled Action",
        "es": "Acción programada",
        "de": "Geplante Aktion",
        "it": "Azione pianificata",
        "zh": "计划操作",
    }
    return titles.get(language, "Scheduled Action")


def _truncate(text: str, max_length: int = 150) -> str:
    """Truncate text for notification body."""
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


async def execute_single_action(
    action_id: uuid.UUID,
    user_id: uuid.UUID,
) -> str:
    """
    Execute a single scheduled action through the agent pipeline.

    Shared by the scheduler job and the POST /execute endpoint.
    Opens its own DB session (background task context).

    Args:
        action_id: Scheduled action UUID.
        user_id: User UUID.

    Returns:
        Response content from the agent.
    """
    from src.domains.agents.api.service import AgentService
    from src.domains.conversations.service import ConversationService
    from src.domains.notifications.service import FCMNotificationService
    from src.domains.scheduled_actions.repository import ScheduledActionRepository
    from src.domains.scheduled_actions.schedule_helpers import compute_next_trigger_utc
    from src.domains.users.service import UserService
    from src.infrastructure.cache.redis import get_redis_cache
    from src.infrastructure.database.session import get_db_context

    async with get_db_context() as db:
        repo = ScheduledActionRepository(db)
        user_service = UserService(db)

        action = await repo.get_by_id(action_id)
        if not action:
            logger.warning(
                "scheduled_action_execute_not_found",
                action_id=str(action_id),
            )
            return ""

        user = await user_service.get_user_by_id(user_id)
        if not user:
            logger.warning(
                "scheduled_action_execute_user_not_found",
                action_id=str(action_id),
                user_id=str(user_id),
            )
            return ""

        user_language = user.language or settings.default_language
        user_timezone = user.timezone or DEFAULT_USER_DISPLAY_TIMEZONE
        session_id = f"{SCHEDULED_ACTIONS_SESSION_PREFIX}{action.id}"

        # === Guard: Check for pending HITL interrupt on user's conversation ===
        try:
            conv_service = ConversationService()
            conversation = await conv_service.get_or_create_conversation(user_id, db)
            agent_service = AgentService()
            await agent_service._ensure_graph_built()

            from langchain_core.runnables import RunnableConfig

            config = RunnableConfig(configurable={"thread_id": str(conversation.id)})
            state_snapshot = await agent_service.graph.aget_state(config)

            has_pending_hitl = any(
                hasattr(t, "interrupts") and t.interrupts for t in (state_snapshot.tasks or [])
            )
            if has_pending_hitl:
                logger.info(
                    "scheduled_action_skipped_hitl_pending",
                    action_id=str(action_id),
                    user_id=str(user_id),
                    conversation_id=str(conversation.id),
                )
                # Recalculate next trigger for the next cycle (skip without error)
                next_trigger = compute_next_trigger_utc(
                    days_of_week=action.days_of_week,
                    hour=action.trigger_hour,
                    minute=action.trigger_minute,
                    user_timezone=action.user_timezone,
                )
                await repo.mark_execution_success(action, next_trigger)
                await db.commit()
                return ""
        except Exception as guard_err:
            logger.warning(
                "scheduled_action_hitl_guard_error",
                action_id=str(action_id),
                error=str(guard_err),
            )
            # Continue execution - guard failure should not block execution

        # === Execute via agent pipeline (with retry on transient errors) ===
        response_content = ""
        last_error: Exception | None = None

        for attempt in range(
            1, SCHEDULED_ACTIONS_MAX_RETRIES + 2
        ):  # +2: range(1, max+2) = [1..max+1]
            # Unique session per attempt to avoid stale checkpoint state.
            # If attempt 1 partially executes the graph before timing out,
            # attempt 2 must start from a clean state, not resume a broken checkpoint.
            attempt_session_id = session_id if attempt == 1 else f"{session_id}_retry_{attempt}"

            try:
                agent_service = AgentService()

                async def _run_stream(
                    svc: AgentService = agent_service,
                    _sid: str = attempt_session_id,
                ) -> str:
                    content_parts: list[str] = []
                    async for chunk in svc.stream_chat_response(
                        user_message=action.action_prompt,
                        user_id=user_id,
                        session_id=_sid,
                        user_timezone=user_timezone,
                        user_language=user_language,
                        auto_approve_plan=True,
                    ):
                        if (
                            chunk.type == "token"
                            and chunk.content
                            and isinstance(chunk.content, str)
                        ):
                            content_parts.append(chunk.content)
                        elif chunk.type == "hitl_interrupt":
                            # HITL interrupt during execution -> non-retryable
                            raise RuntimeError("HITL interrupt during scheduled action execution")
                    return "".join(content_parts)

                response_content = await asyncio.wait_for(
                    _run_stream(),
                    timeout=SCHEDULED_ACTIONS_EXECUTION_TIMEOUT_SECONDS,
                )

                # Success — recalculate next trigger
                next_trigger = compute_next_trigger_utc(
                    days_of_week=action.days_of_week,
                    hour=action.trigger_hour,
                    minute=action.trigger_minute,
                    user_timezone=action.user_timezone,
                )
                await repo.mark_execution_success(action, next_trigger)

                logger.info(
                    "scheduled_action_executed_success",
                    action_id=str(action_id),
                    user_id=str(user_id),
                    response_length=len(response_content),
                    next_trigger_at=next_trigger.isoformat(),
                    attempt=attempt,
                )
                last_error = None
                break

            except (TimeoutError, ConnectionError, OSError) as transient_err:
                last_error = transient_err
                is_last_attempt = attempt > SCHEDULED_ACTIONS_MAX_RETRIES

                if is_last_attempt:
                    logger.warning(
                        "scheduled_action_transient_error_final",
                        action_id=str(action_id),
                        error=str(transient_err),
                        error_type=type(transient_err).__name__,
                        attempt=attempt,
                    )
                else:
                    logger.warning(
                        "scheduled_action_transient_error_retrying",
                        action_id=str(action_id),
                        error=str(transient_err),
                        error_type=type(transient_err).__name__,
                        attempt=attempt,
                        retry_delay=SCHEDULED_ACTIONS_RETRY_DELAY_SECONDS,
                    )
                    await asyncio.sleep(SCHEDULED_ACTIONS_RETRY_DELAY_SECONDS)

            except Exception as exec_err:
                # Non-retryable error (HITL interrupt, RuntimeError, etc.)
                last_error = exec_err
                logger.error(
                    "scheduled_action_execution_error",
                    action_id=str(action_id),
                    error=f"{type(exec_err).__name__}: {exec_err}",
                    attempt=attempt,
                )
                break

        # Mark failure if all attempts failed
        if last_error is not None:
            if isinstance(last_error, TimeoutError):
                error_msg = (
                    f"Execution timed out after {SCHEDULED_ACTIONS_EXECUTION_TIMEOUT_SECONDS}s"
                    f" ({SCHEDULED_ACTIONS_MAX_RETRIES + 1} attempts)"
                )
            else:
                error_msg = f"{type(last_error).__name__}: {last_error}"

            next_trigger = compute_next_trigger_utc(
                days_of_week=action.days_of_week,
                hour=action.trigger_hour,
                minute=action.trigger_minute,
                user_timezone=action.user_timezone,
            )
            await repo.mark_execution_failure(
                action,
                error_msg,
                next_trigger,
                max_consecutive_failures=SCHEDULED_ACTIONS_MAX_CONSECUTIVE_FAILURES,
            )
            logger.warning(
                "scheduled_action_failed_after_retries",
                action_id=str(action_id),
                error=error_msg,
                total_attempts=attempt,
            )

        # === Dispatch notification (FCM + SSE) ===
        # Note: archive_enabled=False because stream_chat_response archives automatically
        if response_content:
            try:
                fcm_service = FCMNotificationService(db)
                title = _get_localized_title(user_language)
                body = _truncate(response_content)

                await fcm_service.send_to_user(
                    user_id=user_id,
                    title=f"{title}: {action.title}",
                    body=body,
                    data={"type": "scheduled_action", "action_id": str(action_id)},
                )
            except Exception as fcm_err:
                logger.warning(
                    "scheduled_action_fcm_failed",
                    action_id=str(action_id),
                    error=str(fcm_err),
                )

            try:
                redis = await get_redis_cache()
                if redis:
                    channel = f"user_notifications:{user_id}"
                    await redis.publish(
                        channel,
                        json.dumps(
                            {
                                "type": "scheduled_action",
                                "content": _truncate(response_content, 500),
                                "action_id": str(action_id),
                                "title": action.title,
                            },
                            ensure_ascii=False,
                        ),
                    )
            except Exception as sse_err:
                logger.warning(
                    "scheduled_action_sse_failed",
                    action_id=str(action_id),
                    error=str(sse_err),
                )

        await db.commit()

    return response_content


async def process_scheduled_actions() -> dict[str, Any]:
    """
    Scheduler job: process all due scheduled actions.

    Runs every 60s via APScheduler. Pattern:
    1. SchedulerLock (Redis SETNX) for multi-worker safety
    2. Recover stale 'executing' actions (crash recovery)
    3. Get and lock due actions (FOR UPDATE SKIP LOCKED)
    4. Execute each action sequentially
    5. Track metrics

    Returns:
        Stats dict with processed, success, failed counts.
    """
    start_time = time.perf_counter()
    job_name = "scheduled_action_executor"

    stats: dict[str, Any] = {
        "processed": 0,
        "success": 0,
        "failed": 0,
        "skipped": 0,
        "recovered": 0,
    }

    try:
        from src.domains.scheduled_actions.repository import ScheduledActionRepository
        from src.infrastructure.cache.redis import get_redis_cache
        from src.infrastructure.database.session import get_db_context
        from src.infrastructure.locks.scheduler_lock import SchedulerLock

        redis = await get_redis_cache()
        async with SchedulerLock(redis, SCHEDULER_JOB_SCHEDULED_ACTION_EXECUTOR) as lock:
            if not lock.acquired:
                logger.debug(
                    "scheduled_action_executor_skipped_lock_busy",
                    job_id=SCHEDULER_JOB_SCHEDULED_ACTION_EXECUTOR,
                )
                return stats

            async with get_db_context() as db:
                repo = ScheduledActionRepository(db)

                # 1. Recovery: reset stale 'executing' actions
                recovered = await repo.recover_stale_executing(
                    timeout_minutes=SCHEDULED_ACTIONS_STALE_TIMEOUT_MINUTES
                )
                stats["recovered"] = recovered

                # 2. Get and lock due actions (FOR UPDATE SKIP LOCKED)
                actions = await repo.get_and_lock_due_actions(limit=SCHEDULED_ACTIONS_BATCH_SIZE)

                if not actions:
                    await db.commit()
                    duration = time.perf_counter() - start_time
                    background_job_duration_seconds.labels(job_name=job_name).observe(duration)
                    return stats

                # Extract identifiers before commit (ORM objects expire after commit)
                action_refs = [(action.id, action.user_id) for action in actions]

                # CRITICAL: Commit status='executing' transition to release FOR UPDATE locks.
                # execute_single_action opens its own session - without this commit it would
                # deadlock trying to UPDATE rows still locked by this transaction.
                # If the process crashes after this commit, recover_stale_executing will
                # reset stale 'executing' actions on the next scheduler cycle.
                await db.commit()

                logger.info(
                    "scheduled_action_batch_started",
                    count=len(action_refs),
                )

                # 3. Process each action sequentially
                # Each call opens its own DB session and handles success/failure marking
                for action_id, action_user_id in action_refs:
                    stats["processed"] += 1

                    try:
                        response = await execute_single_action(
                            action_id=action_id,
                            user_id=action_user_id,
                        )
                        if response:
                            stats["success"] += 1
                        else:
                            stats["skipped"] += 1

                    except Exception as e:
                        stats["failed"] += 1
                        logger.error(
                            "scheduled_action_process_error",
                            action_id=str(action_id),
                            error=str(e),
                        )
                        # execute_single_action handles its own failure marking.
                        # If it raises unexpectedly, the action stays in 'executing'
                        # and will be recovered by recover_stale_executing.

        # Track duration
        duration = time.perf_counter() - start_time
        background_job_duration_seconds.labels(job_name=job_name).observe(duration)

        logger.info(
            "scheduled_action_executor_completed",
            **stats,
            duration_seconds=round(duration, 3),
        )

        return stats

    except Exception as e:
        background_job_errors_total.labels(job_name=job_name).inc()

        duration = time.perf_counter() - start_time
        background_job_duration_seconds.labels(job_name=job_name).observe(duration)

        logger.error(
            "scheduled_action_executor_failed",
            error=str(e),
            error_type=type(e).__name__,
            duration_seconds=round(duration, 3),
        )
        raise
