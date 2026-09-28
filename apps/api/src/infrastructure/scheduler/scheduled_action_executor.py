"""
Scheduled task for executing scheduled actions.

Runs every 60s to check for due actions and execute them through the agent pipeline.
Uses FOR UPDATE SKIP LOCKED to prevent concurrent processing.

Flow (for each due action):
1. Condition routines only: check the condition, and go on only for a NEW fact
   under the daily cap (ADR-322) — a check that finds nothing new re-arms and
   ends there, with no run row
2. Propose-first routines: notify with a link and stop
3. Guard: check no HITL interrupt pending on user's conversation
4. Execute via stream_chat_response(auto_approve_plan=True) with timeout
5. Mark success or failure (auto-disable after N consecutive failures) and
   re-arm from the routine's clock (``trigger.TriggerPlan``)
6. Dispatch notification (FCM + SSE, archive handled by stream_chat_response)

No transaction is held across a wait (ADR-304): the reads are committed before
the condition's source answers, before the model runs and before any push.

Metrics:
- background_job_duration_seconds{job_name="scheduled_action_executor"}
- background_job_errors_total{job_name="scheduled_action_executor"}
"""

import asyncio
import json
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

import structlog

from src.core.config import settings
from src.core.constants import (
    DEFAULT_USER_DISPLAY_TIMEZONE,
    SCHEDULED_ACTIONS_BATCH_SIZE,
    SCHEDULED_ACTIONS_MAX_CONSECUTIVE_FAILURES,
    SCHEDULED_ACTIONS_MAX_RETRIES,
    SCHEDULED_ACTIONS_RETRY_DELAY_SECONDS,
    SCHEDULED_ACTIONS_SESSION_PREFIX,
    SCHEDULED_ACTIONS_SSE_PREVIEW_MAX_LENGTH,
)
from src.core.i18n import normalize_language
from src.core.i18n_drafts import label_separator
from src.core.time_utils import now_utc
from src.core.user_display import resolve_user_display_name
from src.domains.scheduled_actions.condition_ledger import ConditionLedger

# CRITICAL: Import model at module level to register with SQLAlchemy metadata
from src.domains.scheduled_actions.models import (  # noqa: F401
    ScheduledAction,
    ScheduledRunOutcome,
    TriggerKind,
)
from src.domains.scheduled_actions.runs import record_run
from src.domains.scheduled_actions.trigger import TriggerPlan
from src.infrastructure.cache.user_channel import user_notifications_channel
from src.infrastructure.observability.metrics import (
    background_job_duration_seconds,
    background_job_errors_total,
)
from src.infrastructure.proactive.notification import plain_text_for_notification
from src.infrastructure.scheduler.out_of_turn_run import (
    RunOutcome,
    StreamRequest,
    conversation_has_pending_hitl,
    stream_instruction,
)

logger = structlog.get_logger(__name__)


def _get_localized_title(language: str) -> str:
    """Get the localized notification title for scheduled action results.

    Delegates to the centralized ``ProactiveMessages`` (i18n systemic rule).
    The previous inline table was keyed "zh" while ``User.language`` is
    backend-canonical "zh-CN" — Chinese users silently got the English title.

    Args:
        language: Backend-canonical user language code (e.g. "zh-CN").

    Returns:
        Localized title string.
    """
    from src.core.i18n_proactive import ProactiveMessages

    return ProactiveMessages.notification_title("scheduled_action", language)


def _truncate(text: str, max_length: int | None = None) -> str:
    """Truncate already-flattened text for a notification body.

    Args:
        text: Plain text — run it through ``plain_text_for_notification`` first;
            truncating raw HTML cuts mid-tag.
        max_length: Character budget. Defaults to
            ``settings.proactive_notification_max_length``, the same
            user-facing setting the proactive dispatcher honors.

    Returns:
        The text, ellipsized when it exceeds the budget.
    """
    if max_length is None:
        max_length = settings.proactive_notification_max_length
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


