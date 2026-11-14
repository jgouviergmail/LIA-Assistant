"""One engine for « LIA runs an instruction out of turn » (ADR-276).

Three pieces were identical in the routine executor and would have been
identical again in the workboard runner. They are extracted here so there is
ONE implementation of each, and so the workboard inherits by construction what
the routine path learned the hard way:

- :func:`resolve_run_context` — who the run belongs to, and the preferences it
  will answer in. Refuses an inactive account (a deleted one is inactive too).
- :func:`stream_instruction` — admitting the turn once, checking its generation's
  question strictly, then driving ``stream_chat_response`` with bounded attempts.

What this module deliberately does NOT own: the condition gate, propose-first,
the run history, the rescheduling and the notification — those are the
routine's, and the workboard has its own equivalents. Admission and settlement
use short owned sessions, never a transaction around a provider or Redis wait.

Everything the retry loop does is a defect the routine path paid for. A
``content_replacement`` chunk REPLACES the accumulated tokens rather than
appending — the post-processed content arrives after the deltas, and
accumulating only tokens built the notification from the pre-post-processing
text. A HITL interrupt is NOT retryable — asking again a question nobody
answered is not a retry. Each attempt gets a fresh session id, because attempt
one may have half-run the graph and attempt two must not resume a broken
checkpoint. And only the first attempt archives the question (ADR-117), or a
retry would duplicate the row.

**A question is read from the chunks the stream actually emits.** The stream
never carries a bare ``hitl_interrupt`` chunk: an interrupt arrives as
``hitl_interrupt_metadata`` (the action requests), the question's tokens, then
``hitl_interrupt_complete``. Measured 2026-09-09: the previous reader waited
for a chunk type nothing produces, so a turn that stopped on a clarification
settled as a SUCCESS with the tokens streamed before it (ADR-276, lot 7).
"""

from __future__ import annotations

import asyncio
import math
from collections.abc import Awaitable, Callable, Mapping
from contextlib import aclosing
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, assert_never
from uuid import UUID

import structlog

from src.core.constants import (
    DEFAULT_USER_DISPLAY_TIMEZONE,
    INSTANCE_BUDGET_EXHAUSTED_ERROR_CODE,
    USAGE_LIMIT_EXCEEDED_ERROR_CODE,
)
from src.core.conversation_execution import (
    ConversationBusy,
    ExecutionRevoked,
    RunAdmission,
    RunEnd,
)
from src.core.conversation_selection import ConversationSelection
from src.core.i18n import language_scope, normalize_language
from src.core.llm_config_helper import run_bound_seconds
from src.core.run_authority import current_run_authority, run_authority_scope
from src.core.user_display import resolve_user_display_name
from src.domains.agents.api.internal_admission import internal_turn
from src.domains.agents.api.run_origin import RunOrigin, out_of_turn_origin_ctx
from src.domains.agents.services.hitl.protocols import HitlInteractionType
from src.domains.agents.services.nothing_new import DONE_KEY as NOTHING_NEW_DONE_KEY
from src.domains.agents.services.nothing_new import quiet_run_scope
from src.domains.agents.services.streaming.latency_sli import awaited_by_a_person
from src.domains.shared.mcp_preapproval import MCPPreapproval, mcp_preapproval_scope

logger = structlog.get_logger(__name__)

#: Failures worth another attempt: the world blinked, the request did not.
_TRANSIENT_ERRORS = (TimeoutError, ConnectionError, OSError)
#: The calls of one turn that run one after the other, in each mode. A loop is listed
#: once: it is guaranteed one whole call, and the environment's value stays its budget.
_TURN_LLM_SLOTS: tuple[tuple[str, ...], ...] = (
    ("query_analyzer", "react_agent", "response"),
    ("query_analyzer", "planner", "response"),
)


def worst_case_run_seconds(timeout_seconds: int, max_attempts: int, retry_delay: int) -> int:
    """The longest a LEGITIMATE run can hold its claim.

    A ticket's reaper and a routine's recovery exist to free what a dead
    worker still holds, and they must never free what a live worker is still
    running: two runs on one row would spend twice and could act twice.

    The trap it closes is arithmetic. The engine bounds ONE ATTEMPT, and a run
    may retry a transient failure — so a run whose attempts each take the full
    timeout holds its claim for ``timeout × attempts`` plus the pauses between
    them, longer than the number an operator reads as « the timeout ». It lives
    beside the retry policy it measures, so every reader derives it alike.

    Args:
        timeout_seconds: Hard bound of ONE attempt.
        max_attempts: Attempts one run may make, the first included.
        retry_delay: Pause between two attempts.

    Returns:
        The age past which a claim is certainly stranded.
    """
    return timeout_seconds * max_attempts + retry_delay * max(0, max_attempts - 1)


