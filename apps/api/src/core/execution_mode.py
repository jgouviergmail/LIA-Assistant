"""Which engine plans a turn, and what bounds its graph (ADR-070).

Two vocabularies, never confused:

- the REQUESTED mode is a choice — what the person picked for the chat, or what
  a routine's or a ticket's row carries;
- the EXECUTED mode is an engine (``EXECUTION_ENGINES``) — the pipeline planner
  or the ReAct loop, what actually plans the turn. Only an engine reaches a
  register row, a tool or a metric label (``LiaRuntimeContext.turn_engine``,
  read through ``executed_mode_of``).

The graph's recursion bound is set before the graph runs, from what the turn runs
in at that point: the request for a new turn, the engine for a resumed one.
"""

from __future__ import annotations

from typing import TypeIs

from src.core.config import settings
from src.core.constants import (
    EXECUTION_MODE_AUTO,
    EXECUTION_MODE_CHOICES,
    EXECUTION_MODE_REACT,
    REACT_GRAPH_RECURSION_HEADROOM,
    ExecutionMode,
)

__all__ = ["is_execution_mode_choice", "recursion_limit_for"]


def is_execution_mode_choice(value: object) -> TypeIs[ExecutionMode]:
    """Whether ``value`` names one of the modes a person may choose.

    Args:
        value: A stored or received value.

    Returns:
        True for « pipeline », « react » or « auto ».
    """
    return value in EXECUTION_MODE_CHOICES


#: What may end in the loop: the loop asked for, or « auto », whose engine the
#: router settles after the bound is set.
_MAY_RUN_THE_LOOP: frozenset[str] = frozenset({EXECUTION_MODE_REACT, EXECUTION_MODE_AUTO})


def recursion_limit_for(mode: str) -> int:
    """The graph's recursion bound for a turn that runs in ``mode``.

    A loop takes two transitions per iteration, plus the nodes around it; the
    planner's turn is bounded by ``agent_max_iterations``. Anything that cannot
    end in the loop plans in the pipeline (``graph._planning_node``), so it gets
    that bound.

    Args:
        mode: What the turn runs in — a request, or a resumed turn's engine.

    Returns:
        The ``recursion_limit`` of the turn's ``RunnableConfig``.
    """
    if mode in _MAY_RUN_THE_LOOP:
        return settings.react_agent_max_iterations * 2 + REACT_GRAPH_RECURSION_HEADROOM
    return settings.agent_max_iterations
