"""Two turns of one conversation never share a pipeline step key (ADR-263, ADR-231).

Measured in production on 2026-09-22: a pipeline turn ran ``create_reminder_tool``
as ``step_1``, lost its claim, and was SERVED the recorded result of an earlier
turn's ``step_1`` — the reminder was never created and the tool answered as if it
had been. The step key is ``{run_id}:step:{step_id}``; the run id was read from
``configurable``, which has carried no run id since ADR-231, so every turn fell
back to the THREAD id and every ``step_1`` of the conversation was one key.

Only PostgreSQL can prove it: the loss is the unique ``(thread_id,
idempotency_key)`` refusing the second insert. The configs below are the shape
the orchestration service builds — the run id in ``metadata``.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.effects.repository import EffectLedgerRepository
from src.domains.agents.effects.schemas import ClaimRequest
from src.domains.agents.effects.scope import step_effect_key
from src.domains.users.models import User

pytestmark = pytest.mark.integration

_THREAD = "thread-of-one-conversation"


@pytest.fixture
async def user(async_session: AsyncSession) -> User:
    """The conversation's owner."""
    row = User(
        email=f"step-key-{uuid.uuid4().hex[:8]}@test.local",
        hashed_password="x",
        is_active=True,
        is_superuser=False,
        full_name="Step Key Owner",
    )
    async_session.add(row)
    await async_session.flush()
    return row


def _turn_config(run_id: str) -> dict[str, Any]:
    """The config the orchestration service builds for one turn (ADR-231)."""
    return {"configurable": {"thread_id": _THREAD}, "metadata": {"run_id": run_id}}


def _claim(user: User, run_id: str, key: str) -> ClaimRequest:
    return ClaimRequest(
        user_id=user.id,
        thread_id=_THREAD,
        run_id=run_id,
        source="user",
        execution_mode="pipeline",
        tool_name="create_reminder_tool",
        mutation_policy="reversible",
        idempotency_key=key,
        args_digest="b" * 64,
    )


async def test_the_second_turn_s_reminder_is_performed_not_served(
    async_session: AsyncSession, user: User
) -> None:
    repo = EffectLedgerRepository(async_session)
    first_key = step_effect_key(_turn_config("run-monday"), "step_1")
    second_key = step_effect_key(_turn_config("run-tuesday"), "step_1")

    first = await repo.claim(_claim(user, "run-monday", first_key))
    assert first.claim_token is not None
    await repo.close_success(
        first.effect.id, first.claim_token, provider_ref="r1", result_payload={"id": "r1"}
    )
    second = await repo.claim(_claim(user, "run-tuesday", second_key))

    assert second.claimed is True, "the second turn's action was served, not performed"
    assert second.effect.id != first.effect.id


async def test_a_resume_of_the_same_turn_is_still_served(
    async_session: AsyncSession, user: User
) -> None:
    """A HITL resume reuses its run id: the replay stays idempotent."""
    repo = EffectLedgerRepository(async_session)
    key = step_effect_key(_turn_config("run-monday"), "step_1")

    first = await repo.claim(_claim(user, "run-monday", key))
    replay = await repo.claim(_claim(user, "run-monday", key))

    assert first.claimed is True
    assert replay.claimed is False and replay.effect.id == first.effect.id