def unattended_turn_seconds(configured_seconds: int) -> int:
    """How long ONE attempt of a turn nobody waits for may last.

    The environment's budget stands until the calls of one turn need longer. Cut
    at its budget, a routine loses a call the administrator still allowed, and a
    run that already acted is never relaunched (ADR-221 amendment 2026-11-05).
    A claim's recovery cannot know a run's mode, so both modes read the longer
    bound. A voice turn keeps its own budget.

    Args:
        configured_seconds: The budget the environment gives one attempt.

    Returns:
        The bound, in whole seconds.
    """
    return math.ceil(
        max(run_bound_seconds(configured_seconds, *slots) for slots in _TURN_LLM_SLOTS)
    )


class RunOutcome(str, Enum):
    """How an out-of-turn run ended.

    ``WAITING`` is not a failure: the turn ran, and what it found needs the
    person. ``FAILED`` is, and it says so with a typed message.

    ``QUOTA_BLOCKED`` is neither: a ceiling refused the call, so nothing was
    generated and nothing went wrong. Its caller decides what to write —
    a ticket is RELEASED as « skipped », never settled as a failure, because
    a quota refusal is not a generation failure (ADR-272).
    """

    SUCCESS = "success"
    WAITING = "waiting"
    FAILED = "failed"
    QUOTA_BLOCKED = "quota_blocked"
    BUSY = "busy"
    PENDING_QUESTION = "pending_question"


def run_end_of(outcome: RunOutcome) -> RunEnd:
    """How a settled out-of-turn run ended, for the close that releases the account.

    A turn that ran and answered — or asked the person — ended normally; a
    refusal or a failure did not; a turn that never ran did not start (ADR-384).

    Args:
        outcome: The settled outcome.

    Returns:
        The end the close writes.
    """
    match outcome:
        case RunOutcome.SUCCESS | RunOutcome.WAITING:
            return RunEnd.NORMAL
        case RunOutcome.FAILED | RunOutcome.QUOTA_BLOCKED:
            return RunEnd.INTERRUPTED
        case RunOutcome.BUSY | RunOutcome.PENDING_QUESTION:
            return RunEnd.UNSTARTED
        case _:
            assert_never(outcome)


#: The error codes a refusal by a spend ceiling arrives under. Read
#: STRUCTURALLY from the chunk's metadata, never matched on its prose: the
#: sentence is localized by the frontend and would change under us.
_QUOTA_ERROR_CODES = frozenset(
    {USAGE_LIMIT_EXCEEDED_ERROR_CODE, INSTANCE_BUDGET_EXHAUSTED_ERROR_CODE}
)


@dataclass(frozen=True)
class StreamFailure:
    """What the stream itself said went wrong, read from its error chunk.

    Attributes:
        code: The stable ``error_code`` of the chunk's metadata, when it
            carried one.
        message: The technical sentence the chunk carried, for the row.
    """

    code: str | None
    message: str

    @property
    def is_quota(self) -> bool:
        """Whether a spend ceiling is what refused the call."""
        return self.code in _QUOTA_ERROR_CODES


@dataclass(frozen=True)
class RunContext:
    """Who the run belongs to, and how it must answer them.

    Attributes:
        user: The account row, for callers that need more than the four
            preferences below.
        language: Backend-canonical language code.
        timezone: IANA zone the person reads wall clocks in.
        display_name: What the assistant calls them.
        display_mode: ``cards`` | ``html`` | ``html_cards`` | ``markdown``.
        execution_mode: The person's OWN chat mode — read by a turn spoken by
            them (a relayed phone call, lot 4); an unattended run never uses it.
        memory_enabled: Their long-term memory switch.
        journals_enabled: Their journals switch.
        psyche_enabled: Their psyche-engine switch.
    """

    user: Any
    language: str
    timezone: str
    display_name: str
    display_mode: str
    execution_mode: str = "pipeline"
    memory_enabled: bool = False
    journals_enabled: bool = False
    psyche_enabled: bool = False


