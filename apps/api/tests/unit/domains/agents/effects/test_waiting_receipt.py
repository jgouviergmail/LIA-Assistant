"""A recorded handoff is immutable and replayable, without reporting the action done."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.agents.effects import runtime
from src.domains.agents.effects.outcome import read_outcome

pytestmark = pytest.mark.unit


def receipt() -> dict[str, object]:
    return {
        "success": False,
        "phase": "waiting",
        "committed": False,
        "interaction": {
            "interaction_id": str(uuid4()),
            "kind": "secure",
            "expires_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
        },
    }


def test_effect_outcome_distinguishes_waiting_from_failure() -> None:
    result = read_outcome(receipt())
    assert result.waiting is True and result.succeeded is False


async def test_waiting_execution_records_the_same_payload_and_waiting_metric() -> None:
    payload = receipt()
    ledger = AsyncMock()
    metrics = MagicMock()
    ticket = runtime.ClaimTicket(uuid4(), uuid4())
    with (
        patch.object(runtime, "_LEDGER", ledger),
        patch.object(runtime, "effect_outcomes_total", metrics),
    ):
        assert (
            await runtime._perform_and_close(
                ticket, AsyncMock(return_value=payload), policy="draft"
            )
            == payload
        )
    metrics.labels.assert_called_once_with(policy="draft", status="waiting")
    ledger.close.assert_awaited_once()
    assert ledger.close.await_args.kwargs["outcome"].waiting is True
    assert ledger.close.await_args.kwargs["outcome"].payload == payload


async def test_pending_replay_never_reexecutes_the_initial_handoff() -> None:
    from src.domains.agents.effects.scope import EffectScope, effect_scope
    from tests.helpers.runtime_context import installed_runtime_context

    payload = receipt()
    ledger = AsyncMock()
    ledger.claim.return_value = runtime.ClaimTicket(uuid4(), None, payload, "waiting")
    execute = AsyncMock()
    with (
        installed_runtime_context(deps=object()),
        patch.object(runtime, "_LEDGER", ledger),
        effect_scope(
            EffectScope(
                run_id="run",
                idempotency_key="draft:await",
                source="user",
                approved=True,
                approval_kind="draft_critique",
            )
        ),
    ):
        result = await runtime.gated_executor("test_wait", execute)({}, uuid4(), object())
    assert result == payload and result["success"] is False
    execute.assert_not_awaited()
    ledger.close.assert_not_awaited()
