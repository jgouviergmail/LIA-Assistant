"""What LIA writes to the providers' prompt caches, and how it shapes Claude's (ADR-362).

Apart from ``metrics_agents`` (frozen at its audited size), and apart from
``llm_tokens_consumed_total`` on purpose: a written token is already a prompt
token there, so a write counted as one more ``token_type`` would be counted
twice by every expression that sums that counter.
"""

from __future__ import annotations

from prometheus_client import Counter

from src.core.field_names import FIELD_NODE_NAME

#: Prompt tokens written to the provider's prompt cache. ``lifetime`` is
#: ``short`` (the provider's default: Claude's five minutes, billed 1.25x) or
#: ``extended`` (Claude's one hour, billed 2x).
llm_cache_write_tokens_total = Counter(
    "llm_cache_write_tokens_total",
    "Prompt tokens written to the provider's prompt cache, by lifetime",
    ["model", FIELD_NODE_NAME, "lifetime"],
)

#: A streamed Claude response whose START reported cache writes without their
#: lifetime breakdown: its writes are priced at the short rate, so an extended
#: one would be under-billed. Expected 0 — a client upgrade that changed the
#: stream's shape shows here first (``providers/anthropic_hooks``).
llm_cache_write_breakdown_missing_total = Counter(
    "llm_cache_write_breakdown_missing_total",
    "Streamed Claude responses reporting cache writes without their lifetime breakdown",
    ["model"],
)

#: Earlier-turn thinking blocks a Claude request carried back (``kept``: to the
#: model that wrote them, which keeps prior thinking without binding it) or
#: removed (``reason``: ``receiver_binds``, ``receiver_strips``,
#: ``receiver_undeclared``, ``other_model``, ``unknown_origin``, ``disabled``) --
#: ``providers/anthropic_thinking``. ``model`` is the request's model -- the
#: one a ``receiver_undeclared`` series asks to declare.
llm_prior_turn_thinking_blocks_total = Counter(
    "llm_prior_turn_thinking_blocks_total",
    "Earlier-turn thinking blocks a Claude request carried back or removed",
    ["model", "decision", "reason"],
)

__all__ = [
    "llm_cache_write_breakdown_missing_total",
    "llm_cache_write_tokens_total",
    "llm_prior_turn_thinking_blocks_total",
]
