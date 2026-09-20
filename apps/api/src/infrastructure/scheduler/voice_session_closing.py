"""How a voice session closes its books — ONE policy per mode, whichever carrier (ADR-301).

A browser session ends when the person presses stop (``POST /live/sessions/
{id}/end``); a phone call ends when the vendor's post-call webhook arrives.
Both then owe the same things, decided by the MODE alone:

- **delegated** — the voice-only exchanges are archived (the browser did it
  turn by turn; the phone hands its transcript here), the closing card is
  archived with the EXACT figures (the delegated turns found by the session
  key, never a count the client claims — ADR-185), a decision row names the
  session, and the voice-only rows reach the memory and the interests once
  (the delegated turns learned inside the graph);
- **direct** — the transcript becomes the message the person would have typed
  (the relay synthesis, accounted under the session's run id) and is relayed
  as their own turn — BOTH in a task the closing owns, off the request path:
  the person pressed stop, the claim must be released now, and a slow
  provider must not hang the banner nor lock the account out of a new
  session. Nothing of the transcript is archived, the relay learns (a spoken
  turn runs the six extractions), the card says ``scheduled`` (or ``empty``
  when nothing was said) and is REWRITTEN once the words settled — with the
  fate known then, whatever RAISED: a card left at « scheduled » would be a
  promise nobody keeps (a hard crash mid-settle is the one thing that leaves
  it there — the words live in the task alone, as the phone's return does) —
  and a notice on the person's SSE stream reloads the thread. The phone's direct call keeps its own outbox and push
  (``owner_call``); the two share the synthesis and the relay.

It lives here, beside the workboard and phone-relay runners, for the reason
they are here: it archives, records a decision and drives the extractors —
``agents`` — and ``telephony`` must not import ``agents`` (the T2 cycle),
while ``voice_sessions`` imports no carrier. The carriers keep what is theirs
(the Redis record, the ``phone_calls`` row, their own metrics) and call this.
"""

from __future__ import annotations

import uuid
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Final

import structlog
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import LIVE_TURN_TEXT_MAX_CHARS
from src.core.exceptions_domains import UsageLimitExceededError
from src.core.field_names import FIELD_LIVE_SUMMARY
from src.core.i18n_live import get_live_phrases
from src.domains.agents.api.archive_metadata import (
    build_live_session_summary_metadata,
    build_live_turn_metadata,
)
from src.domains.agents.effects.decision_recorder import record_decision
from src.domains.agents.effects.decisions import out_of_turn_decision
from src.domains.agents.effects.models import DecisionOutcome
from src.domains.agents.services.memory_extractor import extract_memories_background
from src.domains.chat.service import TrackingContext
from src.domains.conversations.models import ConversationMessage
from src.domains.conversations.service import ConversationService
from src.domains.interests.services import extract_interests_background
from src.domains.telephony.schemas import SelfCallData, SelfCallRelay
from src.domains.telephony.synthesis_usage import track_voice_synthesis_usage
from src.domains.users.models import User
from src.domains.voice_sessions.session import VoiceCarrier, VoiceSession
from src.domains.voice_sessions.summary import (
    VoiceSessionUsage,
    aggregate_usage,
    count_voice_turns,
    render_summary_markdown,
    rewrite_session_card,
    session_card,
    session_run_ids,
    session_voice_rows,
)
from src.domains.voice_sessions.transcript import VoiceTranscript
from src.infrastructure.async_utils import safe_fire_and_forget
from src.infrastructure.database.session import get_db_context
from src.infrastructure.observability.metrics_live import live_direct_relay_total
from src.infrastructure.proactive.notification import NotificationDispatcher
from src.infrastructure.scheduler.voice_relay import (
    RelayOutcome,
    VoiceRelayRequest,
    run_voice_relay,
    synthesize_relay,
)

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ClosedSession:
    """What the closing produced — the figures the carrier reports.

    Attributes:
        summary_message_id: The archived closing card.
        delegations: Requests handed to LIA (exact, from the session key).
        voice_turns: Exchanges the voice held alone (exact).
        usage: LIA's spend over the session, or None when nothing was recorded.
        relay: A DIRECT session's relay fate at the closing: ``scheduled``
            (the words are becoming the person's own turn) or ``empty``
            (nothing was said); None for a delegated one.
    """

    summary_message_id: uuid.UUID
    delegations: int
    voice_turns: int
    usage: VoiceSessionUsage | None
    relay: str | None = None


