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

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Final, Literal
from uuid import UUID

import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import ValidationError

from src.core.config import settings
from src.core.i18n_telephony import get_return_phrases
from src.core.llm_config_helper import get_llm_config_for_agent
from src.domains.agents.prompts.prompt_loader import load_prompt
from src.domains.telephony.models import PhoneCallOutcome, PhoneCallStatus
from src.domains.telephony.repository import TelephonyRepository
from src.domains.telephony.schemas import ReturnProposal, StructuredCallData
from src.domains.users.models import User
from src.infrastructure.database.session import get_db_context
from src.infrastructure.llm.factory import get_llm
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


def _extract_usage(raw: Any) -> _SynthUsage | None:
    """Extract billable token usage from the structured-output raw AIMessage.

    Mirrors the briefing pipeline: subtract cached from input to expose the
    non-cached billable count. Returns None when the provider reports no usage.
    """
    if raw is None:
        return None
    raw_usage = getattr(raw, "usage_metadata", None) or {}
    if not raw_usage:
        return None
    raw_input = int(raw_usage.get("input_tokens", 0) or 0)
    tokens_out = int(raw_usage.get("output_tokens", 0) or 0)
    tokens_cache = int(
        raw_usage.get("cache_read_input_tokens", 0)
        or raw_usage.get("input_token_details", {}).get("cache_read", 0)
        or 0
    )
    return _SynthUsage(
        tokens_in=max(raw_input - tokens_cache, 0),
        tokens_out=tokens_out,
        tokens_cache=tokens_cache,
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
    except (InvalidOperation, ValueError):
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


def _render_context(
    *,
    objective: str,
    callee_display: str,
    transcript_summary: str,
    transcript: str,
    structured: StructuredCallData,
    language: str,
) -> str:
    """Build the CONTEXT block (data as a HumanMessage — avoids .format brace traps)."""
    parts = [
        f"LANGUAGE: {language}",
        f"OBJECTIVE: {objective}",
        f"CALLEE: {callee_display}",
        f"SUMMARY: {transcript_summary or '(none provided)'}",
        "STRUCTURED OUTCOME:",
        f"- agreed: {structured.agreed if structured.agreed is not None else '(unknown)'}",
        f"- proposed_datetime: {structured.proposed_datetime or '(none)'}",
        f"- location: {structured.location or '(none)'}",
        f"- notes: {structured.notes or '(none)'}",
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
) -> tuple[ReturnProposal, _SynthUsage | None]:
    """Single tool-less LLM call → factual ``summary`` + first-person ``proposal_text``.

    Uses the ``telephony_synthesis`` LLM type + versioned prompt with structured
    output (no domain tools). ``include_raw`` surfaces the underlying AIMessage so
    the caller can track token usage (G-1). The transcript is passed for context
    but is never persisted by the caller (D-8).

    Returns:
        The parsed proposal and the LLM token usage (``None`` when the provider
        reports none, or when a non-``include_raw`` response is returned in tests).
    """
    system = load_prompt("telephony_synthesis_prompt", "v1")
    context = _render_context(
        objective=objective,
        callee_display=callee_display,
        transcript_summary=transcript_summary,
        transcript=transcript,
        structured=structured_data,
        language=user_language,
    )
    llm = get_llm(_LLM_TYPE)
    structured_llm = llm.with_structured_output(ReturnProposal, include_raw=True)
    result = await structured_llm.ainvoke(
        [SystemMessage(content=system), HumanMessage(content=context)]
    )

    if isinstance(result, dict):  # include_raw shape: {"raw", "parsed", "parsing_error"}
        parsed = result.get("parsed")
        usage = _extract_usage(result.get("raw"))
    else:  # defensive (tests / providers that ignore include_raw)
        parsed, usage = result, None

    proposal = (
        parsed if isinstance(parsed, ReturnProposal) else ReturnProposal.model_validate(parsed)
    )
    return proposal, usage


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
        phrases = get_return_phrases(language)

        usage: _SynthUsage | None = None
        try:
            proposal, usage = await synthesize_return(
                transcript=transcript,
                transcript_summary=transcript_summary,
                structured_data=structured,
                objective=call.objective,
                callee_display=call.callee_display,
                user_language=language,
            )
        except Exception as exc:  # noqa: BLE001 — synthesis must not lose the call
            logger.warning("telephony_synthesis_failed", call_id=str(call_id), error=str(exc))
            fallback = transcript_summary or phrases["fallback"]
            proposal = ReturnProposal(summary=transcript_summary or "", proposal_text=fallback)

        claimed = await repo.mark_completed(
            call_id,
            status=status,
            call_seconds=call_seconds,
            summary=proposal.summary,
            structured_data=structured.model_dump(exclude_none=True),
            outcome=_derive_outcome(structured, status),
            completed_at=datetime.now(UTC),
        )
        if not claimed:
            return  # lost the race — another worker already delivered

        # Track the synthesis LLM spend (G-1) — like briefing/heartbeat. Best-effort.
        if usage is not None:
            try:
                await track_proactive_tokens(
                    user_id=call.user_id,
                    task_type=_TASK_TYPE,
                    target_id=str(call_id),
                    conversation_id=None,
                    tokens_in=usage.tokens_in,
                    tokens_out=usage.tokens_out,
                    tokens_cache=usage.tokens_cache,
                    model_name=usage.model_name,
                )
            except Exception as exc:  # noqa: BLE001 — tracking must not lose the delivery
                logger.warning(
                    "telephony_token_tracking_failed", call_id=str(call_id), error=str(exc)
                )

        telephony_calls_total.labels(status=status.value).inc()
        if call_seconds is not None:
            telephony_call_duration_seconds.observe(float(call_seconds))

        if user is not None:
            await NotificationDispatcher().dispatch(
                user=user,
                content=proposal.proposal_text,
                task_type="phone_call",
                target_id=str(call_id),
                metadata={"call_status": status.value},
                db=db,
                title=phrases["title"],
            )
        logger.info("telephony_return_delivered", call_id=str(call_id), status=status.value)