@dataclass(frozen=True)
class StreamRequest:
    """One instruction to run, and the bounds it runs under.

    Attributes:
        user_id: Whose account, quota and conversation.
        prompt: What to do, in the person's own words or their ticket's.
        session_id: Base session id; each attempt derives its own from it.
        language: Backend-canonical language code.
        timezone: IANA zone.
        display_name: What the assistant calls them.
        display_mode: ``cards`` | ``html`` | ``html_cards`` | ``markdown``.
        timeout_seconds: Hard bound of ONE attempt.
        max_attempts: Attempts including the first.
        retry_delay_seconds: Pause between two attempts.
        origin: Published to the turn when the run is a workboard ticket, so
            the archive enrichers and the effect gate can read it.
        run_id: The id the turn must file everything under (ADR-117's detached
            producer path). A caller that has a row to settle supplies it, so
            the three registers, the token logs, the ticket and the question a
            stopped turn leaves on the thread all name the SAME run, across its
            attempts; None lets the graph mint its own.
        execution_mode: ``pipeline`` or ``react`` — the CALLER's decision, never
            the person's chat preference. Nothing here reads
            ``user.execution_mode``: a routine and a ticket each run in the
            mode their own row carries, and the chat header's toggle keeps
            meaning the chat alone. A turn SPOKEN by the person is the
            exception, and its caller passes the person's own mode explicitly.
        spoken_by_person: True when the prompt is the person's OWN words
            (the relay of a phone call they had with LIA, lot 4). The turn
            is then NOT automated — the six extractions run, a plan is not
            pre-approved, the three preference flags below apply — because
            a message the person spoke deserves exactly what a message they
            typed gets.
        memory_enabled: Their long-term memory switch (spoken turns only).
        journals_enabled: Their journals switch (spoken turns only).
        psyche_enabled: Their psyche-engine switch (spoken turns only).
        original_run_id: The run this turn RESUMES when LIA had stopped on a
            question and the prompt is the person's answer (a voice
            delegation, ADR-301) — the chat router's own resumption, so the
            caller also passes it as ``run_id``: the accounting of a question
            and of its answer share one id.
        conversation_id: Explicit discussion, paired with its revision; omitted
            for an autonomous task or external channel targeting current Main.
        conversation_revision: Displayed revision; a stale selection refuses.
        resume_pending: Whether the person is answering a pending question.
            Unattended jobs leave questions untouched and report pending_question.
        admission: Private authority supplied by an owning voice reservation;
            validated by the common door, never accepted from a client payload.
        live_session_id: The voice session's key, stamped on the turn's rows
            so the closing card counts them (ADR-299 A5); None otherwise.
        spoken_text: What the person actually said when the prompt is a
            voice model's rendering of it; archived beside the request.
        person_waiting: True when someone waits for this run's answer — a live
            phone delegation, the person on the line. A routine, a ticket and
            the relay of a finished call wait for nobody, so their turns feed
            no chat latency (``streaming/latency_sli``).
        mcp_preapproval: The MCP servers a ROUTINE's form pre-approved, published
            to the turn for the effect gate (spec 2026-10-29 D9); None for every
            other caller — nothing else may confirm on the person's behalf.
        quiet_when_nothing_new: A ROUTINE's own option (ADR-265 amendment
            2026-11-12 c): the answering model is then told how to declare
            that its answer says nothing new, and ``RunResult.nothing_new``
            carries the declaration; False for every other caller.
    """

    user_id: UUID
    prompt: str
    session_id: str
    language: str
    timezone: str
    display_name: str
    display_mode: str
    timeout_seconds: int
    max_attempts: int
    retry_delay_seconds: int
    origin: RunOrigin | None = None
    run_id: str | None = None
    execution_mode: str = "pipeline"
    spoken_by_person: bool = False
    memory_enabled: bool = False
    journals_enabled: bool = False
    psyche_enabled: bool = False
    original_run_id: str | None = None
    live_session_id: str | None = None
    spoken_text: str | None = None
    person_waiting: bool = False
    mcp_preapproval: MCPPreapproval | None = None
    quiet_when_nothing_new: bool = False
    conversation_id: UUID | None = None
    conversation_revision: int | None = None
    resume_pending: bool = False
    admission: RunAdmission | None = None


@dataclass(frozen=True)
class TurnInterrupt:
    """The question a turn stopped on, as the stream described it.

    Attributes:
        kind: The action request type — ``draft_critique``, ``clarification``…
        question: What LIA would have asked, in the person's language: the
            generated question when the stream carried one, else the tokens
            it streamed for it.
        draft: On a draft critique, what must be confirmed — ``draft_id``,
            ``draft_type``, ``draft_content`` and ``tool_name``, exactly what
            the chat's card would have shown. None for any other question.
    """

    kind: str
    question: str
    draft: dict[str, Any] | None = None


def interrupt_log_facts(interrupt: TurnInterrupt | None) -> dict[str, str | None]:
    """What a failure log may say about the question a run stopped on: its kinds.

    Args:
        interrupt: The question, when the run stopped on one.

    Returns:
        ``interrupt_kind`` and ``draft_type`` — bounded vocabularies, never words.
    """
    if interrupt is None:
        return {"interrupt_kind": None, "draft_type": None}
    draft_type = (interrupt.draft or {}).get("draft_type")
    return {
        "interrupt_kind": interrupt.kind,
        "draft_type": draft_type if isinstance(draft_type, str) else None,
    }


