"""A UI/native creation race cannot spend the same remaining routine slot twice."""

import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.core.exceptions import ValidationError
from src.domains.scheduled_actions.repository import ScheduledActionRepository
from src.domains.scheduled_actions.schemas import ConditionConfig, ScheduledActionCreate
from src.domains.scheduled_actions.service import ScheduledActionService
from src.domains.users.models import User

pytestmark = pytest.mark.integration


async def test_concurrent_creations_share_one_remaining_slot(
    async_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    maker = async_sessionmaker(async_engine, expire_on_commit=False)
    actor = User(
        id=uuid4(), email=f"{uuid4()}@routine.test", hashed_password="test-hash", is_active=True
    )
    async with maker() as db:
        db.add(actor)
        await db.commit()
    monkeypatch.setattr("src.domains.scheduled_actions.service.SCHEDULED_ACTIONS_MAX_PER_USER", 1)
    first_counted = asyncio.Event()
    release = asyncio.Event()
    reads: list[int] = []
    original = ScheduledActionRepository.count_for_user

    async def held_count(repo: ScheduledActionRepository, user_id):
        count = await original(repo, user_id)
        reads.append(count)
        first_counted.set()
        await release.wait()
        return count

    monkeypatch.setattr(ScheduledActionRepository, "count_for_user", held_count)
    data = ScheduledActionCreate(
        title="Watch",
        action_prompt="Read overdue tasks",
        trigger_kind="condition",
        condition_config=ConditionConfig(type="task_overdue"),
    )

    async def create() -> bool:
        async with maker() as db:
            try:
                await ScheduledActionService(db).create(actor.id, data, "Europe/Paris")
                await db.commit()
                return True
            except ValidationError:
                await db.rollback()
                return False

    tasks: list[asyncio.Task[bool]] = []
    try:
        tasks.append(asyncio.create_task(create()))
        await asyncio.wait_for(first_counted.wait(), 5)
        tasks.append(asyncio.create_task(create()))
        # The first creation deliberately retains the owner reservation.
        await asyncio.sleep(0.1)
        assert reads == [0]
        release.set()
        results = await asyncio.wait_for(asyncio.gather(*tasks), 5)
        assert sorted(results) == [False, True]
    finally:
        release.set()
        await asyncio.gather(*tasks, return_exceptions=True)
        async with maker() as db:
            await db.execute(delete(User).where(User.id == actor.id))
            await db.commit()
