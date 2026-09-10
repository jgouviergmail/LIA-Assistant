"""Prometheus metrics for the workboard (ADR-276).

Six instruments, and each answers a question an operator would otherwise have
to guess at:

- **is LIA getting through the board?** ``workboard_runs_total`` splits by
  OUTCOME, so a wall of ``skipped_quota`` reads as a ceiling and not as a
  broken feature — the distinction ADR-272 insists on, made visible.
- **how long does a ticket take?** ``workboard_run_duration_seconds``, whose
  buckets straddle the run timeout: a run that reaches the last bucket is one
  the reaper is about to take back.
- **is the chat being flooded?** ``workboard_notifications_total`` by event.
  Following is off by default (D6) precisely because nobody wants a board that
  talks; this is how that stays true.
- **does an approved action replay as approved?** ``workboard_replays_total``
  by result. A run replaying what the person confirmed on the ticket is let
  through only when the rebuilt draft is IDENTICAL to what they were shown
  (lot 7); a mismatch asks again, safely, and this counts how often that
  safety costs the person a second confirmation.
- **what do the hidden transcripts cost?** ``lia_hidden_run_rows`` and
  ``lia_hidden_run_bytes``. The owner accepted archiving a run's rows instead
  of dropping them, on the condition that the volume be WATCHED rather than
  assumed — the same arbitration, and the same instrument, as the registers'
  own ``lia_ledger_*`` gauges.

Every one of them is drawn on dashboard 29; a metric nobody can see is a metric
nobody acts on (ADR-148), and the coverage ratchet enforces it.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

workboard_runs_total = Counter(
    "workboard_runs_total",
    "Workboard runs settled by the sweep, by how they ended.",
    ["outcome"],
    # outcome: success | waiting | confirming | failed | skipped_quota | skipped_busy
    # The two `skipped_*` are NOT failures: nothing ran, the ticket went back
    # to `todo` and kept its lifetime budget (ADR-272's logging rule).
)

workboard_replays_total = Counter(
    "workboard_replays_total",
    "Approved actions a ticket run rebuilt, by whether the rebuilt draft was the approved one.",
    ["result"],
    # result: matched | mismatched — a mismatch is not a failure: the person is
    # asked again with the NEW preview, and nothing ran (ADR-092's binding).
)

workboard_run_duration_seconds = Histogram(
    "workboard_run_duration_seconds",
    "Wall time of one workboard run, from claim to settle.",
    ["outcome"],
    # The last buckets straddle WORKBOARD_RUN_TIMEOUT_SECONDS_DEFAULT (600):
    # a run landing there is one the reaper is about to release.
    buckets=(1.0, 5.0, 15.0, 30.0, 60.0, 120.0, 300.0, 600.0, 900.0),
)

workboard_notifications_total = Counter(
    "workboard_notifications_total",
    "Chat notifications sent about a ticket, by event and delivery.",
    ["event", "delivered"],
    # event: run_started | run_finished | run_failed | waiting | confirming | assigned
    # delivered: true | false — settled from the dispatch RESULT, never from
    # the absence of an exception (ADR-263).
)

# Both gauges are written by ONE process — the sweep runs on the leader — while
# production serves four uvicorn workers under `PROMETHEUS_MULTIPROC_DIR`. A
# gauge left on the default mode (`all`) exposes one series PER PROCESS, so a
# respawned worker leaves its predecessor's last value standing beside the live
# one, and the dashboard's `max()` would keep showing a volume the retention
# sweep has already removed. `mostrecent` is what the registers' own
# `lia_ledger_*` gauges use, and this is the same instrument for the same
# arbitration (ADR-263).
lia_hidden_run_rows = Gauge(
    "lia_hidden_run_rows",
    "Archived conversation rows hidden from the chat because a run wrote them.",
    multiprocess_mode="mostrecent",
)

lia_hidden_run_bytes = Gauge(
    "lia_hidden_run_bytes",
    "Bytes those hidden rows occupy (content and metadata).",
    multiprocess_mode="mostrecent",
)

__all__ = [
    "lia_hidden_run_bytes",
    "lia_hidden_run_rows",
    "workboard_notifications_total",
    "workboard_replays_total",
    "workboard_run_duration_seconds",
    "workboard_runs_total",
]