@dataclass
class RunResult:
    """What the turn produced, and how it ended.

    Attributes:
        outcome: Success, waiting for the person, or failed.
        text: The answer, post-processed, ready to be shown or stored.
        attempts: How many attempts it took.
        error: A typed message on failure; None otherwise.
        refusals: ``(tool, error_code)`` the gate refused during the turn —
            the STRUCTURED signal a settle reads instead of the model's prose.
        interrupt: The question the turn stopped on, when it stopped on one.
        register: The register the answering model declared (ADR-253), read
            from the ``done`` chunk — a voice restitutes the answer in that
            manner; None when the annotation is off or the turn declared none.
        error_code: Structured exception type or stream error code; never
            derived from the human-readable failure message.
        admission: Private receipt used only for conditional question cleanup;
            it grants no authority after the execution has closed.
        nothing_new: True when the answering model declared that its answer
            says nothing new (a routine told to notify only of something
            new) — on a successful run only, and only on an explicit
            declaration: doubt notifies.
    """

    outcome: RunOutcome
    text: str = ""
    attempts: int = 0
    error: str | None = None
    refusals: list[tuple[str, str]] = field(default_factory=list)
    interrupt: TurnInterrupt | None = None
    register: str | None = None
    error_code: str | None = None
    admission: RunAdmission | None = None
    nothing_new: bool = False


async def resolve_run_context(db: Any, user_id: UUID) -> RunContext | None:
    """Load the account a run belongs to, and the preferences it answers in.

    Args:
        db: The caller's session.
        user_id: Whose run.

    Returns:
        The context, or None when the account is unknown or inactive — a
        deleted account is inactive too, so this is one guard, not two.
    """
    # Imported HERE, not at module level: a module-level import binds the name
    # at import time, and every caller's test patches the SOURCE. The routine
    # executor imported them inside its function for the same reason.
    from src.domains.users.service import UserService

    user = await UserService(db).get_user_by_id(user_id)
    if not user:
        logger.warning("out_of_turn_run_user_not_found", user_id=str(user_id))
        return None
    if not user.is_active:
        logger.info("out_of_turn_run_user_inactive", user_id=str(user_id))
        return None
    return RunContext(
        user=user,
        language=normalize_language(user.language),
        timezone=user.timezone or DEFAULT_USER_DISPLAY_TIMEZONE,
        display_name=resolve_user_display_name(user.full_name, user.email),
        display_mode=getattr(user, "response_display_mode", None) or "cards",
        execution_mode=getattr(user, "execution_mode", None) or "pipeline",
        memory_enabled=bool(getattr(user, "memory_enabled", False)),
        journals_enabled=bool(getattr(user, "journals_enabled", False)),
        psyche_enabled=bool(getattr(user, "psyche_enabled", False)),
    )


async def clear_question_of_run(admission: RunAdmission | None) -> bool:
    """Take back the question a run left on a thread nobody watches (N10).

    The ReAct loop no longer asks when nobody can answer, but a path that does
    not know — a pipeline clarification — still stops on a question. Left on
    the thread, it reads the person's next message as its answer, and every
    later run of the account stands aside for it. Only the run's OWN question
    goes: the person's turn may have saved one since.

    Best-effort by contract: a Redis hiccup must not turn a settled run into a
    failed one.

    Args:
        admission: The exact invocation that asked; absent when nothing ran.

    Returns:
        True when the run's question was found and cleared.
    """
    if admission is None:
        return False
    from src.core.config import settings
    from src.domains.agents.utils.hitl_store import HITLStore
    from src.infrastructure.cache.redis import get_redis_cache

    try:
        store = HITLStore(
            redis_client=await get_redis_cache(),
            ttl_seconds=settings.hitl_pending_data_ttl_seconds,
        )
        return await store.clear_interrupt_for_run(
            str(admission.target.runtime_id), admission.run_id, activity_id=admission.activity_id
        )
    except Exception as clear_error:  # noqa: BLE001 — never costs a settle
        logger.warning(
            "out_of_turn_run_question_clear_failed",
            run_id=admission.run_id,
            error_type=type(clear_error).__name__,
        )
        return False


