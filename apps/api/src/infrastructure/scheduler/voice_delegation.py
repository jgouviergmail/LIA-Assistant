"""The server-side delegation bridge: a voice's request becomes a chat turn (ADR-301).

The browser's live mode delegates from the page (``lib/live/delegation.ts``):
the voice model calls the ONE function, the page posts an ordinary chat turn
stamped with the session, reads the answer off the thread and hands it back,
flattened and bounded. A phone call has no page: the vendor calls this API
with the request, and this module is that same bridge, server-side, with the
same rules — which a test corpus and these tests pin to each other:

- **an empty request costs nothing** — the voice is told to ask again;
- **the newest request wins**: a request that arrives while one runs cancels
  the running turn (the person corrected or completed themselves), its
  caller is told « superseded », and the new one takes the conversation.
  The marker lives in Redis because the vendor's two webhooks may land on two
  workers (``WEB_CONCURRENCY``); the running bridge polls it;
- **a question LIA asked IS the result**: the voice asks the person, and the
  next request — their answer — RESUMES the run that asked, exactly as the
  chat router resumes it (``original_run_id``, the id reused for the
  accounting of question and answer);
- **the turn is the PERSON's own** (``spoken_by_person``): their execution
  mode, their preference flags, the extractions, no plan pre-approved, no
  out-of-turn origin — an ordinary chat turn, as the browser's is;
- **a wait past the vendor's bound leaves the turn RUNNING**: the answer lands
  in the thread and the voice says so; the run stays supervised, so the next
  request still cancels it;
- **nothing reaches the voice as an exception**: a ceiling, a failure and a
  busy conversation each have a line (technical English, ADR-256 — the model
  speaks the person's language).

The lease is the chat's own (``active_run_lease``): a person typing in the
chat while they speak on the phone is two runs on one thread, and the second
must wait or step aside.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass
from enum import Enum
from typing import Final

import structlog
from redis.asyncio import Redis

from src.core.config import settings
from src.core.constants import (
    REDIS_KEY_VOICE_DELEGATION_NEWEST_PREFIX,
    VOICE_DELEGATION_SUPERSEDE_POLL_SECONDS,
)
from src.core.field_names import FIELD_RUN_ID
from src.domains.agents.api.hitl_pending import check_pending_hitl_uncached
from src.domains.agents.display.plain_text import strip_html_if_markup
from src.domains.voice_sessions.mandate import bridge_lines, tone_lines
from src.domains.voice_sessions.projection import bound_to_tokens, flatten_for_voice
from src.domains.voice_sessions.session import VoiceSession
from src.infrastructure.async_utils import safe_fire_and_forget
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.scheduler.out_of_turn_run import (
    RunContext,
    RunOutcome,
    RunResult,
    StreamRequest,
    stream_instruction,
)
from src.infrastructure.streaming.run_stream_broker import ActiveRunLockLost, active_run_lease

logger = structlog.get_logger(__name__)

#: How often a running bridge reads the newest-request marker (a test lowers it).
SUPERSEDE_POLL_SECONDS: float = VOICE_DELEGATION_SUPERSEDE_POLL_SECONDS
#: A delegation is never retried: the person is on the line and would hear it twice.
_ATTEMPTS: Final = 1


class DelegationOutcome(str, Enum):
    """How a delegation ended — two ways the voice has an answer, six it has a line."""

    ANSWERED = "answered"
    QUESTION = "question"
    EMPTY = "empty"
    SUPERSEDED = "superseded"
    TIMED_OUT = "timed_out"
    BUSY = "busy"
    QUOTA_BLOCKED = "quota_blocked"
    FAILED = "failed"


#: The line each outcome without an answer hands the voice.
_LINE_OF: Final[dict[DelegationOutcome, str]] = {
    DelegationOutcome.EMPTY: "empty_request",
    DelegationOutcome.SUPERSEDED: "superseded",
    DelegationOutcome.TIMED_OUT: "timed_out",
    DelegationOutcome.BUSY: "busy",
    DelegationOutcome.QUOTA_BLOCKED: "quota_blocked",
    DelegationOutcome.FAILED: "failed",
}


@dataclass(frozen=True, slots=True)
class DelegationRequest:
    """One request handed to LIA.

    Attributes:
        session: The voice session — its key stamps the rows, its
            conversation holds the pending question.
        request_id: The caller's own id of this request (the vendor's tool
            call id): what the newest-wins marker holds.
        request: The person's request, in their own words.
        spoken_text: What was actually said, when the carrier has it.
        wait_seconds: How long the caller can wait for the answer (the
            vendor's bound, minus a margin) before it must be told the turn
            goes on in the chat.
    """

    session: VoiceSession
    request_id: str
    request: str
    spoken_text: str | None
    wait_seconds: float


@dataclass(frozen=True, slots=True)
class DelegationResult:
    """What the voice is handed.

    Attributes:
        outcome: How the delegation ended.
        text: The answer (flattened, bounded), the question LIA asked, or the
            line naming why there is neither.
        note: The delivery note of the register the answer was said in
            (ADR-253), or None.
    """

    outcome: DelegationOutcome
    text: str
    note: str | None = None


def newest_request_key(session_key: str) -> str:
    """The Redis key holding the id of a session's newest request."""
    return f"{REDIS_KEY_VOICE_DELEGATION_NEWEST_PREFIX}{session_key}"


def _line(outcome: DelegationOutcome) -> DelegationResult:
    return DelegationResult(outcome=outcome, text=bridge_lines()[_LINE_OF[outcome]])


async def _resumption(conversation_id: str) -> str | None:
    """The run a pending question was asked on, or None — never raising.

    The probe is the chat's own authority (the Redis record the chat routes
    on, ADR-276 lot 7); a probe that fails runs the request as a fresh turn.
    """
    try:
        pending = await check_pending_hitl_uncached(conversation_id)
    except Exception as exc:  # noqa: BLE001 — a blind probe never blocks the person's request
        logger.warning("voice_delegation_hitl_probe_failed", error_type=type(exc).__name__)
        return None
    if not pending:
        return None
    run_id = pending.get(FIELD_RUN_ID)
    return run_id if isinstance(run_id, str) and run_id else None


def _stream_request(
    request: DelegationRequest, context: RunContext, resume: str | None
) -> StreamRequest:
    session = request.session
    return StreamRequest(
        user_id=session.user_id,
        prompt=request.request.strip(),
        session_id=f"{session.origin_kind}_{session.origin_id}",
        language=context.language,
        timezone=context.timezone,
        display_name=context.display_name,
        display_mode=context.display_mode,
        timeout_seconds=settings.voice_delegation_run_timeout_seconds,
        max_attempts=_ATTEMPTS,
        retry_delay_seconds=0,
        # No out-of-turn origin: the person is on the line, this is their chat
        # turn — the gate ASKS, the rows are visible, the graph mints the id.
        origin=None,
        run_id=resume,
        execution_mode=context.execution_mode,
        spoken_by_person=True,
        memory_enabled=context.memory_enabled,
        journals_enabled=context.journals_enabled,
        psyche_enabled=context.psyche_enabled,
        original_run_id=resume,
        live_session_id=session.key,
        spoken_text=request.spoken_text,
    )


class _Stepped(str, Enum):
    """Why a supervised run produced no result."""

    SUPERSEDED = "superseded"
    BUSY = "busy"


async def _run_supervised(
    request: DelegationRequest, stream: StreamRequest
) -> RunResult | _Stepped:
    """Run the turn under the conversation's lease, watching the newest marker.

    Returns:
        The result, or why there is none: a newer request cancelled this one
        (or the person's own typed turn took the thread), or the lease could
        not be taken within the bound.
    """
    session = request.session
    redis = await get_redis_cache()
    key = newest_request_key(session.key)
    loop = asyncio.get_running_loop()
    deadline = loop.time() + settings.voice_delegation_lease_wait_seconds
    while True:
        # Read BEFORE taking the lease: a request replaced while it waited
        # (two vendor webhooks on two workers) must not start a turn it would
        # cancel at its first poll — a router call paid for nothing.
        if await _superseded(redis, key, request.request_id):
            logger.info("voice_delegation_superseded_before_lease", origin=session.origin_id)
            return _Stepped.SUPERSEDED
        try:
            async with active_run_lease(
                redis,
                str(session.conversation_id),
                run_id=stream.run_id or f"{session.run_id}:{request.request_id}",
                stream_id=f"{session.origin_kind}:{request.request_id}",
            ) as acquired:
                if acquired:
                    return await _run_until_superseded(redis, key, request.request_id, stream)
        except ActiveRunLockLost:
            # The person's own typed turn took the thread: it wins.
            logger.info("voice_delegation_taken_over", origin=session.origin_id)
            return _Stepped.SUPERSEDED
        if loop.time() >= deadline:
            logger.info("voice_delegation_busy", origin=session.origin_id)
            return _Stepped.BUSY
        await asyncio.sleep(SUPERSEDE_POLL_SECONDS)


async def _superseded(redis: Redis, key: str, request_id: str) -> bool:
    """Whether a newer request of the session took the marker."""
    newest = await redis.get(key)
    return newest is not None and _text(newest) != request_id


async def _run_until_superseded(
    redis: Redis, key: str, request_id: str, stream: StreamRequest
) -> RunResult | _Stepped:
    # The lease may have been waited for: a marker moved meanwhile means the
    # turn is not wanted — nothing is started.
    if await _superseded(redis, key, request_id):
        return _Stepped.SUPERSEDED
    run = asyncio.create_task(stream_instruction(stream))
    try:
        while True:
            done, _ = await asyncio.wait({run}, timeout=SUPERSEDE_POLL_SECONDS)
            if done:
                return run.result()
            if await _superseded(redis, key, request_id):
                run.cancel()
                with suppress(asyncio.CancelledError):
                    await run
                return _Stepped.SUPERSEDED
    except asyncio.CancelledError:
        run.cancel()
        with suppress(asyncio.CancelledError):
            await run
        raise


def _text(value: object) -> str:
    return value.decode() if isinstance(value, bytes) else str(value)


def _flatten(content: str) -> str:
    """The projection with the display layer's own HTML door handed in."""
    return flatten_for_voice(content, strip_html=strip_html_if_markup)


def _shape(result: RunResult) -> DelegationResult:
    """What the voice is handed once the turn ended."""
    if result.outcome is RunOutcome.QUOTA_BLOCKED:
        return _line(DelegationOutcome.QUOTA_BLOCKED)
    if result.outcome is RunOutcome.FAILED:
        return _line(DelegationOutcome.FAILED)
    note = tone_lines().get(result.register) if result.register else None
    budget = settings.live_delegation_result_max_tokens
    cut = bridge_lines()["result_cut"]
    if result.interrupt is not None:
        question = bound_to_tokens(_flatten(result.interrupt.question), budget, cut)
        return DelegationResult(outcome=DelegationOutcome.QUESTION, text=question, note=note)
    answer = bound_to_tokens(_flatten(result.text), budget, cut)
    return DelegationResult(outcome=DelegationOutcome.ANSWERED, text=answer, note=note)


async def delegate(request: DelegationRequest, *, context: RunContext) -> DelegationResult:
    """Hand one request to LIA and wait for what the voice can say.

    Args:
        request: The request and how long its caller can wait.
        context: The account's run context (resolved by the caller).

    Returns:
        The answer, the question, or the line — never an exception.
    """
    session = request.session
    if not request.request.strip():
        return _line(DelegationOutcome.EMPTY)

    redis = await get_redis_cache()
    # The newest request wins: whoever runs reads this marker and steps aside.
    await redis.set(
        newest_request_key(session.key),
        request.request_id,
        ex=settings.voice_delegation_run_timeout_seconds,
    )
    resume = await _resumption(str(session.conversation_id))
    stream = _stream_request(request, context, resume)
    supervised = safe_fire_and_forget(
        _run_supervised(request, stream),
        name=f"voice_delegation_{session.key}_{request.request_id}",
    )
    try:
        verdict = await asyncio.wait_for(asyncio.shield(supervised), timeout=request.wait_seconds)
    except TimeoutError:
        # The turn goes on in the thread — still supervised, so the next
        # request cancels it; the voice says the answer will be in the chat.
        logger.info("voice_delegation_timed_out", origin=session.origin_id)
        return _line(DelegationOutcome.TIMED_OUT)
    except Exception as exc:  # noqa: BLE001 — never an exception to the voice
        logger.error(
            "voice_delegation_failed", origin=session.origin_id, error_type=type(exc).__name__
        )
        return _line(DelegationOutcome.FAILED)
    if verdict is _Stepped.SUPERSEDED:
        return _line(DelegationOutcome.SUPERSEDED)
    if verdict is _Stepped.BUSY:
        return _line(DelegationOutcome.BUSY)
    return _shape(verdict)


__all__ = [
    "DelegationOutcome",
    "DelegationRequest",
    "DelegationResult",
    "delegate",
    "newest_request_key",
]
