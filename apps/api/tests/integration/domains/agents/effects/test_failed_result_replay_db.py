"""A returned post-commit failure stays factual when the exact effect is replayed."""

from contextlib import asynccontextmanager
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.effects.outcome import read_outcome
from src.domains.agents.effects.repository import EffectLedgerRepository
from src.domains.agents.effects.runtime import _Ledger, _serve_lost_claim
from src.domains.agents.effects.schemas import ClaimRequest
from src.domains.users.models import User

pytestmark = pytest.mark.integration


async def test_returned_failure_payload_is_encrypted_and_replayed_without_changing_its_committed_fact(
    async_session: AsyncSession,
    test_user: User,
) -> None:
    request = ClaimRequest(
        user_id=test_user.id,
        thread_id="failed-result-replay",
        run_id=str(uuid4()),
        source="user",
        execution_mode="pipeline",
        tool_name="application_action_executor",
        mutation_policy="draft",
        idempotency_key=str(uuid4()),
        args_digest="a" * 64,
    )

    @asynccontextmanager
    async def session():
        yield async_session
        await async_session.commit()

    ledger = _Ledger()
    result = {
        "success": False,
        "phase": "failed",
        "committed": True,
        "error_code": "POST_COMMIT_FAILURE",
        "values": {"font_size": 18},
    }
    with patch("src.infrastructure.database.session.get_db_context", session):
        won = await ledger.claim(request)
        assert won is not None and won.claim_token is not None
        await ledger.close(won.effect_id, won.claim_token, outcome=read_outcome(result))
        lost = await ledger.claim(request)
    assert lost is not None and lost.claim_token is None and lost.served_status == "failed"
    assert lost.served_result == result
    assert _serve_lost_claim(request.tool_name, lost) == result
    row = (await EffectLedgerRepository(async_session).claim(request)).effect
    assert row.result_payload is not None and "POST_COMMIT_FAILURE" not in row.result_payload
    assert row.result_digest is not None and not row.result_truncated


async def test_failed_result_close_is_fenced_and_truncated_payload_cannot_be_replayed_as_complete(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "effect_result_payload_max_bytes", 1024)
    request = ClaimRequest(
        user_id=test_user.id,
        thread_id="failure-cap",
        run_id=str(uuid4()),
        source="user",
        execution_mode="pipeline",
        tool_name="application_action_executor",
        mutation_policy="draft",
        idempotency_key=str(uuid4()),
        args_digest="b" * 64,
    )
    repo = EffectLedgerRepository(async_session)
    won = await repo.claim(request)
    assert won.claim_token is not None
    payload = {"success": False, "committed": True, "private_note": "é" * 3000}
    assert not await repo.close_failure(
        won.effect.id, uuid4(), error_code="late", result_payload=payload
    )
    assert await repo.close_failure(
        won.effect.id, won.claim_token, error_code="delivery", result_payload=payload
    )
    assert not await repo.close_failure(
        won.effect.id, won.claim_token, error_code="changed", result_payload={}
    )
    await async_session.refresh(won.effect)
    assert won.effect.error_code == "delivery" and won.effect.result_truncated
    assert won.effect.result_payload is not None and "private_note" not in won.effect.result_payload

    @asynccontextmanager
    async def session():
        yield async_session
        await async_session.commit()

    with patch("src.infrastructure.database.session.get_db_context", session):
        lost = await _Ledger().claim(request)
    assert lost is not None and lost.claim_token is None and lost.served_result is None
