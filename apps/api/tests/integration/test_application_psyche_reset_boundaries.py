"""Lost acknowledgements, foreign scopes and fresh personality baselines are distinct boundaries."""

from uuid import uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import ResourceConflictError
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.psyche_reset import execute_psyche_reset, prepare_psyche_reset
from src.domains.agents.application.psyche_reset_schemas import PsycheResetIntent
from src.domains.personalities.models import Personality
from src.domains.psyche.models import PsycheHistory, PsycheState
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("committed", [False, True])
async def test_reset_commit_lost_acknowledgement_is_unknown_even_when_it_committed(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch, committed: bool
) -> None:
    monkeypatch.setattr(settings, "psyche_enabled", True)
    owner = test_user.id
    async_session.add(PsycheState(user_id=owner, mood_pleasure=0.9))
    await async_session.commit()
    draft = await prepare_psyche_reset(async_session, owner, PsycheResetIntent(level="purge"))
    original_commit = async_session.commit

    async def lose_ack():
        if committed:
            await original_commit()
        raise OperationalError("commit", {}, RuntimeError("ack unavailable"))

    monkeypatch.setattr(async_session, "commit", lose_ack)
    receipt = PreferenceWriteReceipt()
    with pytest.raises(CommandRejected, match="COMPLETION_UNKNOWN"):
        await execute_psyche_reset(async_session, owner, draft, receipt)
    assert not receipt.committed
    await async_session.rollback()
    assert (
        await async_session.scalar(select(PsycheState).where(PsycheState.user_id == owner)) is None
    ) is committed


async def test_purge_excludes_every_foreign_record(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "psyche_enabled", True)
    other = User(
        id=uuid4(),
        email=f"psyche-foreign-{uuid4()}@example.test",
        full_name="Other",
        is_active=True,
    )
    async_session.add(other)
    await async_session.flush()
    foreign_id = other.id
    async_session.add_all(
        [
            PsycheState(user_id=test_user.id),
            PsycheState(user_id=foreign_id),
            PsycheHistory(user_id=foreign_id, snapshot_type="message"),
        ]
    )
    await async_session.commit()
    draft = await prepare_psyche_reset(
        async_session, test_user.id, PsycheResetIntent(level="purge")
    )
    await execute_psyche_reset(async_session, test_user.id, draft, PreferenceWriteReceipt())
    assert (
        await async_session.scalar(select(PsycheState).where(PsycheState.user_id == foreign_id))
        is not None
    )
    assert (
        await async_session.scalar(
            select(func.count())
            .select_from(PsycheHistory)
            .where(PsycheHistory.user_id == foreign_id)
        )
        == 1
    )


async def test_changed_personality_baseline_cannot_reuse_old_identity_map(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "psyche_enabled", True)
    profile = Personality(
        id=uuid4(),
        code=f"reset-{uuid4()}",
        emoji="🙂",
        prompt_instruction="PRIVATE",
        trait_openness=0.1,
        trait_extraversion=0.1,
    )
    async_session.add(profile)
    await async_session.flush()
    test_user.personality_id = profile.id
    async_session.add(PsycheState(user_id=test_user.id, mood_pleasure=0.9))
    await async_session.commit()
    draft = await prepare_psyche_reset(async_session, test_user.id, PsycheResetIntent(level="soft"))
    await async_session.execute(
        update(Personality)
        .where(Personality.id == profile.id)
        .values(trait_extraversion=0.9)
        .execution_options(synchronize_session=False)
    )
    await async_session.commit()
    with pytest.raises(ResourceConflictError):
        await execute_psyche_reset(async_session, test_user.id, draft, PreferenceWriteReceipt())
