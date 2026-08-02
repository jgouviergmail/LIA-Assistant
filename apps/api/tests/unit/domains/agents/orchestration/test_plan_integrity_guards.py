"""Guards against the two ways a plan silently answered the wrong question.

Both were measured on 2026-07-23 in the dev API logs, on the same conversation:

RC-1 — a truncated plan nobody checked.
    "What will the weather be like for my two appointments on July 25?"
    query_analysis_complete: primary_domain="weather"
    planner_v3_success:      steps=1  ->  get_events_tool only
    semantic_validation_skipped: reason="single_step_trivial"
    The response node held the question but no weather data, and invented
    temperatures. The read-only exemption assumed a single-step plan meant the
    planner had *consolidated* several domains into one call; here it had
    *dropped* the primary one. A registry lookup separates the two.

RC-2/RC-3 — a parameter whose value was the string "null".
    weather_geocode_completed: query="null"  ->  "Prévisions pour Cappaghnanool, IE"
    `$item.location` resolved to None, and the placeholder sits inside JSON
    quotes, so `null` became the literal text "null" — which sails past every
    `if not location` guard and gets geocoded as a city name.
"""

from __future__ import annotations

import pytest

from src.domains.agents.orchestration.dependency_graph import DependencyGraph
from src.domains.agents.orchestration.plan_schemas import ExecutionPlan, ExecutionStep, StepType
from src.domains.agents.orchestration.semantic_validator import should_trigger_semantic_validation

pytestmark = [pytest.mark.unit]

WEATHER_TOOL = "get_weather_forecast_tool"
EVENTS_TOOL = "get_events_tool"


def _plan(*tools: str) -> ExecutionPlan:
    return ExecutionPlan(
        plan_id="test_plan",
        user_id="00000000-0000-0000-0000-000000000001",
        steps=[
            ExecutionStep(
                step_id=f"step_{idx + 1}",
                step_type=StepType.TOOL,
                # Every producer names the agent, and a TOOL step without one is
                # now refused outright — test data has to look like real data.
                agent_name="test_agent",
                tool_name=tool,
                parameters={},
            )
            for idx, tool in enumerate(tools)
        ],
    )


def _intelligence(primary: str, domains: list[str]) -> dict:
    return {
        "primary_domain": primary,
        "domains": domains,
        "is_mutation_intent": False,
        "has_cardinality_risk": False,
    }


class TestPrimaryDomainCoverage:
    """RC-1: a single step that drops the primary domain is a loss, not a merge."""

    def test_the_prod_case_triggers_validation(self):
        should, reason = should_trigger_semantic_validation(
            _plan(EVENTS_TOOL),
            "What will the weather be like for my two appointments on July 25?",
            query_intelligence=_intelligence("weather", ["weather", "event"]),
        )
        assert should is True
        assert reason == "primary_domain_uncovered:weather"

    def test_a_genuine_consolidation_is_left_alone(self):
        """One step that DOES call a primary-domain tool must stay exempt.

        This is the case the read-only exemption was written for; forcing an
        LLM validation here is the spurious-clarification risk we must not
        reintroduce.
        """
        should, reason = should_trigger_semantic_validation(
            _plan(WEATHER_TOOL),
            "weather in Paris tomorrow",
            query_intelligence=_intelligence("weather", ["weather", "event"]),
        )
        assert should is False
        assert reason == "single_step_trivial"

    def test_multi_step_plan_is_not_affected_by_this_rule(self):
        should, reason = should_trigger_semantic_validation(
            _plan(EVENTS_TOOL, WEATHER_TOOL),
            "weather for my appointments",
            query_intelligence=_intelligence("weather", ["weather", "event"]),
        )
        assert reason != "primary_domain_uncovered:weather"

    @pytest.mark.parametrize("primary", ["", "general", "not_a_domain"])
    def test_unknown_primary_domain_fails_open(self, primary: str):
        """No domain, or one absent from DOMAIN_REGISTRY -> never force."""
        should, reason = should_trigger_semantic_validation(
            _plan(EVENTS_TOOL),
            "hello",
            query_intelligence=_intelligence(primary, [primary] if primary else []),
        )
        assert reason != f"primary_domain_uncovered:{primary}"

    def test_unregistered_tool_fails_open(self):
        """An unknown tool cannot prove the domain is uncovered."""
        should, reason = should_trigger_semantic_validation(
            _plan("some_future_tool"),
            "weather please",
            query_intelligence=_intelligence("weather", ["weather"]),
        )
        assert reason != "primary_domain_uncovered:weather"

    def test_no_query_intelligence_keeps_the_previous_behaviour(self):
        should, reason = should_trigger_semantic_validation(_plan(EVENTS_TOOL), "anything")
        assert should is False
        assert reason == "single_step_trivial"


class TestForEachMissingField:
    """RC-2: `$item.field` resolving to None must mean "not provided"."""

    def _substitute(self, params: dict, item: dict) -> dict:
        return DependencyGraph(_plan(EVENTS_TOOL))._substitute_item_in_params(
            params=params, item=item, item_index=0
        )

    def test_missing_field_drops_the_parameter(self):
        """The prod case: events carry no `location`."""
        resolved = self._substitute(
            {"location": "$item.location", "date": "$item.start_datetime"},
            {"summary": "Rdv podologue", "start_datetime": "2026-07-25T11:15:00+02:00"},
        )
        assert "location" not in resolved
        assert resolved["date"] == "2026-07-25T11:15:00+02:00"

    def test_the_literal_string_null_is_never_produced(self):
        resolved = self._substitute({"location": "$item.location"}, {"summary": "x"})
        assert "null" not in str(resolved).lower()

    def test_present_field_is_substituted_normally(self):
        resolved = self._substitute({"location": "$item.location"}, {"location": "Paris, FR"})
        assert resolved["location"] == "Paris, FR"

    def test_missing_field_inside_a_larger_string_blanks_only_the_placeholder(self):
        """Dropping the whole parameter would discard the surrounding text."""
        resolved = self._substitute({"note": "Weather for $item.location today"}, {"summary": "x"})
        assert resolved["note"] == "Weather for  today"

    def test_falsy_but_present_values_are_preserved(self):
        """0 and "" are values, not absences — neither may be dropped.

        Numbers come back stringified: the placeholder sits inside JSON quotes
        and downstream type coercion handles it. That is pre-existing behaviour,
        deliberately left untouched — only the None case was provably harmful.
        """
        resolved = self._substitute(
            {"count": "$item.count", "label": "$item.label"}, {"count": 0, "label": ""}
        )
        assert resolved["count"] == "0"
        assert resolved["label"] == ""
