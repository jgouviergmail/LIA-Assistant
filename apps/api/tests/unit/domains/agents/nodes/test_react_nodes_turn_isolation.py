"""Turn-isolation and prompt-precision tests for the ReAct nodes.

Covers the 2026-07-02 cross-turn data leak fix:

- ``react_setup_node`` purges ``current_turn_registry`` at the start of every
  ReAct turn (the checkpoint-restored value from the PREVIOUS turn otherwise
  seeds react_execute_tools' intra-turn accumulation, and the response node
  then re-displays last turn's data — e.g. previous events on a route question).
- The ReAct system prompt carries the PRECISION rule and the cross-domain
  semantic dependencies section (same links the pipeline planner receives),
  so the LLM fetches exact values (contact address) instead of settling for
  approximate memory values (a city name).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.domains.agents.nodes.react_nodes import _build_system_prompt, react_setup_node


@pytest.mark.unit
@pytest.mark.asyncio
class TestReactSetupPurgesTurnRegistry:
    """react_setup_node must reset current_turn_registry for the new turn."""

    async def test_setup_returns_empty_current_turn_registry(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.domains.agents.nodes import react_nodes as mod

        monkeypatch.setattr(mod.settings, "react_agent_enabled", True, raising=False)
        monkeypatch.setattr(mod.settings, "journals_enabled", False, raising=False)
        monkeypatch.setattr(mod.settings, "skills_enabled", False, raising=False)

        selector = MagicMock()
        selector.select.return_value = ([], {})
        with patch.object(mod, "ReactToolSelector", return_value=selector):
            state = {
                "messages": [],
                # Simulates the checkpoint-restored leftovers from the previous turn
                "current_turn_registry": {"event_prev": {"payload": {"summary": "old"}}},
            }
            result = await react_setup_node(state, {"configurable": {}})

        assert result.get("current_turn_registry") == {}

    async def test_setup_disabled_returns_empty_update(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Feature flag off → node stays a strict no-op (no purge either)."""
        from src.domains.agents.nodes import react_nodes as mod

        monkeypatch.setattr(mod.settings, "react_agent_enabled", False, raising=False)

        result = await react_setup_node({"messages": []}, {"configurable": {}})

        assert result == {}


@pytest.mark.unit
class TestReactSystemPromptPrecision:
    """The ReAct system prompt carries precision guidance + semantic links."""

    def test_prompt_contains_precision_rule_and_semantic_section(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.config import settings as real_settings

        monkeypatch.setattr(real_settings, "semantic_linking_enabled", True, raising=False)

        state = {
            "personality_instruction": "friendly",
            "user_timezone": "Europe/Paris",
            "user_language": "fr",
            # Dict form — the serialized shape get_qi_attr reads at runtime
            "query_intelligence": {"domains": ["route", "contact"]},
        }

        prompt = _build_system_prompt(state)

        assert "PRECISION" in prompt
        assert "<CrossDomainDataTypes>" in prompt
        # Real registry: contact provides physical_address consumed by route tools
        assert "physical_address" in prompt

    def test_prompt_formats_without_domains(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """No detected domains → the section degrades to its fallback text
        without raising (placeholder parity guard)."""
        state = {"messages": []}

        prompt = _build_system_prompt(state)

        assert "<CrossDomainDataTypes>" in prompt
        assert "{semantic_dependencies}" not in prompt  # placeholder resolved
