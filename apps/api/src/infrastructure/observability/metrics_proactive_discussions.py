"""Prometheus metrics of the proactive discussions producer (ADR-358, ADR-360).

A run spends on the person's behalf in the background and says nothing to them
when it abstains, so this counter is what tells the operator how the producer
behaves: runs that publish, abstain, defer on a backoff, fail, or wait on rules
too long to be read whole.
"""

from prometheus_client import Counter

proactive_discussion_runs_total = Counter(
    "proactive_discussion_runs_total",
    "Proactive discussion runs, by kind and outcome",
    # kind: opening | rebuild
    # outcome: a settled run (completed | skipped | failed | abandoned), a run that
    #          never started (ineligible | budget_exhausted | usage_limit_reached |
    #          controls_over_budget | budget_unconfigured | producer_disabled), or
    #          error when the run raised (``discussion_runner.run_for_owner``)
    ["kind", "outcome"],
)
