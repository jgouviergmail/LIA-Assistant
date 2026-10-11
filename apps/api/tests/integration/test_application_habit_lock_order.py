"""Independent PostgreSQL writers cannot cross the exact native habit comparison."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.config import settings
from src.domains.agents.application import habit_actions
from src.domains.agents.application.habit_action_schemas import (
    HabitDeleteRequest,
    HabitStatusRequest,
)
from src.domains.habits.management_commands import change_managed_habit
from src.domains.habits.models import UserHabit
from src.domains.habits.repository import HabitsRepository
from src.domains.habits.schemas import HabitStatusUpdate
from src.domains.habits.service import HabitsService
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from tests.integration.test_application_memory_independent_transactions import (
    assert_independent_lock_control,
)

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("operation", ["status", "delete", "recompute_fence"])
async def test_native_habit_action_fences_source_ui_and_learning(
    async_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    monkeypatch.setattr(settings, "habits_enabled", True)
    owner, identity = uuid4(), uuid4()
    async with AsyncSession(async_engine) as seed:
        seed.add(
            User(
                id=owner,
                email=f"habit-lock-{owner}@example.test",
                full_name="Disposable",
                is_active=True,
                is_verified=True,
            )
        )
        await seed.commit()
        seed.add(
            UserHabit(
                id=identity,
                user_id=owner,
                kind="recurring_request",
                key="email",
                payload={"version": 1},
                last_observed_at=datetime.now(UTC),
            )
        )
        await seed.commit()
    try:
        async with AsyncSession(async_engine, expire_on_commit=False) as db:
            await assert_independent_lock_control(db, async_engine, owner)
            # The owner lock must precede the child's lock: learning may later
            # insert another FK-backed habit in the same unit of work.
            await db.scalar(select(User.id).where(User.id == owner).with_for_update())
            if operation == "recompute_fence":
                async with AsyncSession(async_engine) as recomputer:
                    user = await recomputer.get(User, owner)
                    seed = AsyncMock(
                        side_effect=AssertionError("No advisory write before owner fence")
                    )
                    monkeypatch.setattr(
                        "src.domains.habits.service.seed_ledger_from_outcomes", seed
                    )
                    await recomputer.execute(text("SET LOCAL lock_timeout = '100ms'"))
                    with pytest.raises(DBAPIError) as parent_fence:
                        await HabitsService(recomputer).recompute_user_profile(user, force=True)
                    assert getattr(parent_fence.value.orig, "sqlstate", None) == "55P03"
                    seed.assert_not_awaited()
                return
            async with AsyncSession(async_engine) as detector:
                await detector.execute(text("SET LOCAL lock_timeout = '100ms'"))
                with pytest.raises(DBAPIError) as parent_fence:
                    await HabitsRepository(detector).upsert_habit(
                        owner, "recurring_request", "email", {"version": 2}, datetime.now(UTC)
                    )
                assert getattr(parent_fence.value.orig, "sqlstate", None) == "55P03"
                await detector.rollback()
            await db.rollback()
            request = (
                HabitStatusRequest(habit_id=identity, status="blocked")
                if operation == "status"
                else HabitDeleteRequest(habit_id=identity)
            )
            draft = await habit_actions.prepare_habit_action(db, owner, request)
            original_flush = db.flush

            async def verify_locks(*args, **kwargs):
                await original_flush(*args, **kwargs)
                async with AsyncSession(async_engine) as observer:
                    with pytest.raises(DBAPIError) as locked:
                        await observer.scalar(
                            select(User.id).where(User.id == owner).with_for_update(nowait=True)
                        )
                    assert getattr(locked.value.orig, "sqlstate", None) == "55P03"
                    await observer.rollback()
                    await observer.execute(text("SET LOCAL lock_timeout = '100ms'"))
                    with pytest.raises(DBAPIError) as ui:
                        await change_managed_habit(
                            observer, owner, identity, HabitStatusUpdate(status="active")
                        )
                    assert getattr(ui.value.orig, "sqlstate", None) == "55P03"
                    await observer.rollback()
                    await observer.execute(text("SET LOCAL lock_timeout = '100ms'"))
                    with pytest.raises(DBAPIError) as detector:
                        await observer.execute(
                            update(UserHabit)
                            .where(UserHabit.id == identity)
                            .values(payload={"version": 2})
                        )
                    assert getattr(detector.value.orig, "sqlstate", None) == "55P03"
                    await observer.rollback()

            monkeypatch.setattr(db, "flush", verify_locks)
            receipt = PreferenceWriteReceipt()
            await habit_actions.execute_habit_action(db, owner, draft, receipt)
            assert receipt.committed
        async with AsyncSession(async_engine) as fresh:
            stored = await fresh.get(UserHabit, identity)
            assert (
                stored is None
                if operation == "delete"
                else stored.status == "blocked" and stored.payload == {"version": 1}
            )
    finally:
        async with AsyncSession(async_engine) as cleanup:
            await cleanup.execute(delete(User).where(User.id == owner))
            await cleanup.commit()