async def stream_instruction(
    request: StreamRequest, *, before_run: Callable[[], Awaitable[None]] | None = None
) -> RunResult:
    """Run one instruction through the pipeline, with a timeout and retries.

    Args:
        request: What to run, and the bounds it runs under.
        before_run: Admission-time check or independent start notification, after
            admission and the question check. Cancellation joins owned resources.

    Returns:
        The answer and how the turn ended. Failures are results; cancellation
        propagates after owned graph resources are drained and joined.
    """
    token = out_of_turn_origin_ctx.set(request.origin) if request.origin is not None else None
    try:
        # Whatever the run writes without an explicit language is written in
        # the person's own (ADR-323): a routine or a ticket has no request.
        with (
            language_scope(request.language),
            awaited_by_a_person(request.person_waiting),
            mcp_preapproval_scope(request.mcp_preapproval),
            quiet_run_scope(request.quiet_when_nothing_new),
        ):
            return await _drive_admitted(request, before_run)
    except ConversationBusy:
        return _settled(request, RunOutcome.BUSY, attempt=0)
    except Exception as exc:
        logger.warning(
            "out_of_turn_admission_failed",
            session_id=request.session_id,
            error_type=type(exc).__name__,
        )
        return _settled(
            request,
            RunOutcome.FAILED,
            attempt=0,
            error=type(exc).__name__,
            error_code=type(exc).__name__,
        )
    finally:
        if token is not None:
            out_of_turn_origin_ctx.reset(token)


async def _drive_admitted(
    request: StreamRequest, before_run: Callable[[], Awaitable[None]] | None
) -> RunResult:
    """Pin one generation and invocation across all attempts, without a transaction wait."""
    async with internal_turn(
        request.user_id,
        selection=ConversationSelection(
            conversation_id=request.conversation_id,
            conversation_revision=request.conversation_revision,
        ),
        admission=request.admission,
        run_id=request.run_id,
        language=request.language,
        answer_pending=request.resume_pending,
    ) as prepared:
        if prepared.pending_question:
            _declare_end(RunOutcome.PENDING_QUESTION)
            return _settled(request, RunOutcome.PENDING_QUESTION, attempt=0)
        if (
            request.original_run_id is not None
            and request.original_run_id != prepared.original_run_id
        ):
            raise ExecutionRevoked()
        request = replace(
            request,
            admission=prepared.admission,
            run_id=prepared.admission.run_id,
            original_run_id=prepared.original_run_id,
        )
        if before_run is not None:
            # This check/notification produces no graph output. The graph slot
            # stays occupied until it completes or its cancellation is joined.
            with run_authority_scope(None):
                await before_run()
        result = await _attempt_until_settled(request)
        _declare_end(result.outcome)
        return result


def _declare_end(outcome: RunOutcome) -> None:
    """Tell the admission this turn owns how it ended, before its close reads it."""
    authority = current_run_authority()
    if authority is not None:
        authority.end = run_end_of(outcome)


async def _attempt_until_settled(request: StreamRequest) -> RunResult:
    """Drive the attempts, and settle from what the last one produced.

    Args:
        request: The instruction and its bounds.

    Returns:
        The result of the first attempt that settled.
    """
    last_error: Exception | None = None
    attempt = 0

    for attempt in range(1, request.max_attempts + 1):
        try:
            read = await asyncio.wait_for(
                _one_attempt(request, attempt), timeout=request.timeout_seconds
            )
        except _TRANSIENT_ERRORS as transient:
            last_error = transient
            refused = await _retry_or_settle(request, attempt, transient)
            if refused is not None:
                return refused
            continue
        except Exception as fatal:  # noqa: BLE001 — settled as a failure, never raised
            logger.error(
                "out_of_turn_run_failed",
                session_id=request.session_id,
                attempt=attempt,
                error_type=type(fatal).__name__,
            )
            return _settled(
                request,
                RunOutcome.FAILED,
                attempt=attempt,
                error=f"{type(fatal).__name__}: {fatal}",
                error_code=type(fatal).__name__,
            )

        text, interrupt, failure = read.text, read.interrupt, read.failure
        if interrupt is not None:
            # Nobody answered the question; asking it again is not a retry.
            return _settled(
                request,
                RunOutcome.WAITING,
                attempt=attempt,
                text=text,
                interrupt=interrupt,
                register=read.register,
            )
        if failure is not None:
            # NOT retried: a ceiling that refused this call refuses the next
            # one too, and a stream that named its own failure has already
            # decided. Retrying would spend the caller's attempts on a verdict
            # that will not change.
            return _settled(
                request,
                await _failure_outcome(failure, request.run_id),
                attempt=attempt,
                text=text,
                error=failure.message or failure.code or "the run was refused",
                error_code=failure.code or "stream_error",
            )
        # A refusal collected by the gate means the turn met something only the
        # person can allow — the answer is real, but the work is not finished.
        outcome = (
            RunOutcome.WAITING
            if request.origin is not None and request.origin.refusals
            else RunOutcome.SUCCESS
        )
        return _settled(
            request,
            outcome,
            attempt=attempt,
            text=text,
            register=read.register,
            nothing_new=read.nothing_new and outcome is RunOutcome.SUCCESS,
        )

    return _settled(
        request,
        RunOutcome.FAILED,
        attempt=attempt,
        error=_failure_message(last_error, request),
        error_code=type(last_error).__name__ if last_error is not None else "no_result",
    )


