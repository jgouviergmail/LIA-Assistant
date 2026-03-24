"""
Unit tests for route_from_initiative.

Phase: ADR-062 — Agent Initiative Phase
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.core.constants import (
    NODE_INITIATIVE,
    STATE_KEY_INITIATIVE_ITERATION,
    STATE_KEY_INITIATIVE_RESULTS,
)
from src.domains.agents.constants import NODE_RESPONSE
from src.domains.agents.nodes.routing import route_from_initiative


@pytest.mark.unit
class TestRouteFromInitiative:
    """Tests for route_from_initiative routing function."""

    @patch("src.core.config.settings")
    def test_disabled_routes_to_response(self, mock_settings: object) -> None:
        mock_settings.initiative_enabled = False
        state: dict = {}
        assert route_from_initiative(state) == NODE_RESPONSE

    @patch("src.core.config.settings")
    def test_iteration_zero_routes_to_response(self, mock_settings: object) -> None:
        mock_settings.initiative_enabled = True
        state: dict = {STATE_KEY_INITIATIVE_ITERATION: 0}
        assert route_from_initiative(state) == NODE_RESPONSE

    @patch("src.core.config.settings")
    def test_actions_executed_loops_back(self, mock_settings: object) -> None:
        mock_settings.initiative_enabled = True
        mock_settings.initiative_max_iterations = 2
        state: dict = {
            STATE_KEY_INITIATIVE_ITERATION: 1,
            STATE_KEY_INITIATIVE_RESULTS: [{"actions_executed": 2}],
        }
        assert route_from_initiative(state) == NODE_INITIATIVE

    @patch("src.core.config.settings")
    def test_max_iterations_routes_to_response(self, mock_settings: object) -> None:
        mock_settings.initiative_enabled = True
        mock_settings.initiative_max_iterations = 1
        state: dict = {
            STATE_KEY_INITIATIVE_ITERATION: 1,
            STATE_KEY_INITIATIVE_RESULTS: [{"actions_executed": 1}],
        }
        assert route_from_initiative(state) == NODE_RESPONSE

    @patch("src.core.config.settings")
    def test_no_actions_routes_to_response(self, mock_settings: object) -> None:
        mock_settings.initiative_enabled = True
        mock_settings.initiative_max_iterations = 2
        state: dict = {
            STATE_KEY_INITIATIVE_ITERATION: 1,
            STATE_KEY_INITIATIVE_RESULTS: [{"actions_executed": 0}],
        }
        assert route_from_initiative(state) == NODE_RESPONSE
