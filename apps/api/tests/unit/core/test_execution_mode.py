"""What bounds a turn's graph, by the mode it was asked to run in (ADR-070).

The bound is decided BEFORE the graph runs, when only the requested mode is
known: a loop needs room for its iterations (each one is two transitions), the
planner does not. Read from settings, never from a literal.
"""

from __future__ import annotations

import pytest

from src.core.config import settings
from src.core.constants import REACT_GRAPH_RECURSION_HEADROOM
from src.core.execution_mode import recursion_limit_for

pytestmark = pytest.mark.unit


def _loop_bound() -> int:
    return settings.react_agent_max_iterations * 2 + REACT_GRAPH_RECURSION_HEADROOM


def test_the_loop_gets_room_for_its_iterations() -> None:
    assert recursion_limit_for("react") == _loop_bound()


def test_an_automatic_turn_gets_the_loops_room() -> None:
    """The router may settle the loop (ADR-390), and the bound is set before it decides."""
    assert recursion_limit_for("auto") == _loop_bound()


def test_the_pipeline_keeps_its_own_bound() -> None:
    assert recursion_limit_for("pipeline") == settings.agent_max_iterations


def test_an_unreadable_value_gets_the_bound_of_the_engine_that_runs_it() -> None:
    """Anything but a mode the loop may run plans in the pipeline (``graph._planning_node``)."""
    assert recursion_limit_for("not-a-mode") == settings.agent_max_iterations