def _next_trigger(action: ScheduledAction, due_at: datetime | None) -> datetime | None:
    """When to arm this routine after the tick that has just ended.

    Every exit of :func:`execute_single_action` — nothing new to act on,
    proposal, pending HITL, success, final failure — re-arms the SAME way, and
    this is the one place that says how. They used to be five literal copies of
    the same call: a rule in five copies gets changed in four, and the exit
    nobody updated re-arms differently from its siblings with nothing to reveal
    it (the shape ADR-248's second invariant names).

    Which clock re-arms it is the routine's own (ADR-322): its recurrence, or
    the system's next check.

    Args:
        action: The routine that has just run.
        due_at: The pending due instant when the tick started (UTC), or
            ``None`` when nothing was pending — a manual run on an exhausted
            series reaches here.

    Returns:
        The next instant, or ``None`` when nothing follows — which the
        repository stores as a null trigger.
    """
    return TriggerPlan.of(action).after_tick(due_at=due_at, now=now_utc())


@dataclass(frozen=True, slots=True)
class _ConditionGate:
    """What a condition check decided, for the rest of the tick (ADR-322)."""

    note: str | None
    """The context line naming the NEW facts, for the routine's prompt."""
    served_state: dict[str, Any] | None
    """The ledger once the new facts are served (a run answered, a proposal sent)."""
    unserved_state: dict[str, Any] | None
    """The ledger if they are not (a pending question, a failed run): still new."""


#: A time routine's gate: no fact, and no ledger to write.
_NO_CONDITION = _ConditionGate(note=None, served_state=None, unserved_state=None)


async def _daily_cap_reached(db: Any, action: ScheduledAction, now: datetime) -> bool:
    """Whether a condition routine already fired its daily share (ADR-322).

    Counted from the run history, since the local midnight of the routine's
    day: the history is the record of what ran, and a second counter beside it
    would be a second answer to the same question.

    Args:
        db: The tick's session.
        action: The routine.
        now: The tick's start (UTC).

    Returns:
        True once ``scheduled_actions_condition_max_fires_per_day`` fires happened.
    """
    from src.domains.scheduled_actions.run_repository import ScheduledActionRunRepository

    tz = ZoneInfo(action.user_timezone)
    local_midnight = datetime.combine(now.astimezone(tz).date(), datetime.min.time(), tz)
    fires = await ScheduledActionRunRepository(db).count_fires_since(
        action.id, local_midnight.replace(fold=0).astimezone(UTC)
    )
    return fires >= settings.scheduled_actions_condition_max_fires_per_day


