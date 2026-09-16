"""The relay: what the person said on the phone becomes their chat turn (lot 4).

After an owner call, the relay synthesis produced the message the person
would have typed. This module hands it to the chat exactly as a typed message
is handed — through the out-of-turn engine in its *spoken by the person* mode:
not automated (the six extractions run), no plan pre-approved, the person's
own execution mode and preference flags, and archived VISIBLE with a
``phone_call`` stamp on every row of the turn.

Every way the relay can NOT run is a named outcome with a sentence in six
languages, and every outcome is counted. Nothing here decides how the row is
settled — ``telephony/owner_call.process_owner_call`` does, on the outbox the
return synthesis armed as ``RELAYING`` — so a crash anywhere in between leaves
a row the stale-relay sweep can still deliver. It lives here, beside the
workboard runner, because it drives the chat engine and reads the run origin:
``telephony`` must not import ``agents`` (the T2 cycle).

Two decisions before any model spends a token: the account holder must have
been the one on the line (``owner_confirmed``), and there must be something
to relay (an empty message is a greeting or a wrong number, never a turn).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import Any, Final
from uuid import UUID

import structlog

from src.core.config import settings
from src.core.i18n_telephony import get_return_phrases
from src.domains.agents.api.run_origin import RunOrigin
from src.domains.telephony.models import PhoneCall, PhoneCallStatus
from src.domains.telephony.repository import TelephonyRepository
from src.domains.telephony.schemas import SelfCallRelay
from src.domains.telephony.spend import phone_call_run_id
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.observability.metrics_telephony import telephony_relay_total
from src.infrastructure.proactive.notification import NotificationDispatcher
from src.infrastructure.scheduler.out_of_turn_run import (
    RunOutcome,
    StreamRequest,
    conversation_has_pending_hitl,
    resolve_run_context,
    stream_instruction,
)
from src.infrastructure.streaming.run_stream_broker import ActiveRunLockLost, active_run_lease

logger = structlog.get_logger(__name__)

#: The origin kind, also the metadata key every row of the turn carries.
RUN_ORIGIN_KIND: Final = "phone_call"
_SESSION_PREFIX: Final = "phone_call_"
_TASK_TYPE: Final = "phone_call"
_RELAY_ATTEMPTS: Final = 1  # a relay is never retried: the words were said once


class RelayOutcome(str, Enum):
    """How the relay ended — two ways it ran, eight ways it did not.

    ``UNANSWERED`` (nobody picked up, or a voicemail) and ``CALL_FAILED`` (the
    line itself failed) are told apart from ``NOT_OWNER`` (someone answered
    and was not the person): production 2026-09-16, a call that died at
    pickup was reported as « someone else answered », which the person had
    every reason to read as a stranger on their own line.
    """

    ANSWERED = "answered"
    WAITING = "waiting"
    EMPTY = "empty"
    NOT_OWNER = "not_owner"
    UNANSWERED = "unanswered"
    CALL_FAILED = "call_failed"
    PENDING_QUESTION = "pending_question"
    BUSY = "busy"
    QUOTA_BLOCKED = "quota_blocked"
    FAILED = "failed"


#: The sentence each fallback outcome puts in the notification, by locale key.
FALLBACK_PHRASE_KEYS: Final[dict[RelayOutcome, str]] = {
    RelayOutcome.EMPTY: "relay_empty",
    RelayOutcome.NOT_OWNER: "relay_not_owner",
    RelayOutcome.UNANSWERED: "relay_unanswered",
    RelayOutcome.CALL_FAILED: "relay_call_failed",
    RelayOutcome.PENDING_QUESTION: "relay_pending_question",
    RelayOutcome.BUSY: "relay_busy",
    RelayOutcome.QUOTA_BLOCKED: "relay_quota_blocked",
    RelayOutcome.FAILED: "relay_failed",
}

_RUN_TO_RELAY: Final[dict[RunOutcome, RelayOutcome]] = {
    RunOutcome.SUCCESS: RelayOutcome.ANSWERED,
    RunOutcome.WAITING: RelayOutcome.WAITING,
    RunOutcome.QUOTA_BLOCKED: RelayOutcome.QUOTA_BLOCKED,
    RunOutcome.FAILED: RelayOutcome.FAILED,
}


@dataclass(frozen=True)
class RelayRequest:
    """One relay to run.

    Attributes:
        call_id: The owner call, stamped on every row of the turn.
        user_id: Whose turn it is.
        relay: What the synthesis produced.
    """

    call_id: UUID
    user_id: UUID
    relay: SelfCallRelay


#: The push a relay that RAN sends, by outcome: the words are already in the
#: chat (the turn archived them), so this is a push and nothing else — for the
#: person who hung up and is not looking at the app.
_RAN_PHRASE_KEYS: Final[dict[RelayOutcome, str]] = {
    RelayOutcome.ANSWERED: "relay_answered",
    RelayOutcome.WAITING: "relay_drafts_waiting",
}


async def _push_relay_ran(
    user: Any, *, outcome: RelayOutcome, language: str, call_id: UUID, db: Any
) -> None:
    """A push, and only a push: the turn's rows are already in the chat."""
    phrases = get_return_phrases(language)
    try:
        await NotificationDispatcher(archive_enabled=False, sse_enabled=False).dispatch(
            user=user,
            content=phrases[_RAN_PHRASE_KEYS[outcome]],
            task_type=_TASK_TYPE,
            target_id=str(call_id),
            metadata={"relay": outcome.value},
            db=db,
            title=phrases["self_call_title"],
            push_enabled=True,
        )
    except Exception as exc:  # noqa: BLE001 — a push failure never undoes the turn
        logger.warning(
            "telephony_relay_push_failed", call_id=str(call_id), error_type=type(exc).__name__
        )


