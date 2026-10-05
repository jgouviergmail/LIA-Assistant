"""Meeting notification costs keep native selection separate from generative synthesis."""

from __future__ import annotations

from typing import Any

from src.core.constants import MEETINGS_PROACTIVE_TASK_TYPE
from src.domains.meetings.models import Meeting
from src.domains.meetings.native_spend import selection_charges
from src.domains.meetings.synthesis import SynthesisUsage
from src.domains.meetings.transcription import TranscriptionOutcome
from src.infrastructure.cache.pricing_cache import get_cached_cost_usd_eur


def synthesis_cost_eur(usage: SynthesisUsage) -> float | None:
    """Return frozen synthesis cost, or the legacy aggregate's administered cost.

    A model without an administered price remains unknown rather than free
    (ADR-185). A pass that spent no token costs an exact zero.
    """
    if usage.billing_records:
        return sum(record.cost_eur for record in usage.billing_records)
    spent = usage.tokens_in + usage.tokens_out + usage.tokens_cache
    if spent == 0:
        return 0.0
    _usd, eur = get_cached_cost_usd_eur(
        model=usage.model_name,
        prompt_tokens=usage.tokens_in,
        completion_tokens=usage.tokens_out,
        cached_tokens=usage.tokens_cache,
        cache_write_tokens=usage.tokens_cache_write,
    )
    return eur if eur > 0 else None


async def track_legacy_synthesis_usage(
    db: Any, meeting: Meeting, usage: SynthesisUsage, *, run_id: str
) -> None:
    """Account aggregates only when no per-attempt capture already owns the spend."""
    from src.infrastructure.proactive.tracking import track_proactive_tokens

    if usage.billing_records or not (usage.tokens_in or usage.tokens_out or usage.tokens_cache):
        return
    await track_proactive_tokens(
        user_id=meeting.user_id,
        task_type=MEETINGS_PROACTIVE_TASK_TYPE,
        target_id=str(meeting.id),
        conversation_id=None,
        tokens_in=usage.tokens_in,
        tokens_out=usage.tokens_out,
        tokens_cache=usage.tokens_cache,
        tokens_cache_write=usage.tokens_cache_write,
        billing_records=usage.billing_records,
        model_name=usage.model_name,
        db=db,
        run_id=run_id,
        source="user",
    )


def cost_metadata(
    meeting: Meeting,
    outcome: TranscriptionOutcome,
    usage: SynthesisUsage,
    *,
    run_id: str | None = None,
) -> dict[str, Any]:
    """The paid units of the exchange, in the shape the chat bubble reads.

    ``tokens_*``, ``model_name`` and ``cost_eur`` are the runner's standard keys
    (``cost_eur`` = everything this exchange cost); the ``stt_*`` and
    ``llm_cost_eur`` keys give the card its breakdown. An unknown price stays
    None rather than counting as zero.
    """
    llm_cost = meeting.synthesis_cost_eur
    charges = [
        charge for charge in selection_charges(meeting) if run_id is None or charge.run_id == run_id
    ]
    selection_cost = sum(charge.cost_eur for charge in charges) if charges else None
    priced = [c for c in (outcome.cost_eur, llm_cost, selection_cost) if c is not None]
    return {
        "tokens_in": usage.tokens_in + sum(charge.input_tokens for charge in charges),
        "tokens_out": usage.tokens_out + sum(charge.output_tokens for charge in charges),
        "tokens_cache": usage.tokens_cache,
        "model_name": usage.model_name,
        "llm_cost_eur": llm_cost,
        "selection_cost_eur": selection_cost,
        "template_selection_usage": [charge.model_dump(mode="json") for charge in charges],
        "stt_cost_eur": outcome.cost_eur,
        "stt_audio_duration_seconds": outcome.audio_duration_seconds,
        "stt_model": outcome.model,
        "cost_eur": round(sum(priced), 6) if priced else None,
    }
