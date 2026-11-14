"""
Scheduled task for executing scheduled actions.

Runs every 60s to check for due actions and execute them through the agent pipeline.
Uses FOR UPDATE SKIP LOCKED to prevent concurrent processing.

Flow (for each due action):
0. Catch-up window (time routines): an occurrence reached past its window is
   not run late — its slot says « missed », and the routine re-arms on the most
   recent occurrence that may still start, else on the next one (ADR-265
   amendment 2026-11-12 b)
1. Usage ceiling: an account past it stands aside BEFORE any source is asked —
   re-armed, never counted as a failure (ADR-272), its reason left on the week
   (a time routine's row) or on the ledger (a condition routine)
2. Condition routines only: check the condition, and go on only for a NEW fact
   under the daily cap (ADR-322) — a check that finds nothing new re-arms and
   ends there, with no run row. Webhook routines only: take the calls that wait
   (ADR-386) — with none, the routine rests until a call wakes it, no run row
3. Propose-first routines: notify with a link and stop
4. Guard: check no HITL interrupt pending on user's conversation
5. Execute via stream_chat_response(auto_approve_plan=True) with timeout — an
   account found busy keeps a time routine's occurrence armed for the next
   pass, inside the same window, instead of losing it to the next occurrence
6. Mark success or failure (auto-disable after N consecutive failures) and
   re-arm from the routine's clock (``trigger.TriggerPlan``)
7. Tell the owner (``scheduled_action_notices``): the result (FCM + SSE, archive
   handled by stream_chat_response), or why there is none — a failure at the
   first of its series and when it pauses the routine, the ceiling once per
   account per window

No transaction is held across a wait (ADR-304): the reads are committed before
the condition's source answers, before the model runs and before any push.

Metrics:
- background_job_duration_seconds{job_name="scheduled_action_executor"}
- background_job_errors_total{job_name="scheduled_action_executor"}
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import (
    DEFAULT_USER_DISPLAY_TIMEZONE,
    SCHEDULED_ACTIONS_BATCH_SIZE,
    SCHEDULED_ACTIONS_EXECUTOR_INTERVAL_SECONDS,
    SCHEDULED_ACTIONS_MAX_CONSECUTIVE_FAILURES,
    SCHEDULED_ACTIONS_MAX_RETRIES,
    SCHEDULED_ACTIONS_RETRY_DELAY_SECONDS,
    SCHEDULED_ACTIONS_SESSION_PREFIX,
)
from src.core.exceptions import ResourceNotFoundError
from src.core.i18n import normalize_language
from src.core.time_utils import now_utc
from src.core.user_display import resolve_user_display_name
from src.domains.agents.utils.helpers import generate_run_id
from src.domains.scheduled_actions.condition_ledger import ConditionLedger, with_check_error

# CRITICAL: Import model at module level to register with SQLAlchemy metadata
from src.domains.scheduled_actions.models import (  # noqa: F401
    ScheduledAction,
    ScheduledActionStatus,
    ScheduledRunOutcome,
    TriggerKind,
)
from src.domains.scheduled_actions.runs import is_manual_run, record_run
from src.domains.scheduled_actions.trigger import DueOccurrence, TriggerPlan
from src.infrastructure.observability.metrics import (
    background_job_duration_seconds,
    background_job_errors_total,
)
from src.infrastructure.scheduler.out_of_turn_run import (
    RunOutcome,
    RunResult,
    StreamRequest,
    clear_question_of_run,
    interrupt_log_facts,
    stream_instruction,
    unattended_turn_seconds,
    worst_case_run_seconds,
)
from src.infrastructure.scheduler.routine_webhook_gate import (
    rest_until,
    serve_calls,
    waiting_calls,
)
from src.infrastructure.scheduler.scheduled_action_housekeeping import (
    close_finished_routines,
    purge_run_history,
    purge_served_calls,
)
from src.infrastructure.scheduler.scheduled_action_notices import (
    RoutineNotice,
    claim_quota_notice,
    failure_notice,
    notify_result,
    send_approval_notification,
    send_routine_notice,
)

if TYPE_CHECKING:
    from src.domains.scheduled_actions.repository import ScheduledActionRepository
    from src.domains.users.schemas import UserProfile

logger = structlog.get_logger(__name__)
ExecutionGuard = Callable[[AsyncSession, ScheduledAction], Awaitable[bool]]


def _next_trigger(
    action: ScheduledAction, due_at: datetime | None, *, failed: bool = False
) -> datetime | None:
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
        failed: Whether the run failed: a webhook routine backs off (ADR-386).

    Returns:
        The next instant, or ``None`` when nothing follows — which the
        repository stores as a null trigger.
    """
    return TriggerPlan.of(action).after_tick(due_at=due_at, now=now_utc(), failed=failed)


