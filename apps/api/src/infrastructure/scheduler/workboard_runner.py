"""The sweep that lets LIA run a ticket alone (ADR-276, lot 2).

One tick does three things, in this order and for a reason:

1. **housekeeping** — release the claims a dead worker still holds, and delete
   the hidden transcripts of tickets closed past the retention window. Both are
   bounded statements, and they run FIRST so a stranded ticket is offered again
   in the very same tick.
2. **claim ONE ticket** — ``FOR UPDATE SKIP LOCKED`` plus a conditional
   ``UPDATE`` in the same transaction, committed before any work starts. One at
   a time on purpose: a worker that claimed five and was killed would strand
   five.
3. **run it, then settle from an EXPLICIT result** — never from the absence of
   an exception.

The three refusals a claimed ticket can meet are NOT failures and never settle
as one (ADR-272's logging rule): an inactive account, a quota ceiling, and a
conversation that is busy. The first is permanent, so the run settles ``failed``
with a typed code and the ticket waits for the person; the other two RELEASE the
claim, give the run back to the ticket's lifetime budget, and log « skipped ».

Two properties are load-bearing:

- **the settle quotes its run.** ``last_run_id`` is the claim's owner token, so
  a person who moved the ticket while the run was in flight WINS and the late
  settle writes nothing (the fencing rule every durable claim owes).
- **the session is not held across the run.** The claim is committed and the
  session closed before the pipeline starts; a run lasts minutes and a database
  connection held that long is a connection nobody else can have.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import structlog

from src.core.config import settings
from src.core.constants import (
    WORKBOARD_RUN_ERROR_MAX_CHARS,
    WORKBOARD_RUN_RETRY_DELAY_SECONDS,
    WORKBOARD_RUN_SESSION_PREFIX,
)
from src.core.i18n_workboard import WorkboardMessages
from src.core.time_utils import now_utc
from src.domains.agents.api.run_origin import ApprovedDraft, RunOrigin
from src.domains.agents.display.plain_text import markdown_to_plain_text
from src.domains.agents.effects.confirmation import readable_tool_name
from src.domains.agents.effects.digest import drafts_digest
from src.domains.agents.utils.helpers import generate_run_id
from src.domains.workboard.brief import build_ticket_brief
from src.domains.workboard.constants import (
    NOTIFICATION_TASK_TYPE,
    RUN_ORIGIN_KIND,
    ActorKind,
    AssigneeKind,
    RunError,
    RunOutcome,
    TicketEventKind,
    TicketStatus,
    worst_case_run_seconds,
)
from src.domains.workboard.models import WorkboardTicket
from src.domains.workboard.notifications import (
    WorkboardEvent,
    board_url,
    intent_url,
    notification_body,
    notification_metadata,
    recipients_for,
    ticket_url,
)
from src.domains.workboard.repository import KEEP_PENDING_ACTION, WorkboardRepository
from src.infrastructure.database.session import get_db_context
from src.infrastructure.observability.metrics_workboard import (
    lia_hidden_run_bytes,
    lia_hidden_run_rows,
    workboard_notifications_total,
    workboard_run_duration_seconds,
    workboard_runs_total,
)
from src.infrastructure.scheduler.out_of_turn_run import (
    RunOutcome as StreamOutcome,
)
from src.infrastructure.scheduler.out_of_turn_run import (
    RunResult,
    StreamRequest,
    TurnInterrupt,
    conversation_has_pending_hitl,
    resolve_run_context,
    stream_instruction,
)
from src.infrastructure.streaming.run_stream_broker import (
    ActiveRunLockLost,
    active_run_lease,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

#: Prometheus label of this spending layer (ADR-272): every model call a sweep
#: makes answers to the account's ceiling AND to the instance's.
SPEND_LAYER = "workboard_runner"


@dataclass(frozen=True)
class ClaimedRun:
    """A ticket taken for a run, and everything the run needs afterwards.

    Attributes:
        ticket_id: What is being run.
        holder_id: The account the run executes on — its tools, its quota, its
            conversation. NULL assignees resolve to the owner before this.
        run_id: The id the turn files everything under: the three ADR-263
            registers, the token logs, the hidden rows and the ticket.
        language: Backend-canonical code the answer comes back in.
        timezone: IANA zone of the holder.
        display_name: What the assistant calls them.
        display_mode: ``cards`` | ``html`` | ``markdown``.
        conversation_id: The thread the run writes into; None when the probe
            could not resolve it, in which case no lock is taken.
        brief: The instruction, composed from the OWNER's words only.
        claimed_at: When the claim landed — the start of what
            ``workboard_run_duration_seconds`` measures. Taken from the claim
            rather than from the tick, because the gates and the brief happen
            in between and a duration that included them would describe the
            sweep instead of the run.
        approved_draft: The action the person approved on the ticket, by
            identity, when this run is its replay (lot 7); None otherwise.
        execution_mode: ``pipeline`` or ``react`` — the TICKET's own choice.
    """

    ticket_id: uuid.UUID
    holder_id: uuid.UUID
    run_id: str
    language: str
    timezone: str
    display_name: str
    display_mode: str
    conversation_id: uuid.UUID | None
    brief: str
    claimed_at: datetime
    execution_mode: str
    approved_draft: ApprovedDraft | None = None


@dataclass(frozen=True)
class SettlePlan:
    """What a finished run writes on its ticket.

    Attributes:
        status: The column the ticket lands in.
        outcome: A :class:`RunOutcome` value.
        comment: What LIA says on the ticket, or None when there is nothing
            honest to say.
        error: A typed code and a bounded message, on failure.
        pending_action: The draft the person must confirm on the ticket, when
            the run stopped on one (lot 7); None clears whatever was there.
    """

    status: str
    outcome: str
    comment: str | None
    error: str | None
    pending_action: dict[str, Any] | None = None


def plan_settle(result: RunResult, *, language: str, timezone: str) -> SettlePlan:
    """Decide what a finished run writes, from what it actually produced.

    PURE, and separated from the writing on purpose: this is the branch table
    the whole feature is judged on, and a table you can call with a value is a
    table you can enumerate in a test.

    Five outcomes, and the third one is the reason this is not a two-line
    function: **an answer with no text is not an answer.** A run that streamed
    nothing would otherwise file an empty comment and move the ticket to « en
    validation », telling the person something was done (ADR-275's doctrine —
    a produced-nothing is a refusal, never a success with a shorter body).

    Args:
        result: What the pipeline returned.
        language: The holder's language — the comment is theirs to read.
        timezone: The holder's zone — a draft's dates are previewed in it.

    Returns:
        The status, the outcome, the comment and the error to store.
    """
    if result.interrupt is not None and result.interrupt.draft is not None:
        return _confirming_plan(result.interrupt, language=language, timezone=timezone)
    if result.outcome is StreamOutcome.WAITING:
        capability = readable_tool_name(result.refusals[0][0]) if result.refusals else None
        sentence = WorkboardMessages.waiting(language, capability)
        # A question the turn asked (a clarification) is quoted after the
        # sentence that says the run stopped: it is what the person must
        # answer, in LIA's own words.
        question = result.interrupt.question if result.interrupt is not None else ""
        # What it managed before stopping is kept: the person reads ONE
        # comment about this run, and dropping the work to keep the
        # question would hide what was already done.
        parts = [part for part in (result.text.strip(), sentence, question) if part]
        return SettlePlan(
            status=TicketStatus.WAITING.value,
            outcome=RunOutcome.WAITING.value,
            comment="\n\n".join(parts),
            error=None,
        )
    if result.outcome is StreamOutcome.SUCCESS and result.text.strip():
        return SettlePlan(
            status=TicketStatus.VALIDATING.value,
            outcome=RunOutcome.SUCCESS.value,
            comment=result.text.strip(),
            error=None,
        )
    # A failure leaves the ticket where the run found it — « en cours », with a
    # code the board renders — and nothing retries it: the person decides, with
    # « Lancer maintenant ». An automatic retry of a permanent failure is how a
    # ticket burns its ten runs overnight.
    code = RunError.EMPTY_ANSWER if result.outcome is StreamOutcome.SUCCESS else RunError.RUN_FAILED
    detail = (result.error or "").strip()
    message = f"{code.value}: {detail}" if detail else code.value
    return SettlePlan(
        status=TicketStatus.IN_PROGRESS.value,
        outcome=RunOutcome.FAILED.value,
        comment=None,
        error=message[:WORKBOARD_RUN_ERROR_MAX_CHARS],
    )


def _confirming_plan(interrupt: TurnInterrupt, *, language: str, timezone: str) -> SettlePlan:
    """What a run writes when it built an action the person must confirm.

    The comment is EXACTLY what the chat showed — the card the renderer wrote
    and the question the model asked, one stream (lot 14) — followed by how to
    answer on the ticket. Nothing is rendered a second time here: until lot 14
    the question already carried the model's card and this appended the
    renderer's preview to it, so the e-mail was read twice on the ticket. The
    draft itself travels on the row, so the answer can be matched to exactly
    what was shown (ADR-092).

    Args:
        interrupt: The draft critique the turn stopped on.
        language: The holder's language.
        timezone: The holder's zone — unused since the card comes with the
            question, kept so every settle plan takes the same arguments.

    Returns:
        The plan: « à confirmer », outcome ``confirming``, the draft stored.
    """
    del timezone
    draft = interrupt.draft or {}
    batch = draft.get("batch") or []
    return SettlePlan(
        status=TicketStatus.CONFIRMING.value,
        outcome=RunOutcome.CONFIRMING.value,
        comment=_bounded_confirming_comment(language, question=interrupt.question),
        error=None,
        pending_action={
            "draft_id": draft.get("draft_id"),
            "draft_type": draft.get("draft_type"),
            "draft_content": draft.get("draft_content") or {},
            "tool_name": draft.get("tool_name"),
            "question": interrupt.question,
            "approved": False,
            **({"batch": batch} if batch else {}),
        },
    )


def _bounded_confirming_comment(language: str, *, question: str) -> str:
    """The confirmation comment, cut to the column's cap from the QUESTION.

    The settle cuts every comment to ``workboard_comment_max_chars`` from the
    end — and the end of this one is the sentence that says how to answer. A
    long card (an email body) must therefore lose its tail, never the
    instruction.

    Args:
        language: The holder's language.
        question: What LIA asked — the card and the question, as streamed.

    Returns:
        A comment that fits the cap with the instruction in place.
    """
    cap = settings.workboard_comment_max_chars
    comment = WorkboardMessages.confirming(language, question=question)
    if len(comment) <= cap:
        return comment
    room = cap - len(WorkboardMessages.confirming(language, question="")) - 3
    shortened = question[: room - 1].rstrip() + "…" if room > 1 else ""
    return WorkboardMessages.confirming(language, question=shortened)


def _approved_draft_of(ticket: WorkboardTicket) -> ApprovedDraft | None:
    """The action the person approved on this ticket, by identity.

    Args:
        ticket: The claimed row.

    Returns:
        The identity the HITL node will let through, or None.
    """
    pending = ticket.pending_action or {}
    if not pending.get("approved"):
        return None
    batch = pending.get("batch") or []
    contents = (
        [dict(item.get("draft_content") or {}) for item in batch]
        if batch
        else [dict(pending.get("draft_content") or {})]
    )
    return ApprovedDraft(
        draft_type=str(pending.get("draft_type") or ""),
        digest=drafts_digest(contents),
    )


def _worst_case_seconds() -> int:
    """How long a legitimate run may hold its claim, on this deployment.

    Reads the two settings and the retry pause through ONE derivation, so the
    reaper cannot free a ticket a live worker is still running — which would
    put two runs on it, spending twice and possibly acting twice.
    """
    return worst_case_run_seconds(
        settings.workboard_run_timeout_seconds,
        settings.workboard_run_max_attempts,
        WORKBOARD_RUN_RETRY_DELAY_SECONDS,
    )


async def _housekeeping(db: AsyncSession, now: datetime) -> None:
    """Release stranded claims and drop transcripts past retention.

    Both are bounded statements over indexed predicates, and both run on every
    tick rather than on a schedule of their own: a second timer is a second
    thing to notice has stopped.

    Args:
        db: The tick's session.
        now: The tick's instant.
    """
    repository = WorkboardRepository(db)
    reaped = await repository.reap_stale_claims(
        older_than=now - timedelta(seconds=_worst_case_seconds())
    )
    purged = await repository.purge_hidden_rows(
        closed_before=now - timedelta(days=settings.workboard_hidden_rows_retention_days)
    )
    if reaped or purged:
        logger.info("workboard_housekeeping", reaped_claims=reaped, purged_rows=purged)
    # The volume the owner asked to WATCH rather than assume (D3b). Published
    # every tick, from the same pass that bounds it — a gauge fed by a separate
    # timer is a second thing to notice has stopped.
    rows, size_bytes = await repository.hidden_volume()
    lia_hidden_run_rows.set(rows)
    lia_hidden_run_bytes.set(size_bytes)


async def _claim_and_prepare(db: AsyncSession, now: datetime) -> ClaimedRun | None:
    """Take the next ticket and answer whether it may actually run.

    Everything that can refuse a run happens here, INSIDE the claim, so a
    refusal always has a claim to release and never leaves a ticket held.

    Args:
        db: The tick's session.
        now: The tick's instant.

    Returns:
        The prepared run, or None when nothing was claimable or the claim was
        given straight back.
    """
    repository = WorkboardRepository(db)
    offered = (
        (
            await db.execute(
                repository.claimable_stmt(
                    now,
                    max_runs=settings.workboard_max_runs_per_ticket,
                    max_attempts=settings.workboard_run_max_attempts,
                )
            )
        )
        .scalars()
        .first()
    )
    if offered is None:
        return None
    run_id = generate_run_id()
    ticket = await repository.claim_ticket(offered, run_id=run_id, now=now)
    if ticket is None:
        # Somebody claimed it between the scan and the write. Nothing to undo.
        return None
    return await _prepare_claimed(repository, ticket, run_id=run_id, now=now)


async def _prepare_claimed(
    repository: WorkboardRepository, ticket: WorkboardTicket, *, run_id: str, now: datetime
) -> ClaimedRun | None:
    """Run the three gates a claimed ticket must pass, then build its brief.

    Args:
        repository: The tick's repository.
        ticket: The claimed row.
        run_id: The claim's owner token.
        now: The tick's instant.

    Returns:
        The prepared run, or None when a gate refused it.
    """
    from src.domains.usage_limits.service import UsageLimitService

    holder = ticket.effective_assignee_id
    context = await resolve_run_context(repository.db, holder)
    if context is None:
        # Permanent, and nothing here can fix it: the ticket keeps its column
        # and says why, rather than being offered again every minute.
        await repository.settle_run(
            ticket_id=ticket.id,
            run_id=run_id,
            status=TicketStatus.IN_PROGRESS.value,
            outcome=RunOutcome.FAILED.value,
            now=now,
            error=RunError.ASSIGNEE_INACTIVE.value,
        )
        return None
    if await UsageLimitService.is_user_blocked_for_llm(holder, layer=SPEND_LAYER):
        await _release(
            repository,
            ticket_id=ticket.id,
            run_id=run_id,
            outcome=RunOutcome.SKIPPED_QUOTA,
            now=now,
            retry_after=now + timedelta(minutes=settings.workboard_quota_retry_minutes),
        )
        return None
    pending, conversation_id = await conversation_has_pending_hitl(
        repository.db, holder, context.language
    )
    if pending:
        await _release(
            repository,
            ticket_id=ticket.id,
            run_id=run_id,
            outcome=RunOutcome.SKIPPED_BUSY,
            now=now,
        )
        return None
    brief = await build_ticket_brief(repository, ticket, language=context.language)
    await repository.add_event(
        ticket_id=ticket.id,
        actor_kind=ActorKind.LIA.value,
        actor_user_id=None,
        kind=TicketEventKind.RUN_STARTED.value,
        payload={"run_id": run_id},
    )
    return ClaimedRun(
        ticket_id=ticket.id,
        holder_id=holder,
        run_id=run_id,
        language=context.language,
        timezone=context.timezone,
        display_name=context.display_name,
        display_mode=context.display_mode,
        conversation_id=conversation_id,
        brief=brief,
        claimed_at=now,
        execution_mode=ticket.execution_mode,
        approved_draft=_approved_draft_of(ticket),
    )


async def _release(
    repository: WorkboardRepository,
    *,
    ticket_id: uuid.UUID,
    run_id: str,
    outcome: RunOutcome,
    now: datetime,
    retry_after: datetime | None = None,
) -> None:
    """Give a claim back, and say so as « skipped » rather than « failed ».

    Args:
        repository: The tick's repository.
        ticket_id: The ticket.
        run_id: The claim's owner token.
        outcome: ``skipped_quota`` or ``skipped_busy``.
        now: The tick's instant.
        retry_after: Not before this instant, on a quota back-off.
    """
    await repository.release_claim(
        ticket_id=ticket_id,
        run_id=run_id,
        outcome=outcome.value,
        now=now,
        retry_after=retry_after,
    )
    workboard_runs_total.labels(outcome=outcome.value).inc()
    logger.info(
        "workboard_run_skipped",
        ticket_id=str(ticket_id),
        run_id=run_id,
        reason=outcome.value,
        retry_after=retry_after.isoformat() if retry_after else None,
    )


async def _run(prepared: ClaimedRun) -> RunResult | None:
    """Drive the turn, under the conversation's own lock.

    Returns None when the thread is already carrying a live run: a person
    typing in the chat owns their conversation, and a ticket can wait a minute.

    The lock is skipped — and the fact logged — when the conversation could not
    be resolved: the probe that resolves it FAILS OPEN by contract, and turning
    « I could not ask » into « I will not run » would make a Redis hiccup stop
    the whole board.

    Args:
        prepared: The claimed run.

    Returns:
        What the turn produced, or None when the thread was busy.
    """
    request = StreamRequest(
        user_id=prepared.holder_id,
        prompt=prepared.brief,
        session_id=f"{WORKBOARD_RUN_SESSION_PREFIX}{prepared.ticket_id}",
        language=prepared.language,
        timezone=prepared.timezone,
        display_name=prepared.display_name,
        display_mode=prepared.display_mode,
        timeout_seconds=settings.workboard_run_timeout_seconds,
        max_attempts=settings.workboard_run_max_attempts,
        retry_delay_seconds=WORKBOARD_RUN_RETRY_DELAY_SECONDS,
        origin=RunOrigin(
            kind=RUN_ORIGIN_KIND,
            ticket_id=str(prepared.ticket_id),
            run_id=prepared.run_id,
            # A ticket can carry a draft to the person, so the gate lets the
            # run BUILD the confirmation instead of refusing it (lot 7).
            can_carry_draft=True,
            approved_draft=prepared.approved_draft,
        ),
        run_id=prepared.run_id,
        # The TICKET's own choice (react by default), never the chat's toggle
        # and never a deployment switch: the person may change it at any point
        # of the ticket's life, and the next run reads what it says.
        execution_mode=prepared.execution_mode,
    )
    if prepared.conversation_id is None:
        logger.warning(
            "workboard_run_unlocked_thread",
            ticket_id=str(prepared.ticket_id),
            run_id=prepared.run_id,
        )
        await _announce_start(prepared)
        return await stream_instruction(request)

    from src.infrastructure.cache.redis import get_redis_cache

    redis = await get_redis_cache()
    try:
        async with active_run_lease(
            redis,
            str(prepared.conversation_id),
            run_id=prepared.run_id,
            stream_id=f"{RUN_ORIGIN_KIND}:{prepared.run_id}",
        ) as acquired:
            if not acquired:
                return None
            await _announce_start(prepared)
            return await stream_instruction(request)
    except ActiveRunLockLost:
        # Another producer took the conversation while the turn was running —
        # the person started talking, typically. `None` is the SAME answer the
        # pre-checks give for a busy conversation: the claim goes back and the
        # ticket retries, rather than spending one of its ten runs on a verdict
        # about work that was never LIA's to finish.
        logger.info(
            "workboard_run_conversation_taken_over",
            ticket_id=str(prepared.ticket_id),
            run_id=prepared.run_id,
        )
        return None


async def _clear_pending_question(prepared: ClaimedRun) -> None:
    """Drop the question the abandoned turn left on the thread.

    A run that stops on a HITL interrupt leaves a pending decision in the
    store, and nobody will ever answer it THERE — the person is asked on the
    ticket instead. Left behind, their next ordinary chat message would be read
    as the answer to a question they never saw (the call
    ``service.py`` already makes when a turn ends on one).

    Best-effort and idempotent: a thread with nothing pending is not an error,
    and a Redis hiccup must not turn a settled run into a failed one.

    Args:
        prepared: The claimed run, for its conversation.
    """
    if prepared.conversation_id is None:
        return
    from src.domains.agents.utils.hitl_store import HITLStore
    from src.infrastructure.cache.redis import get_redis_cache

    try:
        store = HITLStore(
            redis_client=await get_redis_cache(),
            ttl_seconds=settings.hitl_pending_data_ttl_seconds,
        )
        await store.clear_interrupt(thread_id=str(prepared.conversation_id))
    except Exception as clear_error:  # noqa: BLE001 — never costs a settle
        logger.warning(
            "workboard_run_clear_interrupt_failed",
            run_id=prepared.run_id,
            error=str(clear_error),
        )


async def _settle(db: AsyncSession, prepared: ClaimedRun, result: RunResult) -> SettlePlan | None:
    """Write what the run produced, on the ticket it belongs to.

    The comment and the event are written ONLY when the settle landed: a run
    that lost its ticket to a person who moved it must not leave a comment
    about work on a column they closed.

    Args:
        db: A fresh session — the run's own was closed before it started.
        prepared: The claimed run.
        result: What the turn produced.

    Returns:
        What was written, for the caller to notify about once it is committed;
        None when the settle lost the ticket and nothing was written.
    """
    repository = WorkboardRepository(db)
    if result.outcome is StreamOutcome.QUOTA_BLOCKED:
        # A ceiling refused the call, so the turn generated nothing: the claim
        # goes BACK the way the pre-check's own refusal returns it, with the
        # same back-off. Settling it would burn one of the ticket's ten runs
        # and tell the person LIA stumbled — a quota refusal is not a
        # generation failure (ADR-272), and until 2026-09-10 this path read it
        # as « LIA answered nothing » because the stream's error chunk was
        # dropped before anyone could see it.
        now = now_utc()
        await _release(
            repository,
            ticket_id=prepared.ticket_id,
            run_id=prepared.run_id,
            outcome=RunOutcome.SKIPPED_QUOTA,
            now=now,
            retry_after=now + timedelta(minutes=settings.workboard_quota_retry_minutes),
        )
        return None
    plan = plan_settle(result, language=prepared.language, timezone=prepared.timezone)
    if plan.outcome in STOPPED_ON_A_QUESTION:
        await _clear_pending_question(prepared)
    usage = await repository.run_usage(prepared.run_id)
    # A run that stops on a QUESTION or delivers a result to validate has
    # passed the ball: the ticket goes back to its owner in the same statement
    # that settles it. A FAILURE does not — nothing retries it, but nothing is
    # asked of the person either until they say so, and the card must keep
    # saying that LIA is the one that stumbled.
    hand_back = plan.status in HANDED_BACK_STATUSES
    settled = await repository.settle_run(
        ticket_id=prepared.ticket_id,
        run_id=prepared.run_id,
        status=plan.status,
        outcome=plan.outcome,
        now=now_utc(),
        error=plan.error,
        usage=usage,
        hand_back=hand_back,
        # A run that stopped on a draft stores it; one that ran to its end or
        # to a plain question clears what it may have replayed; a FAILURE
        # leaves it alone, so « run now » can still replay the approval.
        pending_action=(
            KEEP_PENDING_ACTION if plan.outcome == RunOutcome.FAILED.value else plan.pending_action
        ),
    )
    if not settled:
        logger.info(
            "workboard_run_settle_lost",
            ticket_id=str(prepared.ticket_id),
            run_id=prepared.run_id,
            outcome=plan.outcome,
        )
        return None
    if plan.comment:
        await repository.add_comment(
            ticket_id=prepared.ticket_id,
            author_kind=ActorKind.LIA.value,
            author_user_id=None,
            # A model answering in HTML would put its tags in front of the
            # person, in the panel, in the push excerpt and in the heartbeat
            # quote alike — and so would the Markdown of its own prose and of
            # the confirmation preview beside it, since a comment is a
            # paragraph of escaped text. Flattened ONCE here, at the only
            # place that writes LIA's words; the flattening only ever shortens,
            # so the cap the confirming comment was built against still holds.
            body=markdown_to_plain_text(plan.comment)[: settings.workboard_comment_max_chars],
            run_id=prepared.run_id,
        )
    await repository.add_event(
        ticket_id=prepared.ticket_id,
        actor_kind=ActorKind.LIA.value,
        actor_user_id=None,
        kind=TicketEventKind.RUN_FINISHED.value,
        payload={"run_id": prepared.run_id, "outcome": plan.outcome},
    )
    if hand_back:
        # The history says WHY the ticket came back, so the panel can tell it
        # from a hand-over and from a connection that ended (lot 5).
        await repository.add_event(
            ticket_id=prepared.ticket_id,
            actor_kind=ActorKind.LIA.value,
            actor_user_id=None,
            kind=TicketEventKind.ASSIGNED.value,
            payload={"to_kind": AssigneeKind.HUMAN.value, "reason": "handed_back"},
        )
    workboard_runs_total.labels(outcome=plan.outcome).inc()
    workboard_run_duration_seconds.labels(outcome=plan.outcome).observe(
        (now_utc() - prepared.claimed_at).total_seconds()
    )
    logger.info(
        "workboard_run_finished",
        ticket_id=str(prepared.ticket_id),
        run_id=prepared.run_id,
        outcome=plan.outcome,
        status=plan.status,
        tokens_in=usage.tokens_in,
        tokens_out=usage.tokens_out,
    )
    return plan


#: Columns a run lands in when the next move is the PERSON's. The ticket goes
#: back to its owner there: a question nobody is holding is a question nobody
#: answers.
HANDED_BACK_STATUSES: frozenset[str] = frozenset(
    {TicketStatus.WAITING.value, TicketStatus.CONFIRMING.value, TicketStatus.VALIDATING.value}
)

#: Outcomes of a run that stopped on a QUESTION the person answers on the
#: ticket — the thread's own record of it is dropped, so the chat stays free.
STOPPED_ON_A_QUESTION: frozenset[str] = frozenset(
    {RunOutcome.WAITING.value, RunOutcome.CONFIRMING.value}
)


def _event_of(plan: SettlePlan) -> WorkboardEvent:
    """Which notification a settled run produces.

    Args:
        plan: What the run wrote.

    Returns:
        The event the recipients will read about.
    """
    if plan.outcome == RunOutcome.WAITING.value:
        return WorkboardEvent.WAITING
    if plan.outcome == RunOutcome.CONFIRMING.value:
        return WorkboardEvent.CONFIRMING
    if plan.outcome == RunOutcome.FAILED.value:
        return WorkboardEvent.RUN_FAILED
    return WorkboardEvent.RUN_FINISHED


async def _notify(
    db: AsyncSession, prepared: ClaimedRun, event: WorkboardEvent, comment: str | None
) -> None:
    """Tell whoever asked to be told, and whoever must be told.

    Best-effort by contract: a notification that could not leave must never
    turn a settled run into a failed one — the ticket already carries the
    answer, which is the durable half.

    Args:
        db: The settling session.
        prepared: The claimed run.
        event: What happened.
        comment: What LIA wrote, when the event carries an answer.
    """
    ticket = await db.get(WorkboardTicket, prepared.ticket_id)
    if ticket is None:  # deleted while the run was in flight
        return
    for user_id in recipients_for(event, ticket):
        await _notify_one(
            db,
            user_id=user_id,
            ticket=ticket,
            event=event,
            run_id=prepared.run_id,
            comment=comment,
        )


async def _announce_start(prepared: ClaimedRun) -> None:
    """« LIA a commencé » — sent once the run REALLY starts.

    After the lease, never at the claim: a claim that is then released for a
    busy thread or a quota ceiling ran nothing, and a person following the
    ticket would have been told about work that did not happen.

    Args:
        prepared: The claimed run.
    """
    async with get_db_context() as db:
        await _notify(db, prepared, WorkboardEvent.RUN_STARTED, None)
        await db.commit()


async def _notify_one(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    ticket: WorkboardTicket,
    event: WorkboardEvent,
    run_id: str,
    comment: str | None,
) -> None:
    """Send ONE notification about a run, through the shared seam.

    The claim, the dispatch and the settle live in the seam's adapter
    (``domains/shared/proactive_sink``), which the assignment notification uses
    too: a proactive notification is an ACTION claimed before it happens and
    closed from what the dispatch REPORTS (ADR-263), and writing that twice is
    one chance too many to write it differently. What stays here is what is
    the WORKBOARD's: which recipient, which sentence, and the counter.

    Args:
        db: The settling session.
        user_id: Who is told.
        ticket: What about.
        event: What happened.
        run_id: The run, shared with the three registers.
        comment: What LIA wrote, when there is one to quote.
    """
    from src.domains.shared.proactive_sink import send_proactive_notification
    from src.domains.users.models import User

    delivered = False
    try:
        user = await db.get(User, user_id)
        if user is None:
            return
        language = getattr(user, "language", None) or settings.default_language
        # The link is built PER RECIPIENT: two sides of a shared ticket do not
        # necessarily read the same language, and an instruction in the wrong
        # one is an instruction the model answers in the wrong one.
        link = intent_url(ticket, language) if event is WorkboardEvent.WAITING else ""
        delivered = await send_proactive_notification(
            db=db,
            user=user,
            content=notification_body(
                event,
                ticket,
                language=language,
                comment=comment,
                intent_url=link,
                ticket_url=ticket_url(ticket),
            ),
            task_type=NOTIFICATION_TASK_TYPE,
            target_id=str(ticket.id),
            metadata=notification_metadata(
                event,
                ticket,
                board_url=board_url(),
                ticket_url=ticket_url(ticket),
                intent_url=link,
            ),
            run_id=run_id,
            # A run speaks up to three times (started, then finished, waiting
            # or confirming): each is its own claimed action, never a replay
            # of the first.
            occurrence=event.value,
        )
    except Exception as notify_error:  # noqa: BLE001 — never costs a settled run
        # `notification_event`, never `event`: structlog OWNS that key — it is
        # the message itself — and passing it raises inside the very handler
        # written so a failed notification costs nothing.
        logger.warning(
            "workboard_notification_failed",
            ticket_id=str(ticket.id),
            run_id=run_id,
            notification_event=event.value,
            error=str(notify_error),
        )
    workboard_notifications_total.labels(event=event.value, delivered=str(delivered).lower()).inc()


async def sweep_workboard_runs() -> None:
    """One tick of the workboard sweep. Never raises.

    A scheduler job that raises is a job the operator finds out about from a
    stack trace; this one settles or releases whatever it took and logs.
    """
    now = datetime.now(UTC)
    try:
        async with get_db_context() as db:
            await _housekeeping(db, now)
            await db.commit()
    except Exception as housekeeping_error:  # noqa: BLE001 — never blocks a run
        logger.warning("workboard_housekeeping_failed", error=str(housekeeping_error))

    try:
        async with get_db_context() as db:
            prepared = await _claim_and_prepare(db, now)
            await db.commit()
    except Exception as claim_error:  # noqa: BLE001 — the reaper covers a lost claim
        logger.error("workboard_claim_failed", error=str(claim_error))
        return
    if prepared is None:
        return

    try:
        result = await _run(prepared)
    except Exception as run_error:  # noqa: BLE001 — a claim always gets settled
        # Everything INSIDE the turn is already settled by the engine; reaching
        # here means the plumbing around it broke (Redis, the lock). The claim
        # is closed now rather than left for the reaper ten minutes later.
        logger.error(
            "workboard_run_crashed",
            ticket_id=str(prepared.ticket_id),
            run_id=prepared.run_id,
            error=f"{type(run_error).__name__}: {run_error}",
        )
        result = RunResult(
            outcome=StreamOutcome.FAILED,
            error=f"{type(run_error).__name__}: {run_error}",
        )

    plan: SettlePlan | None = None
    try:
        async with get_db_context() as db:
            repository = WorkboardRepository(db)
            if result is None:
                await _release(
                    repository,
                    ticket_id=prepared.ticket_id,
                    run_id=prepared.run_id,
                    outcome=RunOutcome.SKIPPED_BUSY,
                    now=now_utc(),
                )
            else:
                plan = await _settle(db, prepared, result)
            await db.commit()
    except Exception as settle_error:  # noqa: BLE001 — the reaper covers the claim
        # The claim was committed and the turn has run; a database that goes
        # away in between leaves nothing to do but say so. Raising here would
        # hand the operator a stack trace from the scheduler for a state the
        # reaper already releases — and it would skip the notification too.
        logger.error(
            "workboard_settle_failed",
            ticket_id=str(prepared.ticket_id),
            run_id=prepared.run_id,
            error=f"{type(settle_error).__name__}: {settle_error}",
        )
        return

    # The notification comes AFTER the settle is committed, in its own session:
    # the ticket carries the answer whatever happens next, and the dispatcher
    # commits its own archived row rather than deciding when ours lands. It is
    # also the LAST thing a tick does, and the least durable: the ticket holds
    # the answer, so a channel that is down costs a log line and nothing else.
    if plan is not None:
        try:
            async with get_db_context() as db:
                await _notify(db, prepared, _event_of(plan), plan.comment)
                await db.commit()
        except Exception as notify_error:  # noqa: BLE001 — never costs a settled run
            logger.warning(
                "workboard_notification_phase_failed",
                ticket_id=str(prepared.ticket_id),
                run_id=prepared.run_id,
                error=f"{type(notify_error).__name__}: {notify_error}",
            )
