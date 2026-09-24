"""The synthesis LLM spend of a call, recorded like every other proactive call (G-1).

Shared by the third-party return and the owner relay: one record shape, one
tracking door. The capture already counts in the one reader's buckets (cache
reads removed from the input, ADR-306), so nothing is subtracted here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal
from uuid import UUID

import structlog

from src.core.config import settings
from src.core.llm_config_helper import get_llm_config_for_agent
from src.domains.telephony.spend import phone_call_run_id
from src.infrastructure.llm.token_capture import TokenCaptureHandler
from src.infrastructure.proactive.tracking import track_proactive_tokens

logger = structlog.get_logger(__name__)

_LLM_TYPE: Final[Literal["telephony_synthesis"]] = "telephony_synthesis"
_TASK_TYPE: Final = "phone_call"


@dataclass(frozen=True)
class SynthUsage:
    """Token usage of the synthesis LLM call, for proactive token tracking (G-1)."""

    tokens_in: int
    tokens_out: int
    tokens_cache: int
    model_name: str
    #: The part of ``tokens_in`` Claude wrote to its prompt cache (ADR-306).
    tokens_cache_write: int = 0


def capture_to_usage(capture: TokenCaptureHandler) -> SynthUsage | None:
    """Convert the captured callback counters to the billable usage record.

    The capture already reports the non-cached billable input (the one
    reader's buckets). Returns None when the provider reported no usage at all.
    """
    if not capture.has_usage:
        return None
    return SynthUsage(
        tokens_in=capture.tokens_in,
        tokens_out=capture.tokens_out,
        tokens_cache=capture.tokens_cache,
        model_name=get_llm_config_for_agent(settings, _LLM_TYPE).model,
        tokens_cache_write=capture.tokens_cache_write,
    )


async def track_synthesis_usage(usage: SynthUsage | None, *, call_id: UUID, user_id: UUID) -> None:
    """Best-effort proactive-token tracking (G-1) — never loses the delivery.

    Extracted from ``process_completed_call`` (CC discipline). The phone's
    door: the call's own run id, shared with its live lookups and its relayed
    turn, so one summary row holds the whole bill (lot 8).
    """
    await track_voice_synthesis_usage(
        usage,
        user_id=user_id,
        task_type=_TASK_TYPE,
        target_id=str(call_id),
        run_id=phone_call_run_id(call_id),
    )


async def track_voice_synthesis_usage(
    usage: SynthUsage | None, *, user_id: UUID, task_type: str, target_id: str, run_id: str
) -> None:
    """The ONE accountant of a relay synthesis, whichever carrier (ADR-301).

    Args:
        usage: What the provider reported; None records nothing.
        user_id: The account the synthesis ran for.
        task_type: The surface (``phone_call``, ``live_session``).
        target_id: The call or the session.
        run_id: The run the euros are filed under — the carrier's own, so the
            session's card and the calls listing read one row.
    """
    if usage is None:
        return
    try:
        await track_proactive_tokens(
            user_id=user_id,
            task_type=task_type,
            target_id=target_id,
            conversation_id=None,
            tokens_in=usage.tokens_in,
            tokens_out=usage.tokens_out,
            tokens_cache=usage.tokens_cache,
            tokens_cache_write=usage.tokens_cache_write,
            model_name=usage.model_name,
            source="user",
            run_id=run_id,
        )
    except Exception as exc:  # noqa: BLE001 — tracking must not lose the delivery
        logger.warning(
            "telephony_token_tracking_failed", target_id=target_id, error_type=type(exc).__name__
        )


__all__ = [
    "SynthUsage",
    "capture_to_usage",
    "track_synthesis_usage",
    "track_voice_synthesis_usage",
]
