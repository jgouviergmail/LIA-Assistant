"""Unit tests for ReAct -> Initiative routing (ADR-070).

The nominal ReAct path may pass through the Initiative node for proactive read-only
enrichment, gated by ``INITIATIVE_REACT_ENABLED``. The ReAct draft path keeps its own
independent edge into the Initiative node and is never gated by this flag.
"""

from __future__ import annotations

import pytest

from src.core.config import settings
from src.domains.agents.nodes.routing import (
    route_from_initiative,
    route_from_react_finalize,
)


@pytest.mark.unit
class TestRouteFromReactFinalize:
    """``route_from_react_finalize`` gates the nominal ReAct path on the flags."""

    def test_routes_to_initiative_when_both_flags_on(self, monkeypatch):
        monkeypatch.setattr(settings, "initiative_enabled", True)
        monkeypatch.setattr(settings, "initiative_react_enabled", True)
        assert route_from_react_finalize({}) == "initiative"

    def test_routes_to_response_when_react_flag_off(self, monkeypatch):
        monkeypatch.setattr(settings, "initiative_enabled", True)
        monkeypatch.setattr(settings, "initiative_react_enabled", False)
        assert route_from_react_finalize({}) == "response"

    def test_routes_to_response_when_initiative_globally_off(self, monkeypatch):
        monkeypatch.setattr(settings, "initiative_enabled", False)
        monkeypatch.setattr(settings, "initiative_react_enabled", True)
        assert route_from_react_finalize({}) == "response"


@pytest.mark.unit
class TestRouteFromInitiativeReactAware:
    """In ReAct there is no orchestrator loop: never loop back to initiative."""

    def test_react_always_proceeds_to_response_even_after_actions(self, monkeypatch):
        monkeypatch.setattr(settings, "initiative_enabled", True)
        monkeypatch.setattr(settings, "initiative_max_iterations", 1)
        state = {
            "execution_mode": "react",
            "initiative_iteration": 1,
            "initiative_results": [{"actions_executed": 2}],
        }
        assert route_from_initiative(state) == "response"