async def _drive(request: RelayRequest, context: Any, run_id: str) -> RelayOutcome:
    stream = StreamRequest(
        user_id=request.user_id,
        prompt=request.relay.relay_message.strip(),
        session_id=f"{_SESSION_PREFIX}{request.call_id}",
        language=context.language,
        timezone=context.timezone,
        display_name=context.display_name,
        display_mode=context.display_mode,
        timeout_seconds=settings.telephony_relay_timeout_seconds,
        max_attempts=_RELAY_ATTEMPTS,
        retry_delay_seconds=0,
        origin=RunOrigin(
            kind=RUN_ORIGIN_KIND, ticket_id=str(request.call_id), run_id=run_id, hidden=False
        ),
        run_id=run_id,
        execution_mode=context.execution_mode,
        spoken_by_person=True,
        memory_enabled=context.memory_enabled,
        journals_enabled=context.journals_enabled,
        psyche_enabled=context.psyche_enabled,
    )
    result = await stream_instruction(stream)
    return _RUN_TO_RELAY.get(result.outcome, RelayOutcome.FAILED)


async def _drive_under_lease(
    request: RelayRequest, context: Any, run_id: str, conversation_id: UUID
) -> RelayOutcome:
    """Take the conversation's lock, with bounded retries; BUSY when never taken."""
    redis = await get_redis_cache()
    for attempt in range(1, settings.telephony_relay_busy_retries + 1):
        try:
            async with active_run_lease(
                redis, str(conversation_id), run_id=run_id, stream_id=f"{RUN_ORIGIN_KIND}:{run_id}"
            ) as acquired:
                if acquired:
                    return await _drive(request, context, run_id)
        except ActiveRunLockLost:
            # The person started talking while the relay ran: their turn wins,
            # and the relay's words are still in the fallback notification.
            logger.info("telephony_relay_conversation_taken_over", call_id=str(request.call_id))
            return RelayOutcome.BUSY
        if attempt < settings.telephony_relay_busy_retries:
            await asyncio.sleep(settings.telephony_relay_busy_delay_seconds)
    return RelayOutcome.BUSY