async def _condition_gate(
    db: Any,
    repo: Any,
    action: ScheduledAction,
    user_id: uuid.UUID,
    *,
    started_at: datetime,
    due_at: datetime | None,
) -> _ConditionGate | None:
    """Check the condition; ``None`` when there is nothing new to act on.

    A fact is new when the ledger never saw its key. A check that finds nothing
    new, cannot read its source, or meets the daily cap RE-ARMS and ends the
    tick here — recorded on the routine's ledger (``last_checked_at``), never
    as a run row: at the default cadence of one check every ten minutes, a row
    per unmet check would write 144 a day per routine for nothing that happened.

    Args:
        db: The tick's session.
        repo: The routine repository on that session.
        action: The routine.
        user_id: Its owner.
        started_at: When the tick started (UTC).
        due_at: The pending due instant when the tick started.

    Returns:
        The gate to run under, or ``None`` when the tick is over (committed).
    """
    from src.domains.users.models import User as UserModel
    from src.infrastructure.scheduler.condition_evaluators import evaluate_condition

    # The evaluators read through the briefing fetchers, which need the ORM
    # User (not the UserProfile schema get_user_by_id returns).
    orm_user = await db.get(UserModel, user_id)
    # The read is done: nothing is held while the source answers (ADR-304).
    await db.commit()
    if orm_user is None:  # defensive — the guards above loaded a profile
        return None
    verdict = await evaluate_condition(
        orm_user,
        action.condition_config or {},
        run_id=f"routine_condition_{action.id.hex[:12]}_{uuid.uuid4().hex[:8]}",
        session_id=f"{SCHEDULED_ACTIONS_SESSION_PREFIX}{action.id}",
    )
    ledger = ConditionLedger.read(action.condition_state)
    fresh = [] if verdict.error else ledger.new_keys(verdict.keys)
    capped = bool(fresh) and await _daily_cap_reached(db, action, started_at)
    unserved = ledger.after_check(
        at=started_at, present=verdict.keys, fired=False, error=verdict.error
    )
    if fresh and not capped:
        # The cap's count was a read: nothing is held while a proposal's push
        # or the model answers (ADR-304).
        await db.commit()
        return _ConditionGate(
            note=verdict.note_for(fresh),
            served_state=ledger.after_check(at=started_at, present=verdict.keys, fired=True),
            unserved_state=unserved,
        )
    await repo.reschedule(action, _next_trigger(action, due_at), condition_state=unserved)
    await db.commit()
    reason = "capped" if capped else (verdict.error or "nothing_new")
    # Routine by design, at every check: only a cap is worth the INFO level.
    log = logger.info if capped else logger.debug
    log("scheduled_action_condition_skipped", action_id=str(action.id), reason=reason)
    return None


async def _send_approval_notification(
    db: Any,
    *,
    user: Any,
    action: ScheduledAction,
    user_language: str,
) -> None:
    """Propose-first notification (N-07): a markdown [Run it now](?intent=) link.

    The absolute URL omits the locale segment on purpose (the connectors
    router precedent): the frontend middleware resolves the user's locale.
    Best-effort — a dispatch failure must not break the tick, the routine
    simply proposes again at its next one.
    """
    from src.core.i18n_proactive import ProactiveMessages
    from src.infrastructure.proactive.notification import NotificationDispatcher

    intent_url = f"{settings.frontend_url}/dashboard/chat?intent={quote(action.action_prompt)}"
    body = ProactiveMessages.routine_approval_body(action.title, intent_url, user_language)
    try:
        await NotificationDispatcher().dispatch(
            user=user,
            content=body,
            task_type="scheduled_action",
            target_id=str(action.id),
            metadata={"approval_proposal": True},
            db=db,
            title=ProactiveMessages.notification_title("scheduled_action", user_language),
        )
    except Exception as exc:  # noqa: BLE001 — the next tick proposes again
        logger.warning(
            "scheduled_action_approval_dispatch_failed",
            action_id=str(action.id),
            error_type=type(exc).__name__,
        )


async def _notify_result(
    db: Any,
    *,
    user_id: uuid.UUID,
    action: ScheduledAction,
    content: str,
    user_language: str,
) -> None:
    """Push the result (FCM) and toast it (SSE); each best-effort.

    The archive is ``stream_chat_response``'s. The content is flattened ONCE
    for both surfaces, before any truncation: the agent response is rich
    content (HTML in ``html`` display mode, data cards in ``cards`` mode,
    Markdown otherwise) while a push body and a toast description both render
    their text verbatim.
    """
    from src.domains.notifications.service import FCMNotificationService
    from src.infrastructure.cache.redis import get_redis_cache

    notification_text = plain_text_for_notification(content)
    try:
        await FCMNotificationService(db).send_to_user(
            user_id=user_id,
            # The reader's punctuation joins the label to the routine's title (ADR-323).
            title=f"{_get_localized_title(user_language)}"
            f"{label_separator(user_language)}{action.title}",
            body=_truncate(notification_text),
            data={"type": "scheduled_action", "action_id": str(action.id)},
        )
    except Exception as fcm_err:
        logger.warning(
            "scheduled_action_fcm_failed",
            action_id=str(action.id),
            error_type=type(fcm_err).__name__,
        )

    try:
        redis = await get_redis_cache()
        if redis:
            await redis.publish(
                user_notifications_channel(user_id),
                json.dumps(
                    {
                        "type": "scheduled_action",
                        "content": _truncate(
                            notification_text, SCHEDULED_ACTIONS_SSE_PREVIEW_MAX_LENGTH
                        ),
                        "action_id": str(action.id),
                        "title": action.title,
                    },
                    ensure_ascii=False,
                ),
            )
    except Exception as sse_err:
        logger.warning(
            "scheduled_action_sse_failed",
            action_id=str(action.id),
            error_type=type(sse_err).__name__,
        )


