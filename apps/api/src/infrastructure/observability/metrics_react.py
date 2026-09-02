"""Prometheus metrics for the ReAct execution loop (ADR-070).

Split out of ``metrics_agents.py``: that module reached its frozen size cap, and
a logical file never grows — it gets a cohesive module extracted instead. These
counters share one subject, the ReAct loop and the guards that bound it, so they
form that cohesive unit rather than an overflow bucket.
"""

from prometheus_client import Counter, Histogram

react_agent_duration_seconds = Histogram(
    "react_agent_duration_seconds",
    "ReAct agent REASONING duration: the seconds charged by react_call_model, "
    "which is what the compute budget bounds. It excludes tool execution time "
    "(see agent_tool_duration_seconds) and, by ADR-170's design, the wall clock "
    "a user spends on a HITL approval. Reading it as the turn's total is how a "
    "delegated sub-agent loop came to be invisible in the dashboards (ADR-256)",
    buckets=[1, 2, 5, 10, 30, 60, 120],
)

react_agent_executions_total = Counter(
    "react_agent_executions_total",
    "Total ReAct agent node executions",
    ["status"],  # success, empty, draft (draft-confirmation handoff), error, timeout
)

react_agent_hitl_interrupts_total = Counter(
    "react_agent_hitl_interrupts_total",
    "HITL interrupts triggered in ReAct mode",
    ["tool_name", "decision"],  # decision: approve, reject
)

react_agent_iterations = Histogram(
    "react_agent_iterations",
    "ReAct agent iteration count distribution",
    buckets=[1, 2, 3, 5, 8, 10, 15],
)

react_agent_tools_called_total = Counter(
    "react_agent_tools_called_total",
    "Tools called by ReAct agent",
    ["tool_name"],
)

# Lot D (2026-09): the loop's iteration count and duration were measured; the
# thing that actually grows — the prompt DELIVERED to the model at each
# iteration — was not. Measured 2026-09-02 with the production windowing:
# 2.3k tokens delivered at iteration 1, 112k at iteration 90 (quadratic
# cumulative growth). These two histograms are the "delivered context" level
# of the working-memory ladder; prefix caching amortises the COST but not the
# window pressure nor the attention dilution they expose.
react_delivered_context_tokens = Histogram(
    "react_delivered_context_tokens",
    "Prompt size (tokens) delivered to the model per ReAct iteration, " "system blocks included",
    buckets=[1_000, 2_000, 5_000, 10_000, 20_000, 40_000, 80_000, 120_000, 200_000],
)

react_context_window_utilization = Histogram(
    "react_context_window_utilization",
    "Delivered ReAct prompt as a fraction of the effective model context "
    "window (llm_models catalogue, ADR-244)",
    buckets=[0.05, 0.10, 0.25, 0.50, 0.70, 0.85, 0.95, 1.0],
)

react_repeated_calls_total = Counter(
    "react_repeated_calls_total",
    "Identical ReAct tool calls (same name AND arguments) refused within a turn. "
    "A non-zero rate on one tool means the model cannot make progress with it — "
    "usually a description or a schema that does not say what it actually needs",
    ["tool_name", "verdict"],  # verdict: block | terminal
)

react_tool_executions_before_interrupt_total = Counter(
    "react_tool_executions_before_interrupt_total",
    "Tool executions that sit BEFORE an interrupting call in the same "
    "AIMessage. An interrupted node never returns, so that work is discarded "
    "and runs again on resume: double quota, double latency, and an approval "
    "decided on data that may have changed since. Read it as "
    "`samples - distinct calls = redundant executions` — one interrupt yields "
    "two samples for one wasted execution, because nothing in state "
    "distinguishes the first pass from the resume. Measure before "
    "restructuring: the blast radius is bounded by the single tool allowed to "
    "interrupt here (delegate_to_sub_agent_tool)",
    ["tool_name"],
)

react_tool_selector_capped_total = Counter(
    "react_tool_selector_capped_total",
    "Turns where the resolved tool count exceeded react_agent_max_tools and "
    "tools had to be dropped. Up to 896 tools can resolve against a cap of 100 "
    "(96 native plus 20 MCP servers of 40 tools), and the selector keeps the "
    "detected domains' tools first — but a non-zero rate means this deployment "
    "is losing capabilities the model can no longer see (ADR-256)",
)

react_tools_resolved = Histogram(
    "react_tools_resolved",
    "Tools resolved for a ReAct turn BEFORE the max_tools cap is applied. The "
    "cap counter only fires once capabilities are already lost; this "
    "distribution is what shows a deployment creeping towards its ceiling",
    buckets=[10, 25, 50, 75, 90, 100, 150, 250, 500],
)

react_unknown_tool_calls_total = Counter(
    "react_unknown_tool_calls_total",
    "Tool calls the loop could not resolve to a bound tool. `not_selected` "
    "means the tool exists in the catalogue but was not bound to this turn — "
    "the cap or the per-request filtering dropped it, so the cap is too low. "
    "`unknown` means no tool of that name exists at all: the model invented it, "
    "so the catalogue is presented badly. The two need opposite fixes, which is "
    "why one counter would have been useless. The tool NAME is deliberately not "
    "a label — it comes from a model, so its cardinality is unbounded; it "
    "travels in the log event instead (ADR-256)",
    ["reason"],  # not_selected | unknown
)
