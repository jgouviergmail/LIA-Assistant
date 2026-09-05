"""What the gate does must be visible to an operator (ADR-263).

Six counters, and two properties that matter more than their existence:

- **each one fires on its own path and on no other.** A counter that goes up
  on everything answers nothing; the anti-vacuity assertions below pin the
  discrimination, not the presence.
- **every label value comes from a closed vocabulary.** ``tool_name`` is free
  text (a third-party MCP server names its own tools), and a free label is how
  a metric becomes a cardinality incident. The AST guard in
  ``test_metric_label_bounds`` refuses one at build time; these tests pin the
  values actually emitted.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from src.domains.agents.effects import runtime as gate_runtime
from src.domains.agents.effects.runtime import ClaimTicket
from src.domains.agents.effects.scope import EffectScope, effect_scope
from src.infrastructure.observability import metrics_effects

pytestmark = [pytest.mark.unit]


def _value(counter: Any, **labels: str) -> float:
    """Current value of one labelled series (0.0 before it ever fires)."""
    return counter.labels(**labels)._value.get()


@pytest.fixture(autouse=True)
def _attended_user() -> Any:
    gate_runtime.reset_policy_cache()
    with patch(
        "src.domains.agents.context.runtime_context.runtime_context_if_running",
        return_value=SimpleNamespace(
            user_id=uuid.uuid4(),
            thread_id="thread-metrics",
            execution_mode="pipeline",
            is_automated_source=False,
        ),
    ):
        yield


def _scope(**overrides: Any) -> EffectScope:
    base: dict[str, Any] = {"run_id": "run-1", "idempotency_key": "step:s1", "source": "user"}
    base.update(overrides)
    return EffectScope(**base)


class _Ledger:
    """A ledger that answers what the test needs, and counts nothing itself."""

    def __init__(self, ticket: ClaimTicket | None) -> None:
        self._ticket = ticket
        self.refusals: list[str] = []

    async def claim(self, request: Any) -> ClaimTicket | None:
        return self._ticket

    async def close(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def refuse(self, request: Any, *, error_code: str) -> None:
        self.refusals.append(error_code)


async def _tool(room: str = "Salon") -> dict[str, Any]:
    return {"success": True, "data": {"id": "1"}}


async def _failing_tool(room: str = "Salon") -> dict[str, Any]:
    return {"success": False, "error": "provider refused"}


def _won_ticket() -> ClaimTicket:
    return ClaimTicket(effect_id=uuid.uuid4(), claim_token=uuid.uuid4())


class TestEachCounterFiresOnItsOwnPath:
    async def test_a_claimed_effect_counts_a_claim_and_an_outcome(self) -> None:
        claims_before = _value(
            metrics_effects.effect_claims_total,
            policy="reversible",
            source="user",
            execution_mode="pipeline",
        )
        outcomes_before = _value(
            metrics_effects.effect_outcomes_total, policy="reversible", status="succeeded"
        )

        gated = gate_runtime.gated("control_hue_light_tool", _tool)
        with (
            patch.object(gate_runtime, "_LEDGER", _Ledger(_won_ticket())),
            patch.object(gate_runtime, "resolve_policy", lambda _n: "reversible"),
            effect_scope(_scope()),
        ):
            await gated(room="Salon")

        assert (
            _value(
                metrics_effects.effect_claims_total,
                policy="reversible",
                source="user",
                execution_mode="pipeline",
            )
            - claims_before
            == 1
        )
        assert (
            _value(metrics_effects.effect_outcomes_total, policy="reversible", status="succeeded")
            - outcomes_before
            == 1
        )

    async def test_a_tool_reported_failure_counts_as_failed_not_succeeded(self) -> None:
        failed_before = _value(
            metrics_effects.effect_outcomes_total, policy="reversible", status="failed"
        )
        ok_before = _value(
            metrics_effects.effect_outcomes_total, policy="reversible", status="succeeded"
        )

        gated = gate_runtime.gated("control_hue_light_tool", _failing_tool)
        with (
            patch.object(gate_runtime, "_LEDGER", _Ledger(_won_ticket())),
            patch.object(gate_runtime, "resolve_policy", lambda _n: "reversible"),
            effect_scope(_scope()),
        ):
            await gated(room="Salon")

        assert (
            _value(metrics_effects.effect_outcomes_total, policy="reversible", status="failed")
            - failed_before
            == 1
        )
        assert (
            _value(metrics_effects.effect_outcomes_total, policy="reversible", status="succeeded")
            - ok_before
            == 0
        ), "a tool that reported failure must not count as a success"

    async def test_a_refusal_counts_its_reason(self) -> None:
        before = _value(
            metrics_effects.effect_refusals_total, reason="confirmation_impossible_unattended"
        )

        gated = gate_runtime.gated("mcp_era_cancel_subscription", _tool)
        with (
            patch.object(gate_runtime, "_LEDGER", _Ledger(None)),
            patch.object(gate_runtime, "resolve_policy", lambda _n: "confirm"),
            effect_scope(_scope(source="scheduled")),
        ):
            await gated(room="Salon")

        assert (
            _value(
                metrics_effects.effect_refusals_total, reason="confirmation_impossible_unattended"
            )
            - before
            == 1
        )

    async def test_an_unrecorded_effect_is_counted_not_silent(self) -> None:
        """The ledger is down and the policy lets the effect through anyway."""
        before = _value(
            metrics_effects.effect_unrecorded_total, policy="reversible", reason="no_claim"
        )

        gated = gate_runtime.gated("control_hue_light_tool", _tool)
        with (
            patch.object(gate_runtime, "_LEDGER", _Ledger(None)),
            patch.object(gate_runtime, "resolve_policy", lambda _n: "reversible"),
            effect_scope(_scope()),
        ):
            result = await gated(room="Salon")

        assert result["success"] is True, "a reversible effect is not blocked by our bookkeeping"
        assert (
            _value(metrics_effects.effect_unrecorded_total, policy="reversible", reason="no_claim")
            - before
            == 1
        )

    async def test_a_lost_claim_counts_whether_it_could_serve_a_record(self) -> None:
        served_before = _value(metrics_effects.effect_already_performed_total, served="record")
        none_before = _value(metrics_effects.effect_already_performed_total, served="none")

        gated = gate_runtime.gated("send_email_tool", _tool)
        lost_with_record = ClaimTicket(
            effect_id=uuid.uuid4(), claim_token=None, served_result={"success": True}
        )
        lost_without = ClaimTicket(effect_id=uuid.uuid4(), claim_token=None, served_result=None)

        with (
            patch.object(gate_runtime, "resolve_policy", lambda _n: "reversible"),
            effect_scope(_scope()),
        ):
            with patch.object(gate_runtime, "_LEDGER", _Ledger(lost_with_record)):
                await gated(room="Salon")
            with patch.object(gate_runtime, "_LEDGER", _Ledger(lost_without)):
                await gated(room="Salon")

        assert (
            _value(metrics_effects.effect_already_performed_total, served="record") - served_before
            == 1
        )
        assert (
            _value(metrics_effects.effect_already_performed_total, served="none") - none_before == 1
        )


class TestTheReadPathCountsNothing:
    async def test_a_read_touches_no_counter(self) -> None:
        """Anti-vacuity: the counters above are not incremented by every call."""
        before = _value(
            metrics_effects.effect_claims_total,
            policy="read",
            source="user",
            execution_mode="pipeline",
        )

        gated = gate_runtime.gated("brave_search_tool", _tool)
        with (
            patch.object(gate_runtime, "resolve_policy", lambda _n: "read"),
            effect_scope(_scope()),
        ):
            await gated(room="Salon")

        assert (
            _value(
                metrics_effects.effect_claims_total,
                policy="read",
                source="user",
                execution_mode="pipeline",
            )
            == before
        )


class TestTheLedgerReportsItsOwnHealth:
    async def test_a_claim_failure_is_counted(self) -> None:
        from src.domains.agents.effects.schemas import ClaimRequest

        before = _value(metrics_effects.effect_ledger_failures_total, operation="claim")

        request = ClaimRequest(
            user_id=uuid.uuid4(),
            thread_id="t",
            run_id="r",
            source="user",
            execution_mode="pipeline",
            tool_name="control_hue_light_tool",
            mutation_policy="reversible",
            idempotency_key="step:s1",
            args_digest="d" * 64,
        )
        with patch(
            "src.infrastructure.database.session.get_db_context",
            side_effect=RuntimeError("no database"),
        ):
            ticket = await gate_runtime._Ledger().claim(request)

        assert ticket is None
        assert _value(metrics_effects.effect_ledger_failures_total, operation="claim") - before == 1
