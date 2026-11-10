"""Direct communication owes a scoped, durable claim, never a confirmation card."""

import asyncio
from dataclasses import replace
from typing import Literal
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest

from src.domains.agents.effects import runtime
from src.domains.agents.effects.gate import GateAction, decide_effect
from src.domains.agents.effects.outcome import ToolOutcome
from src.domains.agents.effects.schemas import ClaimRequest
from src.domains.agents.effects.scope import EffectScope, effect_scope
from src.domains.agents.registry.catalogue import (
    MUTATION_POLICIES,
    POLICIES_REQUIRING_REASON,
)
from tests.helpers.runtime_context import installed_runtime_context, no_runtime_context

pytestmark = pytest.mark.unit

SCOPE = EffectScope(run_id="direct-run", idempotency_key="direct-call")


class Ledger:
    """Only the persistence boundary is doubled; the execution gate is real."""

    def __init__(self, ticket: runtime.ClaimTicket | None) -> None:
        self.ticket = ticket
        self.claims: list[ClaimRequest] = []
        self.closed: list[ToolOutcome] = []
        self.refused: list[str] = []
        self.abandoned: list[str] = []

    async def claim(self, request: ClaimRequest) -> runtime.ClaimTicket | None:
        self.claims.append(request)
        return self.ticket

    async def close(self, effect_id: UUID, token: UUID, *, outcome: ToolOutcome) -> None:
        assert self.ticket is not None and self.ticket.effect_id == effect_id
        assert self.ticket.claim_token == token
        self.closed.append(outcome)

    async def abandon(self, effect_id: UUID, token: UUID, *, error_code: str) -> None:
        assert self.ticket is not None and self.ticket.effect_id == effect_id
        assert self.ticket.claim_token == token
        self.abandoned.append(error_code)

    async def refuse(self, request: ClaimRequest, *, error_code: str) -> None:
        self.refused.append(error_code)


def test_direct_is_declared_and_owes_a_written_reason() -> None:
    assert "direct" in MUTATION_POLICIES
    assert "direct" in POLICIES_REQUIRING_REASON


@pytest.mark.parametrize(
    "scope", [None, replace(SCOPE, run_id=""), replace(SCOPE, idempotency_key="")]
)
def test_missing_execution_identity_refuses_without_a_card(scope: EffectScope | None) -> None:
    verdict = decide_effect("direct", scope)
    assert verdict.action is GateAction.REFUSE
    assert verdict.error_code == "execution_authority_missing"


@pytest.mark.parametrize("approved", [False, True])
def test_an_attended_call_is_ledgered_without_fabricating_approval(approved: bool) -> None:
    scope = replace(SCOPE, approved=approved)
    assert decide_effect("direct", scope).action is GateAction.LEDGER
    assert scope.approved is approved


@pytest.mark.parametrize("approved", [False, True])
@pytest.mark.parametrize("carrier", [False, True])
def test_unattended_calls_keep_the_existing_authority_boundary(
    approved: bool, carrier: bool
) -> None:
    verdict = decide_effect(
        "direct", replace(SCOPE, source="scheduled", approved=approved), carrier=carrier
    )
    assert verdict.action is (GateAction.LEDGER if approved or carrier else GateAction.REFUSE)


def test_direct_does_not_authorize_proactive_communication() -> None:
    assert decide_effect("direct", replace(SCOPE, source="proactive")).action is GateAction.REFUSE


@pytest.mark.parametrize(
    "scope", [None, replace(SCOPE, run_id=""), replace(SCOPE, idempotency_key="")]
)
async def test_missing_identity_is_a_typed_refusal_at_the_real_gate(
    scope: EffectScope | None,
) -> None:
    ledger = Ledger(None)

    async def act() -> dict[str, bool]:
        pytest.fail("an unidentified call cannot act")

    with (
        installed_runtime_context(),
        patch.object(runtime, "current_scope", return_value=scope),
        patch.object(runtime, "_LEDGER", ledger),
        patch.object(runtime, "resolve_policy", return_value="direct"),
    ):
        result = await runtime.gated("send_peer_message_tool", act)()
    assert result["success"] is False and "draft_id" not in result
    assert not ledger.claims


