"""The three registers of ADR-263, on the debug panel (B8).

The panel already showed what a turn PERFORMED, read back from `agent_effects`
after the fact. It showed nothing of the other two: what the turn CONSULTED
(`agent_treatments`) and the turn's own record (`agent_decisions`, the spine
both hang off). A turn that opened nine sources and answered from them looked,
on screen, like a turn that did nothing.

**The source here is the LIVE record, never the database.** The debug payload is
emitted INSIDE `treatment_recorder` and `decision_recorder`, both of which write
on exit: a read of those tables at that instant returns nothing for the current
turn, and « nothing » there is a false negative, not an empty turn. Both
registers publish their in-flight object precisely so a reader inside the turn
can see what is about to be written — that is what this module reads.

Two consequences the payload states rather than hides:

- **the turn's outcome is « so far », not a verdict.** It starts at
  ``interrupted`` and only an explicit success moves it, so the block carries
  ``settled: false``: the row is not written yet, and the panel must not print
  a verdict the register has not reached.
- **a consultation records the CAPABILITY, never the call.** The entries carry
  the tool name, its declared policy, the outcome and the duration — the field
  set IS the privacy contract, and no argument crosses it.
"""

from __future__ import annotations

from typing import Any

from src.core.turn_verdicts import (
    collected_verdicts,
    dropped_verdicts,
    is_collecting_verdicts,
)
from src.domains.agents.effects.decisions import current_turn
from src.domains.agents.effects.treatments import (
    Treatment,
    collected_treatments,
    is_collecting,
)

__all__ = ["registers_debug"]


def _treatment_entry(row: Treatment) -> dict[str, Any]:
    """One consultation, as the panel shows it.

    Args:
        row: The live row.

    Returns:
        The capability, its policy, what was observed and how long it took —
        and nothing else, by contract.
    """
    return {
        "tool_name": row.tool_name,
        "mutation_policy": row.mutation_policy,
        "outcome": row.outcome,
        "duration_ms": row.duration_ms,
    }


def _decision_block() -> dict[str, Any] | None:
    """The turn's own record, or None outside a turn.

    Returns:
        The spine of the turn: who ran it, how, where the router sent it, how
        many steps the planner produced and how it stands SO FAR.
    """
    turn = current_turn()
    if turn is None:
        return None
    return {
        "run_id": turn.run_id,
        "source": turn.source,
        "execution_mode": turn.execution_mode,
        "route": turn.route,
        "plan_step_count": turn.plan_step_count,
        "outcome": turn.outcome.value,
        "stop_reason": turn.stop_reason,
        # The row is written on exit from `decision_recorder`, which has not
        # happened yet: this is what is KNOWN, not what was recorded.
        "settled": False,
    }


def registers_debug() -> dict[str, Any] | None:
    """What the two deferred registers hold for the turn in flight.

    Returns:
        ``{"decision": ..., "treatments": {...}}``, or None when neither
        register is active — emitting an empty block outside a turn would say
        « this turn consulted nothing and decided nothing » about a turn that
        is not there.
    """
    decision = _decision_block()
    # « Consulted nothing » is a fact about a turn; « no turn » is not, and
    # `collected_treatments` answers `()` for both — hence the predicate.
    if decision is None and not is_collecting() and not is_collecting_verdicts():
        return None
    rows = collected_treatments()
    verdicts = collected_verdicts()
    return {
        "decision": decision,
        "treatments": {
            "entries": [_treatment_entry(row) for row in rows],
            "count": len(rows),
            "failed_count": sum(1 for row in rows if row.outcome != "ok"),
        },
        # The silent corrections the turn made to itself (B8). Counted in
        # Prometheus, where an operator reads a RATE; here a person reads
        # « did it happen in THIS exchange ».
        "verdicts": {
            "entries": [{"kind": row.kind, "detail": row.detail} for row in verdicts],
            "count": len(verdicts),
            # A capped list that does not say it is capped reads as an exact
            # count (ADR-185).
            "dropped": dropped_verdicts(),
        },
    }