@dataclass(frozen=True, slots=True)
class _ConditionGate:
    """What a condition check — or a webhook routine's calls — decided for the tick."""

    note: str | None
    """The context naming the NEW facts, or the calls, for the routine's prompt."""
    served_state: dict[str, Any] | None
    """The ledger once the new facts are served (a run answered, a proposal sent)."""
    unserved_state: dict[str, Any] | None
    """The ledger if they are not (a pending question, a failed run): still new."""
    deliveries: tuple[uuid.UUID, ...] = ()
    """The calls the run is shown, served if it answers (ADR-386)."""


#: A time routine's gate: no fact, and no ledger to write.
_NO_CONDITION = _ConditionGate(note=None, served_state=None, unserved_state=None)


@dataclass(frozen=True, slots=True)
class _Tick:
    """One tick of one routine: what each of its settles needs."""

    db: AsyncSession
    repo: ScheduledActionRepository
    action: ScheduledAction
    token: uuid.UUID | None
    """The reservation the tick was handed; a tick that lost it writes nothing."""
    due_at: datetime | None
    """The pending due instant when the tick started, read BEFORE any re-arm."""
    started_at: datetime
    occurrence: DueOccurrence | None = None
    """What was due, for a time routine; None for a run the person started and a watch."""


@dataclass(frozen=True, slots=True)
class _TickEnd:
    """What a tick leaves for the routine's owner once its outcome is durable."""

    text: str = ""
    """The answer to push; empty when the routine did not answer."""
    notice: RoutineNotice | None = None
    """Why it did not run as planned, when the owner is owed a word about it."""
    manual: bool = False
    """Whether the person started the run: such a run is always told its end."""
    silent: bool = False
    """The answer stays in the chat and is not pushed: its owner asked to be
    told only of something new, and the run declared it had nothing new."""


#: A tick with nothing to tell: a check that found nothing new, a proposal
#: (it notified already), a tick that lost the routine.
_NOTHING = _TickEnd()

#: The engine outcomes that ran nothing for a reason other than a ceiling, and
#: the reason each leaves on the week.
_STOOD_ASIDE: dict[RunOutcome, ScheduledRunOutcome] = {
    RunOutcome.BUSY: ScheduledRunOutcome.SKIPPED_BUSY,
    RunOutcome.PENDING_QUESTION: ScheduledRunOutcome.SKIPPED_HITL,
}

#: How long until the scheduler looks at a routine again: an occurrence whose
#: wait would end before that has had its last attempt.
_NEXT_PASS = timedelta(seconds=SCHEDULED_ACTIONS_EXECUTOR_INTERVAL_SECONDS)


def _ledger_of(action: ScheduledAction) -> ConditionLedger:
    """The routine's ledger, read as its condition type forgets (ADR-387)."""
    condition_type = (action.condition_config or {}).get("type")
    return ConditionLedger.read(action.condition_state, condition_type=condition_type)


async def _daily_cap_reached(db: AsyncSession, action: ScheduledAction, now: datetime) -> bool:
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
    db: AsyncSession,
    repo: ScheduledActionRepository,
    action: ScheduledAction,
    user_id: uuid.UUID,
    *,
    started_at: datetime,
    due_at: datetime | None,
    execution_token: uuid.UUID | None = None,
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
        execution_token: The reservation to revalidate before re-arming.

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
    ledger = _ledger_of(action)
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
            # Nothing served yet: the run is told nothing was reported (ADR-387).
            note=verdict.note_for(fresh, first=ledger.last_fired_at is None),
            served_state=ledger.after_check(at=started_at, present=verdict.keys, fired=True),
            unserved_state=unserved,
        )
    if not await _rearm_reserved(repo, action, execution_token, due_at, unserved):
        return None
    await db.commit()
    reason = "capped" if capped else (verdict.error or "nothing_new")
    # Routine by design, at every check: only a cap is worth the INFO level.
    log = logger.info if capped else logger.debug
    log("scheduled_action_condition_skipped", action_id=str(action.id), reason=reason)
    return None


