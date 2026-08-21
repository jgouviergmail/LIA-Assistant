"""Post-call return path: synthesize the outcome + deliver it (spec P4.2 / D-2).

Runs as a fire-and-forget background task from the webhook. It reconciles the
call, extracts the *minimized* outcome (``call_seconds`` + ``StructuredCallData``),
runs a single **tool-less** LLM synthesis, persists ONLY ``summary`` +
``structured_data`` (the raw transcript is never stored — D-8), and delivers the
first-person proposal to the user via the notification dispatcher.

spike (P2.0): confirm the post-call payload field paths against a real ElevenLabs
account. All reads are defensive — a shape drift degrades to a graceful fallback,
never a crash.

The delivery strings (notification title / synthesis-failure fallback) live in
``core.i18n_telephony`` (all 6 languages).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Final, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from pydantic import ValidationError

from src.core.config import settings
from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.core.i18n_telephony import get_return_phrases
from src.core.i18n_types import get_language_name
from src.core.llm_config_helper import get_llm_config_for_agent
from src.domains.telephony.models import PhoneCallOutcome, PhoneCallStatus
from src.domains.telephony.prompts.loader import load_telephony_prompt
from src.domains.telephony.repository import TelephonyRepository
from src.domains.telephony.schemas import ReturnProposal, StructuredCallData
from src.domains.users.models import User
from src.infrastructure.database.session import get_db_context
from src.infrastructure.llm.factory import get_llm
from src.infrastructure.llm.structured_output import get_structured_output_with_retry
from src.infrastructure.llm.token_capture import TokenCaptureHandler
from src.infrastructure.observability.metrics_telephony import (
    telephony_call_duration_seconds,
    telephony_calls_total,
)
from src.infrastructure.proactive.notification import NotificationDispatcher
from src.infrastructure.proactive.tracking import track_proactive_tokens

logger = structlog.get_logger(__name__)

_LLM_TYPE: Final[Literal["telephony_synthesis"]] = "telephony_synthesis"
_TASK_TYPE = "phone_call"
_ACTIVE = (PhoneCallStatus.DIALING, PhoneCallStatus.IN_PROGRESS)


@dataclass(frozen=True)
class _SynthUsage:
    """Token usage of the synthesis LLM call, for proactive token tracking (G-1)."""

    tokens_in: int
    tokens_out: int
    tokens_cache: int
    model_name: str


def _capture_to_usage(capture: TokenCaptureHandler) -> _SynthUsage | None:
    """Convert the captured callback counters to the billable usage record.

    Mirrors the briefing pipeline: subtract cached from input to expose the
    non-cached billable count. Returns None when the provider reported no
    usage at all.
    """
    if not capture.has_usage:
        return None
    return _SynthUsage(
        tokens_in=max(capture.tokens_in - capture.tokens_cache, 0),
        tokens_out=capture.tokens_out,
        tokens_cache=capture.tokens_cache,
        model_name=get_llm_config_for_agent(settings, _LLM_TYPE).model,
    )


def _nested(payload: dict[str, Any], *path: str) -> Any:
    """Walk a dotted path through nested dicts, returning None if any hop misses."""
    current: Any = payload
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _extract_call_seconds(payload: dict[str, Any]) -> Decimal | None:
    raw = _nested(payload, "data", "metadata", "call_duration_secs")
    if raw is None:
        return None
    try:
        return Decimal(str(raw))
    except InvalidOperation, ValueError:
        return None


def _extract_transcript_summary(payload: dict[str, Any]) -> str:
    value = _nested(payload, "data", "analysis", "transcript_summary")
    return value if isinstance(value, str) else ""


def _extract_transcript_text(payload: dict[str, Any], limit: int = 4000) -> str:
    """Join the transcript turns to plain text for synthesis (never persisted)."""
    turns = _nested(payload, "data", "transcript")
    if not isinstance(turns, list):
        return ""
    lines: list[str] = []
    for turn in turns:
        if not isinstance(turn, dict):
            continue
        message = turn.get("message") or turn.get("text") or ""
        if message:
            lines.append(f"{turn.get('role', '')}: {message}".strip())
    return "\n".join(lines)[:limit]


def _extract_structured(payload: dict[str, Any]) -> StructuredCallData:
    """Map ElevenLabs data-collection results to the minimized StructuredCallData.

    Defensive: a wrongly-typed collected value (e.g. ``agreed="maybe"``) must not
    lose the whole return — it degrades to an empty StructuredCallData.
    """
    raw = _nested(payload, "data", "analysis", "data_collection_results")
    if not isinstance(raw, dict):
        return StructuredCallData()
    flat = {k: (v.get("value") if isinstance(v, dict) else v) for k, v in raw.items()}
    try:
        return StructuredCallData.model_validate(flat)  # extra="ignore" drops unknown keys
    except ValidationError as exc:
        # Log only the error TYPE — a ValidationError message embeds the offending
        # input value, which could be a collected detail (location/notes) → PII.
        logger.warning("telephony_structured_data_invalid", error_type=type(exc).__name__)
        return StructuredCallData()


def _map_status(payload: dict[str, Any]) -> PhoneCallStatus:
    """Map the webhook payload to a terminal call status (spike: confirm values)."""
    status = str(_nested(payload, "data", "status") or "").lower()
    reason = str(_nested(payload, "data", "metadata", "termination_reason") or "").lower()
    if "voicemail" in status or "voicemail" in reason:
        return PhoneCallStatus.VOICEMAIL
    if "no_answer" in reason or "no-answer" in reason or "unanswered" in reason:
        return PhoneCallStatus.NO_ANSWER
    if status in ("failed", "error") or "failed" in reason:
        return PhoneCallStatus.FAILED
    # A post-call transcription webhook implies the call connected.
    return PhoneCallStatus.COMPLETED


def _derive_outcome(
    structured: StructuredCallData, status: PhoneCallStatus
) -> PhoneCallOutcome | None:
    """Derive the semantic outcome from the status + agreed flag."""
    if status in (PhoneCallStatus.NO_ANSWER, PhoneCallStatus.VOICEMAIL, PhoneCallStatus.FAILED):
        return PhoneCallOutcome.UNREACHABLE
    if structured.agreed is True:
        return PhoneCallOutcome.OBJECTIVE_MET
    if structured.agreed is False:
        return PhoneCallOutcome.DECLINED
    return PhoneCallOutcome.PARTIAL


# Deterministic English weekday — `%A` depends on the C locale (a documented
# trap). The model reasons in English on the ISO date, then writes its output in
# the user's language.
_EN_WEEKDAYS: Final = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)


def _current_datetime_line(user_timezone: str) -> str:
    """A 'now' the synthesis resolves relative dates against ('this weekend')."""
    now = datetime.now(ZoneInfo(user_timezone))
    return (
        f"CURRENT DATE AND TIME: {now.strftime('%Y-%m-%d %H:%M')} "
        f"({_EN_WEEKDAYS[now.weekday()]}), timezone {user_timezone}. Resolve every "
        "relative reference (today, this weekend, tomorrow) to an ABSOLUTE "
        "weekday + date against this."
    )


def _render_context(
    *,
    objective: str,
    callee_display: str,
    transcript_summary: str,
    transcript: str,
    structured: StructuredCallData,
    language: str,
    user_timezone: str,
) -> str:
    """Build the CONTEXT block (data as a HumanMessage — avoids .format brace traps)."""
    language_name = get_language_name(language)
    parts = [
        f"LANGUAGE: {language_name} ({language}). Write EVERYTHING you output "
        f"ENTIRELY in {language_name}.",
        _current_datetime_line(user_timezone),
        f"OBJECTIVE: {objective}",
        f"CALLEE: {callee_display}",
        f"SUMMARY: {transcript_summary or '(none provided)'}",
        "STRUCTURED OUTCOME:",
        f"- agreed: {structured.agreed if structured.agreed is not None else '(unknown)'}",
        f"- proposed_datetime: {structured.proposed_datetime or '(none)'}",
        f"- location: {structured.location or '(none)'}",
        f"- notes: {structured.notes or '(none)'}",
        f"- additional_costs: {structured.additional_costs or '(none)'}",
        f"- pending_user_decision: {structured.pending_user_decision or '(none)'}",
    ]
    if transcript:
        parts.append(f"TRANSCRIPT EXCERPT:\n{transcript}")
    return "\n".join(parts)


async def synthesize_return(
    *,
    transcript: str,
    transcript_summary: str,
    structured_data: StructuredCallData,
    objective: str,
    callee_display: str,
    user_language: str,
    user_timezone: str,
) -> tuple[ReturnProposal, _SynthUsage | None]:
    """Single tool-less LLM call → factual ``summary`` + first-person ``proposal_text``.

    Uses the ``telephony_synthesis`` LLM type + versioned prompt, routed through
    the central structured-output chokepoint ``get_structured_output_with_retry``
    (never a direct ``with_structured_output`` — AST-guarded): the chokepoint
    carries the provider constraints a raw call silently bypasses, notably
    DeepSeek V4 with thinking enabled, which rejects the forced ``tool_choice``
    with a 400 and must be served via the JSON-mode fallback (prod incident
    2026-07-29 — the fallback then delivered the raw English vendor summary).

    Token usage is captured via :class:`TokenCaptureHandler` (the chokepoint
    returns only the parsed model) so the caller can track spend (G-1); retried
    attempts accumulate into the same counters — they are paid too. The
    transcript is passed for context but is never persisted by the caller (D-8).

    Returns:
        The parsed proposal and the LLM token usage (``None`` when the provider
        reports none).
    """
    system = load_telephony_prompt("telephony_synthesis_prompt", "v1")
    context = _render_context(
        objective=objective,
        callee_display=callee_display,
        transcript_summary=transcript_summary,
        transcript=transcript,
        structured=structured_data,
        language=user_language,
        user_timezone=user_timezone,
    )
    llm = get_llm(_LLM_TYPE)
    provider = get_llm_config_for_agent(settings, _LLM_TYPE).provider
    token_capture = TokenCaptureHandler()
    proposal = await get_structured_output_with_retry(
        llm=llm,
        messages=[SystemMessage(content=system), HumanMessage(content=context)],
        schema=ReturnProposal,
        provider=provider,
        node_name=_LLM_TYPE,
        config=RunnableConfig(callbacks=[token_capture]),
    )
    return proposal, _capture_to_usage(token_capture)


def build_appointment_suggestion(
    *,
    structured: StructuredCallData,
    status: PhoneCallStatus,
    language: str,
    user_timezone: str,
) -> str | None:
    """Deterministic actionable line derived from the extracted call outcome (P14).

    Gate: the call COMPLETED, the callee AGREED, and ``proposed_datetime``
    parses as ISO-8601 (defensive — the extraction is LLM-shaped). A naive
    datetime is interpreted in the user's timezone; an aware one is converted
    to it. Rendered as unambiguous ``YYYY-MM-DD HH:MM`` local time.

    The line invites the user to confirm the calendar action in chat — the
    next turn flows through the normal pipeline (HITL draft included), so no
    parallel draft infrastructure is needed here.

    Args:
        structured: Minimized structured outcome extracted from the call.
        status: Final call status.
        language: User language for the localized phrase.
        user_timezone: IANA timezone name from the user profile.

    Returns:
        The localized suggestion line, or None when the gate is closed.
    """
    if status is not PhoneCallStatus.COMPLETED or structured.agreed is not True:
        return None
    raw = structured.proposed_datetime
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None

    try:
        tz = ZoneInfo(user_timezone)
    except KeyError, ValueError, TypeError:
        tz = ZoneInfo(DEFAULT_USER_DISPLAY_TIMEZONE)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tz)
    datetime_local = parsed.astimezone(tz).strftime("%Y-%m-%d %H:%M")

    phrases = get_return_phrases(language)
    location_part = (
        phrases["appointment_location_part"].format(location=structured.location)
        if structured.location
        else ""
    )
    return phrases["appointment_suggestion"].format(
        datetime_local=datetime_local, location_part=location_part
    )


def _user_display_timezone(user: User | None) -> str:
    """Resolve the user's IANA timezone with the platform default fallback.

    Hoisted out of ``process_completed_call`` to keep that function under the
    CC-15 ratchet (the ``or`` fallback is a branch).
    """
    return getattr(user, "timezone", None) or DEFAULT_USER_DISPLAY_TIMEZONE


def compose_delivery_text(
    *,
    proposal_text: str,
    structured: StructuredCallData,
    status: PhoneCallStatus,
    language: str,
    user_timezone: str,
) -> str:
    """Append the appointment suggestion to the first-person report (P14).

    Best-effort by contract: any failure in the suggestion helper degrades to
    the plain proposal — the return delivery must never be lost over a bonus
    line.

    Args:
        proposal_text: First-person report from the synthesis (or fallback).
        structured: Minimized structured outcome extracted from the call.
        status: Final call status.
        language: User language.
        user_timezone: IANA timezone name from the user profile.

    Returns:
        The delivery text (proposal, possibly followed by the suggestion).
    """
    try:
        suggestion = build_appointment_suggestion(
            structured=structured,
            status=status,
            language=language,
            user_timezone=user_timezone,
        )
    except Exception as exc:  # noqa: BLE001 — bonus line, never lose the return
        logger.warning("telephony_appointment_suggestion_failed", error=str(exc))
        return proposal_text
    if not suggestion:
        return proposal_text
    return f"{proposal_text}\n\n{suggestion}"


async def _synthesize_with_fallback(
    *,
    call_id: UUID,
    transcript: str,
    transcript_summary: str,
    structured: StructuredCallData,
    objective: str,
    callee_display: str,
    language: str,
    user_timezone: str,
    fallback_phrase: str,
) -> tuple[ReturnProposal, _SynthUsage | None]:
    """Run the synthesis; a failure degrades to the plain-summary proposal.

    Extracted from ``process_completed_call`` (CC discipline). The fallback
    proposal is intentionally debrief-empty — it persists as NULL downstream.
    """
    try:
        return await synthesize_return(
            transcript=transcript,
            transcript_summary=transcript_summary,
            structured_data=structured,
            objective=objective,
            callee_display=callee_display,
            user_language=language,
            user_timezone=user_timezone,
        )
    except Exception as exc:  # noqa: BLE001 — synthesis must not lose the call
        logger.warning("telephony_synthesis_failed", call_id=str(call_id), error=str(exc))
        fallback = transcript_summary or fallback_phrase
        return ReturnProposal(summary=transcript_summary or "", proposal_text=fallback), None


async def _track_synthesis_usage(
    usage: _SynthUsage | None, *, call_id: UUID, user_id: UUID
) -> None:
    """Best-effort proactive-token tracking (G-1) — never loses the delivery.

    Extracted from ``process_completed_call`` (CC discipline).
    """
    if usage is None:
        return
    try:
        await track_proactive_tokens(
            user_id=user_id,
            task_type=_TASK_TYPE,
            target_id=str(call_id),
            conversation_id=None,
            tokens_in=usage.tokens_in,
            tokens_out=usage.tokens_out,
            tokens_cache=usage.tokens_cache,
            model_name=usage.model_name,
        )
    except Exception as exc:  # noqa: BLE001 — tracking must not lose the delivery
        logger.warning("telephony_token_tracking_failed", call_id=str(call_id), error=str(exc))


async def process_completed_call(call_id: UUID, payload: dict[str, Any]) -> None:
    """Reconcile a finished call, synthesize the return, persist + deliver it.

    Idempotent: the terminal transition is an atomic conditional UPDATE
    (:meth:`TelephonyRepository.mark_completed`); a duplicated webhook that loses
    the race delivers nothing. Only ``summary`` + ``structured_data`` are stored.
    """
    async with get_db_context() as db:
        repo = TelephonyRepository(db)
        call = await repo.get_by_call_id(call_id)
        if call is None or call.status not in _ACTIVE:
            return  # unknown or already processed

        status = _map_status(payload)
        call_seconds = _extract_call_seconds(payload)
        transcript_summary = _extract_transcript_summary(payload)
        transcript = _extract_transcript_text(payload)
        structured = _extract_structured(payload)

        user = await db.get(User, call.user_id)
        language = user.language if user else settings.default_language
        user_timezone = _user_display_timezone(user)
        phrases = get_return_phrases(language)

        proposal, usage = await _synthesize_with_fallback(
            call_id=call_id,
            transcript=transcript,
            transcript_summary=transcript_summary,
            structured=structured,
            objective=call.objective,
            callee_display=call.callee_display,
            language=language,
            user_timezone=user_timezone,
            fallback_phrase=phrases["fallback"],
        )

        # P14 — append the deterministic appointment suggestion BEFORE arming
        # the outbox record, so every delivery path (dispatch + reaper) carries it.
        delivery_text = compose_delivery_text(
            proposal_text=proposal.proposal_text,
            structured=structured,
            status=status,
            language=language,
            user_timezone=user_timezone,
        )

        # T01: an all-empty debrief (synthesis fallback, or a call with nothing
        # actionable) persists as NULL — absence, not noise.
        debrief = proposal.debrief_dict()
        debrief_or_none = debrief if any(debrief.values()) else None

        claimed = await repo.mark_completed(
            call_id,
            status=status,
            call_seconds=call_seconds,
            summary=proposal.summary,
            structured_data=structured.model_dump(exclude_none=True),
            debrief=debrief_or_none,
            outcome=_derive_outcome(structured, status),
            completed_at=datetime.now(UTC),
            # T1: arm the return as a PENDING outbox record in the same atomic
            # transition, so a crash before the dispatch below cannot lose it.
            notification_content=delivery_text,
            notification_title=phrases["title"],
        )
        if not claimed:
            return  # lost the race — another worker already delivered

        # Track the synthesis LLM spend (G-1) — like briefing/heartbeat. Best-effort.
        await _track_synthesis_usage(usage, call_id=call_id, user_id=call.user_id)

        telephony_calls_total.labels(status=status.value).inc()
        if call_seconds is not None:
            telephony_call_duration_seconds.observe(float(call_seconds))

        if user is None:
            # No recipient (defensive — a CASCADE would normally remove the call):
            # close the outbox record so the reaper does not chase an undeliverable row.
            await repo.mark_notification_delivered(call_id)
            return

        try:
            await NotificationDispatcher().dispatch(
                user=user,
                content=delivery_text,
                task_type="phone_call",
                target_id=str(call_id),
                # T01: the structured debrief rides in the metadata so the chat
                # can render an actionable card (InterestNotificationCard
                # pattern) — same PII surface as the content it accompanies.
                metadata={
                    "call_status": status.value,
                    **({"debrief": debrief_or_none} if debrief_or_none else {}),
                },
                db=db,
                title=phrases["title"],
            )
        except Exception as exc:  # noqa: BLE001 — a dispatch failure must NOT lose the return
            # The call result + PENDING outbox record are already committed; leave
            # the notification PENDING and let the reaper re-dispatch it (T1). Do not
            # re-raise: deliver_return_with_retry would retry the whole flow, but
            # mark_completed is now terminal (returns False), so it could never
            # re-dispatch — the reaper is the single recovery path.
            logger.warning(
                "telephony_return_dispatch_failed",
                call_id=str(call_id),
                error_type=type(exc).__name__,
            )
            return

        await repo.mark_notification_delivered(call_id)
        logger.info("telephony_return_delivered", call_id=str(call_id), status=status.value)


async def deliver_return_with_retry(call_id: UUID, payload: dict[str, Any]) -> None:
    """Durable wrapper around :func:`process_completed_call` (T1).

    The post-call webhook fires this and returns 200 immediately; ElevenLabs
    delivers the payload only once. ``process_completed_call`` is idempotent (the
    terminal transition is an atomic conditional UPDATE), so retrying after a
    transient failure re-attempts the reconcile/synthesis/deliver without risking
    a double delivery — a second pass over an already-completed call returns
    early. This closes the window where a transient error *before*
    ``mark_completed`` would otherwise leave the call stuck in dialing/in_progress
    until the stale reaper marks it failed, losing the return entirely.

    Durability envelope: the task is held in the background-task set and awaited
    at graceful shutdown (``wait_all_background_tasks``). A hard crash mid-flight
    is not recoverable — the raw transcript is never persisted (D-8) — but the
    stale-call reaper still frees the one-active-call slot.

    Only the exception TYPE is logged (an exception message may embed call data).
    """
    max_attempts = max(1, settings.telephony_return_max_attempts)
    delay = settings.telephony_return_retry_delay_seconds
    for attempt in range(1, max_attempts + 1):
        try:
            await process_completed_call(call_id, payload)
            return
        except Exception as exc:  # noqa: BLE001 — a transient failure must not lose the return
            logger.warning(
                "telephony_return_attempt_failed",
                call_id=str(call_id),
                attempt=attempt,
                max_attempts=max_attempts,
                error_type=type(exc).__name__,
            )
            if attempt < max_attempts and delay > 0:
                await asyncio.sleep(delay)
    logger.error(
        "telephony_return_gave_up",
        call_id=str(call_id),
        attempts=max_attempts,
    )
