"""The call becomes a message: the relay synthesis of an owner call (lot 4).

After an owner call, the transcript is turned into the message the person
would have typed — first person, faithful, absolute dates, empty when there
is nothing to relay — plus a neutral summary for the calls list and the flag
that says whether the account holder was really on the line. The runner
(``relay_runner.py``) then hands that message to the chat as the person's
own turn.

Three rules, each a test:

- the transcript is projected under a TOKEN budget at TURN boundaries and the
  cut is stated to the model (ADR-286) — the third-party path cut at 4 000
  characters, sized for an errand, and a twenty-minute conversation would
  lose its end in silence;
- the model is reached through the ONE structured-output chokepoint with the
  call's owner named, so the account's ceiling applies (ADR-272);
- the spend is accounted (``track_proactive_tokens``, task type
  ``phone_call``, source ``user``: the person asked to be called).
"""

from __future__ import annotations

from typing import Any, Final, Literal
from uuid import UUID

import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from pydantic import ValidationError

from src.core.config import settings
from src.core.i18n import get_language_name
from src.core.llm_config_helper import get_llm_config_for_agent
from src.domains.telephony.budget import fit_lines
from src.domains.telephony.payload import (
    current_datetime_line,
    extract_transcript_summary,
    nested,
)
from src.domains.telephony.prompts.loader import load_telephony_prompt
from src.domains.telephony.schemas import SelfCallData, SelfCallRelay
from src.domains.telephony.synthesis_usage import SynthUsage, capture_to_usage
from src.infrastructure.llm.factory import get_llm
from src.infrastructure.llm.structured_output import get_structured_output_with_retry
from src.infrastructure.llm.token_capture import TokenCaptureHandler

logger = structlog.get_logger(__name__)

#: The same slot as the third-party synthesis: the same shape of task (a
#: transcript in, a few fields out), so no fifty-eighth LLM type.
_LLM_TYPE: Final[Literal["telephony_synthesis"]] = "telephony_synthesis"


def project_transcript(payload: dict[str, Any], *, budget_tokens: int) -> tuple[str, bool]:
    """The transcript as ``role: text`` lines, under a token budget.

    Args:
        payload: The post-call webhook payload.
        budget_tokens: What the projection may cost.

    Returns:
        The text and whether turns were left out.
    """
    turns = nested(payload, "data", "transcript")
    if not isinstance(turns, list):
        return "", False
    lines: list[str] = []
    for turn in turns:
        if not isinstance(turn, dict):
            continue
        message = str(turn.get("message") or turn.get("text") or "").strip()
        if message:
            lines.append(f"{turn.get('role', '')}: {message}".strip())
    if not lines:
        return "", False
    return fit_lines(lines, budget_tokens=budget_tokens)


def extract_self_data(payload: dict[str, Any]) -> SelfCallData:
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


def _render_context(
    *,
    objective: str,
    collected: SelfCallData,
    vendor_summary: str,
    transcript: str,
    transcript_cut: bool,
    language: str,
    user_timezone: str,
) -> str:
    """The CONTEXT block, as a HumanMessage f-string (no ``.format`` on data)."""
    language_name = get_language_name(language)
    transcript_heading = (
        "TRANSCRIPT (cut: the end of the call is not shown)" if transcript_cut else "TRANSCRIPT"
    )
    parts = [
        f"LANGUAGE: {language_name} ({language}). Write EVERY field ENTIRELY in {language_name}.",
        current_datetime_line(user_timezone),
        f"OBJECTIVE: {objective or '(a catch-up call)'}",
        "OWNER FLAGS:",
        f"- owner_confirmed (collected): {collected.owner_confirmed if collected.owner_confirmed is not None else '(unknown)'}",
        f"- requests (collected): {collected.requests or '(none)'}",
        f"VENDOR SUMMARY: {vendor_summary or '(none provided)'}",
        f"{transcript_heading}:\n{transcript or '(no transcript)'}",
    ]
    return "\n".join(parts)


async def synthesize_relay(
    *,
    payload: dict[str, Any],
    objective: str,
    user_language: str,
    user_timezone: str,
    user_id: UUID | None,
) -> tuple[SelfCallRelay, SynthUsage | None]:
    """One structured call: the transcript in, the relay message out.

    Args:
        payload: The post-call webhook payload (transcript, analysis).
        objective: What the call was about.
        user_language: Backend-canonical language of the output.
        user_timezone: The person's IANA zone, for the clock.
        user_id: The call's owner, so the account's ceiling applies.

    Returns:
        The relay and the token usage (None when the provider reported none).
    """
    transcript, cut = project_transcript(
        payload, budget_tokens=settings.telephony_relay_transcript_max_tokens
    )
    context = _render_context(
        objective=objective,
        collected=extract_self_data(payload),
        vendor_summary=extract_transcript_summary(payload),
        transcript=transcript,
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


__all__ = ["extract_self_data", "project_transcript", "synthesize_relay"]
