"""An action a tool performs INSIDE the turn but outside its own gate — the
sandbox network run (ADR-298) — is claimed before it happens and closed from
what came back, through the same ledger the gate uses."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from src.domains.agents.effects import runtime as gate_runtime
from src.domains.agents.effects.in_turn_effects import (
    SANDBOX_NETWORK_CAPABILITY,
    in_turn_effect,
)

pytestmark = pytest.mark.unit


class _Ledger:
    def __init__(self) -> None:
        self.claims: list[Any] = []
        self.closed: list[str] = []

    async def claim(self, request: Any) -> Any:
        self.claims.append(request)
        return gate_runtime.ClaimTicket(
            effect_id=uuid.uuid4(), claim_token=uuid.uuid4(), served_result=None
        )

    async def close(self, effect_id: Any, token: Any, *, outcome: Any) -> None:
        self.closed.append("success" if outcome.succeeded else "failure")


@pytest.fixture
def context() -> Any:
    ctx = SimpleNamespace(
        user_id=uuid.uuid4(),
        thread_id="thread-A",
        execution_mode="react",
        is_automated_source=False,
    )
    with patch(
        "src.domains.agents.context.runtime_context.runtime_context_if_running",
        return_value=ctx,
    ):
        yield ctx


class TestClaimedThenClosed:
    async def test_the_row_names_the_hosts_and_closes_from_the_result(self, context: Any) -> None:
        ledger = _Ledger()
        with patch.object(gate_runtime, "_LEDGER", ledger):
            async with in_turn_effect(
                tool_name=SANDBOX_NETWORK_CAPABILITY,
                policy="sandboxed",
                arguments={"hosts": ["api.search.brave.com"], "turn_data_shared": True},
            ) as effect:
                assert ledger.claims and not ledger.closed, "claimed BEFORE the action"
                effect.succeeded = True
        assert ledger.closed == ["success"]
        request = ledger.claims[0]
        assert request.tool_name == SANDBOX_NETWORK_CAPABILITY
        assert request.mutation_policy == "sandboxed"
        assert request.user_id == context.user_id
        assert request.label["i18n_key"] == f"effects.labels.{SANDBOX_NETWORK_CAPABILITY}"
        assert request.label["values"] == {"target": "api.search.brave.com"}

    async def test_under_an_approved_scope_the_row_says_who_approved(self, context: Any) -> None:
        """The draft executor node publishes the approved scope (ADR-263); the
        network act claimed inside it carries that approval — the register
        reads « approved by the person on card d1 »."""
        from src.domains.agents.effects.scope import EffectScope, effect_scope

        ledger = _Ledger()
        scope = EffectScope(
            run_id="run-1",
            idempotency_key="draft:d1",
            source="user",
            approved=True,
            approval_kind="draft_critique",
            approval_ref="d1",
        )
        with patch.object(gate_runtime, "_LEDGER", ledger), effect_scope(scope):
            async with in_turn_effect(
                tool_name=SANDBOX_NETWORK_CAPABILITY, policy="sandboxed", arguments={}
            ) as effect:
                effect.succeeded = True
        request = ledger.claims[0]
        assert request.approval_kind == "draft_critique"
        assert request.approval_ref == "d1"
        assert request.idempotency_key == "draft:d1"

    async def test_left_unsettled_it_closes_as_a_failure(self, context: Any) -> None:
        """The safe direction: a run that raised before reporting is not read as done."""
        ledger = _Ledger()
        with patch.object(gate_runtime, "_LEDGER", ledger), pytest.raises(RuntimeError):
            async with in_turn_effect(
                tool_name=SANDBOX_NETWORK_CAPABILITY, policy="sandboxed", arguments={}
            ):
                raise RuntimeError("container died")
        assert ledger.closed == ["failure"]

    async def test_outside_a_run_context_nothing_is_written(self) -> None:
        ledger = _Ledger()
        with (
            patch(
                "src.domains.agents.context.runtime_context.runtime_context_if_running",
                return_value=None,
            ),
            patch.object(gate_runtime, "_LEDGER", ledger),
        ):
            async with in_turn_effect(
                tool_name=SANDBOX_NETWORK_CAPABILITY, policy="sandboxed", arguments={}
            ) as effect:
                effect.succeeded = True
        assert ledger.claims == [] and ledger.closed == []