async def _load_tick(
    db: AsyncSession,
    repo: ScheduledActionRepository,
    action_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    execution_token: uuid.UUID | None = None,
) -> tuple[ScheduledAction, UserProfile] | None:
    """The routine and its owner, or ``None`` when the tick must not run.

    Returns:
        ``(action, user)`` for an existing routine of an active owner;
        ``None`` otherwise (logged).
    """
    from src.domains.users.service import UserService

    action = await repo.get_by_id(action_id)
    if not action or action.user_id != user_id:
        logger.warning("scheduled_action_execute_not_found", action_id=str(action_id))
        return None

    try:
        user = await UserService(db).get_user_by_id(user_id)
    except ResourceNotFoundError:
        # The public lookup returns active accounts only; an unavailable owner
        # settles without a run. The enclosing DB context commits on return.
        released = await repo.disable_for_unavailable_owner(action_id, user_id, execution_token)
        logger.info(
            "scheduled_action_skipped_owner_unavailable",
            action_id=str(action_id),
            user_id=str(user_id),
            reservation_released=released,
        )
        return None
    return action, user


async def _usage_ceiling_reached(action: ScheduledAction) -> bool:
    """Whether the owner's usage ceiling refuses this tick (logged and counted)."""
    from src.domains.usage_limits.service import UsageLimitService

    return await UsageLimitService.is_user_blocked_for_llm(
        action.user_id,
        layer="scheduled_action_executor",
        extra_log_fields={"action_id": str(action.id)},
    )


async def _execution_is_authorized(
    db: AsyncSession,
    action: ScheduledAction,
    guard: ExecutionGuard | None,
    *,
    token: uuid.UUID | None = None,
) -> bool:
    """Whether the tick may go on — and, holding a reservation, renew it.

    A tick that no longer holds its reservation must neither run nor settle:
    the recovery freed it and another tick may hold the routine now (point 19).
    Each check renews it, the last one right before the model runs, so the
    recovery counts from the run's real start. What the check read or renewed
    is committed at once: what follows waits on a source, a push or a model,
    and a renewal's row lock held across it would stall anyone editing the
    routine meanwhile (ADR-304).

    Args:
        db: The tick's session.
        action: The routine.
        guard: The caller's own authorization check, if any (ADR-335).
        token: The reservation the tick was handed, if any.

    Returns:
        True when the tick may go on.
    """
    if guard is not None and not await guard(db, action):
        return False
    if token is not None and not await _renewed(db, action.id, token):
        return False
    if guard is not None or token is not None:
        await db.commit()
    return True


async def _renewed(db: AsyncSession, action_id: uuid.UUID, token: uuid.UUID) -> bool:
    """Renew the tick's reservation; False (logged) when another tick holds it."""
    from src.domains.scheduled_actions.repository import ScheduledActionRepository

    if await ScheduledActionRepository(db).renew_reservation(action_id, token):
        return True
    logger.warning("scheduled_action_reservation_lost", action_id=str(action_id))
    return False


