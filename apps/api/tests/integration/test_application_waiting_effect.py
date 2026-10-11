"""Actual waiting receipts obey encryption, fencing and immutable settled-event semantics."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.effects.chain_verify import verify_chain
from src.domains.agents.effects.models import EffectStatus
from src.domains.agents.effects.notary import notarise_account
from src.domains.agents.effects.repository import EffectLedgerRepository
from src.domains.agents.effects.schemas import ClaimRequest
from src.domains.users.models import User

pytestmark = pytest.mark.integration


async def test_waiting_effect_is_fenced_encrypted_replayed_and_never_overwritten_as_completion(
    async_session: AsyncSession,
    test_user: User,
) -> None:
    repository = EffectLedgerRepository(async_session)
    request = ClaimRequest(
        user_id=test_user.id,
        thread_id="waiting-effect",
        run_id="waiting-run",
        source="user",
        execution_mode="react",
        tool_name="draft:application_action",
        mutation_policy="draft",
        idempotency_key="draft:waiting",
        args_digest="a" * 64,
    )
    ticket = await repository.claim(request)
    assert ticket.claim_token is not None
    payload = {
        "success": False,
        "phase": "waiting",
        "committed": False,
        "interaction": {
            "interaction_id": str(uuid4()),
            "kind": "secure",
            "expires_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
        },
    }
    assert not await repository.close_waiting(ticket.effect.id, uuid4(), result_payload=payload)
    assert await repository.close_waiting(
        ticket.effect.id, ticket.claim_token, result_payload=payload
    )
    await async_session.commit()
    replay = await repository.claim(request)
    assert not replay.claimed and replay.effect.status == EffectStatus.WAITING
    assert replay.effect.closed_at is not None and replay.effect.error_code is None
    assert "interaction_id" not in replay.effect.result_payload
    assert repository.decrypted_result(replay.effect) == payload
    assert not await repository.close_success(
        replay.effect.id, ticket.claim_token, result_payload={"success": True}
    )
    assert not await repository.close_failure(
        replay.effect.id, ticket.claim_token, error_code="expired"
    )
    # A completion is a separate authorized event; the notarized handoff fact never changes.
    await async_session.refresh(replay.effect)
    assert replay.effect.status == EffectStatus.WAITING
    notarised = await notarise_account(async_session, test_user.id, limit=20)
    await async_session.flush()
    assert notarised.entries == 3
    audit = await verify_chain(async_session, test_user.id, deep=True)
    assert audit.ok and audit.payloads_checked == 2
    assert (await notarise_account(async_session, test_user.id, limit=20)).entries == 0
