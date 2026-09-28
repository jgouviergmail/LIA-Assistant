"""No verdict is not an approval (ADR-263, ``unknown ≠ pass``).

Measured 2026-09-03: with no ``validation_result`` in state the gate logged
*"assuming approval not required"* and wrote ``plan_approved=True``. Nothing
downstream distinguishes "a validator looked and was satisfied" from "nobody
looked", so the state claimed an approval that never happened.

Writing ``None`` instead changes nothing that RUNS — ``route_from_approval_gate``
refuses on an explicit ``False`` alone, and every reader that skips something on
an approval tests ``is True`` — while the state stops claiming it.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

# The package re-exports the FUNCTION under the module's own name, so
# ``from ... import approval_gate_node`` binds the function; import the module.
from src.domains.agents.nodes.approval_gate_node import approval_gate_node

pytestmark = [pytest.mark.unit]


def _plan() -> SimpleNamespace:
    return SimpleNamespace(plan_id="plan-1")


async def _run(state: dict[str, Any]) -> dict[str, Any]:
    with patch("src.domains.agents.nodes.approval_gate_node.track_state_updates"):
        return await approval_gate_node(state, {})  # type: ignore[arg-type]


class TestUnknownIsNotPass:
    async def test_missing_verdict_yields_unknown_not_true(self) -> None:
        result = await _run({"execution_plan": _plan(), "validation_result": None})
        assert result["plan_approved"] is None

    async def test_unknown_is_not_a_rejection_either(self) -> None:
        """The plan still runs: this lot changes what is SAID, not what happens."""
        result = await _run({"execution_plan": _plan(), "validation_result": None})
        assert result["plan_approved"] is not False
        assert "plan_rejection_reason" not in result


class TestTheOtherBranchesAreUnchanged:
    """Pinned so the three-valued key cannot silently change a live path."""

    async def test_a_verdict_that_needs_no_hitl_still_approves(self) -> None:
        verdict = SimpleNamespace(requires_hitl=False)
        result = await _run({"execution_plan": _plan(), "validation_result": verdict})
        assert result["plan_approved"] is True

    async def test_a_verdict_requiring_hitl_is_still_auto_approved(self) -> None:
        """Plan-level HITL stays superseded by tool-level HITL (v1.14.5)."""
        verdict = SimpleNamespace(requires_hitl=True)
        result = await _run({"execution_plan": _plan(), "validation_result": verdict})
        assert result["plan_approved"] is True

    async def test_an_existing_approval_is_still_honoured(self) -> None:
        """A clarification that already approved must not be asked twice."""
        result = await _run(
            {"execution_plan": _plan(), "validation_result": None, "plan_approved": True}
        )
        assert result["plan_approved"] is True


class TestNothingToApprove:
    """No plan is no verdict — never a refusal the person is told they made."""

    async def test_no_plan_yields_no_verdict_and_no_rejection_reason(self) -> None:
        result = await _run({"execution_plan": None, "validation_result": None})
        assert result["plan_approved"] is None
        assert "plan_rejection_reason" not in result

    def test_the_router_answers_without_running_anything(self) -> None:
        from src.domains.agents.nodes.routing import route_from_approval_gate

        state = {"plan_approved": None, "execution_plan": None}
        assert route_from_approval_gate(state) == "response"  # type: ignore[arg-type]
