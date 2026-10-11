"""Production claim construction persists one encrypted readable action in both modes."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.i18n_effects import render_effect_label
from src.domains.agents.effects.labels import readable_label
from src.domains.agents.effects.models import AgentEffect
from src.domains.agents.effects.repository import EffectLedgerRepository
from src.domains.agents.effects.runtime import claim_request_for
from src.domains.agents.effects.scope import EffectScope, effect_scope
from src.domains.users.models import User
from tests.helpers.runtime_context import installed_runtime_context

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("mode", ["pipeline", "react"])
async def test_native_claim_label_is_encrypted_and_replay_keeps_one_action(
    async_session: AsyncSession, test_user: User, mode: str
) -> None:
    draft = {
        "operation_id": "workboard_ticket.create",
        "title": "Create a workboard ticket",
        "intent": {"private_selection": "UNRECORDED_SECRET"},
    }
    with installed_runtime_context(user_id=test_user.id, execution_mode=mode):
        with effect_scope(
            EffectScope(run_id="native-label-run", idempotency_key="native-label-draft")
        ):
            request = claim_request_for("draft:application_action", "draft", {"draft": draft})
    assert request is not None
    assert request.run_id == "native-label-run" and request.execution_mode == mode
    repository = EffectLedgerRepository(async_session)
    claim = await repository.claim(request)
    assert claim.claimed and claim.claim_token is not None
    assert await repository.close_success(
        claim.effect.id, claim.claim_token, result_payload={"success": True}
    )
    await async_session.commit()
    await async_session.refresh(claim.effect)
    assert "Create a workboard ticket" not in claim.effect.label
    key, values = readable_label(claim.effect)
    assert key == "effects.labels.draft.application_action_named"
    assert values == {"target": "create ticket", "operation": draft["operation_id"]}
    assert "create ticket" in render_effect_label({"i18n_key": key, "values": values}, "fr")
    assert "UNRECORDED_SECRET" not in str(request.label) and "UNRECORDED_SECRET" not in str(values)
    replay = await repository.claim(request)
    assert not replay.claimed and replay.effect.id == claim.effect.id
    assert await async_session.scalar(select(func.count(AgentEffect.id))) == 1
