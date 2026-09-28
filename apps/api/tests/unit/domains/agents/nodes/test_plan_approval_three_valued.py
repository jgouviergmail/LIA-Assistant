"""``plan_approved`` is three-valued, and only False refuses (ADR-263).

The gate stopped writing ``True`` when no validator verdict exists (that was
``unknown`` reported as ``pass``). It writes ``None`` — "nobody looked".

The danger this file pins: the reader that RUNS a plan tested the key for
TRUTHINESS (``if plan_approved:``), so ``None`` would silently have meant
"refused" and a plan with no verdict would have stopped at the response node
instead of executing. That would be a real functional regression, invisible to
a node-level test — the routing must be tested, not just the node.

The opposite danger, which the same change created: two readers SKIP a check on
an approval (the semantic validator node and the routing after it). Read through
the refusal predicate, the ``None`` the router writes at every turn start
skipped the validation of every fresh turn — the node was fixed on 2026-09-19,
the routing with ADR-323's review. Those readers test ``is True``.

Doctrine (ADR-184): a verdict is not a fact and a plan runs regardless. What
``None`` buys is a state that no longer claims an approval nobody gave — it
changes what is KNOWN, never what runs.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from src.domains.agents.constants import (
    STATE_KEY_EXECUTION_PLAN,
    STATE_KEY_NEEDS_REPLAN,
    STATE_KEY_PLAN_APPROVED,
    STATE_KEY_PLANNER_ITERATION,
    STATE_KEY_SEMANTIC_VALIDATION,
)
from src.domains.agents.nodes.routing import (
    route_from_approval_gate,
    route_from_semantic_validator,
)
from src.domains.agents.orchestration.plan_predicates import approval_is_refused

pytestmark = [pytest.mark.unit]


def _state(plan_approved: Any) -> dict[str, Any]:
    plan = SimpleNamespace(plan_id="plan-1", steps=[SimpleNamespace(step_id="s1")])
    return {STATE_KEY_EXECUTION_PLAN: plan, STATE_KEY_PLAN_APPROVED: plan_approved}


class TestOnlyAnExplicitRefusalRefuses:
    def test_none_is_not_a_refusal(self) -> None:
        assert approval_is_refused(None) is False

    def test_false_is_a_refusal(self) -> None:
        assert approval_is_refused(False) is True

    def test_true_is_not_a_refusal(self) -> None:
        assert approval_is_refused(True) is False

    def test_a_missing_key_is_no_verdict(self) -> None:
        """Only False refuses: an absent key — a state older than the
        router's reset — is no verdict, and the plan runs like one with None.
        It used to default to False and refuse a plan nobody refused."""
        plan = SimpleNamespace(plan_id="p", steps=[SimpleNamespace(step_id="s1")])
        state = {STATE_KEY_EXECUTION_PLAN: plan}
        assert route_from_approval_gate(state) == "task_orchestrator"


class TestTheRouterStillExecutesAPlanWithNoVerdict:
    """The regression this file exists for."""

    def test_unknown_approval_still_reaches_the_orchestrator(self) -> None:
        assert route_from_approval_gate(_state(None)) == "task_orchestrator"

    def test_approved_still_reaches_the_orchestrator(self) -> None:
        assert route_from_approval_gate(_state(True)) == "task_orchestrator"

    def test_an_explicit_refusal_still_reaches_the_response(self) -> None:
        assert route_from_approval_gate(_state(False)) == "response"

    def test_an_empty_plan_is_still_blocked_under_unknown(self) -> None:
        """The empty-plan safety net must not be weakened by the third value."""
        state = _state(None)
        state[STATE_KEY_EXECUTION_PLAN] = SimpleNamespace(plan_id="p", steps=[])
        assert route_from_approval_gate(state) == "response"


def _fresh_turn(verdict: dict[str, Any], plan_approved: Any = None) -> dict[str, Any]:
    """The state the validator's routing meets: the router reset the flag to None."""
    state = _state(plan_approved)
    state[STATE_KEY_SEMANTIC_VALIDATION] = verdict
    state[STATE_KEY_PLANNER_ITERATION] = 0
    state[STATE_KEY_NEEDS_REPLAN] = False
    return state


