"""The evaluator's decision is read as the structured door reads it: ``schema(**args)``.

Measured 2026-11-08 on the restored prompt (ADR-062 amendment b): 2 evaluations in 50 named
their second action's tool in ``name`` instead of ``tool_name``, and the strict schema threw
the whole decision away, chips included. An action can only name its tool, so that slip is
repaired before validation; anything that needs a guess stays an error.
"""

import pytest
from pydantic import ValidationError

from src.domains.agents.nodes.initiative_schemas import InitiativeDecision

pytestmark = pytest.mark.unit


def _parameter(name: str, value: str) -> dict:
    return {"name": name, "value": {"string_value": value, "value_type": "string"}}


def _decision(*actions: dict) -> dict:
    return {
        "analysis": "A trip to Annecy on Saturday morning",
        "should_act": True,
        "reasoning": "The weather there matters for the drive",
        "actions": list(actions),
        "followup_suggestions": ["Find a restaurant in Annecy for Saturday lunch"],
    }


FIRST = {
    "tool_name": "get_events_tool",
    "parameters": [_parameter("time_min", "2026-10-31T06:00:00+01:00")],
    "rationale": "Anything else planned that morning",
}


def test_an_action_naming_its_tool_in_name_is_repaired() -> None:
    slipped = {
        "name": "get_weather_forecast_tool",
        "parameters": [_parameter("location", "Annecy")],
        "rationale": "Rain on the road matters",
    }
    decision = InitiativeDecision(**_decision(FIRST, slipped))
    assert [action.tool_name for action in decision.actions] == [
        "get_events_tool",
        "get_weather_forecast_tool",
    ]
    assert decision.followup_suggestions == ["Find a restaurant in Annecy for Saturday lunch"]


def test_two_names_for_one_action_stay_an_error() -> None:
    # Which tool is meant would be a guess.
    ambiguous = {**FIRST, "name": "get_weather_forecast_tool"}
    with pytest.raises(ValidationError):
        InitiativeDecision(**_decision(ambiguous))


def test_a_parameter_keeps_its_own_name() -> None:
    decision = InitiativeDecision(**_decision(FIRST))
    assert decision.actions[0].parameters[0].name == "time_min"


def test_an_action_flattened_into_its_parameter_stays_an_error() -> None:
    # The other shape measured that day: nothing in it says which tool was meant.
    flattened = {"rationale": "x", "name": "location", "value": "Annecy", "value_type": "string"}
    with pytest.raises(ValidationError):
        InitiativeDecision(**_decision(flattened))
