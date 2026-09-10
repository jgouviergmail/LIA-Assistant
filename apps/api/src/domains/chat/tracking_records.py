"""The in-memory shapes a :class:`TrackingContext` aggregates before persistence.

One record per billable event -- an LLM call, an image generation, a Google API
call, a TTS synthesis -- accumulated in memory during a run and flushed to the
database once, at the end. They live apart from the service because they are a
data contract: ``run_records`` and the debug panel read them, and the service
that fills them has no business owning their shape.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, NamedTuple


class TokenUsageRecord(NamedTuple):
    """
    In-memory record of token usage for a single LLM node call.

    Used by TrackingContext to aggregate tokens before DB persistence.
    """

    node_name: str
    model_name: str
    prompt_tokens: int
    completion_tokens: int
    cached_tokens: int
    cost_usd: float
    cost_eur: float
    usd_to_eur_rate: Decimal
    # Duration tracking for debug panel (v3.2)
    duration_ms: float = 0.0
    # Call type for debug panel pipeline reconciliation (v3.3)
    call_type: str = "chat"  # "chat" | "embedding"
    # Monotonic sequence counter for chronological ordering (v3.3)
    sequence: int = 0
    # Start position on the RUN timeline in ms (v3.4 debug-panel waterfall).
    # Anchored on the run-level t0 shared by every TrackingContext of the
    # run — the per-context `sequence` cannot order calls across contexts.
    started_offset_ms: float = 0.0
    # Observation fields (ADR-244) — persisted to token_usage_logs so a policy
    # can judge a model on objective facts rather than on inferred quality.
    llm_type: str | None = None
    status: str | None = None
    failure_kind: str | None = None
    # The parameters actually SENT (ADR-263 lot 7). Normalised to one
    # vocabulary — three providers spell the output cap three ways — and read
    # from what LangChain hands the callback, which is the only one of LIA's
    # three answers that survives a later configuration change.
    provider: str | None = None
    temperature: float | None = None
    top_p: float | None = None
    max_output_tokens: int | None = None
    reasoning_level: str | None = None
    reasoning_budget_tokens: int | None = None
    params_digest: str | None = None


class ImageGenerationRecord(NamedTuple):
    """
    In-memory record of an image generation call (immutable).

    Used by TrackingContext to aggregate image generation costs before DB persistence.
    Mirrors GoogleApiRecord pattern for consistency.

    Attributes:
        model: Image generation model used (e.g., "gpt-image-1").
        quality: Quality level used (e.g., "medium").
        size: Image dimensions used (e.g., "1024x1024").
        image_count: Number of images generated.
        cost_usd: Total cost in USD for this call.
        cost_eur: Total cost in EUR for this call.
        usd_to_eur_rate: Exchange rate used.
        prompt_preview: First 200 characters of the prompt (for audit).
    """

    model: str
    quality: str
    size: str
    image_count: int
    cost_usd: Decimal
    cost_eur: Decimal
    usd_to_eur_rate: Decimal
    prompt_preview: str
    duration_ms: float = 0.0
    # Start position on the run timeline in ms (debug-panel waterfall).
    started_offset_ms: float = 0.0


class GoogleApiRecord(NamedTuple):
    """
    In-memory record of a Google API call (immutable).

    Used by TrackingContext to aggregate Google API usage before DB persistence.
    Mirrors TokenUsageRecord pattern for consistency.
    """

    api_name: str
    endpoint: str
    cost_usd: Decimal
    cost_eur: Decimal
    usd_to_eur_rate: Decimal
    cached: bool = False


class TTSUsageRecord(NamedTuple):
    """
    In-memory record of a TTS synthesis call (immutable).

    Mirrors STT cost attribution but on the assistant bubble: each call adds
    one row to the in-memory list and the aggregate is later persisted on
    ``conversation_messages.tts_*`` columns by ``archive_message``. Edge TTS
    (free) does NOT call ``record_tts_call`` — its row stays NULL.
    """

    provider: str
    model: str
    characters: int
    cost_usd: Decimal
    cost_eur: Decimal
    usd_to_eur_rate: Decimal
    duration_ms: float = 0.0


def breakdown_entry(record: TokenUsageRecord) -> dict[str, Any]:
    """One model call, as the debug panel reads it.

    Beside the record rather than inside the tracking context: describing a
    record is the record's own subject, and the context is at its size ceiling.

    Every key is present on EVERY call, ``None`` where nothing was observed
    (B8): a key present on one row and absent on another makes the panel's rows
    disagree about what a row is, and a DEFAULT printed where nothing was
    measured would name a value the provider never saw.

    Args:
        record: One committed call of the run.

    Returns:
        The entry, carrying what was billed, what was SENT and what came back.
    """
    return {
        "node_name": record.node_name,
        "model_name": record.model_name,
        "tokens_in": record.prompt_tokens,
        "tokens_out": record.completion_tokens,
        "tokens_cache": record.cached_tokens,
        "cost_eur": float(record.cost_eur),
        "duration_ms": record.duration_ms,
        "call_type": record.call_type,
        "sequence": record.sequence,
        "started_offset_ms": record.started_offset_ms,
        # The configured SLOT — the graph node says WHERE it ran, never WHICH
        # configuration.
        "llm_type": record.llm_type,
        "status": record.status,
        "failure_kind": record.failure_kind,
        # The parameters actually SENT (ADR-263 lot 7), read from what LangChain
        # handed the callback.
        "provider": record.provider,
        "temperature": record.temperature,
        "top_p": record.top_p,
        "max_output_tokens": record.max_output_tokens,
        "reasoning_level": record.reasoning_level,
        "reasoning_budget_tokens": record.reasoning_budget_tokens,
        "params_digest": record.params_digest,
    }