async def execute_single_action(
    action_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    execution_guard: ExecutionGuard | None = None,
    execution_token: uuid.UUID | None = None,
    started_by_person: bool = False,
) -> str:
    """
    Execute a single scheduled action through the agent pipeline.

    Shared by the scheduler job and the POST /execute endpoint.
    Opens its own DB session (background task context).

    Args:
        action_id: Scheduled action UUID.
        user_id: User UUID.
        execution_guard: The caller's own authorization check (ADR-335).
        execution_token: The reservation the tick was handed; the run then
            renews it before the model and settles only while it holds it.
        started_by_person: Declared by the call site (« run now », a run asked
            in the chat): such a run is the person's act, so the age of the
            pending slot is never a reason to give it up as missed.

    Returns:
        Response content from the agent.
    """
    from src.domains.scheduled_actions.repository import ScheduledActionRepository
    from src.infrastructure.database.session import get_db_context

    async with get_db_context() as db:
        repo = ScheduledActionRepository(db)
        loaded = await _load_tick(db, repo, action_id, user_id, execution_token=execution_token)
        if loaded is None:
            return ""
        action, user = loaded
        if not await _execution_is_authorized(db, action, execution_guard, token=execution_token):
            return ""

        # ADR-265: the run history needs the instant the tick started and the
        # slot it was due for, both read BEFORE any branch re-arms the row.
        started_at = now_utc()
        due_at = action.next_trigger_at
        user_language = normalize_language(user.language)
        # The reads are done: nothing is held while a source, a model or a
        # push answers (ADR-304). The session is ``expire_on_commit=False``.
        await db.commit()

        occurrence = TriggerPlan.of(action).due_occurrence(due_at=due_at, started_at=started_at)
        tick = _Tick(
            db=db,
            repo=repo,
            action=action,
            token=execution_token,
            due_at=due_at,
            started_at=started_at,
            occurrence=occurrence,
        )
        if occurrence is not None and not started_by_person and occurrence.is_late(started_at):
            ended = await _give_up_late(tick, occurrence)
        elif await _usage_ceiling_reached(action):
            ended = await _stand_aside_for_quota(tick, unserved_state=None)
        else:
            ended = await _serve_tick(
                tick, user, guard=execution_guard, user_language=user_language
            )
        # The outcome is durable BEFORE anything leaves the process: a crash
        # during a push must not re-run a routine that already answered.
        await db.commit()

        if ended.text and not ended.silent:
            await notify_result(
                db,
                user_id=user_id,
                action=action,
                content=ended.text,
                user_language=user_language,
            )
        notice = await _owed_notice(ended, user_id)
        if notice is not None:
            await send_routine_notice(
                db, user=user, action=action, kind=notice, user_language=user_language
            )
        await db.commit()

    return ended.text


async def _owed_notice(ended: _TickEnd, user_id: uuid.UUID) -> RoutineNotice | None:
    """The notice to send once the tick is durable, if its owner is owed one.

    The ceiling's notice is the ACCOUNT's, claimed once per window whichever
    routine met the ceiling first; a run the person started is waited for, and
    is told whatever the claim says. Claimed after the commit: nothing is held
    while the cache answers (ADR-304).

    Args:
        ended: How the tick ended.
        user_id: The routine's owner.

    Returns:
        The notice, or None when there is nothing to say or it was said already.
    """
    if ended.notice is not RoutineNotice.QUOTA:
        return ended.notice
    claimed = await claim_quota_notice(user_id)
    return ended.notice if claimed or ended.manual else None


async def _serve_tick(
    tick: _Tick, user: UserProfile, *, guard: ExecutionGuard | None, user_language: str
) -> _TickEnd:
    """Serve a tick its owner's ceiling admitted: check, propose or run.

    Nothing is held open across a wait (ADR-304), and the reservation is
    revalidated before each one.

    Args:
        tick: The tick.
        user: The routine's owner.
        guard: The caller's own authorization check (ADR-335).
        user_language: The owner's backend-canonical language.

    Returns:
        What the tick leaves for its owner.
    """
    db, repo, action = tick.db, tick.repo, tick.action
    # === Condition gate (N-07, ADR-322) ===
    gate = _NO_CONDITION
    if action.trigger_kind == TriggerKind.CONDITION.value:
        checked = await _condition_gate(
            db,
            repo,
            action,
            action.user_id,
            started_at=tick.started_at,
            due_at=tick.due_at,
            execution_token=tick.token,
        )
        if checked is None:
            return _NOTHING
        gate = checked
    elif action.trigger_kind == TriggerKind.WEBHOOK.value:
        calls = await waiting_calls(db, action)
        if not calls.delivery_ids:
            if not await _settle_superseded(repo, action, tick.token, attempts=0):
                rest = await rest_until(db, action.id, switch_open=calls.switch_open)
                await repo.reschedule(action, rest)
            return _NOTHING
        gate = _ConditionGate(calls.note, None, None, calls.delivery_ids)

    if not await _execution_is_authorized(db, action, guard, token=tick.token):
        return _NOTHING
    if action.requires_approval:
        # Propose-first: the run belongs to the CHAT (?intent= — ADR-173),
        # so it flows through the normal pipeline + HITL when the user
        # clicks. The tick only notifies, re-arms without counting an
        # execution, and writes its row.
        await send_approval_notification(db, user=user, action=action, user_language=user_language)
        await _rearm_reserved(repo, action, tick.token, tick.due_at, gate.served_state)
        await _record_unserved(tick, ScheduledRunOutcome.PROPOSED)
        await db.commit()
        logger.info(
            "scheduled_action_approval_proposed",
            action_id=str(action.id),
            user_id=str(action.user_id),
        )
        return _NOTHING

    # The shared engine checks the question only AFTER account admission.
    await db.commit()
    if not await _execution_is_authorized(db, action, guard, token=tick.token):
        return _NOTHING
    return await _run_pipeline(tick, user, gate=gate, user_language=user_language)


