"""Prometheus metrics for Google push channels (lot H, 2026-08).

Covers the two operational surfaces of the push subsystem:
- Notification outcomes on the public webhook — the ignored buckets
  (unknown / bad_token) are a security-relevant signal that must stay
  observable without logging PII.
- Watch ensure/renew sweep results, so a silently failing sync job (expired
  domain verification, revoked credentials) is visible before every channel
  has lapsed back to polling.
"""

from __future__ import annotations

from prometheus_client import Counter, Histogram

push_notifications_total = Counter(
    "push_notifications_total",
    "Google push notifications received, by provider and processing outcome.",
    ["provider", "outcome"],
    # provider: google_calendar | google_drive | google_gmail | unparsed
    # outcome: NotificationOutcome values (processed | sync_ack | debounced |
    #          ignored_unknown | ignored_bad_token | ignored_stale)
)

push_channel_sync_total = Counter(
    "push_channel_sync_total",
    "Per-user watch ensure attempts of the sync job, by result.",
    ["result"],
    # result: ensured | error
)

# ADR-261 — push-driven heartbeat wake. Every queued wake ends in exactly one
# outcome; "notified" is the only one that cost a decision AND produced a
# notification. A sustained "ineligible" share is the eligibility checker
# doing its job, not a defect; a sustained "error" share is.
push_wakes_total = Counter(
    "push_wakes_total",
    "Push-driven heartbeat wakes served by the sweep, per provider and outcome.",
    ["provider", "outcome"],
    # outcome: cooldown | source_disabled | stale | no_signal | ineligible
    #          | no_target | notified | reindexed | no_linked_folder | error
)

push_wake_latency_seconds = Histogram(
    "push_wake_latency_seconds",
    "Seconds between the push notification and the served wake decision.",
    buckets=(5, 15, 30, 60, 120, 180, 300, 600, 1800),
)

rag_drive_push_reindex_total = Counter(
    "rag_drive_push_reindex_total",
    "Drive push notifications turned into targeted reindexations of linked folders.",
    ["outcome"],
    # outcome: reindexed | no_linked_folder | locked | error
)
