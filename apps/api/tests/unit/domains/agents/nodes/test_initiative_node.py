"""
Unit tests for initiative_node.

Tests the post-execution proactive enrichment node.

Phase: ADR-062 — Agent Initiative Phase
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.domains.agents.nodes.initiative_node import (
    InitiativeAction,
    InitiativeDecision,
    _extract_domains,
    _extract_original_query,
    _format_interests,
    _format_memory_facts,
)
from src.domains.agents.orchestration.plan_schemas import ParameterItem, ParameterValue


@pytest.mark.unit
class TestInitiativeDecision:
    """Tests for InitiativeDecision schema."""

    def test_no_action_decision(self) -> None:
        decision = InitiativeDecision(
            analysis="No cross-domain signals found.",
            should_act=False,
            reasoning="Results are self-contained.",
        )
        assert not decision.should_act
        assert decision.actions == []
        assert decision.suggestion is None

    def test_action_with_suggestion(self) -> None:
        decision = InitiativeDecision(
            analysis="Email mentions a meeting.",
            should_act=True,
            reasoning="Check calendar availability.",
            actions=[
                InitiativeAction(
                    tool_name="get_events_tool",
                    parameters=[
                        ParameterItem(
                            name="start_date",
                            value=ParameterValue(string_value="2026-03-26", value_type="string"),
                        )
                    ],
                    rationale="Check Thursday availability",
                )
            ],
            suggestion="Would you like me to create a calendar event?",
        )
        assert decision.should_act
        assert len(decision.actions) == 1
        assert decision.suggestion is not None


@pytest.mark.unit
class TestExtractDomains:
    """Tests for _extract_domains."""

    def test_none_qi(self) -> None:
        state: dict = {"query_intelligence": None}
        assert _extract_domains(state) == []

    def test_qi_with_domains(self) -> None:
        qi = MagicMock()
        qi.domains = ["email", "contact"]
        state: dict = {"query_intelligence": qi}
        assert _extract_domains(state) == ["email", "contact"]

    def test_qi_without_domains_attr(self) -> None:
        qi = MagicMock(spec=[])
        state: dict = {"query_intelligence": qi}
        assert _extract_domains(state) == []


@pytest.mark.unit
class TestExtractOriginalQuery:
    """Tests for _extract_original_query."""

    def test_finds_last_human_message(self) -> None:
        from langchain_core.messages import AIMessage, HumanMessage

        state: dict = {
            "messages": [
                HumanMessage(content="first question"),
                AIMessage(content="response"),
                HumanMessage(content="second question"),
            ]
        }
        assert _extract_original_query(state) == "second question"

    def test_empty_messages(self) -> None:
        state: dict = {"messages": []}
        assert _extract_original_query(state) == ""


@pytest.mark.unit
class TestFormatHelpers:
    """Tests for formatting helpers."""

    def test_format_memory_facts_none(self) -> None:
        assert _format_memory_facts(None) == "No relevant memories."

    def test_format_memory_facts_with_data(self) -> None:
        result = _format_memory_facts(["Fact 1", "Fact 2"])
        assert "Fact 1" in result
        assert "Fact 2" in result

    def test_format_interests_empty(self) -> None:
        assert _format_interests({"interests": []}) == "No known interests."

    def test_format_interests_with_data(self) -> None:
        profile = {
            "interests": [
                {"topic": "cycling", "category": "sports", "status": "active"},
                {"topic": "cooking", "category": "hobbies", "status": "inactive"},
            ]
        }
        result = _format_interests(profile)
        assert "cycling" in result
        assert "cooking" not in result  # inactive filtered out


@pytest.mark.unit
@pytest.mark.asyncio
class TestInitiativeSkippedWhenSkillActive:
    """Initiative is skipped when a skill is driving the turn.

    Skills define a deterministic output contract (plan_template + references).
    Running initiative on top would inject orthogonal domains (e.g. "nearby
    places" during a daily briefing), polluting the skill's intended output
    and confusing the response LLM that must follow the skill's formatting.
    """

    async def test_skips_when_execution_plan_carries_skill_name(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.domains.agents.nodes import initiative_node as mod

        monkeypatch.setattr(mod.settings, "initiative_enabled", True, raising=False)

        plan = MagicMock()
        plan.metadata = {"skill_name": "briefing-quotidien"}
        state = {
            "execution_plan": plan,
            "initiative_iteration": 0,
        }
        config = {"configurable": {"user_id": "test-user"}}

        result = await mod.initiative_node(state, config)

        assert result.get("initiative_skipped_reason") == "skill_active"
        assert result.get("initiative_iteration") == 1

    async def test_runs_when_plan_has_no_skill_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Regular (non-skill) plans still proceed past the skill check.

        Verified by letting the node reach the next early-return
        (``no_adjacent_read_only_tools``) — proof the skill check did not
        short-circuit first.
        """
        from src.domains.agents.nodes import initiative_node as mod

        monkeypatch.setattr(mod.settings, "initiative_enabled", True, raising=False)

        plan = MagicMock()
        plan.metadata = {}  # no skill_name
        state = {
            "execution_plan": plan,
            "initiative_iteration": 0,
            "query_intelligence": None,  # forces empty executed_domains
        }
        config = {"configurable": {"user_id": "test-user"}}

        result = await mod.initiative_node(state, config)

        assert result.get("initiative_skipped_reason") != "skill_active"

    async def test_skips_when_plan_metadata_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A plan without ``metadata`` attribute does not crash the check."""
        from src.domains.agents.nodes import initiative_node as mod

        monkeypatch.setattr(mod.settings, "initiative_enabled", True, raising=False)

        plan = MagicMock()
        plan.metadata = None
        state = {
            "execution_plan": plan,
            "initiative_iteration": 0,
            "query_intelligence": None,
        }
        config = {"configurable": {"user_id": "test-user"}}

        result = await mod.initiative_node(state, config)

        # Not skipped for "skill_active" since no skill_name present
        assert result.get("initiative_skipped_reason") != "skill_active"
