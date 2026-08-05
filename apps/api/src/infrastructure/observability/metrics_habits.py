"""Prometheus metrics for the learned-habits subsystem (ADR-214).

The nightly profile job and the habit-row sync are batch work: without
metrics, a silently failing recompute would leave every profile stale and
nothing would notice until a user asked why their habits stopped updating.

All metrics are best-effort: incrementing them must never break the job.
"""

from __future__ import annotations

from prometheus_client import Counter, Histogram

habit_profile_users_total = Counter(
    "habit_profile_users_total",
    "Outcome of each per-user nightly profile recompute. A sustained 'error' "
    "share means profiles are going stale; 'skipped_no_delta' is the healthy "
    "steady state for inactive accounts.",
    ["outcome"],
    # outcome: computed | skipped_no_delta | skipped_no_activity
    #          | skipped_user_disabled | error
)

habit_profile_job_seconds = Histogram(
    "habit_profile_job_seconds",
    "Wall-clock duration of one full nightly habit-profile job run.",
    buckets=(1, 5, 15, 30, 60, 120, 300, 600),
)

user_habits_synced_total = Counter(
    "user_habits_synced_total",
    "Habit-row sync actions performed by the nightly job.",
    ["action"],
    # action: created | updated | blocked | removed
)

heartbeat_ticks_deferred_total = Counter(
    "heartbeat_ticks_deferred_total",
    "Proactive heartbeat ticks deferred toward a learned rhythm window "
    "(ADR-214 tick scoring, own flag). A sustained surge with no matching "
    "in-window deliveries would mean the anti-starvation rule is broken.",
    ["day_class"],
    # day_class: weekday | weekend
)

habit_ambient_block_total = Counter(
    "habit_ambient_block_total",
    "Ambient rhythm-block presence per flow (portrait-counter precedent) — "
    "the observable trace of a prompt injection that has no debug section.",
    ["flow", "kind"],
    # kind: rhythm | unusual_hour | absence
)