async def _load_tick(
    db: Any, repo: Any, action_id: uuid.UUID, user_id: uuid.UUID
) -> tuple[ScheduledAction, Any] | None:
    """The routine and its owner, or ``None`` when the tick must not run.

    Returns:
        ``(action, user)`` for an existing routine of an active owner under
        their usage limits; ``None`` otherwise (logged).
    """
    from src.domains.usage_limits.service import UsageLimitService
    from src.domains.users.service import UserService

    action = await repo.get_by_id(action_id)
    if not action:
        logger.warning("scheduled_action_execute_not_found", action_id=str(action_id))
        return None

    user = await UserService(db).get_user_by_id(user_id)
    if not user:
        logger.warning(
            "scheduled_action_execute_user_not_found",
            action_id=str(action_id),
            user_id=str(user_id),
        )
        return None

    # Guard: skip inactive users (deleted users also have is_active=False)
    if not user.is_active:
        logger.info(
            "scheduled_action_skipped_user_inactive",
            action_id=str(action_id),
            user_id=str(user_id),
            is_active=user.is_active,
        )
        return None

    # Guard: usage limit pre-check (LLM-consuming task)
    if await UsageLimitService.is_user_blocked_for_llm(
        user_id,
        layer="scheduled_action_executor",
        extra_log_fields={"action_id": str(action_id)},
    ):
        return None
    return action, user


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
    from src.domains.scheduled_actions.repository import ScheduledActionRepository
    from src.infrastructure.database.session import get_db_context

    async with get_db_context() as db:
        repo = ScheduledActionRepository(db)
        loaded = await _load_tick(db, repo, action_id, user_id)
        if loaded is None:
            return ""
        action, user = loaded

        # ADR-265: the run history needs the instant the tick started and the
        # slot it was due for, both read BEFORE any branch re-arms the row.
        started_at = now_utc()
        due_at = action.next_trigger_at
        user_language = normalize_language(user.language)
        # The reads are done: nothing is held while a source, a model or a
        # push answers (ADR-304). The session is ``expire_on_commit=False``.
        await db.commit()

        # === Condition gate (N-07, ADR-322) ===
        gate = _NO_CONDITION
        if action.trigger_kind == TriggerKind.CONDITION.value:
            checked = await _condition_gate(
                db, repo, action, user_id, started_at=started_at, due_at=due_at
            )
            if checked is None:
                return ""
            gate = checked

        async def _settle(outcome: ScheduledRunOutcome, state: dict[str, Any] | None) -> None:
            """Re-arm without counting an execution, write the row, commit."""
            await repo.reschedule(action, _next_trigger(action, due_at), condition_state=state)
            await record_run(
                db, action, due_at=due_at, started_at=started_at, outcome=outcome, attempts=0
            )
            await db.commit()

        if action.requires_approval:
            # Propose-first: the run belongs to the CHAT (?intent= — ADR-173),
            # so it flows through the normal pipeline + HITL when the user
            # clicks. The tick only notifies and re-arms.
            await _send_approval_notification(
                db, user=user, action=action, user_language=user_language
            )
            await _settle(ScheduledRunOutcome.PROPOSED, gate.served_state)
            logger.info(
                "scheduled_action_approval_proposed",
                action_id=str(action_id),
                user_id=str(user_id),
            )
            return ""

        # === Guard: the thread must not already hold an unanswered question ===
        # The probe FAILS OPEN (it is the engine's contract): failing to ask
        # whether a question is pending must not become a reason to do nothing.
        has_pending_hitl, pending_conversation_id = await conversation_has_pending_hitl(
            db, user_id, user_language
        )
        if has_pending_hitl:
            logger.info(
                "scheduled_action_skipped_hitl_pending",
                action_id=str(action_id),
                user_id=str(user_id),
                conversation_id=str(pending_conversation_id),
            )
            if action.trigger_kind != TriggerKind.CONDITION.value:
                # A skipped slot counts no execution: nothing ran.
                await _settle(ScheduledRunOutcome.SKIPPED_HITL, None)
            else:
                # The facts stay new and the next check tries again — with no
                # row: a question can wait for days, a row at every check
                # would say nothing the chat does not already show.
                await repo.reschedule(
                    action, _next_trigger(action, due_at), condition_state=gate.unserved_state
                )
                await db.commit()
            return ""

        # The probe's reads are done: nothing is held while the model runs.
        await db.commit()
        response_content = await _run_pipeline(
            db,
            repo,
            action,
            user,
            gate=gate,
            started_at=started_at,
            due_at=due_at,
            user_language=user_language,
        )
        # The outcome is durable BEFORE any push: a crash during the
        # notification must not re-run a routine that already answered.
        await db.commit()

        if response_content:
            await _notify_result(
                db,
                user_id=user_id,
                action=action,
                content=response_content,
                user_language=user_language,
            )
        await db.commit()

    return response_content


