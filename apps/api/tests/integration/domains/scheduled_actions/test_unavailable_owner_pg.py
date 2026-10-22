"""Unavailable owners release only their own reservation, preserving current edits."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.domains.scheduled_actions.models import ScheduledAction, ScheduledActionRun
from src.domains.scheduled_actions.repository import ScheduledActionRepository
from src.infrastructure.scheduler import scheduled_action_executor as executor
from tests.fixtures.factories import UserFactory

pytestmark = pytest.mark.integration


async def _reserved(
    maker: async_sessionmaker[AsyncSession], committed_user_ids: list[UUID]
) -> tuple[UUID, UUID, UUID]:
    async with maker() as db:
        user = UserFactory.create()
        db.add(user)
        await db.flush()
        committed_user_ids.append(user.id)
        token = uuid4()
        action = ScheduledAction(
            user_id=user.id,
            title="Unavailable owner",
            action_prompt="Never execute this instruction",
            recurrence={"freq": "daily", "interval": 1, "anchor_date": "2026-09-01"},
            user_timezone="UTC",
            next_trigger_at=datetime(2026, 9, 1, tzinfo=UTC),
            status="executing",
            execution_token=token,
            is_enabled=True,
        )
        db.add(action)
        await db.commit()
        return action.id, user.id, token


@pytest.mark.parametrize("deleted", [False, True])
async def test_unavailable_owner_is_disabled_without_running_or_stale_recovery(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
    monkeypatch: pytest.MonkeyPatch,
    deleted: bool,
) -> None:
    from src.domains.users.models import User

    maker = async_sessionmaker(async_engine, expire_on_commit=False, autoflush=False)
    action_id, user_id, token = await _reserved(maker, committed_user_ids)

    @asynccontextmanager
    async def sessions() -> AsyncIterator[AsyncSession]:
        async with maker() as db:
            yield db
            await db.commit()

    async with maker() as db:
        owner = await db.get(User, user_id)
        assert owner is not None
        owner.is_active = False
        owner.deleted_at = datetime.now(UTC) if deleted else None
        await db.commit()
    stream = AsyncMock()
    monkeypatch.setattr(executor, "stream_instruction", stream)
    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", sessions)

    assert await executor.execute_single_action(action_id, user_id, execution_token=token) == ""
    async with maker() as db:
        action = await db.get(ScheduledAction, action_id)
        assert action is not None
        assert not action.is_enabled and action.status == "active"
        assert action.execution_token is None and action.execution_count == 0
        assert action.consecutive_failures == 0 and action.last_error is None
        assert (
            await ScheduledActionRepository(db).recover_stale_executing(
                older_than=datetime.now(UTC)
            )
            == 0
        )
        assert not list(await db.scalars(select(ScheduledActionRun.id)))
    stream.assert_not_awaited()


@pytest.mark.parametrize("change", ["edits", "cancelled", "new_worker", "reactivated"])
async def test_owner_disable_is_atomic_and_preserves_concurrent_state(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
    change: str,
) -> None:
    from src.domains.users.models import User

    maker = async_sessionmaker(async_engine, expire_on_commit=False, autoflush=False)
    action_id, user_id, token = await _reserved(maker, committed_user_ids)
    replacement = uuid4() if change == "new_worker" else token
    next_trigger = datetime(2027, 1, 1, tzinfo=UTC)
    async with maker() as original:
        stale = await original.get(ScheduledAction, action_id)
        assert stale is not None
        async with maker() as other:
            owner = await other.get(User, user_id)
            current = await other.get(ScheduledAction, action_id)
            assert owner is not None and current is not None
            owner.is_active = change == "reactivated"
            current.title = "Concurrent edit"
            current.next_trigger_at = next_trigger
            current.execution_token = None if change == "cancelled" else replacement
            current.status = "active" if change == "cancelled" else "executing"
            await other.commit()
        changed = await ScheduledActionRepository(original).disable_for_unavailable_owner(
            action_id, user_id, token
        )
        await original.commit()
    assert changed == (change == "edits")
    async with maker() as db:
        current = await db.get(ScheduledAction, action_id)
        assert current is not None
        assert current.title == "Concurrent edit" and current.next_trigger_at == next_trigger
        assert current.is_enabled == (change != "edits")
        assert current.status == ("active" if change in {"edits", "cancelled"} else "executing")
        assert current.execution_token == (
            None if change in {"edits", "cancelled"} else replacement
        )
