"""Unit tests for `_plan_execution_failed` (response_node, audit D3).

When a turn's execution plan totally failed (e.g. its only MCP step timed out),
the response node must not activate the plan's ``skill_name`` and dress the
failure up as a successful skill answer.
"""

from __future__ import annotations

import pytest

from src.domains.agents.constants import (
    STATE_KEY_AGENT_RESULTS,
    STATE_KEY_CURRENT_TURN_ID,
    make_agent_result_key,
)
from src.domains.agents.nodes.response_node import _plan_execution_failed


@pytest.mark.unit
class TestPlanExecutionFailed:
    def _state(self, turn_id: int, status: str | None) -> dict:
        results = {}
        if status is not None:
            results[make_agent_result_key(turn_id, "plan_executor")] = {"status": status}
        return {STATE_KEY_CURRENT_TURN_ID: turn_id, STATE_KEY_AGENT_RESULTS: results}

    def test_failed_plan_returns_true(self):
        assert _plan_execution_failed(self._state(3, "failed")) is True

    def test_successful_plan_returns_false(self):
        assert _plan_execution_failed(self._state(3, "success")) is False

    def test_no_plan_executor_entry_returns_false(self):
        # A skill-only turn with no plan executor result must NOT be treated as failed.
        assert _plan_execution_failed(self._state(3, None)) is False

    def test_empty_state_returns_false(self):
        assert _plan_execution_failed({}) is False

    def test_failed_entry_of_other_turn_is_ignored(self):
        # A failed plan_executor from a PREVIOUS turn must not gate this turn.
        state = {
            STATE_KEY_CURRENT_TURN_ID: 5,
            STATE_KEY_AGENT_RESULTS: {
                make_agent_result_key(4, "plan_executor"): {"status": "failed"},
            },
        }
        assert _plan_execution_failed(state) is False

    def test_non_dict_entry_returns_false(self):
        state = {
            STATE_KEY_CURRENT_TURN_ID: 1,
            STATE_KEY_AGENT_RESULTS: {make_agent_result_key(1, "plan_executor"): "corrupt"},
        }
        assert _plan_execution_failed(state) is False
