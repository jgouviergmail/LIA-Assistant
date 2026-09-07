"""Prometheus metrics for the daily relationship debrief.

Three, and each answers a question an operator would otherwise have no way to
ask:

- **is this slot actually working?** The debrief is a NEW LLM slot, so its most
  likely operational failure is a model an admin routed it to that cannot
  answer a schema — and the user-visible symptom is a generic "the debrief
  could not be written" on one card. ``outcome`` makes that visible instance-wide.
- **is the lease long enough?** ``relation_debrief_lease_seconds`` must exceed
  the whole build (evidence read + LLM), or a slow provider hands the row to a
  second builder mid-call. The histogram is the only way to check that against
  reality rather than against a guess.
- **does the chat ever use it?** A debrief nothing injects is a feature paid for
  and never spent.

Token usage is deliberately NOT here: it goes through ``track_proactive_tokens``
into ``token_usage_logs`` + ``user_statistics``, which dashboard 05 already
reads. A second accounting would be one nobody thinks to open.

Every metric below is referenced by a panel in
``grafana/dashboards/05-llm-tokens-cost.json`` — a metric nobody can see is a
metric nobody acts on (ADR-148).
"""

from __future__ import annotations

from prometheus_client import Counter, Histogram

relation_debrief_builds_total = Counter(
    "relation_debrief_builds_total",
    "Relationship-debrief build attempts, by what they settled on.",
    ["outcome"],
    # outcome: ready | empty | failed | unchanged (verified, no model call)
    #        | declined (somebody else owned the build, or today's was there)
)

relation_debrief_build_duration_seconds = Histogram(
    "relation_debrief_build_duration_seconds",
    "Time to build one relationship debrief (evidence read + LLM call).",
    buckets=(0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 40.0, 80.0),
)

relation_debrief_injections_total = Counter(
    "relation_debrief_injections_total",
    "Chat turns that carried a written debrief into the prompt.",
)
