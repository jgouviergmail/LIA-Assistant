"""``plan_approved`` is three-valued, and only False refuses (ADR-263).

The gate stopped writing ``True`` when no validator verdict exists (that was
``unknown`` reported as ``pass``). It writes ``None`` — "nobody looked".

The danger this file pins: three readers tested the key for TRUTHINESS
(``if plan_approved:``), so ``None`` would silently have meant "refused" and a
plan with no verdict would have stopped at the response node instead of
executing. That would be a real functional regression, invisible to a
node-level test — the routing must be tested, not just the node.

Doctrine (ADR-184): a verdict is not a fact and a plan runs regardless. What
``None`` buys is that the effect gate (lot 2) can tell an approval from a
silence — it changes what is KNOWN, never what runs.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from src.domains.agents.constants import STATE_KEY_EXECUTION_PLAN, STATE_KEY_PLAN_APPROVED
from src.domains.agents.nodes.routing import route_from_approval_gate
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

    def test_a_missing_key_defaults_to_refusal_like_today(self) -> None:
        """The readers default to False when the key is absent — unchanged."""
        assert approval_is_refused(False) is True


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
