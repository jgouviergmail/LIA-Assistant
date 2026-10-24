"""Prometheus metrics of the proactive discussions producer (ADR-358, ADR-360).

A run spends on the person's behalf in the background and says nothing to them
when it abstains, so this counter is what tells the operator how the producer
behaves: runs that publish, abstain, defer on a backoff, fail, never start (and
why), or wait on rules too long to be read whole. The two gauges say what the
execution tables occupy, which only shrink with an account (audit AC-034a).
"""

from prometheus_client import Counter, Gauge

proactive_discussion_runs_total = Counter(
    "proactive_discussion_runs_total",
    "Proactive discussion runs, by kind and outcome",
    # kind: opening | rebuild
    # outcome: a settled run (completed | skipped | failed | abandoned), a run that
    #          never started — what held the person's attention (recent_turn |
    #          pending_opening | recent_alert | recent_opening | reminder_due |
    #          turn_streaming | approval_pending), or capability_disabled |
    #          claim_refused | stale_claim | budget_exhausted | usage_limit_reached |
    #          controls_over_budget | budget_unconfigured | producer_disabled — or
    #          error when the run raised (``discussion_runner.run_for_owner``)
    ["kind", "outcome"],
)

proactive_discussion_table_rows = Gauge(
    "proactive_discussion_table_rows",
    "Rows of a proactive discussions execution table: the planner's estimate, an exact "
    "count where it has none — no retention ships, it is decided on this figure (AC-034b)",
    # table: one of DISCUSSION_TABLES (domains/proactive_discussions/volume.py)
    ["table"],
    multiprocess_mode="mostrecent",
)

proactive_discussion_table_bytes = Gauge(
    "proactive_discussion_table_bytes",
    "Bytes a proactive discussions execution table occupies, indexes included "
    "(pg_total_relation_size)",
    # table: one of DISCUSSION_TABLES (domains/proactive_discussions/volume.py)
    ["table"],
    multiprocess_mode="mostrecent",
)
