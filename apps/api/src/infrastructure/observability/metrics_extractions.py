"""Prometheus metrics for the post-response background extractions.

The response node schedules six fire-and-forget subsystems after every turn —
long-term memory, interests, open loops, personal journal, psyche and the
recurrence ledger — each behind its own chain of guards.

Until this module existed, the only way to know whether a given turn actually
fed any of them was to read the code: every skip was logged at ``debug`` level
and nothing aggregated the decisions. Two production defects survived precisely
because of that blind spot — external channels never feeding journals, and HITL
draft turns extracting nothing at all.

All metrics are best-effort: incrementing them must never break the response
node. Emission sites wrap the call in ``contextlib.suppress``.
"""

from __future__ import annotations

from prometheus_client import Counter

post_response_extraction_scheduled_total = Counter(
    "post_response_extraction_scheduled_total",
    "Outcome of every post-response background extraction decision. A sustained "
    "'trivial', 'user_disabled' or 'no_user' share on a given kind means that "
    "subsystem is silently starving.",
    ["kind", "outcome"],
    # kind:    memory | interests | open_loops | journal | psyche | recurrence
    # outcome: scheduled | automated_source | user_disabled | feature_disabled
    #          | trivial | no_user | not_applicable | error
    # Not every kind emits every outcome — the guards genuinely differ; the
    # authoritative per-kind vocabulary lives next to the emission sites in
    # domains/agents/nodes/post_response_extractions.py.
)
