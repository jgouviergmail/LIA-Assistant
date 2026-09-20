"""The voice session becomes a message: the relay synthesis and the relayed turn (ADR-301).

After a DIRECT voice session — an owner call under the direct mandate, a
browser session in direct mode — the transcript is turned into the message
the person would have typed (first person, faithful, absolute dates, empty
when there is nothing to relay), plus a neutral summary and the flag saying
whether the account holder was really on the line; then that message is
handed to the chat as the person's own turn. Extracted from
``telephony/self_call_relay.py`` (ADR-290 lot 4) so the browser's direct
session is relayed exactly like a phone call; the phone's rows and pushes
stay in ``phone_relay_runner``.

Three rules, each a test:

- the transcript is projected under a TOKEN budget at TURN boundaries and the
  cut is stated to the model (ADR-286);
- the model is reached through the ONE structured-output chokepoint with the
  session's owner named, so the account's ceiling applies (ADR-272), and the
  spend is accounted by the caller (``synthesis_usage``, the CALLER road);
- the relayed turn is a turn the person SPOKE: not automated, no plan
  pre-approved, their own execution mode and preference flags, archived
  VISIBLE with the session's origin stamp on every row;
- **no database session is held across the turn** (the workboard runner's
  own rule): the two probes before it run on a session this module opens
  and closes, and the turn opens its own. Measured 2026-09-20 on the direct
  session's settle: the caller's session sat 8.9 s in ``idle in
  transaction`` — the whole relayed turn — for two SELECTs it had finished.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import Any, Final, Literal
from uuid import UUID

import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from pydantic import ValidationError

from src.core.config import settings
from src.core.constants import LIVE_DELEGATION_TOOL_NAME
from src.core.i18n import get_language_name
from src.core.llm_config_helper import get_llm_config_for_agent
from src.core.prompt_store import parse_prompt_sections, read_prompt_file
from src.domains.agents.api.run_origin import RunOrigin
from src.domains.telephony.budget import fit_lines
from src.domains.telephony.payload import current_datetime_line, extract_transcript_summary, nested
from src.domains.telephony.prompts.loader import load_telephony_prompt
from src.domains.telephony.schemas import SelfCallData, SelfCallRelay
from src.domains.telephony.synthesis_usage import SynthUsage, capture_to_usage
from src.domains.voice_sessions.session import VoiceCarrier, VoiceSession
from src.domains.voice_sessions.transcript import VoiceTranscript
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.database.session import get_db_context
from src.infrastructure.llm.factory import get_llm
from src.infrastructure.llm.structured_output import get_structured_output_with_retry
from src.infrastructure.llm.token_capture import TokenCaptureHandler
from src.infrastructure.scheduler.out_of_turn_run import (
    RunContext,
    RunOutcome,
    StreamRequest,
    conversation_has_pending_hitl,
    resolve_run_context,
    stream_instruction,
)
from src.infrastructure.streaming.run_stream_broker import ActiveRunLockLost, active_run_lease

logger = structlog.get_logger(__name__)

#: The synthesis slot, shared with the third-party debrief.
_LLM_TYPE: Final[Literal["telephony_synthesis"]] = "telephony_synthesis"
_RELAY_ATTEMPTS: Final = 1  # a relay is never retried: the words were said once
#: The one-line scaffolds of the CONTEXT block (ADR-284: prose lives in a file).
_LINES: Final = "voice_relay_lines"
#: The line of the context naming what carried the session, per carrier: the
#: prompt's rule on who was speaking reads it (an authenticated session in the
#: app is the account holder's by construction; a phone call is confirmed on
#: the transcript).
_SESSION_LINE_KEY: Final[dict[VoiceCarrier, str]] = {
    VoiceCarrier.PHONE: "session_phone",
    VoiceCarrier.BROWSER: "session_browser",
}


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


_RUN_TO_RELAY: Final[dict[RunOutcome, RelayOutcome]] = {
    RunOutcome.SUCCESS: RelayOutcome.ANSWERED,
    RunOutcome.WAITING: RelayOutcome.WAITING,
    RunOutcome.QUOTA_BLOCKED: RelayOutcome.QUOTA_BLOCKED,
    RunOutcome.FAILED: RelayOutcome.FAILED,
}


# ---------------------------------------------------------------------------
# Reading the vendor's post-call payload (the phone's way in)
# ---------------------------------------------------------------------------


def transcript_of_payload(payload: dict[str, Any]) -> VoiceTranscript:
    """The turns of a post-call payload, delegated exchanges marked.

    A delegated exchange is a call of the ONE delegation function, named by
    the same constant the browser's declaration and the phone's webhook tool
    read — so the transcript and the tool cannot disagree on its name.
    """
    return VoiceTranscript.from_vendor_payload(payload, delegation_tool=LIVE_DELEGATION_TOOL_NAME)


def collected_of_payload(payload: dict[str, Any]) -> SelfCallData:
    """What the voice agent collected about the owner call.

    Defensive like its third-party sibling: a mistyped value degrades to an
    empty record rather than losing the relay.

    Args:
        payload: The post-call webhook payload.

    Returns:
        The collected owner flag and requests, or an empty record.
    """
    raw = nested(payload, "data", "analysis", "data_collection_results")
    if not isinstance(raw, dict):
        return SelfCallData()
    flat = {k: (v.get("value") if isinstance(v, dict) else v) for k, v in raw.items()}
    try:
        return SelfCallData.model_validate(flat)
    except ValidationError as exc:
        logger.warning("telephony_self_data_invalid", error_type=type(exc).__name__)
        return SelfCallData()


def vendor_summary_of_payload(payload: dict[str, Any]) -> str:
    """The vendor's own summary of the call, or ""."""
    return extract_transcript_summary(payload)


