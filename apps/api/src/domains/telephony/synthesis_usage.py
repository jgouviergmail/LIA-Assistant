"""The synthesis LLM spend of a call, recorded like every other proactive call (G-1).

Shared by the third-party return and the owner relay: one record shape, one
tracking door, one subtraction of the cached tokens.
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


def capture_to_usage(capture: TokenCaptureHandler) -> SynthUsage | None:
    """Convert the captured callback counters to the billable usage record.

    Mirrors the briefing pipeline: subtract cached from input to expose the
    non-cached billable count. Returns None when the provider reported no
    usage at all.
    """
    if not capture.has_usage:
        return None
    return SynthUsage(
        tokens_in=max(capture.tokens_in - capture.tokens_cache, 0),
        tokens_out=capture.tokens_out,
        tokens_cache=capture.tokens_cache,
        model_name=get_llm_config_for_agent(settings, _LLM_TYPE).model,
    )


async def track_synthesis_usage(usage: SynthUsage | None, *, call_id: UUID, user_id: UUID) -> None:
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
            source="user",
            # Lot 8: the call's own run id, shared with its live lookups and
            # its relayed turn, so one summary row holds the whole bill.
            run_id=phone_call_run_id(call_id),
        )
    except Exception as exc:  # noqa: BLE001 — tracking must not lose the delivery
        logger.warning("telephony_token_tracking_failed", call_id=str(call_id), error=str(exc))


__all__ = ["SynthUsage", "capture_to_usage", "track_synthesis_usage"]