async def _run_pipeline(
    db: Any,
    repo: Any,
    action: ScheduledAction,
    user: Any,
    *,
    gate: _ConditionGate,
    started_at: datetime,
    due_at: datetime | None,
    user_language: str,
) -> str:
    """Run the routine's instruction through the shared engine, and mark the outcome.

    The retry policy, the timeout, the fresh session per attempt and the
    ``content_replacement`` rule live in the engine (ADR-276); what a ROUTINE
    does with the outcome stays here.

    Returns:
        The answer, empty on a failure.
    """
    prompt = action.action_prompt
    if gate.note:
        # Factual context for the pipeline (raw item names — the agent
        # phrases them in the user's language).
        prompt = f"{action.action_prompt}\n\n[Trigger context] {gate.note}"
    result = await stream_instruction(
        StreamRequest(
            user_id=action.user_id,
            prompt=prompt,
            session_id=f"{SCHEDULED_ACTIONS_SESSION_PREFIX}{action.id}",
            language=user_language,
            timezone=user.timezone or DEFAULT_USER_DISPLAY_TIMEZONE,
            display_name=resolve_user_display_name(user.full_name, user.email),
            display_mode=getattr(user, "response_display_mode", None) or "cards",
            timeout_seconds=settings.scheduled_actions_execution_timeout_seconds,
            max_attempts=SCHEDULED_ACTIONS_MAX_RETRIES + 1,
            retry_delay_seconds=SCHEDULED_ACTIONS_RETRY_DELAY_SECONDS,
            # The ROUTINE's own choice (the loop by default): nobody is there
            # to steer a plan when it fires. Never the person's chat preference
            # — the header toggle speaks for the chat alone.
            execution_mode=action.execution_mode,
        )
    )
    # A routine has nobody to ask, so a question it cannot ask is a failure —
    # the behaviour this path has always had. The workboard reads the same
    # outcome differently, which is why the engine names it rather than
    # deciding for its callers.
    error_msg: str | None = result.error
    if result.outcome is RunOutcome.WAITING:
        error_msg = "RuntimeError: HITL interrupt during scheduled action execution"
    # A ceiling refusal (``QUOTA_BLOCKED``) carries its message, so it takes the
    # failure path below and the OCCURRENCE is abandoned — the series re-arms
    # on its own next slot. A routine has no « skipped » outcome to write:
    # ``ScheduledRunOutcome`` declares five, one per exit, and the weekly grid
    # colours a cell from them.
    next_trigger = _next_trigger(action, due_at)
    if error_msg is None:
        # The ledger's new facts are served only by a REAL run: a failed one
        # leaves them new, so the next check tries the fact again.
        await repo.mark_execution_success(action, next_trigger, condition_state=gate.served_state)
        outcome = ScheduledRunOutcome.SUCCESS
        logger.info(
            "scheduled_action_executed_success",
            action_id=str(action.id),
            user_id=str(action.user_id),
            response_length=len(result.text),
            next_trigger_at=next_trigger.isoformat() if next_trigger else None,
            attempt=result.attempts,
        )
    else:
        await repo.mark_execution_failure(
            action,
            error_msg,
            next_trigger,
            max_consecutive_failures=SCHEDULED_ACTIONS_MAX_CONSECUTIVE_FAILURES,
            condition_state=gate.unserved_state,
        )
        outcome = ScheduledRunOutcome.FAILURE
        # The message is kept on the routine for its owner; the log carries
        # the exception's TYPE, a fact, never the text it quotes (ADR-317).
        kind = error_msg.split(":", 1)[0]
        logger.warning(
            "scheduled_action_failed_after_retries",
            action_id=str(action.id),
            error_type=kind if kind.isidentifier() else "refused",
            total_attempts=result.attempts,
        )
    await record_run(
        db,
        action,
        due_at=due_at,
        started_at=started_at,
        outcome=outcome,
        attempts=result.attempts,
        error=error_msg,
    )
    return result.text


