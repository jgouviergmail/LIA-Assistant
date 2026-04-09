"""
Unit tests for ReAct execution mode routing functions.

Phase: ADR-070 — ReAct Execution Mode
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage

from src.domains.agents.constants import NODE_REACT_EXECUTE_TOOLS, NODE_REACT_FINALIZE
from src.domains.agents.nodes.routing import route_from_react_call_model


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
    def test_timeout_routes_to_finalize(self, mock_settings: object) -> None:
        """Timeout exceeded → force finalize regardless of tool_calls."""
        import time

        mock_settings.react_agent_max_iterations = 15
        mock_settings.react_agent_timeout_seconds = 120
        ai_msg = AIMessage(
            content="",
            tool_calls=[{"id": "tc_1", "name": "search", "args": {}}],
        )
        # Simulate start_time 200 seconds ago (> 120s timeout)
        state: dict = {
            "messages": [ai_msg],
            "react_iteration": 2,
            "react_start_time": time.time() - 200,
        }
        assert route_from_react_call_model(state) == NODE_REACT_FINALIZE

    @patch("src.core.config.settings")
    def test_within_timeout_continues(self, mock_settings: object) -> None:
        """Within timeout → normal routing (continue if tool_calls)."""
        import time

        mock_settings.react_agent_max_iterations = 15
        mock_settings.react_agent_timeout_seconds = 120
        ai_msg = AIMessage(
            content="",
            tool_calls=[{"id": "tc_1", "name": "search", "args": {}}],
        )
        # Simulate start_time 10 seconds ago (< 120s timeout)
        state: dict = {
            "messages": [ai_msg],
            "react_iteration": 2,
            "react_start_time": time.time() - 10,
        }
        assert route_from_react_call_model(state) == NODE_REACT_EXECUTE_TOOLS
