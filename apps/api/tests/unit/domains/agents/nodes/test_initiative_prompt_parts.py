"""The initiative evaluator's prompt parts render exactly as before the JEV gate left (ADR-374).

Characterization pinned on 2026-11-08 from the code that still carried the gate: the
gate's omission bookkeeping goes, the words the evaluator reads stay byte for byte.
"""

from types import SimpleNamespace

import pytest

from src.domains.agents.nodes import initiative_node as node

pytestmark = pytest.mark.unit


def _registry() -> dict[str, object]:
    return {
        "email_1": {
            "id": "email_1",
            "type": "EMAIL",
            "payload": {
                "id": "provider-id",
                "subject": "Contract renewal",
                "snippet": "S" * 180,
                "from": "alice@example.org",
                "to": ["bob@example.org", "carol@example.org", "dan@example.org"],
                "labels": ["L" * 90],
                "is_unread": True,
                "size": 42,
                "score": 0.5,
                "_private": "hidden",
                "status": "confirmed",
                "creator": {"email": "x@example.org"},
                "nested": {"a": 1},
                "empty_list": [],
                "none_value": None,
                "f1": "1",
                "f2": "2",
                "f3": "3",
            },
            "meta": {"source": "gmail", "domain": "email", "turn_id": 3},
        },
        "weird": {"id": "weird", "type": "EMAIL", "payload": "not a dict", "meta": {}},
    }


def test_registry_items_render_their_first_eight_readable_fields() -> None:
    expected = (
        "[email] subject: Contract renewal; snippet: " + "S" * 150 + "…; "
        "from: alice@example.org; to: bob@example.org (+2 more); labels: " + "L" * 80 + "; "
        "is_unread: True; size: 42; score: 0.5"
    )
    assert node._format_execution_summary({}, registry=_registry(), current_turn_id=3) == expected


def test_without_registry_the_current_turn_step_results_render() -> None:
    agent_results = {
        "3:plan_executor": {
            "status": "success",
            "agent_name": "plan_executor",
            "data": {
                "step_results": [
                    {"tool_name": f"tool_{i}", "result": {"message": f"Found {i} items."}}
                    for i in range(6)
                ]
                + ["not-a-dict"]
            },
        },
        "3:failed": {"status": "error", "agent_name": "mail", "error": "Provider timeout"},
        "2:old": {
            "status": "success",
            "agent_name": "old",
            "data": {"step_results": [{"tool_name": "old_tool", "result": {"message": "stale"}}]},
        },
        "3:raw": {
            "status": "success",
            "agent_name": "raw",
            "data": {"aggregated_results": [{"tool_name": "raw_tool", "result": "R" * 260}]},
        },
    }
    expected = "\n".join(
        [
            *(f"[tool_{i}] Found {i} items." for i in range(5)),
            "[mail] ERROR: Provider timeout",
            "[raw_tool] " + "R" * 200,
        ]
    )
    assert node._format_execution_summary(agent_results, registry={}, current_turn_id=3) == expected


def test_nothing_retrieved_says_so() -> None:
    assert (
        node._format_execution_summary({}, registry={}, current_turn_id=3)
        == "No execution results."
    )


def test_interests_memory_and_tools_render_as_the_evaluator_reads_them() -> None:
    interests = {
        "interests": [
            {"topic": f"Topic {i}", "category": "hobby", "status": "active" if i != 2 else "paused"}
            for i in range(8)
        ]
    }
    assert node._format_interests(interests) == (
        "User interests: Topic 0 (hobby), Topic 1 (hobby), Topic 3 (hobby), Topic 4 (hobby)"
    )
    assert node._format_interests({"interests": []}) == "No known interests."
    assert node._format_memory_facts(["Likes trains", "Lives in Lyon"]) == (
        "Relevant user context:\n- Likes trains\n- Lives in Lyon"
    )
    assert node._format_memory_facts(None) == "No relevant memories."

    def param(name: str, required: bool = False, description: str = "") -> SimpleNamespace:
        return SimpleNamespace(name=name, required=required, description=description)

    manifests = [
        SimpleNamespace(
            name="get_events_tool",
            description="Read events",
            parameters=[
                param("date", description="ISO date"),
                param("calendar_id", required=True),
                param("max_results"),
            ],
        ),
        SimpleNamespace(name="get_weather_tool", description="Weather", parameters=[]),
    ]
    assert node._format_tools_for_prompt(manifests) == (
        "- get_events_tool: Read events | Params: date: ISO date, calendar_id (required), "
        "max_results\n- get_weather_tool: Weather"
    )
