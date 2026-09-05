"""The gate around a real coroutine: claim, run, close — or refuse (ADR-263).

The database is stubbed here; the ledger's own semantics are proven against a
real PostgreSQL in ``tests/integration/domains/agents/effects``. What this file
pins is the ORDER and the FAILURE MODES, which is where a gate goes wrong:

- the claim is committed BEFORE the effect (an email is not transactional);
- a lost claim does not re-run the effect, it serves what was recorded;
- a refusal never reaches the tool;
- the ledger being down never blocks an effect the user did not have to
  confirm, and always blocks one they did (owner decision, 2026-09-03).
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from src.domains.agents.effects import runtime as gate_runtime
from src.domains.agents.effects.gate import ERROR_CONFIRMATION_MISSING
from src.domains.agents.effects.scope import EffectScope, effect_scope

pytestmark = [pytest.mark.unit]


CALLS: list[dict[str, Any]] = []


async def _tool(**kwargs: Any) -> dict[str, Any]:
    """A tool that records its calls and reports a provider identifier."""
    CALLS.append(kwargs)
    return {"success": True, "data": {"message_id": "m-1"}}


@pytest.fixture(autouse=True)
def _reset() -> Any:
    """Clear state, and give every test a run context to attribute rows to.

    Outside a graph run there is no user to own a ledger row, and the gate
    deliberately runs the effect unrecorded rather than inventing an owner —
    a behaviour pinned by ``TestWithoutARunContext`` below.
    """
    CALLS.clear()
    gate_runtime.reset_policy_cache()
    context = SimpleNamespace(
        user_id=uuid.uuid4(),
        thread_id="thread-A",
        execution_mode="react",
        is_automated_source=False,
    )
    with patch(
        "src.domains.agents.context.runtime_context.runtime_context_if_running",
        return_value=context,
    ):
        yield context


@pytest.fixture
def ledger() -> Any:
    """A stubbed ledger recording claims and closes."""

    class _Ledger:
        def __init__(self) -> None:
            self.claims: list[Any] = []
            self.closed: list[tuple[str, Any]] = []
            self.refusals: list[tuple[Any, str]] = []
            self.claim_result: Any = "win"

        async def claim(self, request: Any) -> Any:
            self.claims.append(request)
            if self.claim_result == "win":
                return gate_runtime.ClaimTicket(
                    effect_id=uuid.uuid4(), claim_token=uuid.uuid4(), served_result=None
                )
            if self.claim_result == "served":
                return gate_runtime.ClaimTicket(
                    effect_id=uuid.uuid4(),
                    claim_token=None,
                    served_result={"success": True, "data": {"served": True}},
                )
            return None  # ledger unavailable

        async def close(self, effect_id: Any, token: Any, *, outcome: Any) -> None:
            self.closed.append(("success" if outcome.succeeded else "failure", outcome))

        async def refuse(self, request: Any, *, error_code: str) -> None:
            self.refusals.append((request, error_code))

    return _Ledger()


def _install(ledger: Any) -> Any:
    return patch.object(gate_runtime, "_LEDGER", ledger)


def _policy(value: str | None) -> Any:
    return patch.object(gate_runtime, "resolve_policy", lambda _name: value)


def _scope() -> EffectScope:
    return EffectScope(run_id="run-1", idempotency_key="call-1", source="user")


class TestPassThrough:
    async def test_a_read_reaches_the_tool_without_a_row(self, ledger: Any) -> None:
        gated = gate_runtime.gated("get_emails_tool", _tool)
        with _install(ledger), _policy("read"), effect_scope(_scope()):
            result = await gated(query="x")
        assert result["success"] is True
        assert CALLS == [{"query": "x"}]
        assert ledger.claims == []

    async def test_the_wrapper_is_marked_so_the_boot_can_check_it(self) -> None:
        gated = gate_runtime.gated("get_emails_tool", _tool)
        assert getattr(gated, gate_runtime.EFFECT_GATED_ATTR, False) is True

    async def test_wrapping_twice_does_not_nest(self) -> None:
        """Registration can run again (a module reload); one gate is enough."""
        once = gate_runtime.gated("get_emails_tool", _tool)
        twice = gate_runtime.gated("get_emails_tool", once)
        assert twice is once


class TestRefusal:
    async def test_a_confirm_without_approval_never_reaches_the_tool(self, ledger: Any) -> None:
        """It asks instead of failing — the tool still does not run."""
        gated = gate_runtime.gated("mcp_x_delete", _tool)
        with _install(ledger), _policy("confirm"), effect_scope(_scope()):
            result = await gated(target="a")
        assert CALLS == []
        payload = result.model_dump()
        assert payload["metadata"]["requires_confirmation"] is True
        assert payload["metadata"]["draft_type"] == "tool_call"

    async def test_a_refusal_writes_the_fact_down(self, ledger: Any) -> None:
        """A refusal is what the answer will say: it belongs in the ledger."""
        gated = gate_runtime.gated("mcp_x_delete", _tool)
        with _install(ledger), _policy("confirm"), effect_scope(_scope()):
            await gated(target="a")
        assert len(ledger.refusals) == 1
        assert ledger.refusals[0][1] == ERROR_CONFIRMATION_MISSING
        assert ledger.claims == [], "asking claims nothing: no effect was performed"


class TestLedgeredEffect:
    async def test_it_claims_then_runs_then_closes(self, ledger: Any) -> None:
        gated = gate_runtime.gated("control_hue_light_tool", _tool)
        with _install(ledger), _policy("reversible"), effect_scope(_scope()):
            result = await gated(room="Salon")

        assert len(ledger.claims) == 1
        assert CALLS == [{"room": "Salon"}]
        assert ledger.closed and ledger.closed[0][0] == "success"
        assert ledger.closed[0][1].provider_ref == "m-1"
        assert result["success"] is True

    async def test_the_claim_carries_the_authority(self, ledger: Any) -> None:
        gated = gate_runtime.gated("control_hue_light_tool", _tool)
        scope = EffectScope(
            run_id="run-9",
            idempotency_key="call-9",
            source="scheduled",
            approved=True,
            approval_kind="tool_confirmation",
        )
        with _install(ledger), _policy("reversible"), effect_scope(scope):
            await gated(room="Salon")

        request = ledger.claims[0]
        assert request.run_id == "run-9"
        assert request.idempotency_key == "call-9"
        assert request.source == "scheduled"
        assert request.approval_kind == "tool_confirmation"
        assert request.mutation_policy == "reversible"
        assert len(request.args_digest) == 64

    async def test_a_failing_tool_closes_the_row_as_failed(self, ledger: Any) -> None:
        async def _failing(**_kwargs: Any) -> dict[str, Any]:
            return {"success": False, "error": {"code": "EXTERNAL_API_ERROR"}}

        gated = gate_runtime.gated("control_hue_light_tool", _failing)
        with _install(ledger), _policy("reversible"), effect_scope(_scope()):
            await gated(room="Salon")
        assert ledger.closed[0][0] == "failure"

    async def test_a_raising_tool_closes_the_row_and_re_raises(self, ledger: Any) -> None:
        async def _raising(**_kwargs: Any) -> dict[str, Any]:
            raise RuntimeError("provider down")

        gated = gate_runtime.gated("control_hue_light_tool", _raising)
        with _install(ledger), _policy("reversible"), effect_scope(_scope()):
            with pytest.raises(RuntimeError):
                await gated(room="Salon")
        assert ledger.closed[0][0] == "failure"


class TestTheApprovalIsSpentOnce:
    async def test_a_lost_claim_serves_the_record_instead_of_re_running(self, ledger: Any) -> None:
        """The measured defect: one confirmation, two executions."""
        ledger.claim_result = "served"
        gated = gate_runtime.gated("send_email_tool", _tool)
        with _install(ledger), _policy("reversible"), effect_scope(_scope()):
            result = await gated(to="a@b.c")

        assert CALLS == [], "the effect must not happen twice"
        assert result == {"success": True, "data": {"served": True}}


class TestWhenTheLedgerItselfIsDown:
    async def test_an_exempt_mutation_still_happens(self, ledger: Any) -> None:
        """Our own bookkeeping must not be why a light stays on."""
        ledger.claim_result = "down"
        gated = gate_runtime.gated("control_hue_light_tool", _tool)
        with _install(ledger), _policy("reversible"), effect_scope(_scope()):
            result = await gated(room="Salon")
        assert CALLS == [{"room": "Salon"}]
        assert result["success"] is True

    async def test_a_confirmed_effect_is_refused(self, ledger: Any) -> None:
        """What the user confirmed must be recorded, or not done at all."""
        ledger.claim_result = "down"
        gated = gate_runtime.gated("mcp_x_delete", _tool)
        scope = EffectScope(
            run_id="r",
            idempotency_key="k",
            source="user",
            approved=True,
            approval_kind="tool_confirmation",
        )
        with _install(ledger), _policy("confirm"), effect_scope(scope):
            result = await gated(target="a")
        assert CALLS == []
        assert result["success"] is False


class TestWithoutARunContext:
    """No graph run means no user to attribute a row to — and no invented one."""

    async def test_a_ledgered_effect_runs_unrecorded(self, ledger: Any) -> None:
        gated = gate_runtime.gated("control_hue_light_tool", _tool)
        with (
            _install(ledger),
            _policy("reversible"),
            patch(
                "src.domains.agents.context.runtime_context.runtime_context_if_running",
                return_value=None,
            ),
            effect_scope(_scope()),
        ):
            result = await gated(room="Salon")
        assert CALLS == [{"room": "Salon"}]
        assert ledger.claims == []
        assert result["success"] is True

    async def test_a_confirm_is_refused_without_a_row(self, ledger: Any) -> None:
        gated = gate_runtime.gated("mcp_x_delete", _tool)
        scope = EffectScope(
            run_id="r",
            idempotency_key="k",
            source="user",
            approved=True,
            approval_kind="tool_confirmation",
        )
        with (
            _install(ledger),
            _policy("confirm"),
            patch(
                "src.domains.agents.context.runtime_context.runtime_context_if_running",
                return_value=None,
            ),
            effect_scope(scope),
        ):
            result = await gated(target="a")
        assert CALLS == []
        assert result["success"] is False


class TestWithoutAScope:
    async def test_an_exempt_mutation_runs_and_is_counted(self, ledger: Any) -> None:
        gated = gate_runtime.gated("control_hue_light_tool", _tool)
        with _install(ledger), _policy("reversible"):
            result = await gated(room="Salon")
        assert CALLS == [{"room": "Salon"}]
        assert result["success"] is True

    async def test_a_confirm_asks_rather_than_running(self, ledger: Any) -> None:
        """No scope means nobody confirmed — but somebody can still be asked."""
        gated = gate_runtime.gated("mcp_x_delete", _tool)
        with _install(ledger), _policy("confirm"):
            result = await gated(target="a")
        assert CALLS == []
        assert result.model_dump()["metadata"]["requires_confirmation"] is True


class TestThePolicyReadIsTotal:
    """A policy the gate cannot read must never break a working tool call.

    Found by ``tests/agents`` (the suite outside the pre-commit hook, which has
    now caught five defects): a test installs a MagicMock registry, the manifest
    returns a MagicMock policy, and the gate turned every call into a
    ``ValidationError``. A gate that can take the assistant down when a
    declaration is unreadable is worse than the hole it closes — so an
    unreadable policy reads as UNKNOWN, loudly, and the tool keeps working.
    """

    def test_a_non_string_policy_reads_as_unknown(self) -> None:
        from unittest.mock import MagicMock

        registry = MagicMock()
        registry.get_tool_manifest.return_value.mutation_policy = MagicMock()
        with patch("src.domains.agents.registry.get_global_registry", return_value=registry):
            assert gate_runtime.resolve_policy("some_tool") is None

    def test_an_unknown_string_policy_reads_as_unknown(self) -> None:
        from unittest.mock import MagicMock

        registry = MagicMock()
        registry.get_tool_manifest.return_value.mutation_policy = "whatever"
        with patch("src.domains.agents.registry.get_global_registry", return_value=registry):
            assert gate_runtime.resolve_policy("some_tool") is None

    def test_a_declared_policy_still_reads(self) -> None:
        from unittest.mock import MagicMock

        registry = MagicMock()
        registry.get_tool_manifest.return_value.mutation_policy = "reversible"
        with patch("src.domains.agents.registry.get_global_registry", return_value=registry):
            assert gate_runtime.resolve_policy("some_tool") == "reversible"

    async def test_an_unreadable_policy_lets_the_tool_run(self, ledger: Any) -> None:
        from unittest.mock import MagicMock

        gated = gate_runtime.gated("some_tool", _tool)
        registry = MagicMock()
        registry.get_tool_manifest.return_value.mutation_policy = MagicMock()
        with (
            _install(ledger),
            patch("src.domains.agents.registry.get_global_registry", return_value=registry),
            effect_scope(_scope()),
        ):
            result = await gated(x=1)
        assert result["success"] is True
        assert ledger.claims == []