async def _retry_or_settle(
    request: StreamRequest, attempt: int, transient: Exception
) -> RunResult | None:
    """Decide what a transient failure leads to: another attempt, or the end.

    A retry replays the WHOLE turn. Measured in production: an attempt reached
    its bound while a browser task ran, and the retry performed the browser
    tasks again. So a retry is refused once the run may have acted (point 20).

    Args:
        request: The instruction and its bounds.
        attempt: The attempt that just failed, 1-based.
        transient: What it failed with.

    Returns:
        A FAILED result when a retry would replay an action; None to go on —
        to the next attempt, or past the last one to the usual failure.
    """
    logger.warning(
        "out_of_turn_run_transient_error",
        session_id=request.session_id,
        attempt=attempt,
        error_type=type(transient).__name__,
    )
    if attempt >= request.max_attempts:
        return None
    if await _may_have_started(request.run_id):
        logger.warning(
            "out_of_turn_run_retry_refused_after_effect",
            session_id=request.session_id,
            run_id=request.run_id,
            attempt=attempt,
        )
        return _settled(
            request,
            RunOutcome.FAILED,
            attempt=attempt,
            error=_failure_message(transient, request, attempts=attempt),
            error_code=type(transient).__name__,
        )
    if request.retry_delay_seconds:
        await asyncio.sleep(request.retry_delay_seconds)
    return None


async def _failure_outcome(failure: StreamFailure, run_id: str | None) -> RunOutcome:
    """Only an unstarted quota refusal may give a job back to its automatic queue."""
    if failure.is_quota and not await _may_have_started(run_id):
        return RunOutcome.QUOTA_BLOCKED
    return RunOutcome.FAILED


async def _may_have_started(run_id: str | None) -> bool:
    """A paid or acting turn cannot be requeued, including after a later quota refusal."""
    authority = current_run_authority()
    return bool(authority is not None and authority.external_work_started) or await _run_acted(
        run_id
    )


async def _run_acted(run_id: str | None) -> bool:
    """Whether an attempt of this run may have acted on the world (ADR-263).

    The register answers: any action row of the run but a refusal says it may
    have. A register that cannot be read answers yes — doubt never retries, an
    action that may have happened must not happen twice. A caller that names no
    run can read nothing, and keeps the retry it always had.

    Args:
        run_id: The run, or None when the graph minted its own per attempt.

    Returns:
        True when a retry could replay an action.
    """
    if not run_id:
        return False
    from src.domains.agents.effects.repository import EffectLedgerRepository
    from src.infrastructure.database.session import get_db_context

    try:
        async with get_db_context() as db:
            return await EffectLedgerRepository(db).acted_in_run(run_id)
    except Exception as read_error:  # noqa: BLE001 — doubt never retries
        logger.warning(
            "out_of_turn_run_effects_unreadable",
            run_id=run_id,
            error_type=type(read_error).__name__,
        )
        return True


async def _one_attempt(request: StreamRequest, attempt: int) -> _StreamReader:
    """Consume one full generation.

    The generator is consumed to its end even when it announces a question:
    its tail commits the turn's token accounting, and breaking out of it would
    close the generator before that runs.

    Args:
        request: The instruction and its bounds.
        attempt: 1-based attempt number.

    Returns:
        The reader, holding the post-processed answer, the question the turn
        stopped on, the refusal the stream announced and the register it
        declared — each None when the turn had none.
    """
    # A fresh session per retry: attempt one may have half-run the graph, and
    # attempt two must start clean rather than resume a broken checkpoint.
    session_id = request.session_id if attempt == 1 else f"{request.session_id}_retry_{attempt}"
    from src.domains.agents.api.service import AgentService

    reader = _StreamReader()
    stream = AgentService().stream_chat_response(
        user_message=request.prompt,
        user_id=request.user_id,
        session_id=session_id,
        user_timezone=request.timezone,
        user_language=request.language,
        user_display_name=request.display_name,
        user_display_mode=request.display_mode,
        # Passed explicitly: the default of this parameter is « pipeline », so
        # every out-of-turn run silently ignored the mode until a ticket asked
        # for the loop — and then the CALLER decides, never the chat toggle.
        user_execution_mode=request.execution_mode,
        # A turn the person SPOKE is theirs: not automated (the extractions
        # run), no plan pre-approved, their own preference flags (lot 4).
        is_automated_source=not request.spoken_by_person,
        auto_approve_plan=not request.spoken_by_person,
        user_memory_enabled=request.spoken_by_person and request.memory_enabled,
        user_journals_enabled=request.spoken_by_person and request.journals_enabled,
        user_psyche_enabled=request.spoken_by_person and request.psyche_enabled,
        # The archive door returns the same request id on a preparation retry;
        # the preceding attempt may have failed before it archived anything.
        archive_user_message=True,
        # The SAME id across attempts on purpose: the ticket paid for every one
        # of them, so the cost aggregate must find them all under one run.
        run_id=request.run_id,
        # A voice delegation (ADR-301): the run a pending question is answered
        # on, the session stamp of the rows, the words actually spoken.
        original_run_id=request.original_run_id,
        live_session_id=request.live_session_id,
        spoken_text=request.spoken_text,
        target=request.admission.target if request.admission is not None else None,
        admission=request.admission,
    )
    async with aclosing(stream):
        async for chunk in stream:
            reader.feed(chunk)
    return reader


