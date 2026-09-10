"""One engine for « LIA runs an instruction out of turn » (ADR-276).

Three pieces were identical in the routine executor and would have been
identical again in the workboard runner. They are extracted here so there is
ONE implementation of each, and so the workboard inherits by construction what
the routine path learned the hard way:

- :func:`resolve_run_context` — who the run belongs to, and the preferences it
  will answer in. Refuses an inactive account (a deleted one is inactive too).
- :func:`conversation_has_pending_hitl` — whether the person's thread already
  holds a question nobody answered. It FAILS OPEN: the guard exists to avoid
  stepping on a pending question, and failing to ASK must not become a reason
  to do nothing at all.
- :func:`stream_instruction` — driving ``stream_chat_response`` with a timeout
  and a retry policy.

What this module deliberately does NOT own: the condition gate, propose-first,
the run history, the rescheduling and the notification — those are the
routine's, and the workboard has its own equivalents. It also opens no database
session of its own on the streaming path: the caller owns the transaction it
was already in.

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
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import UUID

import structlog

from src.core.config import settings
from src.core.constants import (
    DEFAULT_USER_DISPLAY_TIMEZONE,
    INSTANCE_BUDGET_EXHAUSTED_ERROR_CODE,
    USAGE_LIMIT_EXCEEDED_ERROR_CODE,
)
from src.core.user_display import resolve_user_display_name
from src.domains.agents.api.run_origin import RunOrigin, out_of_turn_origin_ctx
from src.domains.agents.services.hitl.protocols import HitlInteractionType

logger = structlog.get_logger(__name__)

#: Failures worth another attempt: the world blinked, the request did not.
_TRANSIENT_ERRORS = (TimeoutError, ConnectionError, OSError)


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
        display_mode: ``cards`` | ``html`` | ``markdown``.
    """

    user: Any
    language: str
    timezone: str
    display_name: str
    display_mode: str


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
        display_mode: ``cards`` | ``html`` | ``markdown``.
        timeout_seconds: Hard bound of ONE attempt.
        max_attempts: Attempts including the first.
        retry_delay_seconds: Pause between two attempts.
        origin: Published to the turn when the run is a workboard ticket, so
            the archive enrichers and the effect gate can read it.
        run_id: The id the turn must file everything under (ADR-117's detached
            producer path). A caller that has a row to settle supplies it, so
            the three registers, the token logs and the ticket all name the
            SAME run; None lets the graph mint its own, which is what the
            routine path has always done.
        execution_mode: ``pipeline`` or ``react`` — the CALLER's decision, never
            the person's chat preference. Nothing here reads
            ``user.execution_mode``: a routine keeps the deterministic pipeline
            it has always run on, a ticket asks for the autonomous loop, and
            the chat header's toggle keeps meaning the chat alone.
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
    """

    outcome: RunOutcome
    text: str = ""
    attempts: int = 0
    error: str | None = None
    refusals: list[tuple[str, str]] = field(default_factory=list)
    interrupt: TurnInterrupt | None = None


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
        language=user.language or settings.default_language,
        timezone=user.timezone or DEFAULT_USER_DISPLAY_TIMEZONE,
        display_name=resolve_user_display_name(user.full_name, user.email),
        display_mode=getattr(user, "response_display_mode", None) or "cards",
    )


async def conversation_has_pending_hitl(
    db: Any, user_id: UUID, language: str
) -> tuple[bool, UUID | None]:
    """Whether the person's thread already holds an unanswered question.

    Reads the SAME authority the chat reads — the pending-HITL record in Redis
    — and not the graph's checkpoint. The chat routes the person's next message
    as the answer to a question on the strength of that record alone, and a
    run that stopped on a question moves it to the ticket and deletes the
    record (ADR-276, lot 7); the checkpoint behind it still says « interrupted »
    until the next input starts a fresh run, exactly as it does after a chat
    turn. Reading the checkpoint made every later ticket of the account step
    aside for a question nobody could see any more.

    Fails OPEN: this guard exists to avoid stepping on a pending question, and
    failing to ASK must not become a reason to do nothing at all.

    Args:
        db: The caller's session.
        user_id: Whose thread.
        language: Used only when the conversation must be created.

    Returns:
        ``(pending, conversation_id)``; the id is None when the probe failed.
    """
    from src.domains.agents.api.hitl_pending import check_pending_hitl_uncached
    from src.domains.conversations.service import ConversationService

    try:
        conversation = await ConversationService().get_or_create_conversation(
            user_id, db, language=language
        )
        pending = await check_pending_hitl_uncached(str(conversation.id)) is not None
        return pending, conversation.id
    except Exception as probe_error:  # noqa: BLE001 — a blind probe never blocks
        logger.warning(
            "out_of_turn_run_hitl_probe_failed",
            user_id=str(user_id),
            error=str(probe_error),
        )
        return False, None


async def stream_instruction(request: StreamRequest) -> RunResult:
    """Run one instruction through the pipeline, with a timeout and retries.

    Args:
        request: What to run, and the bounds it runs under.

    Returns:
        The answer and how the turn ended. Never raises: an out-of-turn caller
        has a row to settle whatever happened.
    """
    token = out_of_turn_origin_ctx.set(request.origin) if request.origin is not None else None
    try:
        return await _attempt_until_settled(request)
    finally:
        if token is not None:
            out_of_turn_origin_ctx.reset(token)


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
            text, interrupt, failure = await asyncio.wait_for(
                _one_attempt(request, attempt), timeout=request.timeout_seconds
            )
        except _TRANSIENT_ERRORS as transient:
            last_error = transient
            logger.warning(
                "out_of_turn_run_transient_error",
                session_id=request.session_id,
                attempt=attempt,
                error_type=type(transient).__name__,
            )
            if attempt < request.max_attempts and request.retry_delay_seconds:
                await asyncio.sleep(request.retry_delay_seconds)
            continue
        except Exception as fatal:  # noqa: BLE001 — settled as a failure, never raised
            logger.error(
                "out_of_turn_run_failed",
                session_id=request.session_id,
                attempt=attempt,
                error=f"{type(fatal).__name__}: {fatal}",
            )
            return _settled(
                request,
                RunOutcome.FAILED,
                attempt=attempt,
                error=f"{type(fatal).__name__}: {fatal}",
            )

        if interrupt is not None:
            # Nobody answered the question; asking it again is not a retry.
            return _settled(
                request, RunOutcome.WAITING, attempt=attempt, text=text, interrupt=interrupt
            )
        if failure is not None:
            # NOT retried: a ceiling that refused this call refuses the next
            # one too, and a stream that named its own failure has already
            # decided. Retrying would spend the caller's attempts on a verdict
            # that will not change.
            return _settled(
                request,
                RunOutcome.QUOTA_BLOCKED if failure.is_quota else RunOutcome.FAILED,
                attempt=attempt,
                text=text,
                error=failure.message or failure.code or "the run was refused",
            )
        # A refusal collected by the gate means the turn met something only the
        # person can allow — the answer is real, but the work is not finished.
        outcome = (
            RunOutcome.WAITING
            if request.origin is not None and request.origin.refusals
            else RunOutcome.SUCCESS
        )
        return _settled(request, outcome, attempt=attempt, text=text)

    return _settled(
        request,
        RunOutcome.FAILED,
        attempt=attempt,
        error=_failure_message(last_error, request),
    )


async def _one_attempt(
    request: StreamRequest, attempt: int
) -> tuple[str, TurnInterrupt | None, StreamFailure | None]:
    """Consume one full generation.

    The generator is consumed to its end even when it announces a question:
    its tail commits the turn's token accounting, and breaking out of it would
    close the generator before that runs.

    Args:
        request: The instruction and its bounds.
        attempt: 1-based attempt number.

    Returns:
        ``(text, interrupt, failure)`` — the post-processed answer, the
        question the turn stopped on, and the refusal the stream announced;
        each None when the turn had none.
    """
    # A fresh session per retry: attempt one may have half-run the graph, and
    # attempt two must start clean rather than resume a broken checkpoint.
    session_id = request.session_id if attempt == 1 else f"{request.session_id}_retry_{attempt}"
    from src.domains.agents.api.service import AgentService

    reader = _StreamReader()
    async for chunk in AgentService().stream_chat_response(
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
        is_automated_source=True,
        auto_approve_plan=True,
        # Archive-first persisted the question on attempt one; a retry must not
        # duplicate the row.
        archive_user_message=(attempt == 1),
        # The SAME id across attempts on purpose: the ticket paid for every one
        # of them, so the cost aggregate must find them all under one run.
        run_id=request.run_id,
    ):
        reader.feed(chunk)
    return reader.text, reader.interrupt, reader.failure


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
    """

    tokens: list[str] = field(default_factory=list)
    replacement: str | None = None
    asked: Mapping[str, Any] | None = None
    question_tokens: list[str] = field(default_factory=list)
    question: str | None = None
    failure: StreamFailure | None = None

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
) -> RunResult:
    """Build the result, carrying whatever the gate refused along the way.

    Args:
        request: The instruction that ran.
        outcome: How it ended.
        attempt: How many attempts it took.
        text: The answer, when there is one.
        error: A typed message, on failure.
        interrupt: The question the turn stopped on, when it stopped on one.

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
    )


def _failure_message(error: Exception | None, request: StreamRequest) -> str:
    """Say what went wrong, naming the bound when a timeout is what did.

    Args:
        error: The last transient failure, when there was one.
        request: The instruction, for its timeout value.

    Returns:
        A typed, bounded message — never a traceback.
    """
    if isinstance(error, TimeoutError):
        return (
            f"Execution timed out after {request.timeout_seconds}s "
            f"({request.max_attempts} attempts)"
        )
    if error is not None:
        return f"{type(error).__name__}: {error}"
    return "Execution produced no result"
