"""Prometheus metrics for the ReAct execution loop (ADR-070).

Split out of ``metrics_agents.py``: that module reached its frozen size cap, and
a logical file never grows — it gets a cohesive module extracted instead. These
counters share one subject, the ReAct loop and the guards that bound it, so they
form that cohesive unit rather than an overflow bucket.
"""

from prometheus_client import Counter, Histogram

react_agent_duration_seconds = Histogram(
    "react_agent_duration_seconds",
    "ReAct agent total execution duration",
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
