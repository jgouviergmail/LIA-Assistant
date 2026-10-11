"""UI and native manual launches share one execution reservation."""

import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.core.exceptions import ResourceConflictError, ResourceNotFoundError
from src.domains.scheduled_actions.schemas import ConditionConfig, ScheduledActionCreate
from src.domains.scheduled_actions.service import ScheduledActionService
from src.domains.users.models import User

pytestmark = pytest.mark.integration


async def test_two_manual_launches_can_reserve_only_one_execution(
    async_engine: AsyncEngine,
) -> None:
    maker = async_sessionmaker(async_engine, expire_on_commit=False)
    actor = User(
        id=uuid4(), email=f"{uuid4()}@routine.test", hashed_password="test", is_active=True
    )
    async with maker() as db:
        db.add(actor)
        await db.commit()
        row = await ScheduledActionService(db).create(
            actor.id,
            ScheduledActionCreate(
                title="Run",
                action_prompt="Read tasks",
                trigger_kind="condition",
                condition_config=ConditionConfig(type="task_overdue"),
            ),
            "Europe/Paris",
        )
        await db.commit()
    reserved, release = asyncio.Event(), asyncio.Event()

    async def reserve(*, held: bool) -> bool:
        async with maker() as db:
            try:
                await ScheduledActionService(db).reserve_manual_execution(row.id, actor.id)
                if held:
                    reserved.set()
                    await release.wait()
                await db.commit()
                return True
            except ResourceConflictError:
                await db.rollback()
                return False

    tasks: list[asyncio.Task[bool]] = []
    try:
        tasks.append(asyncio.create_task(reserve(held=True)))
        await asyncio.wait_for(reserved.wait(), 5)
        tasks.append(asyncio.create_task(reserve(held=False)))
        await asyncio.sleep(0.1)
        assert not tasks[1].done()
        release.set()
        assert sorted(await asyncio.wait_for(asyncio.gather(*tasks), 5)) == [False, True]
    finally:
        release.set()
        await asyncio.gather(*tasks, return_exceptions=True)
        async with maker() as db:
            await db.execute(delete(User).where(User.id == actor.id))
            await db.commit()


async def test_manual_reservation_hides_foreign_and_deleted_targets(
    async_session: AsyncSession, test_user: User
) -> None:
    row = await ScheduledActionService(async_session).create(
        test_user.id,
        ScheduledActionCreate(
            title="Run",
            action_prompt="Read tasks",
            trigger_kind="condition",
            condition_config=ConditionConfig(type="task_overdue"),
        ),
        "Europe/Paris",
    )
    await async_session.commit()
    with pytest.raises(ResourceNotFoundError):
        await ScheduledActionService(async_session).reserve_manual_execution(row.id, uuid4())
    with pytest.raises(ResourceNotFoundError):
        await ScheduledActionService(async_session).reserve_manual_execution(uuid4(), test_user.id)


async def test_a_late_job_cannot_release_a_new_manual_reservation(
    async_session: AsyncSession, test_user: User
) -> None:
    source = ScheduledActionService(async_session)
    row = await source.create(
        test_user.id,
        ScheduledActionCreate(
            title="Run",
            action_prompt="Read tasks",
            trigger_kind="condition",
            condition_config=ConditionConfig(type="task_overdue"),
        ),
        "Europe/Paris",
    )
    await source.reserve_manual_execution(row.id, test_user.id)
    first = row.execution_token
    assert first is not None
    await source.repository.release_manual_execution(row.id, test_user.id, first)
    await source.reserve_manual_execution(row.id, test_user.id)
    second = row.execution_token
    assert second is not None and second != first
    assert not await source.repository.release_manual_execution(row.id, test_user.id, first)
    await async_session.refresh(row)
    assert row.status == "executing" and row.execution_token == second
    assert await source.repository.release_manual_execution(row.id, test_user.id, second)
