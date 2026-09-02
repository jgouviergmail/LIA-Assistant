"""What a ReAct turn may spend, and the single predicate that says stop.

Two questions live here, and they are the same subject:

- **How many iterations does this turn START with?** :func:`effective_react_budget`
  (ADR-238) — pure math over the query's domain span, the one complexity signal
  the setup node already holds. Unknown complexity falls back to the ceiling: an
  uninformed guess must never under-budget a hard query, so the adaptive path
  only ever SAVES on provably simple ones.
- **May it keep going?** :func:`react_exit_reason` (ADR-170, ADR-248, ADR-256) —
  the arithmetic over what the turn has actually spent.

The rule this module exists to keep whole: **the stop condition has exactly one
implementation** (ADR-248). The router applies :func:`react_exit_reason` to
decide, ``react_finalize_node`` applies it to EXPLAIN. A second copy would let
the loop stop for a reason the answer never mentions.

Two time budgets, deliberately not one (ADR-256):

- ``react_elapsed_seconds`` counts the model's own REASONING, charged by
  ``react_call_model_node``. Its threshold is ADR-170's and does not move.
- ``react_tool_seconds`` counts DELEGATED work — a sub-agent loop, an iterative
  MCP task, a browser run — each of which opens its own LLM loop behind one
  ``tool_call``. Before ADR-256 that work charged nothing anywhere, so no
  predicate could see it.

Summing the two into one counter was measured and rejected: a single delegation
at its pipeline bound (300 s) equals 100 % of the reasoning budget, so turns
that complete today would start being cut.

Both exclude the wall clock a user spends on a HITL approval, for ADR-170's
structural reason: ``interrupt()`` raises, so an interrupted node never returns
and charges nothing.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domains.agents.models import MessagesState

__all__ = [
    "TIMEOUT_ATTRIBUTION_MARGIN",
    "abandoned_call_message",
    "effective_react_budget",
    "loop_compute_seconds",
    "loop_tool_seconds",
    "react_exit_reason",
    "react_iteration_budget",
    "tool_timeout_message",
    "uncharged_wall_seconds",
]


#: How close to its own bound a call must have run for a timeout to be
#: attributed to US rather than to the tool. A margin, not equality: the
#: ``wait_for`` wakes a hair late, and scheduling jitter must not turn our own
#: cut into "the tool timed out by itself".
TIMEOUT_ATTRIBUTION_MARGIN = 0.95


def effective_react_budget(
    domain_count: int, *, base: int, per_extra_domain: int, ceiling: int
) -> int:
    """Iteration budget this turn STARTS with (ADR-238).

    ADR-248 made this the initial allowance rather than the final one: a loop
    that spends it productively earns more (see :func:`react_iteration_budget`).

    Args:
        domain_count: Domains the analyzer attributed to the query
            (0 = unknown — conservative fallback to the ceiling).
        base: Budget of a single-domain query.
        per_extra_domain: Extra iterations granted per additional domain.
        ceiling: Hard cap (the historical ``react_agent_max_iterations``).

    Returns:
        The effective budget, always in ``[1, ceiling]``.
    """
    if domain_count < 1:
        return ceiling
    budget = base + (domain_count - 1) * per_extra_domain
    return max(1, min(budget, ceiling))


def react_iteration_budget(state: MessagesState) -> int:
    """Iterations this turn may spend (ADR-238 adaptive value, else the ceiling).

    Args:
        state: Current graph state.

    Returns:
        The effective budget.
    """
    # Late import: the routing tests patch ``src.core.config.settings``, and a
    # module-level binding would ignore the patch (same convention as the router).
    from src.core.config import settings as _settings

    ceiling = int(_settings.react_agent_max_iterations)
    budget = int(state.get("react_max_iterations_effective") or ceiling)
    if not getattr(_settings, "react_progress_extension_enabled", False):
        return min(budget, ceiling)

    # ADR-248: the loop buys more iterations with results, not with promises.
    # Reaching the allowance having spent it PRODUCTIVELY earns another block;
    # a loop that stopped producing stops being extended and ends here.
    step = int(_settings.react_iterations_progress_extension)
    productive = int(state.get("react_productive_iterations", 0) or 0)
    while budget <= productive and budget < ceiling:
        budget += step
    return min(budget, ceiling)


def react_exit_reason(state: MessagesState) -> str | None:
    """Why the loop must stop now — ONE predicate, two readers.

    The router applies it to decide, ``react_finalize_node`` applies it to
    EXPLAIN. A second copy of this arithmetic would let the loop stop for a
    reason the answer never mentions, which is how a cut-short investigation
    came to be served as a finished one (2026-08-28).

    The two time budgets are checked separately and named separately. Reporting
    a delegated overrun as ``compute_budget`` would tell the user the model
    thought too long when in fact a sub-agent did — the same invented diagnosis
    ADR-182 removed, pointing the other way.

    Args:
        state: Current graph state.

    Returns:
        ``"max_iterations"``, ``"compute_budget"``, ``"tool_budget"``, or None
        to keep going.
    """
    if int(state.get("react_iteration", 0)) >= react_iteration_budget(state):
        return "max_iterations"
    from src.core.config import settings as _settings

    compute_elapsed = float(state.get("react_elapsed_seconds") or 0.0)
    if compute_elapsed > 0.0 and compute_elapsed > _settings.react_agent_timeout_seconds:
        return "compute_budget"

    tool_elapsed = float(state.get("react_tool_seconds") or 0.0)
    if tool_elapsed > 0.0 and tool_elapsed > _settings.react_tool_budget_seconds:
        return "tool_budget"
    return None


def loop_compute_seconds(state: MessagesState) -> float:
    """Return the loop's own REASONING time for this turn.

    The wall clock cannot be used for latency either: ``interrupt()`` raises, so
    a node that waits on a HITL approval never returns and never charges
    anything, while ``time.time()`` keeps running. Reporting the difference as
    ReAct latency turns a user's thinking time into a performance regression on
    the dashboards (ADR-170).

    Args:
        state: Current graph state.

    Returns:
        Seconds of model compute charged by the loop's nodes.
    """
    return float(state.get("react_elapsed_seconds") or 0.0)


def loop_tool_seconds(state: MessagesState) -> float:
    """Return the seconds this turn spent INSIDE tools.

    Counted separately from :func:`loop_compute_seconds` because a delegating
    tool opens its own LLM loop: 20 iterations for a sub-agent, 50 for an
    iterative MCP task or a browser run. Before ADR-256 that work charged
    nothing anywhere, so no predicate could see it.

    Args:
        state: Current graph state.

    Returns:
        Seconds charged by tool execution this turn.
    """
    return float(state.get("react_tool_seconds") or 0.0)


def uncharged_wall_seconds(state: MessagesState, charged_s: float) -> float | None:
    """Return the wall time this turn did NOT charge to any node.

    ``wall - charged``. Two things live in there, and the name deliberately
    claims neither: the HITL approval wait when the turn was interrupted, and
    the graph's own overhead (checkpoint writes, node scheduling, routing)
    otherwise. A turn with no interrupt at all still reports ~0.5 s — measured
    in the dev container — so calling this field "hitl_wait" would have made an
    operator read graph overhead as user hesitation.

    It is the quantity the loop budget used to be charged for (ADR-170);
    surfacing it turns the old defect into a signal.

    Args:
        state: Current graph state.
        charged_s: Seconds already charged for this turn (reasoning plus tools).

    Returns:
        Rounded seconds, or None when the turn carries no start stamp.
    """
    start_time = state.get("react_start_time")
    if start_time is None:
        return None
    return round(max(0.0, (time.time() - start_time) - charged_s), 2)


def abandoned_call_message(reason: str) -> str:
    """The result handed back for a call the loop stopped before running.

    English technical message, like every other guard in this package
    (:func:`~src.domains.agents.utils.loop_guard.repeated_call_message`): the
    model reformulates for the user in their own language. It names the stop
    condition and says what to do next — a bare refusal is what a stalled model
    retries verbatim.

    Why it exists at all: without it the ``AIMessage`` keeps ``tool_calls``
    nobody answers, LangGraph persists that, and every later turn on the thread
    is rejected by the provider (measured 2026-09-02: one budget exit, eight
    dead requests on the same call id). Answering the call makes the history
    valid BY CONSTRUCTION instead of relying on the turn-start repair.

    The caller resolves the reason — this function never defaults. A second
    defaulting rule here would let the banner the user reads and the result the
    model is given name different causes, which is ADR-248's "one stop
    condition, one wording" broken at small scale.

    Args:
        reason: The already-resolved stop condition, as it also appears in
            ``react_agent_result.truncation``.

    Returns:
        The ToolMessage body.
    """
    return (
        f"This tool was NOT executed: the reasoning loop stopped first ({reason}). "
        "No result is available and none will arrive — the turn ends here. "
        "Answer with what the other tools already returned, say plainly what "
        "could not be checked, and let the user ask again for the rest."
    )


def tool_timeout_message(tool_name: str, *, bound_s: float, elapsed_s: float) -> str:
    """The result handed back for a call that ran out of time.

    English technical message, like its two siblings
    (:func:`abandoned_call_message`,
    :func:`~src.domains.agents.utils.loop_guard.repeated_call_message`): the
    model reformulates for the user in their own language, and it has to say
    what to do next — a bare refusal is what a stalled model retries verbatim.

    **Which timeout fired is part of the message.** A tool may raise a timeout
    of its own — an inner ``wait_for``, an MCP call hitting the per-server bound
    its owner configured — well before ours would have. Saying "stopped after
    300 s" there states a number the run never reached, which is the invented
    diagnosis ADR-182 removed. The elapsed time decides, with a margin: the
    ``wait_for`` wakes a hair late, and scheduling jitter must not turn our own
    cut into "the tool gave up by itself".

    Args:
        tool_name: The call that did not return.
        bound_s: The budget this call was given (ADR-256 policy).
        elapsed_s: What it actually spent before raising.

    Returns:
        The ToolMessage body.
    """
    if elapsed_s >= bound_s * TIMEOUT_ATTRIBUTION_MARGIN:
        return (
            f"Tool '{tool_name}' was stopped after {bound_s:.0f}s (execution budget). "
            "Its result is unavailable — try a narrower request, or another tool."
        )
    return (
        f"Tool '{tool_name}' timed out on its own after {elapsed_s:.0f}s. "
        "Its result is unavailable — try a narrower request, or another tool."
    )
