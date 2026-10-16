"""A FOR_EACH item reaches its step's parameters whole, whatever its type.

The substitution spliced each value into the JSON TEXT of the parameters and parsed
it back. A bare ``$item`` whose item was a string arrived with its own quotes inside
the quotes the parameter already had (``""Musée du Louvre, Paris""``); the parse
failed, and the step ran with the literal ``"$item"`` — measured on Docker dev
2026-10-16: three walking routes sent to Google with destination ``$item``, billed,
answered « no route ». An object or a list met the same fate; the substitution now
works on the parameters themselves, so no value is ever re-parsed.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.domains.agents.orchestration.dependency_graph import DependencyGraph
from src.domains.agents.orchestration.plan_schemas import ExecutionPlan, ExecutionStep, StepType

pytestmark = pytest.mark.unit

ORIGIN = "Gare Saint-Lazare, Paris"
DESTINATIONS = ["Musée du Louvre, Paris", "Opéra Garnier, Paris", "Place de la Concorde, Paris"]
ROUTE_PARAMS = {"origin": ORIGIN, "destination": "$item", "travel_mode": "WALK"}


def _plan(parameters: dict[str, Any]) -> ExecutionPlan:
    """The live plan: a route matrix, then one route per destination it returned."""
    return ExecutionPlan(
        user_id="user_123",
        session_id="session_456",
        execution_mode="sequential",
        steps=[
            ExecutionStep(
                step_id="step_1",
                step_type=StepType.TOOL,
                agent_name="route_agent",
                tool_name="get_route_matrix_tool",
                parameters={"origins": [ORIGIN], "destinations": DESTINATIONS},
            ),
            ExecutionStep(
                step_id="step_2",
                step_type=StepType.TOOL,
                agent_name="route_agent",
                tool_name="get_route_tool",
                parameters=parameters,
                depends_on=["step_1"],
                for_each="$steps.step_1.destinations",
                for_each_max=10,
            ),
        ],
    )


def _substitute(params: dict[str, Any], item: Any, index: int = 0) -> dict[str, Any]:
    return DependencyGraph(_plan(ROUTE_PARAMS))._substitute_item_in_params(params, item, index)


class TestTheLiveCase:
    def test_each_route_step_receives_its_own_destination(self) -> None:
        graph = DependencyGraph(_plan(ROUTE_PARAMS))
        steps, _ = graph.expand_for_each_steps({"step_1": {"destinations": DESTINATIONS}})
        routes = [step for step in steps if step.step_id.startswith("step_2_item_")]
        assert [step.parameters["destination"] for step in routes] == DESTINATIONS
        assert {step.parameters["origin"] for step in routes} == {ORIGIN}
        assert {step.parameters["travel_mode"] for step in routes} == {"WALK"}


class TestAWholeItem:
    @pytest.mark.parametrize(
        "item", ["Musée du Louvre, Paris", 'He said "hi" \\ twice', "", "two\nlines", "a $item b"]
    )
    def test_a_string_item_is_the_value(self, item: str) -> None:
        assert _substitute({"destination": "$item"}, item)["destination"] == item

    def test_an_object_item_is_the_value_never_the_same_object(self) -> None:
        item = {"name": "Louvre", "location": {"lat": 48.86, "lng": 2.34}}
        resolved = _substitute({"place": "$item"}, item)
        assert resolved["place"] == item
        assert resolved["place"] is not item

    def test_a_list_item_is_the_value(self) -> None:
        assert _substitute({"names": "$item"}, ["a", "b"])["names"] == ["a", "b"]

    def test_a_missing_item_leaves_the_parameter_out(self) -> None:
        assert _substitute({"destination": "$item", "mode": "WALK"}, None) == {"mode": "WALK"}


class TestAFieldHoldingAnObject:
    def test_the_object_is_the_value(self) -> None:
        item = {"location": {"lat": 48.86, "lng": 2.34}}
        assert _substitute({"where": "$item.location"}, item)["where"] == {
            "lat": 48.86,
            "lng": 2.34,
        }

    def test_a_list_field_is_the_value(self) -> None:
        assert _substitute({"to": "$item.emails"}, {"emails": ["a@x.test"]})["to"] == ["a@x.test"]


class TestInsideText:
    def test_a_string_item_reads_as_text(self) -> None:
        note = _substitute({"note": "Itinéraire vers $item"}, "Opéra Garnier, Paris")["note"]
        assert note == "Itinéraire vers Opéra Garnier, Paris"

    def test_an_object_reads_as_its_json(self) -> None:
        note = _substitute({"note": "Lieu : $item"}, {"name": "Louvre"})["note"]
        assert note == 'Lieu : {"name": "Louvre"}'

    def test_the_index_reads_as_its_number(self) -> None:
        label = _substitute({"label": "Étape $item_index sur 3"}, "x", 2)["label"]
        assert label == "Étape 2 sur 3"


class TestNoReferenceSurvives:
    @pytest.mark.parametrize(
        "item", ["x", 'q"uote', "back\\slash", {"k": 'v"'}, ["a"], 0, 1.5, True, None]
    )
    def test_whatever_the_item_no_parameter_keeps_a_reference(self, item: Any) -> None:
        params = {
            "a": "$item",
            "b": "before $item after",
            "c": "$item.k",
            "d": "$item_index",
            "e": ["$item", "n° $item_index"],
            "f": {"nested": "$item"},
        }
        assert "$item" not in repr(_substitute(params, item, 1))