# ---------------------------------------------------------------------------
# The voice-only rows (what the learning reads)
# ---------------------------------------------------------------------------


def voice_turn_messages(rows: list[tuple[str, str]]) -> list[BaseMessage]:
    """The archived voice-only rows as the extractors read them."""
    messages: list[BaseMessage] = []
    for role, text in rows:
        if not text.strip():
            continue
        messages.append(HumanMessage(content=text) if role == "user" else AIMessage(content=text))
    return messages


async def _learn(
    *,
    user_id: uuid.UUID,
    memory_enabled: bool,
    conversation_id: uuid.UUID,
    run_id: str,
    messages: list[BaseMessage],
    language: str,
) -> None:
    session_id = f"live_{run_id}"
    async with TrackingContext(run_id, user_id, session_id, conversation_id):
        if memory_enabled:
            await extract_memories_background(
                str(user_id),
                messages,
                session_id,
                personality_instruction=None,
                conversation_id=str(conversation_id),
                parent_run_id=run_id,
            )
        await extract_interests_background(
            str(user_id),
            messages,
            session_id,
            conversation_id=str(conversation_id),
            user_language=language,
            parent_run_id=run_id,
        )


async def schedule_voice_learning(
    *,
    user_id: uuid.UUID,
    memory_enabled: bool,
    conversation_id: uuid.UUID,
    run_id: str,
    rows: list[tuple[str, str]],
    language: str,
    run_inline: bool = False,
) -> None:
    """Hand the voice-only exchanges to the extractors, never raising.

    A delegated turn ran the six post-response extractions inside the graph.
    A voice-only exchange ran in no graph, so its words would reach no memory
    and no interest — the session's end hands them to the same two extractors
    the response node schedules, once, under the person's own switch (memory)
    and the operator's capabilities (both extractors read them at the act),
    and under the session's run id: a ``TrackingContext`` published here,
    since these extractors spend on the ambient tracker (the TURN road).

    Args:
        user_id: The account.
        memory_enabled: The person's own memory switch (the interests have none).
        conversation_id: The conversation the rows belong to.
        run_id: The session's run id — what the spend is filed under.
        rows: ``(role, text)`` of every voice-only row, in order.
        language: The person's backend-canonical language.
        run_inline: Tests only — await instead of scheduling.
    """
    messages = voice_turn_messages(rows)
    if not messages:
        return
    # Only PRIMITIVES cross into the background task: an ORM row belongs to
    # the request's session, which is gone by the time the task runs.
    coroutine = _learn(
        user_id=user_id,
        memory_enabled=memory_enabled,
        conversation_id=conversation_id,
        run_id=run_id,
        messages=messages,
        language=language,
    )
    if run_inline:
        try:
            await coroutine
        except Exception as exc:  # noqa: BLE001 - learning must never break the end of a session
            logger.warning("voice_learning_failed", run_id=run_id, error_type=type(exc).__name__)
        return
    safe_fire_and_forget(coroutine, name=f"voice_learning_{run_id}", run_id=run_id)


# ---------------------------------------------------------------------------
# The direct policy: the words become the person's own turn (ADR-301)
# ---------------------------------------------------------------------------

#: What the closing can say of the relay before the turn ran.
RELAY_SCHEDULED: Final = "scheduled"


async def _synthesize_direct(
    session: VoiceSession, transcript: VoiceTranscript
) -> tuple[str, SelfCallRelay | None]:
    """The relay message of a direct session, or the reason there is none.

    Every failure is a named fate, never an exception. An authenticated
    browser session IS the account holder's: the synthesis's own owner flag
    — a model output the prompt asks to copy from the collected one — is
    overwritten, so a model that does not copy it cannot turn the person's
    own session into « someone else was speaking » (``NOT_OWNER``).
    """
    try:
        relay, usage = await synthesize_relay(
            carrier=session.carrier,
            transcript=transcript,
            collected=SelfCallData(owner_confirmed=True),
            vendor_summary="",
            objective="",
            user_language=session.language,
            user_timezone=session.timezone,
            user_id=session.user_id,
        )
    except UsageLimitExceededError:
        return RelayOutcome.QUOTA_BLOCKED.value, None
    except Exception as exc:  # noqa: BLE001 — the settle never loses the session
        logger.warning(
            "voice_direct_synthesis_failed", origin=session.origin_id, error_type=type(exc).__name__
        )
        return RelayOutcome.FAILED.value, None
    await track_voice_synthesis_usage(
        usage,
        user_id=session.user_id,
        task_type=session.origin_kind,
        target_id=session.origin_id,
        run_id=session.run_id,
    )
    if not relay.relay_message.strip():
        return RelayOutcome.EMPTY.value, None
    if session.carrier is VoiceCarrier.BROWSER:
        relay = relay.model_copy(update={"owner_confirmed": True})
    return RELAY_SCHEDULED, relay


