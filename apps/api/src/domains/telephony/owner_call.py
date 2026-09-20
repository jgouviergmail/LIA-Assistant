"""The return path of an owner call: synthesize, claim, relay, settle (lot 4).

The third-party path synthesizes a debrief and NOTIFIES. The owner path
synthesizes the message the person would have typed and RELAYS it as their
own chat turn, and the row is claimed ``RELAYING`` before the turn runs so a
crash anywhere after the claim still leaves a return the stale-relay sweep
can deliver.

Order, and why:

1. a call nobody answered (no answer, voicemail, failed) has NO mode: no
   model is spent on it, and the person is told « nobody answered » or « the
   call failed » whatever they chose — never « someone else answered »,
   which is what a person reads when they picked up and the line died
   (production 2026-09-16). Decided BEFORE the mode (review 2026-09-20: a
   Live call closed with nothing to deliver, so a line that never picked
   up left the person, or the routine that planned the call, uninformed);
2. a LIVE call (ADR-301) delegated every request while the person was on the
   line: nothing is synthesised nor relayed — the voice-only exchanges are
   archived and the closing card drawn, the browser's own closing;
3. a DIRECT call synthesises BEFORE the claim, like its sibling: a duplicated
   webhook may synthesize twice, only one claim wins;
4. the claim arms the FALLBACK notification (the reason « failed » plus the
   recap): it is what the sweep sends when nothing settles the row;
5. the live tools (or the delegation tool) come off the agent (lot 7,
   best-effort — the dial path detaches again before the next stranger's
   call if this fails);
6. the relay runs, then :func:`phone_relay_runner.settle_owner_call` decides
   (the runner lives beside the workboard's, in ``infrastructure/scheduler``:
   it drives the chat engine, and ``telephony`` must not import ``agents``).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import structlog

from src.core.i18n_telephony import get_return_phrases
from src.domains.conversations.service import ConversationService
from src.domains.telephony.live_tools import detach_live_tools
from src.domains.telephony.models import (
    NotificationStatus,
    PhoneCall,
    PhoneCallOutcome,
    PhoneCallStatus,
)
from src.domains.telephony.payload import extract_transcript_summary
from src.domains.telephony.repository import TelephonyRepository
from src.domains.telephony.schemas import SelfCallRelay
from src.domains.telephony.synthesis_usage import SynthUsage, track_synthesis_usage
from src.domains.voice_sessions.session import VoiceCarrier, VoiceSession
from src.infrastructure.observability.metrics_telephony import (
    telephony_call_duration_seconds,
    telephony_calls_total,
)
from src.infrastructure.scheduler.phone_relay_runner import (
    RelayOutcome,
    RelayRequest,
    count_relay_outcome,
    fallback_text,
    run_relay,
    settle_owner_call,
)
from src.infrastructure.scheduler.voice_relay import (
    collected_of_payload,
    synthesize_relay,
    transcript_of_payload,
    vendor_summary_of_payload,
)
from src.infrastructure.scheduler.voice_session_closing import close_voice_session

logger = structlog.get_logger(__name__)

_UNANSWERED = (PhoneCallStatus.NO_ANSWER, PhoneCallStatus.VOICEMAIL, PhoneCallStatus.FAILED)
#: What the person is told when nobody spoke: the line failed, or nobody
#: picked up — two different things to read.
_SILENT_OUTCOMES = {
    PhoneCallStatus.NO_ANSWER: RelayOutcome.UNANSWERED,
    PhoneCallStatus.VOICEMAIL: RelayOutcome.UNANSWERED,
    PhoneCallStatus.FAILED: RelayOutcome.CALL_FAILED,
}


async def _synthesize(
    *,
    call: PhoneCall,
    payload: dict[str, Any],
    language: str,
    user_timezone: str,
) -> tuple[SelfCallRelay, SynthUsage | None, bool]:
    """The relay, or a wordless one when the model could not be reached.

    Returns:
        ``(relay, usage, synthesized)`` — ``synthesized`` False means the
        fallback relay (vendor summary, nothing to relay) is in hand.
    """
    try:
        relay, usage = await synthesize_relay(
            carrier=VoiceCarrier.PHONE,
            transcript=transcript_of_payload(payload),
            collected=collected_of_payload(payload),
            vendor_summary=vendor_summary_of_payload(payload),
            objective=call.objective,
            user_language=language,
            user_timezone=user_timezone,
            user_id=call.user_id,
        )
        return relay, usage, True
    except Exception as exc:  # noqa: BLE001 — synthesis must not lose the call
        logger.warning("telephony_relay_synthesis_failed", call_id=str(call.id), error=str(exc))
        return (
            SelfCallRelay(
                owner_confirmed=True,
                relay_message="",
                summary=extract_transcript_summary(payload),
            ),
            None,
            False,
        )


def _outcome_of(relay: SelfCallRelay, status: PhoneCallStatus) -> PhoneCallOutcome:
    if status in _UNANSWERED:
        return PhoneCallOutcome.UNREACHABLE
    if relay.owner_confirmed and relay.relay_message.strip():
        return PhoneCallOutcome.OBJECTIVE_MET
    return PhoneCallOutcome.PARTIAL


async def process_owner_call(
    *,
    db: Any,
    repo: TelephonyRepository,
    call: PhoneCall,
    payload: dict[str, Any],
    user: Any,
    language: str,
    user_timezone: str,
    status: PhoneCallStatus,
    call_seconds: Decimal | None,
) -> None:
    """Close an owner call's books from its webhook, exactly once, by what it RAN.

    A call nobody answered is closed the same way whatever the mode (it has
    none: nothing was said). A LIVE call (ADR-301) delegated every request
    while the person was on the line: nothing is synthesised, nothing
    relayed, nothing pushed — the voice-only exchanges are archived and the
    closing card drawn, the browser's own closing. A DIRECT call is relayed
    as the person's own turn.

    Args:
        db: The session the caller opened.
        repo: The repository bound to it.
        call: The active call row.
        payload: The post-call webhook payload.
        user: The account, or None (defensive).
        language: The person's backend-canonical language.
        user_timezone: Their IANA zone.
        status: The terminal status read from the payload.
        call_seconds: The call's duration, when the payload carries it.
    """
    if status in _UNANSWERED:
        await _close_unanswered_call(
            db=db,
            repo=repo,
            call=call,
            payload=payload,
            user=user,
            language=language,
            status=status,
            call_seconds=call_seconds,
        )
    elif call.call_mode == "delegated":
        await _close_live_owner_call(
            db=db,
            repo=repo,
            call=call,
            payload=payload,
            user=user,
            language=language,
            user_timezone=user_timezone,
            status=status,
            call_seconds=call_seconds,
        )
    else:
        await _close_direct_owner_call(
            db=db,
            repo=repo,
            call=call,
            payload=payload,
            user=user,
            language=language,
            user_timezone=user_timezone,
            status=status,
            call_seconds=call_seconds,
        )


def _count_call(status: PhoneCallStatus, call_seconds: Decimal | None) -> None:
    """One terminal call, counted once the claim is won."""
    telephony_calls_total.labels(status=status.value).inc()
    if call_seconds is not None:
        telephony_call_duration_seconds.observe(float(call_seconds))


async def _claim_relaying(
    *,
    repo: TelephonyRepository,
    call: PhoneCall,
    payload: dict[str, Any],
    relay: SelfCallRelay,
    language: str,
    status: PhoneCallStatus,
    call_seconds: Decimal | None,
) -> bool:
    """Close the row ``RELAYING``, the fallback armed; False when a duplicated webhook won."""
    return await repo.mark_completed(
        call.id,
        status=status,
        call_seconds=call_seconds,
        summary=relay.summary,
        structured_data=collected_of_payload(payload).model_dump(exclude_none=True),
        debrief=None,
        outcome=_outcome_of(relay, status),
        completed_at=datetime.now(UTC),
        # The FALLBACK the stale-relay sweep sends if nothing settles the row.
        notification_content=fallback_text(relay, RelayOutcome.FAILED, language),
        notification_title=get_return_phrases(language)["self_call_title"],
        notification_status=NotificationStatus.RELAYING,
    )


async def _close_unanswered_call(
    *,
    db: Any,
    repo: TelephonyRepository,
    call: PhoneCall,
    payload: dict[str, Any],
    user: Any,
    language: str,
    status: PhoneCallStatus,
    call_seconds: Decimal | None,
) -> None:
    """Nobody picked up, or the line failed: no model, no session books, the person told.

    The same closing whatever mode the call was DIALLED under — a call that
    never connected ran no mode. The row is armed ``RELAYING`` with the
    fallback and settled at once with the silent outcome, so the person (or
    the routine that planned the call) reads « nobody answered » or « the
    line failed » rather than nothing.
    """
    relay = SelfCallRelay(
        owner_confirmed=False, relay_message="", summary=extract_transcript_summary(payload)
    )
    if not await _claim_relaying(
        repo=repo,
        call=call,
        payload=payload,
        relay=relay,
        language=language,
        status=status,
        call_seconds=call_seconds,
    ):
        return  # a duplicated webhook lost the race
    _count_call(status, call_seconds)
    # The call is over: the agent gives the owner's tools back (lot 7).
    await detach_live_tools(db, user_id=call.user_id)
    if user is None:
        # Nobody to tell: close the outbox, and say so rather than « answered ».
        await repo.mark_relay_delivered(call.id, outcome=RelayOutcome.FAILED.value)
        return
    outcome = count_relay_outcome(_SILENT_OUTCOMES[status])
    await settle_owner_call(
        repo=repo, call=call, user=user, relay=relay, outcome=outcome, language=language, db=db
    )


async def _close_direct_owner_call(
    *,
    db: Any,
    repo: TelephonyRepository,
    call: PhoneCall,
    payload: dict[str, Any],
    user: Any,
    language: str,
    user_timezone: str,
    status: PhoneCallStatus,
    call_seconds: Decimal | None,
) -> None:
    """The DIRECT call's closing: synthesise, claim, relay as the person's turn, settle."""
    relay, usage, synthesized = await _synthesize(
        call=call, payload=payload, language=language, user_timezone=user_timezone
    )
    if not await _claim_relaying(
        repo=repo,
        call=call,
        payload=payload,
        relay=relay,
        language=language,
        status=status,
        call_seconds=call_seconds,
    ):
        return  # a duplicated webhook lost the race: the winner relays
    await track_synthesis_usage(usage, call_id=call.id, user_id=call.user_id)
    _count_call(status, call_seconds)
    # The call is over: the agent gives the owner's lookups back (lot 7).
    await detach_live_tools(db, user_id=call.user_id)
    if user is None:
        # Nobody to relay to: close the outbox, and say so rather than « answered ».
        await repo.mark_relay_delivered(call.id, outcome=RelayOutcome.FAILED.value)
        return
    if synthesized:
        # The relay opens its own short sessions: the webhook's ``db`` holds no
        # transaction while the turn runs (its last commit was the detach).
        outcome = await run_relay(RelayRequest(call_id=call.id, user_id=call.user_id, relay=relay))
    else:
        outcome = count_relay_outcome(RelayOutcome.FAILED)
    await settle_owner_call(
        repo=repo, call=call, user=user, relay=relay, outcome=outcome, language=language, db=db
    )


async def _close_live_owner_call(
    *,
    db: Any,
    repo: TelephonyRepository,
    call: PhoneCall,
    payload: dict[str, Any],
    user: Any,
    language: str,
    user_timezone: str,
    status: PhoneCallStatus,
    call_seconds: Decimal | None,
) -> None:
    """The Live call's closing: the row, the agent's tools, the session's books.

    The row is closed with NO return to deliver (``notification_status``
    NULL): every request the person made already reached the chat during the
    call. Then the voice session closes through the carrier-neutral door —
    the phone's voice-only turns archived from the vendor's transcript, the
    card with the EXACT figures, the decision row, the learning — exactly what
    the browser's session does at its end. The call was answered: an
    unanswered one never reaches this function.
    """
    collected = collected_of_payload(payload)
    transcript = transcript_of_payload(payload)
    delegated_turns = len(transcript.turns) - len(transcript.voice_only())
    outcome = (
        PhoneCallOutcome.OBJECTIVE_MET
        if collected.owner_confirmed is not False and delegated_turns > 0
        else PhoneCallOutcome.PARTIAL
    )
    phrases = get_return_phrases(language)
    claimed = await repo.mark_completed(
        call.id,
        status=status,
        call_seconds=call_seconds,
        summary=vendor_summary_of_payload(payload),
        structured_data=collected.model_dump(exclude_none=True),
        debrief=None,
        outcome=outcome,
        completed_at=datetime.now(UTC),
        notification_content="",
        notification_title=phrases["self_call_title"],
        notification_status=None,
    )
    if not claimed:
        return  # a duplicated webhook lost the race
    _count_call(status, call_seconds)
    # The call is over: the agent gives the delegation tool back.
    await detach_live_tools(db, user_id=call.user_id)
    if user is None:
        return  # nobody to close for

    conversation = await ConversationService().get_or_create_conversation(
        call.user_id, db, language=language
    )
    session = VoiceSession.phone(
        call_id=call.id,
        mode="delegated",
        user_id=call.user_id,
        conversation_id=conversation.id,
        language=language,
        timezone=user_timezone,
    )
    closed = await close_voice_session(
        db,
        session=session,
        memory_enabled=bool(user.memory_enabled),
        outcome="ended",
        duration_seconds=int(call_seconds or 0),
        transcript=transcript,
        # The vendor's offsets count from the answer; the row holds the dial.
        # The seconds of ringing shift every turn by the same amount — the
        # exchange count and the order, which the card reads, are untouched.
        started_at=call.initiated_at or datetime.now(UTC),
    )
    logger.info(
        "telephony_live_call_closed",
        call_id=str(call.id),
        delegations=closed.delegations,
        voice_turns=closed.voice_turns,
    )


__all__ = ["process_owner_call"]
