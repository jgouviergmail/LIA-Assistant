"""Whether a run may have acted, as a retry must ask it (point 20).

A retry replays the whole turn. Measured in production: an attempt reached its
bound while a browser task ran, and the retry performed the browser tasks
again. The engine therefore asks the register before retrying, and the answer
is SQL over the real table: a mocked session would only echo the question.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.effects.repository import EffectLedgerRepository
from src.domains.agents.effects.schemas import ClaimRequest
from src.domains.users.models import User

pytestmark = pytest.mark.integration


def _request(user: User, run_id: str) -> ClaimRequest:
    return ClaimRequest(
        user_id=user.id,
        thread_id="acted-in-run",
        run_id=run_id,
        source="scheduled",
        execution_mode="react",
        tool_name="browser_task_tool",
        mutation_policy="reversible",
        idempotency_key=str(uuid4()),
        args_digest="c" * 64,
    )


async def test_a_run_acted_once_it_holds_anything_but_a_refusal(
    async_session: AsyncSession, test_user: User
) -> None:
    repo = EffectLedgerRepository(async_session)
    run_id = str(uuid4())
    assert await repo.acted_in_run(run_id) is False

    await repo.refuse(_request(test_user, run_id), error_code="confirmation_impossible_unattended")
    assert await repo.acted_in_run(run_id) is False, "a refusal performed nothing"

    claimed = await repo.claim(_request(test_user, run_id))
    assert claimed.claim_token is not None
    assert await repo.acted_in_run(run_id) is True, "a claim may have acted"

    await repo.close_abandoned(claimed.effect.id, claimed.claim_token, error_code="cancelled")
    assert await repo.acted_in_run(run_id) is True, "cancelled in flight: outcome unknown"


async def test_another_run_s_action_is_not_this_run_s(
    async_session: AsyncSession, test_user: User
) -> None:
    repo = EffectLedgerRepository(async_session)
    await repo.claim(_request(test_user, str(uuid4())))

    assert await repo.acted_in_run(str(uuid4())) is False
