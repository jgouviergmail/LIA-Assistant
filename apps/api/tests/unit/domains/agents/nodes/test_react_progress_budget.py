"""A loop that is still finding things must not be cut on a counter.

ADR-238 scales the ReAct iteration budget with the query's DOMAIN SPAN. A deep
single-domain investigation therefore gets the minimum — six iterations in
production — and an email search that was working perfectly (six iterations,
six tool calls, results coming back) was stopped mid-flight. Domain span
measures how WIDE a question is; it says nothing about how DEEP the answer is
buried.

The budget now extends while the loop earns it: each time the loop reaches its
current allowance having spent it PRODUCTIVELY, it is granted another block.
A loop that stops producing stops being extended, which is the whole point —
the ceiling (`react_agent_max_iterations`) and the compute-time budget remain
the hard bounds, unchanged.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.domains.agents.utils.react_budget import react_iteration_budget

pytestmark = [pytest.mark.unit]


def _state(base: int | None, productive: int) -> dict[str, Any]:
    return {
        "react_max_iterations_effective": base,
        "react_productive_iterations": productive,
    }


@pytest.fixture(autouse=True)
def budget_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.core.config import settings

    monkeypatch.setattr(settings, "react_progress_extension_enabled", True, raising=False)
    monkeypatch.setattr(settings, "react_iterations_progress_extension", 4, raising=False)
    monkeypatch.setattr(settings, "react_agent_max_iterations", 90, raising=False)


class TestProductivityEarnsIterations:
    def test_an_unproductive_loop_keeps_its_base_budget(self) -> None:
        assert react_iteration_budget(_state(6, 0)) == 6

    def test_a_loop_short_of_its_budget_is_not_extended(self) -> None:
        """Extensions are earned at the boundary, not in advance."""
        assert react_iteration_budget(_state(6, 5)) == 6

    def test_reaching_the_budget_productively_grants_a_block(self) -> None:
        assert react_iteration_budget(_state(6, 6)) == 10

    def test_extensions_compound_while_the_work_keeps_paying(self) -> None:
        assert react_iteration_budget(_state(6, 10)) == 14
        assert react_iteration_budget(_state(6, 14)) == 18

    def test_a_loop_that_stops_producing_stops_growing(self) -> None:
        """11 productive out of a 14 budget: no new block, the loop will end."""
        assert react_iteration_budget(_state(6, 11)) == 14


class TestTheHardBoundsStillHold:
    def test_the_ceiling_is_never_exceeded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.core.config import settings

        monkeypatch.setattr(settings, "react_agent_max_iterations", 12, raising=False)

        assert react_iteration_budget(_state(6, 100)) == 12

    def test_the_extension_can_be_switched_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.core.config import settings

        monkeypatch.setattr(settings, "react_progress_extension_enabled", False, raising=False)

        assert react_iteration_budget(_state(6, 50)) == 6

    def test_no_adaptive_base_falls_back_to_the_ceiling(self) -> None:
        """Unchanged ADR-238 behaviour when the adaptive budget is disabled."""
        assert react_iteration_budget(_state(None, 0)) == 90


class TestProductivityIsCounted:
    """Only a tool that actually returned something counts."""

    def test_a_successful_call_is_productive(self) -> None:
        from src.domains.agents.nodes.react_nodes import _is_productive_result

        assert _is_productive_result({"success": True, "data": [1, 2]}) is True
        assert _is_productive_result("plain string result") is True

    def test_a_declared_failure_is_not_productive(self) -> None:
        from src.domains.agents.nodes.react_nodes import _is_productive_result

        assert _is_productive_result({"success": False, "error": {"code": "TIMEOUT"}}) is False

    def test_an_empty_result_is_not_productive(self) -> None:
        """Nothing came back, so nothing was learned — do not buy more of it."""
        from src.domains.agents.nodes.react_nodes import _is_productive_result

        assert _is_productive_result(None) is False
        assert _is_productive_result("") is False

    def test_the_execute_node_carries_the_counter(self) -> None:
        import inspect

        from src.domains.agents.nodes import react_nodes

        source = inspect.getsource(react_nodes.react_execute_tools_node)
        assert "react_productive_iterations" in source

    def test_the_counter_is_declared_in_the_state(self) -> None:
        """An undeclared key is silently dropped by LangGraph (systemic rule)."""
        from src.domains.agents.models import MessagesState

        assert "react_productive_iterations" in MessagesState.__annotations__