async def _run_pipeline(
    tick: _Tick, user: UserProfile, *, gate: _ConditionGate, user_language: str
) -> _TickEnd:
    """Run the routine's instruction through the shared engine, and mark the outcome.

    The retry policy, the timeout, the fresh session per attempt and the
    ``content_replacement`` rule live in the engine (ADR-276); what a ROUTINE
    does with the outcome stays here.

    Args:
        tick: The tick; nothing is held open on its session while the model
            runs, and its settle writes only while its reservation still holds
            the routine.
        user: The routine's owner, for the language, zone and display preferences.
        gate: The condition gate's verdict (the fact to serve, if any).
        user_language: The owner's backend-canonical language.

    Returns:
        The answer, or the notice of why there is none.
    """
    action = tick.action
    # ONE id for the run, across its attempts: the registers, the token logs
    # and a question the turn may leave on the thread all name it.
    run_id = generate_run_id()
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
            timeout_seconds=_attempt_bound_seconds(),
            max_attempts=SCHEDULED_ACTIONS_MAX_RETRIES + 1,
            retry_delay_seconds=SCHEDULED_ACTIONS_RETRY_DELAY_SECONDS,
            # The ROUTINE's own choice (the loop by default): nobody is there
            # to steer a plan when it fires. Never the person's chat preference
            # — the header toggle speaks for the chat alone.
            execution_mode=action.execution_mode,
            run_id=run_id,
            # Spec D9: the servers its form ticked — the only pre-approval there is.
            mcp_preapproval=action.mcp_preapproval,
            quiet_when_nothing_new=action.notify_only_when_new,
        )
    )
    if result.outcome is RunOutcome.BUSY and await _wait_for_account(tick):
        return _NOTHING
    if result.outcome in _STOOD_ASIDE:
        await _stand_aside(tick, _STOOD_ASIDE[result.outcome], gate.unserved_state)
        return _NOTHING
    if result.outcome is RunOutcome.QUOTA_BLOCKED:
        # A ceiling refused the call before anything was generated: the same
        # exit as the pre-check's own refusal, never a failure (ADR-272) —
        # until 2026-11-12 five of them paused the routine.
        return await _stand_aside_for_quota(tick, unserved_state=gate.unserved_state)
    # A routine has nobody to ask, so a question it cannot ask is a failure —
    # the behaviour this path has always had. The workboard reads the same
    # outcome differently, which is why the engine names it rather than
    # deciding for its callers. The ReAct loop no longer asks here (N10), but a
    # path that does not know — a pipeline clarification — still stops on a
    # question: it is taken back, or it would read the person's next message
    # as its answer and make every later routine stand aside.
    error_msg: str | None = result.error
    if result.outcome is RunOutcome.WAITING:
        error_msg = "RuntimeError: HITL interrupt during scheduled action execution"
        await clear_question_of_run(result.admission)
    outcome = ScheduledRunOutcome.SUCCESS if error_msg is None else ScheduledRunOutcome.FAILURE
    notice: RoutineNotice | None = None
    if not await _settle_superseded(tick.repo, action, tick.token, attempts=result.attempts):
        notice = await _mark_routine(tick, gate, result, error_msg=error_msg)
    # Written even when the routine is another tick's: the run happened, and a
    # condition routine's daily cap counts its runs from these rows (ADR-322).
    await record_run(
        tick.db,
        action,
        due_at=tick.due_at,
        started_at=tick.started_at,
        outcome=outcome,
        attempts=result.attempts,
        error=error_msg,
        run_id=run_id,
    )
    # The answer is archived either way; a run that declared it had nothing
    # new is simply not pushed to an owner who asked for that. A failure is
    # always told: its notice does not read this.
    silent = action.notify_only_when_new and result.nothing_new
    return _TickEnd(text=result.text, notice=notice, silent=silent)


