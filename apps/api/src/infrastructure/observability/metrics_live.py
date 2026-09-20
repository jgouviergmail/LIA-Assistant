"""Prometheus metrics for the live voice mode (ADR-299).

Counts and durations only — never a token of the provider (owner directive
2026-09-16). Every metric here is drawn on dashboard ``30-live.json``; the
coverage ratchet refuses a blind one.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

live_mint_total = Counter(
    "live_mint_total",
    "Ephemeral-credential mints, by outcome (a reconnection mints one too).",
    ["provider", "outcome"],
    # outcome: ok | connector_missing | session_in_progress | instance_busy |
    #          rate_limited | provider_error
)

live_sessions_total = Counter(
    "live_sessions_total",
    "Live sessions that ended, by outcome (the client's own statement).",
    ["provider", "outcome"],
)

live_tool_calls_total = Counter(
    "live_tool_calls_total",
    "Lookups a DIRECT live session asked the API for (ADR-300 wave 4), by provider and outcome: "
    "ok, refused_mode (not a direct session), refused_tool (not declared or switched off), "
    "budget_exceeded.",
    ["provider", "outcome"],
)

live_sessions_active = Gauge(
    "live_sessions_active",
    "Live sessions currently claimed on this instance (pruned sorted set).",
)

# A DIRECT session's words relayed into the chat at its end (ADR-301), by
# outcome — the phone's ``telephony_relay_total`` vocabulary, on the browser.
live_direct_relay_total = Counter(
    "live_direct_relay_total",
    "Direct live sessions relayed into the chat as the person's own turn, by outcome (ADR-301).",
    ["outcome"],
)

live_session_duration_seconds = Histogram(
    "live_session_duration_seconds",
    "Duration of an ended live session.",
    buckets=(30.0, 60.0, 120.0, 300.0, 600.0, 1200.0, 1800.0, 3600.0),
)

live_session_extensions_total = Counter(
    "live_session_extensions_total",
    "Extensions of a live session past its cap: `explicit` on the person's word, "
    "`rolling` when a model with no cap renews its slice in silence (owner decisions 2026-09-19).",
    ["provider", "kind"],
)

live_voice_samples_total = Counter(
    "live_voice_samples_total",
    "Voice samples synthesised on the person's own key, by outcome (never a token counted).",
    ["provider", "outcome"],
    # outcome: ok | voice_unknown | connector_missing | rate_limited | provider_error
)

live_offer_exchanges_total = Counter(
    "live_offer_exchanges_total",
    "SDP offers exchanged on the person's key for an offer connection (GPT-Live), by outcome.",
    ["provider", "outcome"],
    # outcome: ok | refused (bad or used nonce, not an offer provider) | provider_error
)

live_turns_archived_total = Counter(
    "live_turns_archived_total",
    "Voice-only exchanges archived into the conversation, by role.",
    ["role"],
)