class TestTheValidatorVerdictIsReadOnAFreshTurn:
    """Only the person's explicit confirmation skips the validator's verdict."""

    def test_a_clarification_the_validator_asks_for_is_asked(self) -> None:
        verdict = {"requires_clarification": True, "is_valid": False}
        assert route_from_semantic_validator(_fresh_turn(verdict)) == "clarification"

    def test_a_plan_the_planner_can_fix_goes_back_to_it(self) -> None:
        verdict = {"requires_clarification": False, "is_valid": False}
        assert route_from_semantic_validator(_fresh_turn(verdict)) == "planner"

    def test_a_valid_plan_reaches_the_gate(self) -> None:
        verdict = {"requires_clarification": False, "is_valid": True}
        assert route_from_semantic_validator(_fresh_turn(verdict)) == "approval_gate"

    def test_the_person_s_confirmation_still_skips_the_verdict(self) -> None:
        """clarification_node writes True: asking again would loop for ever."""
        verdict = {"requires_clarification": True, "is_valid": False}
        state = _fresh_turn(verdict, plan_approved=True)
        assert route_from_semantic_validator(state) == "approval_gate"


class TestTheNodeAndItsRoutingTogether:
    """The defect lived in the COMPOSITION: the node's output, read by the
    routing after it. Each half tested alone was green."""

    @staticmethod
    async def _route(state: dict[str, Any]) -> str:
        from src.domains.agents.nodes.semantic_validator_node import semantic_validator_node

        update = await semantic_validator_node(state)
        return route_from_semantic_validator({**state, **update})

    async def test_an_early_detection_with_no_plan_asks_the_person(self) -> None:
        """The incident's shape: « insufficient content » detected before any plan
        was built — it used to reach the gate and be told as a rejected plan."""
        verdict = {"requires_clarification": True, "is_valid": False}
        state = _fresh_turn(verdict)
        state[STATE_KEY_EXECUTION_PLAN] = None

        assert await self._route(state) == "clarification"

    async def test_an_empty_answer_to_an_early_detection_is_asked_again(self) -> None:
        """The planner's early return kept ``needs_replan``: the validator's
        routing sent the turn straight back to the planner, which detected the
        same gap again — a loop to the recursion limit. It consumes the replan
        like its other returns do, and the person is asked again."""
        from unittest.mock import patch

        from langchain_core.messages import HumanMessage
        from langchain_core.runnables import RunnableConfig

        from src.domains.agents.constants import STATE_KEY_MESSAGES
        from src.domains.agents.nodes.planner_node_v3 import planner_node_v3
        from src.domains.agents.orchestration.validation_models import (
            SemanticValidationResult,
        )

        early = SemanticValidationResult(
            is_valid=False,
            issues=[],
            confidence=1.0,
            requires_clarification=True,
            clarification_questions=["What should the e-mail say?"],
            validation_duration_seconds=0.0,
        )
        state = _fresh_turn({"requires_clarification": False, "is_valid": True})
        state[STATE_KEY_EXECUTION_PLAN] = None
        state[STATE_KEY_NEEDS_REPLAN] = True  # the empty answer's replan
        state[STATE_KEY_MESSAGES] = [HumanMessage(content="send it")]

        with (
            patch(
                "src.domains.agents.nodes.planner_node_v3._has_potential_skill_match",
                return_value=False,
            ),
            patch(
                "src.domains.agents.orchestration.semantic_validator."
                "detect_early_insufficient_content",
                return_value=early,
            ),
        ):
            update = await planner_node_v3(state, RunnableConfig(metadata={"run_id": "r"}))

        assert update[STATE_KEY_NEEDS_REPLAN] is False
        # Planner, then the validator node, then its routing: asked, not looped.
        assert await self._route({**state, **update}) == "clarification"

    async def test_an_answer_that_adds_information_replans_without_validating(self) -> None:
        """The plan the answer made stale is not validated again: the node
        builds no validator and returns nothing, and the routing sends it back to
        the planner whatever the verdict would be. A validator raising would be
        swallowed by the node's own error net, so the oracle is the call itself."""
        from unittest.mock import MagicMock, patch

        from src.domains.agents.nodes.semantic_validator_node import (
            semantic_validator_node,
        )

        verdict = {"requires_clarification": True, "is_valid": False}
        state = _fresh_turn(verdict)
        state[STATE_KEY_NEEDS_REPLAN] = True
        validator = MagicMock()

        with patch(
            "src.domains.agents.nodes.semantic_validator_node.PlanSemanticValidator",
            validator,
        ):
            update = await semantic_validator_node(state)

        assert update == {}
        validator.assert_not_called()
        assert route_from_semantic_validator({**state, **update}) == "planner"