# ---------------------------------------------------------------------------
# The synthesis
# ---------------------------------------------------------------------------


def project_transcript(transcript: VoiceTranscript, *, budget_tokens: int) -> tuple[str, bool]:
    """The transcript as ``role: text`` lines, under a token budget.

    Args:
        transcript: The session's turns.
        budget_tokens: What the projection may cost.

    Returns:
        The text and whether turns were left out.
    """
    lines = transcript.lines()
    if not lines:
        return "", False
    return fit_lines(lines, budget_tokens=budget_tokens)


def relay_lines() -> dict[str, str]:
    """The one-line scaffolds of the context block, from their lines file."""
    return dict(parse_prompt_sections(read_prompt_file(_LINES), 2))


def _render_context(
    *,
    carrier: VoiceCarrier,
    objective: str,
    collected: SelfCallData,
    vendor_summary: str,
    transcript: str,
    transcript_cut: bool,
    language: str,
    user_timezone: str,
) -> str:
    """The CONTEXT block, as a HumanMessage f-string (no ``.format`` on data)."""
    lines = relay_lines()
    language_name = get_language_name(language)
    transcript_heading = lines["transcript_heading_cut" if transcript_cut else "transcript_heading"]
    owner = collected.owner_confirmed
    parts = [
        f"LANGUAGE: {language_name} ({language}). Write EVERY field ENTIRELY in {language_name}.",
        current_datetime_line(user_timezone),
        lines[_SESSION_LINE_KEY[carrier]],
        f"OBJECTIVE: {objective or lines['objective_default']}",
        "OWNER FLAGS:",
        f"- owner_confirmed (collected): {owner if owner is not None else lines['owner_unknown']}",
        f"- requests (collected): {collected.requests or lines['requests_none']}",
        f"VENDOR SUMMARY: {vendor_summary or lines['vendor_summary_none']}",
        f"{transcript_heading}:\n{transcript or lines['transcript_none']}",
    ]
    return "\n".join(parts)


async def synthesize_relay(
    *,
    carrier: VoiceCarrier,
    transcript: VoiceTranscript,
    collected: SelfCallData,
    vendor_summary: str,
    objective: str,
    user_language: str,
    user_timezone: str,
    user_id: UUID | None,
) -> tuple[SelfCallRelay, SynthUsage | None]:
    """One structured call: the transcript in, the relay message out.

    Args:
        carrier: The line that carried the session — named to the model, whose
            rule on who was speaking differs: a browser session is the account
            holder's by construction, a phone call is confirmed on the transcript.
        transcript: The session's turns (delegated exchanges included — the
            synthesis reads everything that was said).
        collected: What the vendor collected (the phone); empty for a browser.
        vendor_summary: The vendor's own summary, or "".
        objective: What the session was about, or "".
        user_language: Backend-canonical language of the output.
        user_timezone: The person's IANA zone, for the clock.
        user_id: The session's owner, so the account's ceiling applies.

    Returns:
        The relay and the token usage (None when the provider reported none);
        the caller files the usage under the session's run id.
    """
    projected, cut = project_transcript(
        transcript, budget_tokens=settings.telephony_relay_transcript_max_tokens
    )
    context = _render_context(
        carrier=carrier,
        objective=objective,
        collected=collected,
        vendor_summary=vendor_summary,
        transcript=projected,
        transcript_cut=cut,
        language=user_language,
        user_timezone=user_timezone,
    )
    system = load_telephony_prompt("telephony_self_call_relay_prompt", "v1")
    llm = get_llm(_LLM_TYPE)
    provider = get_llm_config_for_agent(settings, _LLM_TYPE).provider
    token_capture = TokenCaptureHandler()
    relay = await get_structured_output_with_retry(
        llm=llm,
        messages=[SystemMessage(content=system), HumanMessage(content=context)],
        schema=SelfCallRelay,
        provider=provider,
        node_name=_LLM_TYPE,
        config=RunnableConfig(callbacks=[token_capture]),
        user_id=user_id,
    )
    return relay, capture_to_usage(token_capture)