async def _record_unserved(tick: _Tick, outcome: ScheduledRunOutcome) -> None:
    """Write the row of a tick that ran nothing: no attempt, no error."""
    await record_run(
        tick.db,
        tick.action,
        due_at=tick.due_at,
        started_at=tick.started_at,
        outcome=outcome,
        attempts=0,
    )


async def _stand_aside(
    tick: _Tick, outcome: ScheduledRunOutcome, condition_state: dict[str, Any] | None
) -> bool:
    """Re-arm a routine whose tick ran nothing, and leave the reason on its week.

    Never counted as an execution or a failure. A time routine's unserved slot
    gets its row; a condition routine's does not — its checks are recorded on
    its ledger, and a row per check stood aside would write one every ten
    minutes (ADR-322) — nor does a webhook routine's, whose calls wait (ADR-386).

    Args:
        tick: The tick.
        outcome: Why nothing ran.
        condition_state: The ledger to write, for a condition routine.

    Returns:
        True when this tick still held the routine, and so settled it.
    """
    action = tick.action
    if not await _rearm_reserved(tick.repo, action, tick.token, tick.due_at, condition_state):
        return False
    # A webhook routine looks again at the next pass: a row per pass would be one a minute.
    if action.trigger_kind == TriggerKind.TIME.value:
        await _record_unserved(tick, outcome)
    return True


async def _give_up_late(tick: _Tick, occurrence: DueOccurrence) -> _TickEnd:
    """Record an occurrence reached past its window, and arm what may still start.

    A morning routine answered in the afternoon is not the morning's (ADR-265
    amendment 2026-11-12 b). Not a failure, and nobody is told: the week says
    « missed », where an outage that skipped five routines would otherwise
    answer with five notices.

    Args:
        tick: The tick.
        occurrence: The occurrence it was due for, now too old.

    Returns:
        Nothing to tell the owner.
    """
    armed = TriggerPlan.of(tick.action).after_missed(due_at=occurrence.at, now=tick.started_at)
    if await _rearm_at(tick, armed):
        await _record_unserved(tick, ScheduledRunOutcome.SKIPPED_LATE)
        logger.info(
            "scheduled_action_occurrence_missed",
            action_id=str(tick.action.id),
            late_seconds=int((tick.started_at - occurrence.at).total_seconds()),
            next_trigger_at=armed.isoformat() if armed else None,
        )
    return _NOTHING


async def _wait_for_account(tick: _Tick) -> bool:
    """Leave a due occurrence armed for the scheduler's next pass.

    A busy account is a turn under way — a matter of minutes. Re-armed on the
    NEXT occurrence, as every other exit is, a daily routine was lost for a day
    because its owner was typing at 08:00, or because two routines of one
    account were due the same minute. Nothing is written while it waits: the
    occurrence is still pending, and its row will be the run's, or the reason
    it was given up. A question waiting for the person is not waited for: it
    lasts as long as the person takes.

    Args:
        tick: The tick the engine found no room for.

    Returns:
        True when the occurrence stays armed (or the tick lost the routine);
        False when its wait is over and the tick stands aside for good.
    """
    occurrence = tick.occurrence
    if occurrence is None or now_utc() + _NEXT_PASS > occurrence.retry_until:
        return False
    await _rearm_at(tick, occurrence.at)
    return True


async def _rearm_at(tick: _Tick, next_trigger: datetime | None) -> bool:
    """Arm the instant this tick chose, while it still holds the routine."""
    if await _settle_superseded(tick.repo, tick.action, tick.token, attempts=0):
        return False
    await tick.repo.reschedule(tick.action, next_trigger)
    return True