#: The fates under which the words BECAME a turn: the chat holds them.
_RELAY_RAN: Final[frozenset[str]] = frozenset(
    {RelayOutcome.ANSWERED.value, RelayOutcome.WAITING.value}
)


async def _relay_direct(
    session: VoiceSession, transcript: VoiceTranscript
) -> tuple[str, str | None]:
    """The fate of a direct session's words, and their recap when they could not become a turn.

    The phone's fallback push carries the neutral recap when the relay did
    not run; the browser's card carries the same, so nothing said is lost in
    silence on a busy thread, a pending question, a ceiling or a failure.
    No session of the closing's is open here: the synthesis calls a model,
    the relay runs a turn, and each opens what it needs for as long as it
    needs it.
    """
    fate, relay = await _synthesize_direct(session, transcript)
    if relay is None:
        return fate, None
    outcome = await run_voice_relay(VoiceRelayRequest(session=session, relay=relay))
    recap = None if outcome.value in _RELAY_RAN else relay.summary.strip() or None
    return outcome.value, recap


async def _settle_card(
    db: AsyncSession,
    session: VoiceSession,
    card_id: uuid.UUID,
    fate: str,
    recap: str | None,
    *,
    extensions: int,
) -> None:
    """Rewrite the card with the fate (and the recap), tell the person's screen, commit."""
    await _rewrite_card(db, session, card_id, fate, extensions=extensions, relay_summary=recap)
    user = await db.get(User, session.user_id)
    if user is not None:
        await _notify_relay(db, user, session, fate)
    await db.commit()


async def _settle_direct_relay(
    session: VoiceSession, transcript: VoiceTranscript, card_id: uuid.UUID, *, extensions: int
) -> None:
    """Synthesise, relay, rewrite the card with the fate, tell the person's screen.

    The card does not stay at « scheduled » for anything that RAISES: whatever
    broke — the relay's Redis lease, the rewrite's session — the fate known at
    that instant is written on a fresh session, and a turn that DID run is
    never reported as failed by a rewrite that failed after it.

    Durability envelope, the phone's own (``return_synthesis``): the task is
    held in the background-task set and drained at graceful shutdown; a hard
    crash mid-flight is not recoverable — the transcript lives in this task
    alone, nothing persists it — and the card then keeps « scheduled ».

    The settle's session is opened AFTER the turn ran, for the rewrite and
    the notice alone: a session opened before it sat in ``idle in
    transaction`` for the whole turn (measured 8.9 s, 2026-09-20).
    """
    fate, recap = RelayOutcome.FAILED.value, None
    try:
        fate, recap = await _relay_direct(session, transcript)
        async with get_db_context() as db:
            await _settle_card(db, session, card_id, fate, recap, extensions=extensions)
    except Exception as exc:  # noqa: BLE001 — the fate is written whatever broke
        logger.error(
            "voice_direct_relay_settle_failed",
            origin=session.origin_id,
            fate=fate,
            error_type=type(exc).__name__,
        )
        # Best effort on a fresh session: the first one may be the broken thing.
        with suppress(Exception):
            async with get_db_context() as db:
                await _settle_card(db, session, card_id, fate, recap, extensions=extensions)
    live_direct_relay_total.labels(outcome=fate).inc()
    logger.info("voice_direct_relay_settled", origin=session.origin_id, outcome=fate)