# ---------------------------------------------------------------------------
# The relayed turn
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VoiceRelayRequest:
    """One relay to run.

    Attributes:
        session: The session the words were said in — its origin is stamped
            on every row of the turn, its run id files the spend.
        relay: What the synthesis produced.
    """

    session: VoiceSession
    relay: SelfCallRelay


async def _drive(request: VoiceRelayRequest, context: RunContext) -> RelayOutcome:
    session = request.session
    stream = StreamRequest(
        user_id=session.user_id,
        prompt=request.relay.relay_message.strip(),
        session_id=f"{session.origin_kind}_{session.origin_id}",
        language=context.language,
        timezone=context.timezone,
        display_name=context.display_name,
        display_mode=context.display_mode,
        timeout_seconds=settings.telephony_relay_timeout_seconds,
        max_attempts=_RELAY_ATTEMPTS,
        retry_delay_seconds=0,
        origin=RunOrigin(
            kind=session.origin_kind,
            ticket_id=session.origin_id,
            run_id=session.run_id,
            hidden=False,
        ),
        run_id=session.run_id,
        execution_mode=context.execution_mode,
        spoken_by_person=True,
        memory_enabled=context.memory_enabled,
        journals_enabled=context.journals_enabled,
        psyche_enabled=context.psyche_enabled,
    )
    result = await stream_instruction(stream)
    return _RUN_TO_RELAY.get(result.outcome, RelayOutcome.FAILED)


async def _drive_under_lease(
    request: VoiceRelayRequest, context: RunContext, conversation_id: UUID
) -> RelayOutcome:
    """Take the conversation's lock, with bounded retries; BUSY when never taken."""
    redis = await get_redis_cache()
    session = request.session
    for attempt in range(1, settings.telephony_relay_busy_retries + 1):
        try:
            async with active_run_lease(
                redis,
                str(conversation_id),
                run_id=session.run_id,
                stream_id=f"{session.origin_kind}:{session.run_id}",
            ) as acquired:
                if acquired:
                    return await _drive(request, context)
        except ActiveRunLockLost:
            # The person started talking while the relay ran: their turn wins,
            # and the relay's words are still in the fallback notification.
            logger.info("voice_relay_conversation_taken_over", origin=session.origin_id)
            return RelayOutcome.BUSY
        if attempt < settings.telephony_relay_busy_retries:
            await asyncio.sleep(settings.telephony_relay_busy_delay_seconds)
    return RelayOutcome.BUSY


async def run_voice_relay(
    request: VoiceRelayRequest, *, context: RunContext | None = None
) -> RelayOutcome:
    """Run the relayed turn, or name why it could not run.

    Two decisions before any model spends a token: the account holder must
    have been the one on the line (``owner_confirmed``), and there must be
    something to relay (an empty message is a greeting or a wrong number,
    never a turn). The carrier counts the outcome and tells the person its
    own way (a push on the phone, a notice in the browser).

    The two probes run on a session THIS function opens and closes before the
    turn: a runner holds no connection across a model turn (the workboard
    runner's rule) — the turn's own sessions live inside the engine.

    Args:
        request: The relay to run.
        context: The account's run context when the caller already resolved
            it (the phone does, to build the session); resolved here otherwise.

    Returns:
        The outcome; ``ANSWERED`` and ``WAITING`` mean the turn ran.
    """
    if not request.relay.owner_confirmed:
        return RelayOutcome.NOT_OWNER
    if not request.relay.relay_message.strip():
        return RelayOutcome.EMPTY

    user_id = request.session.user_id
    async with get_db_context() as db:
        if context is None:
            context = await resolve_run_context(db, user_id)
        if context is None:
            return RelayOutcome.FAILED
        pending, conversation_id = await conversation_has_pending_hitl(
            db, user_id, context.language
        )
    if pending:
        return RelayOutcome.PENDING_QUESTION

    if conversation_id is None:
        logger.warning("voice_relay_unlocked_thread", origin=request.session.origin_id)
        return await _drive(request, context)
    return await _drive_under_lease(request, context, conversation_id)


__all__ = [
    "RelayOutcome",
    "VoiceRelayRequest",
    "collected_of_payload",
    "project_transcript",
    "relay_lines",
    "run_voice_relay",
    "synthesize_relay",
    "transcript_of_payload",
    "vendor_summary_of_payload",
]
