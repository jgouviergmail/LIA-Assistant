"""The relay of an owner call: its outbox, its pushes, its settle (ADR-290 lot 4).

After an owner call under the DIRECT mandate, the relay synthesis produced
the message the person would have typed. The TURN itself — a spoken turn,
not automated, the person's own execution mode, archived VISIBLE under the
call's run id — is the shared voice relay's (``voice_relay.run_voice_relay``,
ADR-301: a browser session in direct mode runs the very same turn). What
stays here is the phone's: the ``RELAYING`` outbox row, the push that says
the chat holds the answer (the person hung up and is not looking at the
app), the fallback notification when nothing ran, and the settle.

Every way the relay can NOT run is a named outcome with a sentence in six
languages, and every outcome is counted. Nothing here decides how the row is
settled but :func:`settle_owner_call`, on the outbox the return synthesis
armed as ``RELAYING`` — so a crash anywhere in between leaves a row the
stale-relay sweep can still deliver. It lives here, beside the workboard
runner, because it drives the chat engine and reads the run origin:
``telephony`` must not import ``agents`` (the T2 cycle).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.i18n_telephony import get_return_phrases
from src.domains.conversations.service import ConversationService
from src.domains.telephony.models import PhoneCall, PhoneCallStatus
from src.domains.telephony.repository import TelephonyRepository
from src.domains.telephony.schemas import SelfCallRelay
from src.domains.users.models import User
from src.domains.voice_sessions.session import VoiceSession
from src.infrastructure.database.session import get_db_context
from src.infrastructure.observability.metrics_telephony import telephony_relay_total
from src.infrastructure.proactive.notification import NotificationDispatcher
from src.infrastructure.scheduler.out_of_turn_run import resolve_run_context
from src.infrastructure.scheduler.voice_relay import (
    RelayOutcome,
    VoiceRelayRequest,
    run_voice_relay,
)

logger = structlog.get_logger(__name__)

#: The task type of the phone's pushes (the origin kind and the session key
#: prefix are the voice session's own — ``VoiceSession.phone``).
_TASK_TYPE: Final = "phone_call"


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
    user: User, *, outcome: RelayOutcome, language: str, call_id: UUID, db: AsyncSession
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


async def run_relay(request: RelayRequest) -> RelayOutcome:
    """Run the relayed turn through the shared relay, count it, push when it ran.

    The account and its conversation are resolved on a session of this
    function's, closed before the turn; the push after it opens another.
    Nothing of the webhook's session is touched in between, so no connection
    sits idle in a transaction while the model answers (the workboard
    runner's rule, ADR-301 review 2026-09-20).

    Args:
        request: The relay to run.

    Returns:
        The outcome; ``ANSWERED`` and ``WAITING`` mean the turn ran, and both
        send a push saying so — the person on the phone may not be looking at
        the app.
    """
    async with get_db_context() as db:
        context = await resolve_run_context(db, request.user_id)
        if context is None:
            return _counted(RelayOutcome.FAILED)
        conversation = await ConversationService().get_or_create_conversation(
            request.user_id, db, language=context.language
        )
        conversation_id = conversation.id
    session = VoiceSession.phone(
        call_id=request.call_id,
        mode="direct",
        user_id=request.user_id,
        conversation_id=conversation_id,
        language=context.language,
        timezone=context.timezone,
    )
    outcome = await run_voice_relay(
        VoiceRelayRequest(session=session, relay=request.relay), context=context
    )
    if outcome in _RAN_PHRASE_KEYS:
        async with get_db_context() as db:
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
    user: User,
    relay: SelfCallRelay,
    outcome: RelayOutcome,
    language: str,
    db: AsyncSession,
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
    "RelayOutcome",
    "RelayRequest",
    "count_relay_outcome",
    "fallback_text",
    "run_relay",
    "settle_owner_call",
]
