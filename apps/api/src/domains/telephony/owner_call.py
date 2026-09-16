"""The return path of an owner call: synthesize, claim, relay, settle (lot 4).

The third-party path synthesizes a debrief and NOTIFIES. The owner path
synthesizes the message the person would have typed and RELAYS it as their
own chat turn, and the row is claimed ``RELAYING`` before the turn runs so a
crash anywhere after the claim still leaves a return the stale-relay sweep
can deliver.

Order, and why:

1. no model is spent on a call nobody answered (no answer, voicemail,
   failed): the relay is « unanswered » or « the call failed » by
   construction — never « someone else answered », which is what a person
   reads when they picked up and the line died (production 2026-09-16);
2. the synthesis runs BEFORE the claim, like its sibling: a duplicated
   webhook may synthesize twice, only one claim wins;
3. the claim arms the FALLBACK notification (the reason « failed » plus the
   recap): it is what the sweep sends when nothing settles the row;
4. the live tools come off the agent (lot 7, best-effort — the dial path
   detaches again before the next stranger's call if this fails);
5. the relay runs, then :func:`phone_relay_runner.settle_owner_call` decides
   (the runner lives beside the workboard's, in ``infrastructure/scheduler``:
   it drives the chat engine, and ``telephony`` must not import ``agents``).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import structlog

from src.core.i18n_telephony import get_return_phrases
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
from src.domains.telephony.self_call_relay import extract_self_data, synthesize_relay
from src.domains.telephony.synthesis_usage import SynthUsage, track_synthesis_usage
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
            payload=payload,
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
    """Turn an owner call's webhook into the person's chat turn, exactly once.

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
    answered = status not in _UNANSWERED
    if answered:
        relay, usage, synthesized = await _synthesize(
            call=call, payload=payload, language=language, user_timezone=user_timezone
        )
    else:
        relay, usage, synthesized = (
            SelfCallRelay(
                owner_confirmed=False,
                relay_message="",
                summary=extract_transcript_summary(payload),
            ),
            None,
            True,
        )

    phrases = get_return_phrases(language)
    claimed = await repo.mark_completed(
        call.id,
        status=status,
        call_seconds=call_seconds,
        summary=relay.summary,
        structured_data=extract_self_data(payload).model_dump(exclude_none=True),
        debrief=None,
        outcome=_outcome_of(relay, status),
        completed_at=datetime.now(UTC),
        # The FALLBACK the stale-relay sweep sends if nothing settles the row.
        notification_content=fallback_text(relay, RelayOutcome.FAILED, language),
        notification_title=phrases["self_call_title"],
        notification_status=NotificationStatus.RELAYING,
    )
    if not claimed:
        return  # a duplicated webhook lost the race: the winner relays

    await track_synthesis_usage(usage, call_id=call.id, user_id=call.user_id)
    telephony_calls_total.labels(status=status.value).inc()
    if call_seconds is not None:
        telephony_call_duration_seconds.observe(float(call_seconds))
    # The call is over: the agent gives the owner's lookups back (lot 7).
    await detach_live_tools(db, user_id=call.user_id)

    if user is None:
        # Nobody to relay to: close the outbox, and say so rather than « answered ».
        await repo.mark_relay_delivered(call.id, outcome=RelayOutcome.FAILED.value)
        return

    if not answered:
        outcome = count_relay_outcome(_SILENT_OUTCOMES[status])
    elif not synthesized:
        outcome = count_relay_outcome(RelayOutcome.FAILED)
    else:
        outcome = await run_relay(
            RelayRequest(call_id=call.id, user_id=call.user_id, relay=relay), db=db
        )
    await settle_owner_call(
        repo=repo, call=call, user=user, relay=relay, outcome=outcome, language=language, db=db
    )


__all__ = ["process_owner_call"]
