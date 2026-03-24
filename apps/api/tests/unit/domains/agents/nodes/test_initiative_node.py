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
