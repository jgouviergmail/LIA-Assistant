"""The structural FOR_EACH check flags N copies of a tool fed by ONE producer — nothing else.

Measured on Docker dev, 2026-10-30 (the MCP confirmation programme's full-turn
proof): « supprime la note Courses du 21 octobre, puis montre-moi la liste à jour »
was planned ``list_notes → delete_note → list_notes`` — read, act, read again,
the shape a step waiting on an act's real result takes (spec 2026-10-29 D7). The
check collected the dependencies of the two ``list_notes`` steps, found ONE
(``step_2``: the first read depends on nothing, so it added nothing), and called
it « N steps that all depend on one parent »: every replan was refused, then the
turn asked the person « pour tous les éléments concernés, ou pour un seul ? ».

A copy that depends on nothing is a read of its own, not an item of an iteration.
"""

from __future__ import annotations

import pytest

from src.domains.agents.orchestration.plan_schemas import ExecutionPlan, ExecutionStep, StepType
from src.domains.agents.orchestration.semantic_validator import (
    SemanticIssueType,
    validate_for_each_patterns,
)

pytestmark = pytest.mark.unit


def _step(step_id: str, tool_name: str, *after: str) -> ExecutionStep:
    return ExecutionStep(
        step_id=step_id,
        step_type=StepType.TOOL,
        tool_name=tool_name,
        agent_name="test_agent",
        parameters={},
        depends_on=list(after),
    )


def _plan(*steps: ExecutionStep) -> ExecutionPlan:
    return ExecutionPlan(plan_id="test", user_id="test_user", steps=list(steps))


def test_a_read_again_after_an_act_is_not_an_iteration() -> None:
    plan = _plan(
        _step("step_1", "mcp_user_ab12cd34_list_notes"),
        _step("step_2", "mcp_user_ab12cd34_delete_note", "step_1"),
        _step("step_3", "mcp_user_ab12cd34_list_notes", "step_2"),
    )

    assert validate_for_each_patterns(plan) == (True, None, None)


def test_one_copy_fed_by_the_producer_and_one_of_its_own_is_not_an_iteration() -> None:
    plan = _plan(
        _step("step_1", "get_events_tool"),
        _step("step_2", "get_route_tool", "step_1"),
        _step("step_3", "get_route_tool"),
    )

    assert validate_for_each_patterns(plan) == (True, None, None)


def test_copies_all_fed_by_one_producer_are_still_an_iteration() -> None:
    plan = _plan(
        _step("step_1", "get_events_tool"),
        _step("step_2", "get_route_tool", "step_1"),
        _step("step_3", "get_route_tool", "step_1"),
        _step("step_4", "get_route_tool", "step_1"),
    )

    is_valid, feedback, issue_type = validate_for_each_patterns(plan)

    assert is_valid is False
    assert issue_type == SemanticIssueType.CARDINALITY_MISMATCH
    assert feedback is not None and "'step_1'" in feedback and "3 separate" in feedback


def test_copies_fed_by_two_producers_are_not_one_iteration() -> None:
    plan = _plan(
        _step("step_1", "get_events_tool"),
        _step("step_2", "search_contacts_tool"),
        _step("step_3", "get_route_tool", "step_1"),
        _step("step_4", "get_route_tool", "step_2"),
    )

    assert validate_for_each_patterns(plan) == (True, None, None)
