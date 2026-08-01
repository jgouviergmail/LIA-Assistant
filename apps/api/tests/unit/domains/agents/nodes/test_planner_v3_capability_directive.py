"""The planner NODE must actually honour the directive, not merely be able to.

``ensure_directive_step`` is unit-tested on its own, but a perfect function
nobody calls guarantees nothing. This exercises the real ``planner_node_v3``
with the real ContextVar, only the planning service being stubbed — the seam
between "a capability was invoked" and "the plan carries it" is exactly where a
refactor would silently drop the wiring.

Position matters as much as presence: the seeding must land BEFORE the plan is
validated, so the validator sees the plan that will actually run. The
``validation_result`` returned by the node is what proves it.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.core.context import capability_directive_ctx
from src.domains.agents.analysis.query_intelligence import QueryIntelligence, UserGoal
from src.domains.agents.constants import STATE_KEY_EXECUTION_PLAN
from src.domains.agents.nodes.planner_node_v3 import planner_node_v3
from src.domains.agents.orchestration.plan_schemas import (
    ExecutionPlan,
    ExecutionStep,
    StepType,
)

pytestmark = pytest.mark.unit

DIRECTIVE = {"capability": "person_overview", "subject": "Paul Martin"}


@pytest.fixture(autouse=True)
def _reset_directive_ctx() -> Iterator[None]:
    """Never leak a directive into another test (or another request)."""
    token = capability_directive_ctx.set(None)
    yield
    capability_directive_ctx.reset(token)


def _intelligence() -> QueryIntelligence:
    return QueryIntelligence(
        original_query="Fais-moi un point 360° sur Paul Martin",
        english_query="Give me a 360 overview of Paul Martin",
        immediate_intent="360 overview about a person",
        immediate_confidence=0.95,
        user_goal=UserGoal.FIND_INFORMATION,
        goal_reasoning="the user pressed the 360° button on a relationship card",
        domains=["peer", "contact"],
        primary_domain="peer",
    )


def _llm_plan() -> ExecutionPlan:
    """The plan production actually produced, plus one step that ADDS something.

    `get_emails_tool` is what the planner reached for instead of the overview —
    and it is superseded, so it must go. `get_tasks_tool` is not: it answers a
    question the capability does not, so it must stay. One plan carrying both
    proves the two halves of the contract in the node, not only in the unit.
    """
    return ExecutionPlan(
        user_id="00000000-0000-0000-0000-000000000001",
        steps=[
            ExecutionStep(
                step_id="step_1",
                step_type=StepType.TOOL,
                agent_name="email_agent",
                tool_name="get_emails_tool",
                parameters={"query": "Paul"},
            ),
            ExecutionStep(
                step_id="step_2",
                step_type=StepType.TOOL,
                agent_name="task_agent",
                tool_name="get_tasks_tool",
                parameters={},
            ),
        ],
    )


async def _run_node(directive: dict[str, str] | None) -> dict[str, Any]:
    """Run the real node with a stubbed planning service."""
    capability_directive_ctx.set(directive)

    intelligence = _intelligence()
    state: dict[str, Any] = {
        "_query_intelligence_obj": intelligence,
        "messages": [],
        "oauth_scopes": [],
    }
    config = {"configurable": {"run_id": "test-run", "user_id": "u"}}

    planning_result = type(
        "PlanningResult",
        (),
        {
            "success": True,
            "plan": _llm_plan(),
            "tokens_used": 0,
            "tokens_saved": 0,
            "used_template": False,
            "used_panic_mode": False,
        },
    )()

    service = AsyncMock()
    service.plan = AsyncMock(return_value=planning_result)

    with patch(
        "src.domains.agents.services.smart_planner_service.get_smart_planner_service",
        return_value=service,
    ):
        return await planner_node_v3(state, config)  # type: ignore[arg-type]


class TestTheNodeHonoursTheDirective:
    async def test_the_capability_reaches_the_state(self) -> None:
        """End of the transport chain: ChatRequest → ContextVar → plan."""
        result = await _run_node(DIRECTIVE)
        plan = result[STATE_KEY_EXECUTION_PLAN]

        assert [step.tool_name for step in plan.steps] == [
            "get_person_overview_tool",
            "get_tasks_tool",
        ]
        assert plan.steps[0].parameters == {"person_name": "Paul Martin"}

    async def test_the_validator_sees_the_seeded_plan(self) -> None:
        """Seeded BEFORE validation — the doctrine, and the useful order.

        Validating the plan the LLM produced and then changing it would mean
        the verdict describes a plan that never ran.
        """
        result = await _run_node(DIRECTIVE)
        validation = result["validation_result"]
        plan = result[STATE_KEY_EXECUTION_PLAN]

        assert validation is not None
        # The service returned a plan WITHOUT the capability; the validator saw
        # one WITH it — so the seeding necessarily happened first.
        assert plan.steps[0].tool_name == "get_person_overview_tool"

    async def test_no_directive_leaves_the_plan_alone(self) -> None:
        """Every ordinary turn: the node behaves exactly as before."""
        result = await _run_node(None)
        plan = result[STATE_KEY_EXECUTION_PLAN]

        assert [step.tool_name for step in plan.steps] == ["get_emails_tool", "get_tasks_tool"]