@dataclass
class _StreamReader:
    """What one generation said, read chunk by chunk.

    Attributes:
        tokens: The answer's deltas, in order.
        replacement: The post-processed answer, when the stream sent one.
        asked: The first action request of an interrupt, when one arrived.
        question_tokens: The question's own deltas.
        question: The question the stream settled on, when it said so.
        failure: The refusal the stream announced, when it announced one.
        register: The register the ``done`` chunk declared (ADR-253), if any.
        nothing_new: Whether the ``done`` chunk carried the answering model's
            declaration that its answer says nothing new.
    """

    tokens: list[str] = field(default_factory=list)
    replacement: str | None = None
    asked: Mapping[str, Any] | None = None
    question_tokens: list[str] = field(default_factory=list)
    question: str | None = None
    failure: StreamFailure | None = None
    register: str | None = None
    nothing_new: bool = False

    def feed(self, chunk: Any) -> None:
        """Read one chunk.

        Args:
            chunk: A ``ChatStreamChunk`` (or anything with the same three
                attributes).
        """
        text = chunk.content if isinstance(chunk.content, str) else None
        if chunk.type == "token" and text is not None:
            self.tokens.append(text)
        elif chunk.type == "content_replacement" and text is not None:
            # REPLACES the deltas: the post-processed content is the canonical
            # answer, and appending would ship the pre-processing text too.
            self.replacement = text
        elif chunk.type == "hitl_interrupt_metadata":
            self.asked = _first_action_request(chunk)
        elif chunk.type == "hitl_question_token" and text is not None:
            self.question_tokens.append(text)
        elif chunk.type == "hitl_interrupt_complete":
            self.question = _generated_question(chunk)
        elif chunk.type == "error":
            # The stream's OWN verdict. Dropping it is how every refusal — a
            # spend ceiling, a provider failure, a pending question on the
            # conversation — reached the ticket as « LIA answered nothing »:
            # measured 2026-09-10, an error chunk left the reader with no
            # token and no interrupt, and `plan_settle` reads that as
            # `workboard_empty_answer`. An invented diagnosis (ADR-182), on
            # the one line the person reads to know what happened.
            self.failure = StreamFailure(code=_error_code(chunk), message=text or "")
        elif chunk.type == "done":
            self.register = _register_of(chunk)
            self.nothing_new = _declares_nothing_new(chunk)

    @property
    def text(self) -> str:
        """The answer: the post-processed one when sent, else the deltas."""
        return self.replacement if self.replacement is not None else "".join(self.tokens)

    @property
    def interrupt(self) -> TurnInterrupt | None:
        """The question the turn stopped on, or None when it ran to its end."""
        if self.asked is None and self.question is None:
            return None
        return _interrupt_of(self.asked, self.question or "".join(self.question_tokens))


def _declares_nothing_new(chunk: Any) -> bool:
    """Whether the ``done`` chunk carries an explicit « nothing new » declaration.

    Args:
        chunk: The ``done`` chunk.

    Returns:
        True on the boolean ``True`` alone: doubt notifies.
    """
    metadata = getattr(chunk, "metadata", None)
    return isinstance(metadata, Mapping) and metadata.get(NOTHING_NEW_DONE_KEY) is True


def _register_of(chunk: Any) -> str | None:
    """The register the ``done`` chunk's expressivity annotation names, or None.

    Args:
        chunk: The ``done`` chunk.

    Returns:
        ``metadata.expressivity.register`` when it is a non-empty string.
    """
    metadata = getattr(chunk, "metadata", None)
    if not isinstance(metadata, Mapping):
        return None
    annotation = metadata.get("expressivity")
    if not isinstance(annotation, Mapping):
        return None
    register = annotation.get("register")
    return register if isinstance(register, str) and register else None