async def _rewrite_card(
    db: AsyncSession,
    session: VoiceSession,
    card_id: uuid.UUID,
    relay: str,
    *,
    extensions: int,
    relay_summary: str | None = None,
) -> None:
    """The card archived at the closing said « scheduled »; it now says the fate.

    The figures are read AGAIN: the relayed turn spent under the session's own
    run id after the card was written, and a card that kept the closing's
    figure would understate the bill it claims to state (ADR-185).
    """
    row = await session_card(db, card_id)
    if row is None:
        logger.warning("voice_direct_relay_card_missing", origin=session.origin_id)
        return
    figures = dict((row.message_metadata or {}).get(FIELD_LIVE_SUMMARY) or {})
    outcome = str(figures.get("outcome") or "ended")
    duration_seconds = int(figures.get("duration_seconds") or 0)
    delegations = int(figures.get("delegations") or 0)
    voice_turns = int(figures.get("voice_turns") or 0)
    usage = await aggregate_usage(db, [session.run_id])
    await rewrite_session_card(
        db,
        card_id,
        content=render_summary_markdown(
            language=session.language,
            outcome=outcome,
            mode=session.mode,
            duration_seconds=duration_seconds,
            delegations=delegations,
            voice_turns=voice_turns,
            usage=usage,
            extensions=extensions,
            relay=relay,
            relay_summary=relay_summary,
        ),
        metadata=build_live_session_summary_metadata(
            run_id=session.run_id,
            live_session_id=session.key,
            outcome=outcome,
            duration_seconds=duration_seconds,
            delegations=delegations,
            voice_turns=voice_turns,
            usage=usage.model_dump() if usage else None,
            extensions=extensions,
            mode=session.mode,
            relay=relay,
            relay_summary=relay_summary,
        ),
    )


async def _notify_relay(db: AsyncSession, user: User, session: VoiceSession, relay: str) -> None:
    """A notice on the person's SSE stream and nothing else: the rows are in the chat."""
    phrases = get_live_phrases(session.language)
    try:
        await NotificationDispatcher(
            fcm_enabled=False, channel_enabled=False, archive_enabled=False, sse_enabled=True
        ).dispatch(
            user=user,
            content=phrases[f"relay_{relay}"],
            task_type=session.origin_kind,
            target_id=session.origin_id,
            metadata={"event": "live_relay", "relay": relay, "session_id": session.origin_id},
            db=db,
            title=phrases["summary_title"],
            commit_before_notification=False,
            push_enabled=False,
        )
    except Exception as exc:  # noqa: BLE001 — a notice failing never undoes the turn
        logger.warning(
            "voice_direct_relay_notice_failed",
            origin=session.origin_id,
            error_type=type(exc).__name__,
        )


# ---------------------------------------------------------------------------
# The closing
# ---------------------------------------------------------------------------


async def archive_row(
    db: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    role: str,
    content: str,
    metadata: dict[str, Any],
) -> ConversationMessage:
    """The ONE door every row of a closing goes through (a test seam by name)."""
    return await ConversationService().archive_message(conversation_id, role, content, metadata, db)


async def archive_voice_turns(
    db: AsyncSession, *, session: VoiceSession, transcript: VoiceTranscript, started_at: datetime
) -> int:
    """Archive the voice-only turns of a transcript, one row each (the phone's way in).

    The browser archives its exchanges one at a time; the phone holds nothing
    until the vendor's post-call payload, so its voice-only turns are archived
    HERE, at the closing, with the metadata the browser's rows carry: the
    rows of one exchange share the ``started_at`` of its first turn (derived
    from the vendor's offset) and the ``ended_at`` of its last, so the
    exchange count (distinct stamps, ADR-185) reads both carriers alike.

    Args:
        db: The carrier's session; the rows are flushed, not committed.
        session: The session.
        transcript: The whole transcript; only voice-only turns are archived.
        started_at: When the session started, to place each turn in time.

    Returns:
        The number of rows archived.
    """
    archived = 0
    for index, exchange in enumerate(transcript.voice_only_exchanges()):
        # The vendor's offsets are whole seconds, and two exchanges may share
        # one (the greeting and the answer both at 0, measured 2026-09-20):
        # the exchange's rank breaks the tie, so « one exchange, one stamp »
        # holds and the order is kept.
        opened = started_at + timedelta(seconds=exchange[0].offset_seconds, microseconds=index)
        ended = started_at + timedelta(seconds=exchange[-1].offset_seconds, microseconds=index)
        for turn in exchange:
            await archive_row(
                db,
                conversation_id=session.conversation_id,
                role=turn.role,
                content=turn.text[:LIVE_TURN_TEXT_MAX_CHARS],
                metadata=build_live_turn_metadata(
                    run_id=session.run_id,
                    live_session_id=session.key,
                    started_at=opened,
                    ended_at=ended,
                ),
            )
            archived += 1
    return archived