async def _purge_run_history() -> int:
    """Drop run rows older than the retention; best effort, never raises.

    Returns:
        How many rows went (0 when nothing was old enough or the purge failed).
    """
    from datetime import timedelta

    from src.domains.scheduled_actions.run_repository import ScheduledActionRunRepository
    from src.infrastructure.database.errors import database_error_fields
    from src.infrastructure.database.session import get_db_context

    cutoff = now_utc() - timedelta(days=settings.scheduled_actions_runs_retention_days)
    try:
        async with get_db_context() as db:
            purged = await ScheduledActionRunRepository(db).purge_older_than(cutoff)
            await db.commit()
            return purged
    except Exception as exc:
        # A database failure is logged by its facts, never by its text (ADR-317).
        logger.warning(
            "scheduled_action_runs_purge_failed",
            error_type=type(exc).__name__,
            **database_error_fields(exc),
        )
        return 0


async def _close_finished_routines() -> int:
    """Close the routines with no future left; best effort, never raises.

    A series ends three ways — its ``SeriesEnd`` date reached, its
    ``after_count`` exhausted, its single occurrence consumed — and all three
    leave the same state: a NULL trigger. Nothing closed those rows, so they
    stayed enabled and « active » for good, indistinguishable from a pause.

    Disabled, never deleted: the person must be able to see what they had
    posted. In its OWN session so a failure cannot poison the batch that
    follows.

    Returns:
        How many were closed (0 when none were due or the sweep failed).
    """
    from src.domains.scheduled_actions.repository import ScheduledActionRepository
    from src.infrastructure.database.session import get_db_context

    try:
        async with get_db_context() as db:
            closed = await ScheduledActionRepository(db).close_finished()
            await db.commit()
            return closed
    except Exception as exc:  # noqa: BLE001 — housekeeping never costs the tick
        logger.warning(
            "scheduled_action_close_finished_failed",
            error_type=type(exc).__name__,
        )
        return 0


