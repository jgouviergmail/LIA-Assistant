"""Prometheus transport for the effect gate and its ledger (ADR-263).

Six counters answering one question each, and one gauge that answers the only
question a counter cannot: *is an effect still claimed and never closed?* A row
stuck in ``CLAIMED`` means a turn died between the claim and its outcome — the
effect may or may not have happened, and nobody would ever be told.

Cardinality contract, shared with ``metrics_product.py``: at most three bounded
labels per metric, and **never** ``tool_name`` — a third-party MCP server names
its own tools, so that label's value set belongs to nobody. Enforced at build
time by ``tests/unit/infrastructure/observability/test_effect_metric_label_bounds.py``.

Every metric here is wired to dashboard 28 (``28-effect-ledger.json``) or to an
alert rule; the coverage ratchet refuses a blind one.
"""

from prometheus_client import Counter, Gauge

# ---------------------------------------------------------------------------
# Counters — what the gate did
# ---------------------------------------------------------------------------

effect_claims_total = Counter(
    "lia_effect_claims_total",
    "Effects claimed before being performed, by declared policy, authority "
    "source and execution mode",
    ["policy", "source", "execution_mode"],
)

effect_outcomes_total = Counter(
    "lia_effect_outcomes_total",
    "Claimed effects closed from an explicit result, by policy and outcome "
    "(a tool that reported failure closes as failed, never as succeeded)",
    ["policy", "status"],
)

effect_refusals_total = Counter(
    "lia_effect_refusals_total",
    "Effects the gate refused to perform, by reason (missing confirmation on "
    "an unattended turn, ledger unavailable for a confirm policy, ...)",
    ["reason"],
)

effect_unrecorded_total = Counter(
    "lia_effect_unrecorded_total",
    "Effects performed WITHOUT a ledger row because the ledger was "
    "unavailable or no run context named a user — the gap is loud, never silent",
    ["policy", "reason"],
)

effect_already_performed_total = Counter(
    "lia_effect_already_performed_total",
    "Duplicate attempts stopped by a lost claim, and whether the winner's "
    "result could be served (record) or was not written yet (none)",
    ["served"],
)

effect_ledger_failures_total = Counter(
    "lia_effect_ledger_failures_total",
    "Ledger operations that failed, by operation — the health of the register "
    "itself, distinct from the health of what it records",
    ["operation"],
)

# ---------------------------------------------------------------------------
# DB-backed gauge (pattern ``lifetime_metrics.py`` / ``metrics_product.py``):
# Prometheus cannot see rows, so the exact SQL truth is computed by the
# repository and merely transported here.
# ---------------------------------------------------------------------------

treatments_total = Counter(
    "lia_treatments_total",
    "Capabilities CONSULTED by a turn, counted from what the register actually "
    "persisted — a flush that failed leaves this untouched and raises "
    'lia_effect_ledger_failures_total{operation="treatments_flush"} instead',
    ["domain", "outcome", "execution_mode"],
)

treatments_uncollected_total = Counter(
    "lia_treatments_uncollected_total",
    "Capabilities consulted while a turn was running with NO register open — "
    "the signal a second entry point would otherwise produce silently. Zero is "
    "the only acceptable value in production",
    ["execution_mode"],
)

ledger_rows = Gauge(
    "lia_ledger_rows",
    "Estimated rows in a transparency register (pg_class.reltuples, refreshed "
    "by ANALYZE) — an estimate on purpose: a COUNT(*) every sync would "
    "sequentially scan the largest table in the schema",
    ["table"],
    multiprocess_mode="mostrecent",
)

ledger_bytes = Gauge(
    "lia_ledger_bytes",
    "Bytes a transparency register actually occupies, indexes included "
    "(pg_total_relation_size) — no purge job ships with the registers, so the "
    "day one is needed is decided on this figure (ADR-263)",
    ["table"],
    multiprocess_mode="mostrecent",
)

effect_claimed_orphans = Gauge(
    "lia_effect_claimed_orphans",
    "Effects still CLAIMED past the staleness threshold — a turn that died "
    "between claiming and closing, whose outcome nobody will ever learn",
    multiprocess_mode="mostrecent",
)


# ---------------------------------------------------------------------------
# The tamper-evident chain (ADR-263, lot 5)
# ---------------------------------------------------------------------------
# Notarising is asynchronous, so the chain has a WINDOW: a row created at T is
# covered at T+delta, and a rewrite inside delta leaves no trace. That window is
# published rather than assumed — the lag gauge is what makes the design's one
# concession measurable instead of rhetorical.

ledger_chain_entries_total = Counter(
    "lia_ledger_chain_entries_total",
    "Links appended to a per-account tamper-evident chain, by the stage they "
    "cover (chain.genesis | effect.claimed | effect.settled | treatment.recorded)",
    ["kind"],
)

ledger_chain_pass_failures_total = Counter(
    "lia_ledger_chain_pass_failures_total",
    "Notary passes rolled back for one account — a lost race against a "
    "concurrent notary, or a database error. The work stays pending and the "
    "next tick redoes it, so a few are normal and a rising rate is not",
)

ledger_chain_breaks_total = Counter(
    "lia_ledger_chain_breaks_total",
    "Chain breaks OBSERVED, by reason (sequence | prev_hash | entry_hash | "
    "payload). Any value above zero means a register row or a chain entry was "
    "altered outside the application — this is the metric the chain exists for",
    ["reason"],
)

ledger_chain_pending = Gauge(
    "lia_ledger_chain_pending",
    "Register rows waiting to be notarised. A steady small number is the "
    "notary keeping up; a rising one is the notary stalled, and every row in "
    "it is a row whose alteration would currently leave no trace",
    multiprocess_mode="mostrecent",
)

ledger_chain_lag_seconds = Gauge(
    "lia_ledger_chain_lag_seconds",
    "Age of the OLDEST un-notarised register row — the width of the window in "
    "which a rewrite leaves no trace. The honest cost of not taxing every "
    "action with a synchronous hash (measured: 6,0 ms vs 0,21 ms, x28)",
    multiprocess_mode="mostrecent",
)


# ---------------------------------------------------------------------------
# The decision register (ADR-263, lot 6)
# ---------------------------------------------------------------------------

decisions_total = Counter(
    "lia_decisions_total",
    "Turns recorded, by how they ended, in which mode and under whose "
    "authority. A turn that never answered has its own value — a register "
    "holding only the turns that went well is an account nobody should trust",
    ["outcome", "execution_mode", "source"],
)