async def _stand_aside_for_quota(tick: _Tick, *, unserved_state: dict[str, Any] | None) -> _TickEnd:
    """Stand a routine aside for its account's usage ceiling, and say why.

    A condition routine's reason goes on its ledger, in place of the row a
    check never writes: refused before its check, nothing was read and nothing
    it had seen is forgotten; refused inside its turn, the facts the check
    found stay new.

    Args:
        tick: The tick.
        unserved_state: The ledger of a check that already ran, or None when
            the ceiling refused the tick before it.

    Returns:
        The ceiling's notice for the owner, or nothing for a tick that lost
        the routine.
    """
    ledger: dict[str, Any] | None = None
    if tick.action.trigger_kind == TriggerKind.CONDITION.value:
        ledger = (
            with_check_error(unserved_state, "quota_blocked")
            if unserved_state is not None
            # Refused before its check: nothing was read, so nothing moves but the reason.
            else _ledger_of(tick.action).after_check(
                at=tick.started_at, present=(), fired=False, error="quota_blocked"
            )
        )
    if not await _stand_aside(tick, ScheduledRunOutcome.SKIPPED_QUOTA, ledger):
        return _NOTHING
    return _TickEnd(notice=RoutineNotice.QUOTA, manual=is_manual_run(tick.due_at, tick.started_at))


async def _mark_routine(
    tick: _Tick, gate: _ConditionGate, result: RunResult, *, error_msg: str | None
) -> RoutineNotice | None:
    """Mark the routine with its run's outcome and re-arm it.

    Args:
        tick: The tick, which still holds the routine.
        gate: The condition gate's verdict (the ledger state to write).
        result: The engine's outcome of the run.
        error_msg: The failure message; None on a success.

    Returns:
        The notice a failure owes the owner (the first of a series, the one
        that pauses the routine, a run the person started); None otherwise.
    """
    repo, action = tick.repo, tick.action
    next_trigger = _next_trigger(action, tick.due_at, failed=error_msg is not None)
    if error_msg is None:
        # The ledger's new facts — and the calls — are served only by a REAL
        # run: a failed one leaves them waiting for the next.
        await repo.mark_execution_success(action, next_trigger, condition_state=gate.served_state)
        await serve_calls(tick.db, action.id, gate.deliveries)
        logger.info(
            "scheduled_action_executed_success",
            action_id=str(action.id),
            user_id=str(action.user_id),
            response_length=len(result.text),
            nothing_new=result.nothing_new,
            next_trigger_at=next_trigger.isoformat() if next_trigger else None,
            attempt=result.attempts,
        )
        return None
    marked = await repo.mark_execution_failure(
        action,
        error_msg,
        next_trigger,
        max_consecutive_failures=SCHEDULED_ACTIONS_MAX_CONSECUTIVE_FAILURES,
        condition_state=gate.unserved_state,
    )
    # The message is kept on the routine for its owner; the log carries the
    # exception's TYPE, a fact, never the text it quotes (ADR-317).
    logger.warning(
        "scheduled_action_failed_after_retries",
        action_id=str(action.id),
        error_type=result.error_code or result.outcome.value,
        total_attempts=result.attempts,
        **interrupt_log_facts(result.interrupt),
    )
    # Read from the row the repository returns: the threshold has ONE owner.
    return failure_notice(
        consecutive_failures=marked.consecutive_failures,
        disabled=marked.status == ScheduledActionStatus.ERROR.value,
        manual=is_manual_run(tick.due_at, tick.started_at),
    )


async def _rearm_reserved(
    repo: ScheduledActionRepository,
    action: ScheduledAction,
    token: uuid.UUID | None,
    due_at: datetime | None,
    condition_state: dict[str, Any] | None,
) -> bool:
    """Re-arm only the reservation this tick owns, without committing its caller's work."""
    if await _settle_superseded(repo, action, token, attempts=0):
        return False
    await repo.reschedule(action, _next_trigger(action, due_at), condition_state=condition_state)
    return True


