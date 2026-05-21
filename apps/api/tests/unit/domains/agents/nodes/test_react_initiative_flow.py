"""Unit tests for the ReAct → Initiative wiring (ADR-070).

Exercises the cross-component contract at the function level (no DB/Redis/LLM):
``route_from_react_finalize`` gates the nominal path on the flags, and the
``response_node`` merge keeps the ReAct answer alive alongside an Initiative
entry (verified through the shared agent_results formatter).
"""

from __future__ import annotations

import pytest

from src.core.config import settings
from src.domains.agents.formatters.agent_results import format_agent_results_for_prompt
from src.domains.agents.nodes.response_node import _merge_react_synthesis_result
from src.domains.agents.nodes.routing import route_from_react_finalize


@pytest.mark.unit
class TestReactInitiativeFlow:
    def test_flag_on_routes_into_initiative(self, monkeypatch):
        monkeypatch.setattr(settings, "initiative_enabled", True)
        monkeypatch.setattr(settings, "initiative_react_enabled", True)
        assert route_from_react_finalize({"execution_mode": "react"}) == "initiative"

    def test_flag_off_skips_initiative(self, monkeypatch):
        monkeypatch.setattr(settings, "initiative_enabled", True)
        monkeypatch.setattr(settings, "initiative_react_enabled", False)
        assert route_from_react_finalize({"execution_mode": "react"}) == "response"

    def test_answer_and_findings_coexist(self):
        """After Initiative wrote its entry, the ReAct answer is still delivered."""
        after_initiative = {"4:initiative": {"status": "success", "data": {"weather": "18C"}}}
        merged = _merge_react_synthesis_result(after_initiative, "Your meeting is at 3pm.", 4, {})
        summary = format_agent_results_for_prompt(merged, current_turn_id=4)
        assert "Your meeting is at 3pm." in summary  # ReAct answer survived
