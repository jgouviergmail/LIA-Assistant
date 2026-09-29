"""Meeting notification costs keep native selection separate from generative synthesis."""

from __future__ import annotations

from typing import Any

from src.domains.meetings.models import Meeting
from src.domains.meetings.native_spend import selection_charges
from src.domains.meetings.synthesis import SynthesisUsage
from src.domains.meetings.transcription import TranscriptionOutcome


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