async def _settle_superseded(
    repo: ScheduledActionRepository,
    action: ScheduledAction,
    token: uuid.UUID | None,
    *,
    attempts: int,
) -> bool:
    """Whether another tick took the routine while the model ran (point 19).

    Every settle uses this fence, including a condition check, a proposal and
    a pending question. A source or push may take longer than expected; an
    explicit reservation cancellation can occur at any time. The current
    holder's state is never this tick's to overwrite.

    Args:
        repo: The routines' repository on the tick's session.
        action: The routine.
        token: The tick's reservation; None when the caller holds none.
        attempts: How many attempts the run made, for the log line.

    Returns:
        True when the settle must write nothing.
    """
    if token is None or await repo.lock_reserved(action.id, token) is not None:
        return False
    logger.warning(
        "scheduled_action_settle_superseded", action_id=str(action.id), attempts=attempts
    )
    return True


def _attempt_bound_seconds() -> int:
    """How long one attempt of a routine may last, read by its run and its recovery.

    Returns:
        The bound, in seconds.
    """
    return unattended_turn_seconds(settings.scheduled_actions_execution_timeout_seconds)


def _reservation_lifetime_seconds() -> int:
    """How long a live tick may hold its reservation: the recovery's threshold.

    The worst case of a run — every attempt at its bound, plus the pauses
    between them — or the configured threshold when an operator set a longer
    one. With the defaults, the setting alone fell under that worst case, and
    the recovery could hand a live run's routine to the next tick: two runs
    (point 19).

    Returns:
        The threshold, in seconds.
    """
    return max(
        settings.scheduled_actions_stale_timeout_minutes * 60,
        worst_case_run_seconds(
            _attempt_bound_seconds(),
            SCHEDULED_ACTIONS_MAX_RETRIES + 1,
            SCHEDULED_ACTIONS_RETRY_DELAY_SECONDS,
        ),
    )


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
    APScheduler caps this job at ``max_instances=1``, step 2 uses FOR UPDATE
    SKIP LOCKED + an atomic transition to 'executing' under a fresh token, and
    the recovery of step 1 never frees a reservation younger than the worst
    case of a run. A tick that lost its reservation anyway — a manual run, or a
    second scheduler during a failover — neither runs nor settles: the token is
    renewed before the model and checked again at the settle. A Redis lock here
    was worse than redundant: retained for its full TTL (300s), it throttled
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
        "calls_purged": 0,
        "finished_closed": 0,
    }

    try:
        from src.domains.scheduled_actions.repository import ScheduledActionRepository
        from src.infrastructure.database.session import get_db_context

        # 0. Retention of the run history (ADR-265): inside this tick rather
        # than a job of its own — no new interval to jitter, no new lock — in
        # its OWN session so a failed DELETE cannot poison the batch, and
        # BEFORE the empty-batch early return, which is the common tick.
        stats["runs_purged"] = await purge_run_history(now_utc())
        stats["calls_purged"] = await purge_served_calls(now_utc())
        # 0b. Close the routines with no future left (ADR-281, lot 5). Beside
        # the retention for the same reasons — no new interval, no new lock —
        # and in the same place: a routine that will never fire again must stop
        # LOOKING active on the person's screen.
        stats["finished_closed"] = await close_finished_routines()

        async with get_db_context() as db:
            repo = ScheduledActionRepository(db)

            # 1. Recovery: reset stale 'executing' actions — never younger than a
            # live run can be, or the next tick would run it a second time.
            recovered = await repo.recover_stale_executing(
                older_than=now_utc() - timedelta(seconds=_reservation_lifetime_seconds())
            )
            stats["recovered"] = recovered

            # 2. Get and lock due actions (FOR UPDATE SKIP LOCKED)
            actions = await repo.get_and_lock_due_actions(limit=SCHEDULED_ACTIONS_BATCH_SIZE)

            if not actions:
                await db.commit()
                duration = time.perf_counter() - start_time
                background_job_duration_seconds.labels(job_name=job_name).observe(duration)
                return stats

            # Extract identifiers before commit (ORM objects expire after commit),
            # the reservation token included: each run holds the routine by it.
            action_refs = [
                (action.id, action.user_id, action.execution_token) for action in actions
            ]

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

            async def _run_one(
                action_id: uuid.UUID, action_user_id: uuid.UUID, token: uuid.UUID | None
            ) -> str:
                """Execute one action and return its outcome for the counters."""
                async with semaphore:
                    try:
                        response = await execute_single_action(
                            action_id=action_id,
                            user_id=action_user_id,
                            execution_token=token,
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
                *(_run_one(action_id, user_id, token) for action_id, user_id, token in action_refs),
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