async def process_scheduled_actions() -> dict[str, Any]:
    """
    Scheduler job: process all due scheduled actions.

    Runs every 60s via APScheduler. Pattern:
    1. Recover stale 'executing' actions (crash recovery)
    2. Get and lock due actions (FOR UPDATE SKIP LOCKED)
    3. Execute each action with bounded concurrency
    4. Track metrics

    Step 0, before all of these: purge run-history rows past their retention.

    Single execution is guaranteed WITHOUT a Redis SchedulerLock (F003): the
    scheduler runs on a single leader-elected worker (``SchedulerLeaderElector``),
    APScheduler caps this job at ``max_instances=1``, and step 2 uses FOR UPDATE
    SKIP LOCKED + an atomic transition to 'executing' — so even a transient
    two-scheduler failover window cannot double-process an action. A Redis lock
    here was worse than redundant: retained for its full TTL (300s), it throttled
    this 60s job to one run per five minutes.

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
        "runs_purged": 0,
        "finished_closed": 0,
    }

    try:
        from src.domains.scheduled_actions.repository import ScheduledActionRepository
        from src.infrastructure.database.session import get_db_context

        # 0. Retention of the run history (ADR-265): inside this tick rather
        # than a job of its own — no new interval to jitter, no new lock — in
        # its OWN session so a failed DELETE cannot poison the batch, and
        # BEFORE the empty-batch early return, which is the common tick.
        stats["runs_purged"] = await _purge_run_history()
        # 0b. Close the routines with no future left (ADR-281, lot 5). Beside
        # the retention for the same reasons — no new interval, no new lock —
        # and in the same place: a routine that will never fire again must stop
        # LOOKING active on the person's screen.
        stats["finished_closed"] = await _close_finished_routines()

        async with get_db_context() as db:
            repo = ScheduledActionRepository(db)

            # 1. Recovery: reset stale 'executing' actions
            recovered = await repo.recover_stale_executing(
                timeout_minutes=settings.scheduled_actions_stale_timeout_minutes
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

            # 3. Process the batch with BOUNDED concurrency.
            #
            # Each call opens its own DB session and handles its own
            # success/failure marking, so running several at once respects the
            # rule that an AsyncSession is never shared across tasks. Executing
            # them one at a time made the tick cost the SUM of the batch: 373
            # ticks measured in production with a 0.01s median but a tail at
            # 26s, 51s, 81s and 187s, and 34 ticks dropped by APScheduler
            # (max_instances=1) because the previous one was still running —
            # every action due inside that window fired late.
            #
            # The bound is a setting, not a constant: unbounded fan-out would
            # replace a scheduling delay with a burst against the LLM provider
            # and the connection pool. Setting it to 1 restores the old
            # behaviour exactly.
            semaphore = asyncio.Semaphore(settings.scheduled_actions_max_concurrency)

            async def _run_one(action_id: uuid.UUID, action_user_id: uuid.UUID) -> str:
                """Execute one action and return its outcome for the counters."""
                async with semaphore:
                    try:
                        response = await execute_single_action(
                            action_id=action_id,
                            user_id=action_user_id,
                        )
                        return "success" if response else "skipped"
                    except Exception as e:
                        logger.error(
                            "scheduled_action_process_error",
                            action_id=str(action_id),
                            error=str(e),
                        )
                        # execute_single_action handles its own failure marking.
                        # If it raises unexpectedly, the action stays in
                        # 'executing' and recover_stale_executing resets it.
                        return "failed"

            # return_exceptions=True so one sibling can never cancel the batch;
            # _run_one already converts every failure into an outcome, this is
            # the belt to that pair of braces.
            outcomes = await asyncio.gather(
                *(_run_one(action_id, user_id) for action_id, user_id in action_refs),
                return_exceptions=True,
            )

            for outcome in outcomes:
                stats["processed"] += 1
                if isinstance(outcome, BaseException):
                    stats["failed"] += 1
                    logger.error(
                        "scheduled_action_batch_task_error",
                        error=str(outcome),
                        error_type=type(outcome).__name__,
                    )
                else:
                    stats[outcome] += 1

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