async def run_relay(request: RelayRequest, *, db: Any) -> RelayOutcome:
    """Run the relayed turn, or name why it could not run.

    Args:
        request: The relay to run.
        db: The caller's session (the probes read on it).

    Returns:
        The outcome; ``ANSWERED`` and ``WAITING`` mean the turn ran, and both
        send a push saying so — the person on the phone may not be looking at
        the app.
    """
    if not request.relay.owner_confirmed:
        return _counted(RelayOutcome.NOT_OWNER)
    if not request.relay.relay_message.strip():
        return _counted(RelayOutcome.EMPTY)

    context = await resolve_run_context(db, request.user_id)
    if context is None:
        return _counted(RelayOutcome.FAILED)

    pending, conversation_id = await conversation_has_pending_hitl(
        db, request.user_id, context.language
    )
    if pending:
        return _counted(RelayOutcome.PENDING_QUESTION)

    # The SAME run id as the call's live lookups and its synthesis (lot 8): the
    # per-run summary the chat meter reads on the relayed answer is then the
    # whole call's bill.
    run_id = phone_call_run_id(request.call_id)
    if conversation_id is None:
        logger.warning("telephony_relay_unlocked_thread", call_id=str(request.call_id))
        outcome = await _drive(request, context, run_id)
    else:
        outcome = await _drive_under_lease(request, context, run_id, conversation_id)

    if outcome in _RAN_PHRASE_KEYS:
        await _push_relay_ran(
            context.user,
            outcome=outcome,
            language=context.language,
            call_id=request.call_id,
            db=db,
        )
    return _counted(outcome)


def _counted(outcome: RelayOutcome) -> RelayOutcome:
    telephony_relay_total.labels(outcome=outcome.value).inc()
    return outcome


def count_relay_outcome(outcome: RelayOutcome) -> RelayOutcome:
    """Count an outcome decided OUTSIDE the runner (a call nobody answered)."""
    return _counted(outcome)


def fallback_text(relay: SelfCallRelay, outcome: RelayOutcome, language: str) -> str:
    """The notification a relay that did not run leaves: the reason, then the recap."""
    phrases = get_return_phrases(language)
    reason = phrases[FALLBACK_PHRASE_KEYS[outcome]]
    summary = relay.summary.strip()
    return f"{reason}\n\n{summary}" if summary else reason


async def settle_owner_call(
    *,
    repo: TelephonyRepository,
    call: PhoneCall,
    user: Any,
    relay: SelfCallRelay,
    outcome: RelayOutcome,
    language: str,
    db: Any,
) -> None:
    """Settle the ``RELAYING`` outbox row from what the relay did.

    A turn that ran delivers the return (the chat holds it). Anything else
    hands the row to the notification path with the reason as its content:
    dispatched now, and left ``PENDING`` for the reaper if the dispatch fails.
    """
    if outcome in (RelayOutcome.ANSWERED, RelayOutcome.WAITING):
        await repo.mark_relay_delivered(call.id, outcome=outcome.value)
        logger.info("telephony_relay_delivered", call_id=str(call.id), outcome=outcome.value)
        return

    content = fallback_text(relay, outcome, language)
    if not await repo.mark_relay_fallback(call.id, content=content, outcome=outcome.value):
        return  # settled meanwhile (a stale-relay sweep, a race): nothing to add
    phrases = get_return_phrases(language)
    try:
        await NotificationDispatcher().dispatch(
            user=user,
            content=content,
            task_type=_TASK_TYPE,
            target_id=str(call.id),
            metadata={"call_status": PhoneCallStatus(call.status).value, "relay": outcome.value},
            db=db,
            title=phrases["self_call_title"],
        )
    except Exception as exc:  # noqa: BLE001 — PENDING stays for the reaper (T1)
        logger.warning(
            "telephony_relay_fallback_dispatch_failed",
            call_id=str(call.id),
            error_type=type(exc).__name__,
        )
        return
    await repo.mark_notification_delivered(call.id)
    logger.info("telephony_relay_fallback_delivered", call_id=str(call.id), outcome=outcome.value)


__all__ = [
    "FALLBACK_PHRASE_KEYS",
    "RUN_ORIGIN_KIND",
    "RelayOutcome",
    "RelayRequest",
    "count_relay_outcome",
    "fallback_text",
    "run_relay",
    "settle_owner_call",
]
