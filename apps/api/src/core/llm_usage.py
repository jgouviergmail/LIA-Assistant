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

``LLMUsage`` is a DISPLAY summary. ``LLMBillingRecord`` is the internal bridge
from each priced provider attempt to the ledger: it retains the captured
tariff until persistence, and is excluded from the public display DTO.
``token_usage_logs`` remains the accounting record — one row per call, retained
past account deletion, and one of the five sources the Article-12 extraction
composes. The internal bridge never replaces that database record.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class LLMBillingRecord(BaseModel):
    """Internal, immutable price of one provider attempt at its UTC start."""

    model_config = ConfigDict(frozen=True)

    model_name: str
    started_at: float
    tokens_in: int = Field(ge=0)
    tokens_out: int = Field(ge=0)
    tokens_cache: int = Field(ge=0)
    tokens_cache_write: int = Field(0, ge=0)
    cost_usd: float = Field(ge=0)
    cost_eur: float = Field(ge=0)
    usd_to_eur_rate: float = Field(gt=0)
    status: Literal["success", "error"] = "success"
    failure_kind: str | None = None


class LLMUsage(BaseModel):
    """Token usage + EUR cost summary for a single LLM call."""

    model_config = ConfigDict(frozen=True)

    tokens_in: int = Field(0, ge=0, description="Input/prompt tokens (excluding cached).")
    tokens_out: int = Field(0, ge=0, description="Output/completion tokens.")
    tokens_cache: int = Field(0, ge=0, description="Cached input tokens (when supported).")
    tokens_cache_write: int = Field(
        0,
        ge=0,
        description=(
            "The part of tokens_in Claude wrote to its prompt cache, billed above "
            "the input price (ADR-306); already inside cost_eur."
        ),
    )
    cost_eur: float = Field(
        0.0,
        ge=0.0,
        description="Computed cost in EUR using the active pricing cache.",
    )
    model_name: str | None = Field(None, description="Model identifier used for the call.")
    billing_records: tuple[LLMBillingRecord, ...] = Field(default=(), exclude=True)
    accounting_handled: bool = Field(default=False, exclude=True)
