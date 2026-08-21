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

from prometheus_client import Counter

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