async def close_voice_session(
    db: AsyncSession,
    *,
    session: VoiceSession,
    memory_enabled: bool,
    outcome: str,
    duration_seconds: int,
    extensions: int = 0,
    transcript: VoiceTranscript | None = None,
    started_at: datetime | None = None,
    learn_inline: bool = False,
) -> ClosedSession:
    """Close a session's books: rows, card, decision — and, delegated, the learning.

    A DIRECT session archived no exchange and teaches nothing here: its words
    become the person's own turn (the relay), which learns — the rule is
    stated in the mode, never left to an empty list.

    Args:
        db: The carrier's session; committed here, once the card is archived.
        session: The session.
        memory_enabled: The person's own memory switch, read by the learning.
        outcome: A ``VoiceSessionOutcome``.
        duration_seconds: From the first credential (or the dial) to the end.
        extensions: How many times the person prolonged the session (browser).
        transcript: The whole transcript: a delegated phone call archives its
            voice-only turns first (a delegated browser session archived them
            turn by turn and passes None); a DIRECT session relays it.
        started_at: When the session started — required with a transcript
            that is archived.
        learn_inline: Tests only.

    Returns:
        The figures the carrier reports.

    Raises:
        ValueError: A transcript with no ``started_at`` — its turns could not
            be placed in time, and a guessed instant would misdate them.
    """
    relay: str | None = None
    if session.delegated:
        if transcript is not None:
            if started_at is None:
                raise ValueError("a transcript needs the session's started_at")
            await archive_voice_turns(
                db, session=session, transcript=transcript, started_at=started_at
            )
    else:
        # DIRECT: nothing of the transcript is archived; it becomes the
        # person's own turn in the task below — the card says so now, and
        # says the fate once the words settled. No model runs here.
        relay = RELAY_SCHEDULED if transcript else RelayOutcome.EMPTY.value
    run_ids = await session_run_ids(
        db, conversation_id=session.conversation_id, live_session_id=session.key
    )
    # The session's OWN run id carries what the tool host filed under it — a
    # direct session's lookups, the learning; nothing else on a delegated one.
    usage = await aggregate_usage(db, [*run_ids, session.run_id])
    # The card's figures are EXACT, never the client's claim (ADR-185).
    delegations = len(run_ids)
    voice_turns = await count_voice_turns(
        db, conversation_id=session.conversation_id, live_session_id=session.key
    )
    row = await archive_row(
        db,
        conversation_id=session.conversation_id,
        role="assistant",
        content=render_summary_markdown(
            language=session.language,
            outcome=outcome,
            mode=session.mode,
            duration_seconds=duration_seconds,
            delegations=delegations,
            voice_turns=voice_turns,
            usage=usage,
            extensions=extensions,
            relay=relay,
        ),
        metadata=build_live_session_summary_metadata(
            run_id=session.run_id,
            live_session_id=session.key,
            outcome=outcome,
            duration_seconds=duration_seconds,
            delegations=delegations,
            voice_turns=voice_turns,
            usage=usage.model_dump() if usage else None,
            extensions=extensions,
            mode=session.mode,
            relay=relay,
        ),
    )
    await db.commit()
    if relay == RELAY_SCHEDULED and transcript is not None:
        # The synthesis and the turn run in a task the closing owns, on a
        # session of their own: the end answers now, the card is rewritten
        # when the words settled.
        safe_fire_and_forget(
            _settle_direct_relay(session, transcript, row.id, extensions=extensions),
            name=f"voice_direct_relay_{session.run_id}",
        )
    voice_rows = await session_voice_rows(
        db, conversation_id=session.conversation_id, live_session_id=session.key
    )
    decision = out_of_turn_decision(
        run_id=session.run_id,
        user_id=session.user_id,
        thread_id=str(session.conversation_id),
        source="user",
    )
    decision.route = session.origin_kind
    decision.response_message_id = row.id
    decision.outcome = (
        DecisionOutcome.ANSWERED if outcome == "ended" else DecisionOutcome.INTERRUPTED
    )
    await record_decision(decision)
    if session.delegated:
        await schedule_voice_learning(
            user_id=session.user_id,
            memory_enabled=memory_enabled,
            conversation_id=session.conversation_id,
            run_id=session.run_id,
            rows=voice_rows,
            language=session.language,
            run_inline=learn_inline,
        )
    return ClosedSession(
        summary_message_id=row.id,
        delegations=delegations,
        voice_turns=voice_turns,
        usage=usage,
        relay=relay,
    )


__all__ = [
    "RELAY_SCHEDULED",
    "ClosedSession",
    "archive_row",
    "archive_voice_turns",
    "close_voice_session",
    "schedule_voice_learning",
    "voice_turn_messages",
]
