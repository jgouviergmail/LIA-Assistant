"""What one LLM call consumed, in one shape.

Tokens and euros for a single call, surfaced beside whatever that call produced
so a reader can see what the answer in front of them cost.

It lived in ``domains/briefing/schemas`` while the Today dashboard was the only
surface showing it. The relationship debrief shows the same thing beside the
same kind of artefact, and had grown its own byte-identical holder — a second
vocabulary for one concept, which is how two surfaces come to report a cost
differently.

Here rather than in either domain: ``core`` is imported by everything, so no
domain has to create an edge to another to describe a cost (the argument
``resolve_user_timezone`` and ``prompt_store`` already settled).

It is a DISPLAY summary, never an accounting record. ``token_usage_logs`` is
the record — one row per call, retained past account deletion, and one of the
five sources the Article-12 extraction composes. Anything that needs to ADD
costs up reads that; this only ever describes the one call beside it.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class LLMUsage(BaseModel):
    """Token usage + EUR cost summary for a single LLM call."""

    model_config = ConfigDict(frozen=True)

    tokens_in: int = Field(0, ge=0, description="Input/prompt tokens (excluding cached).")
    tokens_out: int = Field(0, ge=0, description="Output/completion tokens.")
    tokens_cache: int = Field(0, ge=0, description="Cached input tokens (when supported).")
    cost_eur: float = Field(
        0.0,
        ge=0.0,
        description="Computed cost in EUR using the active pricing cache.",
    )
    model_name: str | None = Field(None, description="Model identifier used for the call.")
