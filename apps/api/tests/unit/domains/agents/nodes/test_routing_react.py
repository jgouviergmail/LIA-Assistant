"""
Unit tests for ReAct execution mode routing functions.

Phase: ADR-070 — ReAct Execution Mode
"""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage

from src.domains.agents.constants import (
    NODE_DRAFT_CRITIQUE,
    NODE_REACT_CALL_MODEL,
    NODE_REACT_EXECUTE_TOOLS,
    NODE_REACT_FINALIZE,
)
from src.domains.agents.nodes.routing import (
    route_from_react_call_model,
    route_from_react_execute_tools,
)


@pytest.mark.unit
class TestRouteFromReactCallModel:
    """Tests for route_from_react_call_model routing function."""

    @patch("src.core.config.settings")
    def test_tool_calls_routes_to_execute_tools(self, mock_settings: object) -> None:
        """LLM produced tool_calls → continue loop to execute_tools."""
        mock_settings.react_agent_max_iterations = 15
        ai_msg = AIMessage(
            content="",
            tool_calls=[{"id": "tc_1", "name": "search_contacts", "args": {"query": "Marc"}}],
        )
        state: dict = {"messages": [ai_msg], "react_iteration": 1}
        assert route_from_react_call_model(state) == NODE_REACT_EXECUTE_TOOLS

    @patch("src.core.config.settings")
    def test_no_tool_calls_routes_to_finalize(self, mock_settings: object) -> None:
        """LLM produced no tool_calls → finalize (done reasoning)."""
        mock_settings.react_agent_max_iterations = 15
        ai_msg = AIMessage(content="Here is your answer.")
        state: dict = {"messages": [ai_msg], "react_iteration": 1}
        assert route_from_react_call_model(state) == NODE_REACT_FINALIZE

    @patch("src.core.config.settings")
    def test_max_iterations_routes_to_finalize(self, mock_settings: object) -> None:
        """Max iterations reached → force finalize regardless of tool_calls."""
        mock_settings.react_agent_max_iterations = 5
        ai_msg = AIMessage(
            content="",
            tool_calls=[{"id": "tc_1", "name": "search", "args": {}}],
        )
        state: dict = {"messages": [ai_msg], "react_iteration": 5}
        assert route_from_react_call_model(state) == NODE_REACT_FINALIZE

    @patch("src.core.config.settings")
    def test_empty_messages_routes_to_finalize(self, mock_settings: object) -> None:
        """Empty messages → finalize (safety)."""
        mock_settings.react_agent_max_iterations = 15
        state: dict = {"messages": [], "react_iteration": 0}
        assert route_from_react_call_model(state) == NODE_REACT_FINALIZE

    @patch("src.core.config.settings")
    def test_compute_budget_exhausted_routes_to_finalize(self, mock_settings: object) -> None:
        """Budget spent on actual compute → finalize."""
        mock_settings.react_agent_max_iterations = 15
        mock_settings.react_agent_timeout_seconds = 120
        ai_msg = AIMessage(
            content="",
            tool_calls=[{"id": "tc_1", "name": "search_contacts", "args": {}}],
        )
        state: dict = {
            "messages": [ai_msg],
            "react_iteration": 3,
            "react_elapsed_seconds": 200.0,
        }
        assert route_from_react_call_model(state) == NODE_REACT_FINALIZE

    @patch("src.core.config.settings")
    def test_within_compute_budget_continues(self, mock_settings: object) -> None:
        """Within budget → normal routing (continue if tool_calls)."""
        mock_settings.react_agent_max_iterations = 15
        mock_settings.react_agent_timeout_seconds = 120
        ai_msg = AIMessage(
            content="",
            tool_calls=[{"id": "tc_1", "name": "search_contacts", "args": {}}],
        )
        state: dict = {
            "messages": [ai_msg],
            "react_iteration": 1,
            "react_elapsed_seconds": 10.0,
        }
        assert route_from_react_call_model(state) == NODE_REACT_EXECUTE_TOOLS

    @patch("src.core.config.settings")
    def test_human_approval_time_is_not_charged_to_the_loop(self, mock_settings: object) -> None:
        """The regression this budget exists for (ADR-170).

        ``interrupt()`` raises, so the node never returns and no timestamp is
        refreshed; ``Command(resume=…)`` re-enters at that node, and the router
        — where the turn-start reset lives — does not replay. With a wall clock,
        an approval slower than the timeout ended the resumed turn on the very
        next routing. Measured on a real graph: 2.01 s wall for 0.0102 s compute.
        """
        mock_settings.react_agent_max_iterations = 15
        mock_settings.react_agent_timeout_seconds = 120
        ai_msg = AIMessage(
            content="",
            tool_calls=[{"id": "tc_1", "name": "search_contacts", "args": {}}],
        )
        state: dict = {
            "messages": [ai_msg],
            "react_iteration": 2,
            # Three hours of wall clock: the user went to lunch mid-approval.
            "react_start_time": time.time() - 10_800,
            # Ten seconds of actual compute.
            "react_elapsed_seconds": 10.0,
        }
        assert route_from_react_call_model(state) == NODE_REACT_EXECUTE_TOOLS

    def test_pending_draft_routes_to_hitl_dispatch(self) -> None:
        """A prepared draft → hand off to the shared HITL dispatch node."""
        state: dict = {
            "pending_draft_critique": {"draft_id": "draft_1", "draft_type": "event"},
        }
        assert route_from_react_execute_tools(state) == NODE_DRAFT_CRITIQUE

    def test_no_draft_routes_to_call_model(self) -> None:
        """No draft (None) → continue the normal ReAct loop."""
        state: dict = {"pending_draft_critique": None}
        assert route_from_react_execute_tools(state) == NODE_REACT_CALL_MODEL

    def test_missing_key_routes_to_call_model(self) -> None:
        """Absent key → continue the normal ReAct loop (no mis-route)."""
        state: dict = {}
        assert route_from_react_execute_tools(state) == NODE_REACT_CALL_MODEL

    def test_empty_draft_dict_routes_to_call_model(self) -> None:
        """Falsy draft value (empty dict) → continue the loop, not a handoff."""
        state: dict = {"pending_draft_critique": {}}
        assert route_from_react_execute_tools(state) == NODE_REACT_CALL_MODEL


@pytest.mark.unit
class TestAdaptiveBudgetRouting:
    """ADR-238: the router honors the per-turn effective budget, ceiling
    fallback when the setup did not compute one (flag off / legacy state)."""

    def test_effective_budget_stops_the_loop_early(self):
        from src.core.config import settings
        from src.domains.agents.constants import NODE_REACT_FINALIZE
        from src.domains.agents.nodes.routing import route_from_react_call_model

        state = {
            "messages": [],
            "react_iteration": 4,
            "react_max_iterations_effective": 4,
        }

        assert settings.react_agent_max_iterations > 4
        assert route_from_react_call_model(state) == NODE_REACT_FINALIZE

    def test_missing_budget_falls_back_to_the_configured_ceiling(self):
        from src.core.config import settings
        from src.domains.agents.constants import NODE_REACT_FINALIZE
        from src.domains.agents.nodes.routing import route_from_react_call_model

        state = {
            "messages": [],
            "react_iteration": settings.react_agent_max_iterations,
            "react_max_iterations_effective": None,
        }

        assert route_from_react_call_model(state) == NODE_REACT_FINALIZE
