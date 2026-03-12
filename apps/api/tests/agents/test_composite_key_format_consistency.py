"""
Test composite key format consistency across the codebase.

This test ensures that all modules use the standard `make_agent_result_key()` function
to create composite keys with the colon format: "turn_id:agent_name"

Regression test for bug: "First search returns no results"
Root cause: mappers.py used underscore format while rest of codebase used colon format
"""

import pytest

from src.domains.agents.constants import make_agent_result_key
from src.domains.agents.orchestration.mappers import map_execution_result_to_agent_result
from src.domains.agents.orchestration.schemas import ExecutionResult, StepResult


def test_mapper_uses_standard_composite_key_format():
    """Test that mapper creates composite keys using standard colon format."""

    # Arrange: Create a mock ExecutionResult
    execution_result = ExecutionResult(
        success=True,
        completed_steps=1,
        total_steps=1,
        step_results=[
            StepResult(
                step_index=0,
                tool_name="search_contacts_tool",
                args={"query": "test"},
                success=True,
                result={
                    "success": True,
                    "data": {"contacts": [], "total_count": 0},
                },
                execution_time_ms=100,
            )
        ],
        failed_step_index=None,
        error=None,
        total_execution_time_ms=100,
    )

    turn_id = 1
    plan_id = "test_plan"

    # Act: Call mapper (what task_orchestrator_node does)
    agent_results = map_execution_result_to_agent_result(
        execution_result=execution_result,
        plan_id=plan_id,
        turn_id=turn_id,
    )

    # Assert: Mapper key matches standard function key
    mapper_key = list(agent_results.keys())[0]
    standard_key = make_agent_result_key(turn_id, "plan_executor")

    assert mapper_key == standard_key, (
        f"Mapper uses inconsistent key format!\n"
        f"  Mapper key:    '{mapper_key}'\n"
        f"  Standard key:  '{standard_key}'\n"
        f"Expected format: 'turn_id:agent_name' (with colon)"
    )


def test_composite_key_contains_colon_not_underscore():
    """Test that composite keys use colon separator, not underscore."""

    # Arrange
    execution_result = ExecutionResult(
        success=True,
        completed_steps=1,
        total_steps=1,
        step_results=[
            StepResult(
                step_index=0,
                tool_name="test_tool",
                args={},
                success=True,
                result={"success": True, "data": {}},
                execution_time_ms=50,
            )
        ],
        failed_step_index=None,
        error=None,
        total_execution_time_ms=50,
    )

    # Act
    agent_results = map_execution_result_to_agent_result(
        execution_result=execution_result,
        plan_id="test",
        turn_id=5,
    )

    # Assert: Key format verification
    mapper_key = list(agent_results.keys())[0]

    # Must contain colon (correct format)
    assert ":" in mapper_key, (
        f"Composite key missing colon separator: '{mapper_key}'\n"
        f"Expected format: 'turn_id:agent_name'"
    )

    # Must NOT be underscore format (old bug)
    assert mapper_key != "5_plan_executor", (
        f"Composite key uses old underscore format: '{mapper_key}'\n"
        f"This was the bug that caused 'first search returns no results'"
    )

    # Must be correct colon format
    assert (
        mapper_key == "5:plan_executor"
    ), f"Composite key has unexpected format: '{mapper_key}'\nExpected: '5:plan_executor'"


def test_composite_key_can_be_parsed_by_response_node():
    """Test that composite keys created by mapper can be parsed by response_node logic."""

    # Arrange
    execution_result = ExecutionResult(
        success=True,
        completed_steps=2,
        total_steps=2,
        step_results=[
            StepResult(
                step_index=0,
                tool_name="tool_a",
                args={},
                success=True,
                result={"success": True, "data": {"result": "A"}},
                execution_time_ms=50,
            ),
            StepResult(
                step_index=1,
                tool_name="tool_b",
                args={},
                success=True,
                result={"success": True, "data": {"result": "B"}},
                execution_time_ms=75,
            ),
        ],
        failed_step_index=None,
        error=None,
        total_execution_time_ms=125,
    )

    # Act
    agent_results = map_execution_result_to_agent_result(
        execution_result=execution_result,
        plan_id="test",
        turn_id=3,
    )

    # Assert: Simulate response_node parsing logic
    for composite_key, _result in agent_results.items():
        # response_node.py line 43: if ":" in composite_key
        assert (
            ":" in composite_key
        ), f"response_node cannot parse key without colon: '{composite_key}'"

        # response_node.py line 44: turn_id_str, agent_name = composite_key.split(":", 1)
        parts = composite_key.split(":", 1)
        assert (
            len(parts) == 2
        ), f"Composite key cannot be split into turn_id and agent_name: '{composite_key}'"

        turn_id_str, agent_name = parts

        # Must be able to convert turn_id to int
        try:
            parsed_turn_id = int(turn_id_str)
        except ValueError as e:
            pytest.fail(f"Cannot parse turn_id from key '{composite_key}': {e}")

        # Verify parsed values
        assert parsed_turn_id == 3, f"Wrong turn_id parsed: {parsed_turn_id}"
        assert agent_name == "plan_executor", f"Wrong agent_name parsed: {agent_name}"


def test_multiple_turns_use_different_composite_keys():
    """Test that different turns produce different composite keys."""

    # Arrange
    execution_result = ExecutionResult(
        success=True,
        completed_steps=1,
        total_steps=1,
        step_results=[
            StepResult(
                step_index=0,
                tool_name="test_tool",
                args={},
                success=True,
                result={"success": True, "data": {}},
                execution_time_ms=50,
            )
        ],
        failed_step_index=None,
        error=None,
        total_execution_time_ms=50,
    )

    # Act: Map results for different turns
    results_turn1 = map_execution_result_to_agent_result(execution_result, "plan1", turn_id=1)
    results_turn2 = map_execution_result_to_agent_result(execution_result, "plan2", turn_id=2)
    results_turn99 = map_execution_result_to_agent_result(execution_result, "plan99", turn_id=99)

    # Assert: Keys are different
    key1 = list(results_turn1.keys())[0]
    key2 = list(results_turn2.keys())[0]
    key99 = list(results_turn99.keys())[0]

    assert key1 == "1:plan_executor"
    assert key2 == "2:plan_executor"
    assert key99 == "99:plan_executor"

    # All must be different
    assert key1 != key2 != key99


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