def _error_code(chunk: Any) -> str | None:
    """The stable code an error chunk carries, or None when it carries none.

    Args:
        chunk: The error chunk.

    Returns:
        Its ``error_code``, when the metadata is a mapping that has one.
    """
    metadata = getattr(chunk, "metadata", None)
    if not isinstance(metadata, Mapping):
        return None
    code = metadata.get("error_code")
    return code if isinstance(code, str) else None


def _first_action_request(chunk: Any) -> Mapping[str, Any]:
    """The action the interrupt asks about, as the metadata chunk carries it.

    Args:
        chunk: The ``hitl_interrupt_metadata`` chunk.

    Returns:
        The first action request; an empty mapping when the chunk names none,
        so the turn still settles as stopped rather than as finished.
    """
    metadata = getattr(chunk, "metadata", None) or {}
    requests = metadata.get("action_requests") if isinstance(metadata, Mapping) else None
    if isinstance(requests, list) and requests and isinstance(requests[0], Mapping):
        return requests[0]
    return {}


def _generated_question(chunk: Any) -> str:
    """The question the stream settled on, as the completion chunk carries it.

    Args:
        chunk: The ``hitl_interrupt_complete`` chunk.

    Returns:
        The generated question, or an empty string when the chunk has none.
    """
    metadata = getattr(chunk, "metadata", None) or {}
    generated = metadata.get("generated_question") if isinstance(metadata, Mapping) else None
    return generated if isinstance(generated, str) else ""


def _interrupt_of(action: Mapping[str, Any] | None, question: str) -> TurnInterrupt:
    """Reduce an interrupt to what a settle needs.

    Args:
        action: The first action request, when the stream named one.
        question: What LIA would have asked.

    Returns:
        The question, and the draft when the interrupt is a draft critique —
        the ONE kind a ticket can carry to the person (lot 7).
    """
    request = dict(action or {})
    kind = str(request.get("type") or "unknown")
    draft: dict[str, Any] | None = None
    if kind == HitlInteractionType.DRAFT_CRITIQUE.value:
        draft = {
            key: request.get(key)
            for key in ("draft_id", "draft_type", "draft_content", "tool_name")
        }
        # A FOR_EACH batch presents its first draft and confirms them ALL on
        # one answer: the ticket must show every one of them, and the replay's
        # identity must cover the whole list (lot 7).
        batch = request.get("batch_drafts")
        if isinstance(batch, list) and len(batch) > 1:
            draft["batch"] = [
                {key: item.get(key) for key in ("draft_id", "draft_type", "draft_content")}
                for item in batch
                if isinstance(item, Mapping)
            ]
    return TurnInterrupt(kind=kind, question=question.strip(), draft=draft)


def _settled(
    request: StreamRequest,
    outcome: RunOutcome,
    *,
    attempt: int,
    text: str = "",
    error: str | None = None,
    interrupt: TurnInterrupt | None = None,
    register: str | None = None,
    error_code: str | None = None,
    nothing_new: bool = False,
) -> RunResult:
    """Build the result, carrying whatever the gate refused along the way.

    Args:
        request: The instruction that ran.
        outcome: How it ended.
        attempt: How many attempts it took.
        text: The answer, when there is one.
        error: A typed message, on failure.
        interrupt: The question the turn stopped on, when it stopped on one.
        register: The register the answer was said in, when one was declared.
        error_code: Structured exception type or stream error code.
        nothing_new: Whether the answering model declared it had nothing new.

    Returns:
        The result the caller settles its row from.
    """
    return RunResult(
        outcome=outcome,
        text=text,
        attempts=attempt,
        error=error,
        refusals=list(request.origin.refusals) if request.origin is not None else [],
        interrupt=interrupt,
        register=register,
        error_code=error_code,
        nothing_new=nothing_new,
        admission=request.admission,
    )


def _failure_message(
    error: Exception | None, request: StreamRequest, *, attempts: int | None = None
) -> str:
    """Say what went wrong, naming the bound when a timeout is what did.

    Args:
        error: The last transient failure, when there was one.
        request: The instruction, for its timeout value.
        attempts: How many attempts actually ran — fewer than the bound when a
            retry was refused; the bound when omitted.

    Returns:
        A typed, bounded message — never a traceback.
    """
    if isinstance(error, TimeoutError):
        made = attempts if attempts is not None else request.max_attempts
        return (
            f"Execution timed out after {request.timeout_seconds}s "
            f"({made} attempt{'s' if made > 1 else ''})"
        )
    if error is not None:
        return f"{type(error).__name__}: {error}"
    return "Execution produced no result"
