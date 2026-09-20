"""Prometheus metrics for agentic telephony (outbound calls).

Covers:
- Terminal call outcomes (by status), incremented when a call reaches a terminal
  state (completed / no_answer / voicemail / failed / cancelled).
- Call duration (factual seconds — never converted to money, D-9).
- Post-call webhooks ignored by the foreign-filter (unknown/mismatched/forged),
  a security-relevant signal that must stay observable without logging PII.
"""

from __future__ import annotations

from prometheus_client import Counter, Histogram

telephony_calls_total = Counter(
    "telephony_calls_total",
    "Outbound calls that reached a terminal state, by status.",
    ["status"],
    # status: completed | no_answer | voicemail | failed | cancelled
)

telephony_call_duration_seconds = Histogram(
    "telephony_call_duration_seconds",
    "Billed-by-the-user call duration in seconds (factual, never metered to money).",
    buckets=(5.0, 15.0, 30.0, 60.0, 120.0, 300.0, 600.0, 1200.0),
)

telephony_webhook_ignored_total = Counter(
    "telephony_webhook_ignored_total",
    "Post-call webhooks dropped by the foreign-filter / signature check.",
    ["reason"],
    # reason: unknown_call | agent_mismatch | bad_signature | malformed
)

telephony_notification_recovered_total = Counter(
    "telephony_notification_recovered_total",
    "Return notifications recovered by the reaper after a crash left them PENDING (T1).",
    ["result"],
    # result: delivered | failed (attempt cap reached) | skipped (no recipient)
)

telephony_return_recovered_total = Counter(
    "telephony_return_recovered_total",
    "Return syntheses replayed by the reaper after a crash stranded the RECEIVED "
    "inbox before completion (T1 approach A).",
    ["result"],
    # result: recovered (re-synthesized) | failed (decode/synthesis error this tick)
    #       | expired (past max-age, retired to FAILED + transcript purged)
)

telephony_relay_total = Counter(
    "telephony_relay_total",
    "Owner calls relayed into the chat as the person's own turn, by outcome (lot 4).",
    ["outcome"],
)

# The Live mode's delegation (ADR-301): one request the voice on the phone
# handed to LIA through ``send_to_lia``, by how it ended — the bridge's own
# vocabulary (answered | question | empty | superseded | timed_out | busy |
# quota_blocked | failed) plus the route's refusals (refused_call |
# refused_secret | refused_mode | refused_request).
telephony_delegations_total = Counter(
    "telephony_delegations_total",
    "Requests a Live owner call handed to LIA, by outcome (ADR-301).",
    ["outcome"],
)

telephony_delegation_duration_seconds = Histogram(
    "telephony_delegation_duration_seconds",
    "Seconds a Live owner call's delegation took, from the vendor's call-back to its answer (ADR-301).",
    buckets=(1, 2, 5, 10, 20, 30, 45, 60, 90, 120, 180),
)

# ``surface``: the voice the lookup served — the owner call (``phone_call``) or a
# direct live session (``live_session``, ADR-300 wave 4). Same rule, same door.
telephony_live_tool_calls_total = Counter(
    "telephony_live_tool_calls_total",
    "Live lookups a voice asked for — an owner call or a direct live session — by tool, outcome and surface (lot 7, ADR-300 wave 4).",
    ["tool", "outcome", "surface"],
    # tool: the allow-listed registry name, or "unknown" before one is resolved
    # outcome: ok | failed | timeout | budget_exceeded | refused_flag
    #        | refused_call | refused_secret | refused_tool | refused_mode
    # surface: phone_call | live_session
)

telephony_live_tool_duration_seconds = Histogram(
    "telephony_live_tool_duration_seconds",
    "Wall-clock duration of a live lookup run for a voice (lot 7, ADR-300 wave 4).",
    ["tool", "surface"],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0),
)
