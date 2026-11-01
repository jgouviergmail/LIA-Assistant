"""The domain of the last list a turn SHOWED — where « the 2nd one » points (ADR-367).

The tool's name used to decide (``search_``/``list_``/``find_``/``query_``):
no unified tool carries such a prefix (``get_emails_tool``…), so the list the
person last saw was never recorded for the main domains, and a lookup another
step consumed counted as shown.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.domains.agents.nodes.execution_state import _detect_list_tool_domain
from src.domains.agents.orchestration.plan_schemas import ExecutionPlan, ExecutionStep, StepType

pytestmark = pytest.mark.unit


def _step(step_id: str, tool: str, depends_on: list[str] | None = None) -> ExecutionStep:
    return ExecutionStep(
        step_id=step_id,
        step_type=StepType.TOOL,
        agent_name="agent",
        tool_name=tool,
        depends_on=depends_on or [],
    )


def _registry(*produced: tuple[str, str, int]) -> dict[str, Any]:
    return {
        f"{step}-{domain}-{n}": {"id": f"{step}-{n}", "meta": {"step_id": step, "domain": domain}}
        for step, domain, count in produced
        for n in range(count)
    }


def _detect(steps: list[ExecutionStep], registry: dict[str, Any]) -> str | None:
    plan = ExecutionPlan(user_id="u", steps=steps)
    return _detect_list_tool_domain(plan, {step.step_id: {} for step in steps}, registry)


def test_a_listing_by_a_unified_tool_is_the_shown_list() -> None:
    assert _detect([_step("s1", "get_emails_tool")], _registry(("s1", "emails", 5))) == "emails"


def test_a_single_item_is_no_list() -> None:
    assert _detect([_step("s1", "get_emails_tool")], _registry(("s1", "emails", 1))) is None


def test_a_lookup_another_step_consumed_was_not_shown() -> None:
    steps = [_step("s1", "get_emails_tool"), _step("s2", "reply_email_tool", depends_on=["s1"])]
    assert _detect(steps, _registry(("s1", "emails", 3))) is None


def test_the_last_list_shown_wins() -> None:
    steps = [_step("s1", "get_emails_tool"), _step("s2", "get_events_tool")]
    assert _detect(steps, _registry(("s1", "emails", 2), ("s2", "events", 3))) == "events"


def test_a_step_that_did_not_complete_showed_nothing() -> None:
    plan = ExecutionPlan(user_id="u", steps=[_step("s1", "get_emails_tool")])
    assert _detect_list_tool_domain(plan, {}, _registry(("s1", "emails", 4))) is None
