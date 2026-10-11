"""Application mutations cannot spend a missing or changed human approval."""

from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest

from src.domains.agents.effects import runtime
from src.domains.agents.effects.digest import draft_digest
from src.domains.agents.effects.scope import EffectScope, effect_scope

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("fault", ["absent", "unapproved", "digest", "reference", "kind"])
async def test_invalid_approval_cannot_even_claim_the_mutation(fault: str) -> None:
    content = {"command_id": str(uuid4()), "intent": {"font_size": 17}}
    scope = EffectScope(
        run_id="r-1",
        idempotency_key="draft:d-1",
        approved=fault != "unapproved",
        approval_kind="other" if fault == "kind" else "draft_critique",
        approval_ref=None if fault == "reference" else "d-1",
        draft_digest="changed" if fault == "digest" else draft_digest(content),
    )
    execute = AsyncMock(return_value={"success": True})
    ledger = AsyncMock()
    gated = runtime.gated_executor("application_action", execute, strict=True)
    with (
        patch.object(runtime, "_LEDGER", ledger),
        patch.object(runtime, "current_scope", return_value=None if fault == "absent" else scope),
    ):
        result = await gated(content, uuid4(), None)
    assert result["success"] is False
    assert result["error_code"] == "CONFIRMATION_MISSING"
    ledger.claim.assert_not_awaited()
    execute.assert_not_awaited()


async def test_ledger_outage_never_allows_an_application_mutation() -> None:
    content = {"command_id": str(uuid4())}
    scope = EffectScope(
        run_id="r-1",
        idempotency_key="draft:d-1",
        approved=True,
        approval_kind="draft_critique",
        approval_ref="d-1",
        draft_digest=draft_digest(content),
    )
    execute = AsyncMock(return_value={"success": True})
    ledger = AsyncMock()
    ledger.claim.return_value = None
    gated = runtime.gated_executor("application_action", execute, strict=True)
    with (
        effect_scope(scope),
        patch.object(runtime, "_LEDGER", ledger),
        patch.object(runtime, "_build_request", return_value=object()),
    ):
        result = await gated(content, uuid4(), None)
    assert result == {"success": False, "error_code": "DEPENDENCY_ERROR"}
    execute.assert_not_awaited()


async def test_application_family_cannot_omit_or_disable_the_strict_policy() -> None:
    execute = AsyncMock(return_value={"success": True})
    with patch.object(runtime, "current_scope", return_value=None):
        result = await runtime.gated_executor("application_action", execute)({}, uuid4(), None)
    assert result == {"success": False, "error_code": "CONFIRMATION_MISSING"}
    execute.assert_not_awaited()


def test_a_legacy_gate_cannot_be_relabelled_as_an_application_executor() -> None:
    execute = AsyncMock(return_value={"success": True})
    legacy = runtime.gated_executor("legacy", execute)
    with pytest.raises(ValueError):
        runtime.gated_executor("application_action", legacy)


async def test_default_policy_remains_compatible_with_the_existing_executor() -> None:
    calls: list[UUID] = []

    async def legacy(content: dict[str, object], user_id: UUID, deps: object) -> dict[str, object]:
        calls.append(user_id)
        return {"success": True}

    actor = uuid4()
    with (
        patch.object(runtime, "_build_request", return_value=None),
        patch.object(runtime, "record_integrity_event", new_callable=AsyncMock),
    ):
        result = await runtime.gated_executor("legacy", legacy)({}, actor, None)
    assert result["success"] is True
    assert calls == [actor]
