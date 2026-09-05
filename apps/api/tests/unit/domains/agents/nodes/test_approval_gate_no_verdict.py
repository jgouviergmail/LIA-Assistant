"""No verdict is not an approval (ADR-263, ``unknown ≠ pass``).

Measured 2026-09-03: with no ``validation_result`` in state the gate logged
*"assuming approval not required"* and wrote ``plan_approved=True``. Nothing
downstream distinguishes "a validator looked and was satisfied" from "nobody
looked", so the effect gate of lot 2 would read an approval that never happened.

Writing ``None`` instead changes NOTHING today — the router never reads this
key, and the only reader (``response_node``) tests ``is True`` for its
stale-rejection coherence check — while giving the effect gate a truthful third
value.
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

    async def test_no_plan_is_still_a_refusal(self) -> None:
        result = await _run({"execution_plan": None, "validation_result": None})
        assert result["plan_approved"] is False
        assert result["plan_rejection_reason"]

    async def test_an_existing_approval_is_still_honoured(self) -> None:
        """A clarification that already approved must not be asked twice."""
        result = await _run(
            {"execution_plan": _plan(), "validation_result": None, "plan_approved": True}
        )
        assert result["plan_approved"] is True