@pytest.mark.parametrize("mode", ["pipeline", "react"])
async def test_a_won_claim_precedes_the_act_and_records_its_explicit_outcome(mode: str) -> None:
    ledger = Ledger(runtime.ClaimTicket(uuid4(), uuid4(), None))
    acted: list[str] = []

    async def act(message: str) -> dict[str, object]:
        assert len(ledger.claims) == 1
        acted.append(message)
        return {"success": True, "message_id": "queued-id", "status": "pending"}

    with (
        installed_runtime_context(execution_mode=mode) as context,
        effect_scope(SCOPE),
        patch.object(runtime, "_LEDGER", ledger),
        patch.object(runtime, "resolve_policy", return_value="direct"),
    ):
        result = await runtime.gated("send_peer_message_tool", act)(message="hello")
    assert acted == ["hello"]
    assert result["status"] == "pending"
    assert len(ledger.closed) == 1 and ledger.closed[0].succeeded
    claim = ledger.claims[0]
    assert claim.user_id == context.user_id
    assert claim.execution_mode == mode
    assert claim.idempotency_key == SCOPE.idempotency_key
    assert claim.approval_kind is None and claim.approval_ref is None


@pytest.mark.parametrize("has_context", [False, True])
async def test_no_owner_or_unavailable_ledger_never_runs_the_act(has_context: bool) -> None:
    ledger = Ledger(None)
    acted: list[bool] = []

    async def act() -> dict[str, bool]:
        acted.append(True)
        return {"success": True}

    with (
        installed_runtime_context() if has_context else no_runtime_context(),
        effect_scope(SCOPE),
        patch.object(runtime, "_LEDGER", ledger),
        patch.object(runtime, "resolve_policy", return_value="direct"),
    ):
        result = await runtime.gated("send_peer_message_tool", act)()
    assert not acted
    assert result["success"] is False
    assert "draft_id" not in result


@pytest.mark.parametrize("status", ["claimed", "abandoned", "failed", "succeeded"])
async def test_a_lost_claim_never_repeats_an_uncertain_act(status: str) -> None:
    served = {"success": True, "message_id": "same-id"} if status == "succeeded" else None
    ledger = Ledger(runtime.ClaimTicket(uuid4(), None, served, status))

    async def act() -> dict[str, bool]:
        pytest.fail("the lost claim must never reach the tool")

    with (
        installed_runtime_context(),
        effect_scope(SCOPE),
        patch.object(runtime, "_LEDGER", ledger),
        patch.object(runtime, "resolve_policy", return_value="direct"),
    ):
        result = await runtime.gated("send_peer_message_tool", act)()
    assert result["success"] is (status == "succeeded")
    if served is not None:
        assert result == served
    assert not ledger.closed


@pytest.mark.parametrize("failure", ["declared", "cancelled"])
async def test_failure_and_cancellation_close_the_claim_honestly(
    failure: Literal["declared", "cancelled"],
) -> None:
    ledger = Ledger(runtime.ClaimTicket(uuid4(), uuid4(), None))

    async def act() -> dict[str, bool]:
        if failure == "cancelled":
            raise asyncio.CancelledError
        return {"success": False}

    with (
        installed_runtime_context(),
        effect_scope(SCOPE),
        patch.object(runtime, "_LEDGER", ledger),
        patch.object(runtime, "resolve_policy", return_value="direct"),
    ):
        if failure == "cancelled":
            with pytest.raises(asyncio.CancelledError):
                await runtime.gated("send_peer_message_tool", act)()
            assert ledger.abandoned == ["cancelled"]
        else:
            result = await runtime.gated("send_peer_message_tool", act)()
            assert result["success"] is False
            assert len(ledger.closed) == 1 and not ledger.closed[0].succeeded
