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
