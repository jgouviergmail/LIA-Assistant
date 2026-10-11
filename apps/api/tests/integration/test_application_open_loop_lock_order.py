"""Independent PostgreSQL sessions prove source UI/extractor writers cannot cross the native CAS."""

from uuid import uuid4

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.config import settings
from src.domains.agents.application import open_loop_actions
from src.domains.agents.application.open_loop_action_schemas import (
    OpenLoopCloseRequest,
    OpenLoopUpdateRequest,
)
from src.domains.open_loops.models import OpenLoop
from src.domains.open_loops.repository import OpenLoopRepository
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from tests.integration.test_application_memory_independent_transactions import (
    assert_independent_lock_control,
)

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("operation", ["update", "close"])
async def test_native_commitment_locks_fence_independent_source_writers(
    async_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    monkeypatch.setattr(settings, "open_loops_enabled", True)
    owner, identity = uuid4(), uuid4()
    async with AsyncSession(async_engine) as seed:
        seed.add(
            User(
                id=owner,
                email=f"loop-lock-{owner}@example.test",
                full_name="Disposable",
                is_active=True,
                is_verified=True,
            )
        )
        await seed.commit()
        seed.add(
            OpenLoop(id=identity, user_id=owner, subject="Confirmed promise", direction="user_owes")
        )
        await seed.commit()
    try:
        async with AsyncSession(async_engine, expire_on_commit=False) as db:
            await assert_independent_lock_control(db, async_engine, owner)
            request = (
                OpenLoopCloseRequest(loop_id=identity)
                if operation == "close"
                else OpenLoopUpdateRequest.model_validate(
                    {"loop_id": str(identity), "changes": {"subject": "Native correction"}}
                )
            )
            draft = await open_loop_actions.prepare_open_loop_action(db, owner, request)
            source = open_loop_actions.apply_open_loop_change

            async def verify_locks(*args, **kwargs):
                await source(*args, **kwargs)
                async with AsyncSession(async_engine) as observer:
                    with pytest.raises(DBAPIError) as locked:
                        await observer.scalar(
                            select(User.id).where(User.id == owner).with_for_update(nowait=True)
                        )
                    assert getattr(locked.value.orig, "sqlstate", None) == "55P03"
                    await observer.rollback()
                    await observer.execute(text("SET LOCAL lock_timeout = '100ms'"))
                    with pytest.raises(DBAPIError) as concurrent:
                        await OpenLoopRepository(observer).update_loop(
                            identity, owner, subject="Competing UI correction"
                        )
                    assert getattr(concurrent.value.orig, "sqlstate", None) == "55P03"
                    await observer.rollback()

            monkeypatch.setattr(open_loop_actions, "apply_open_loop_change", verify_locks)
            receipt = PreferenceWriteReceipt()
            await open_loop_actions.execute_open_loop_action(db, owner, draft, receipt)
            assert receipt.committed
        async with AsyncSession(async_engine) as fresh:
            stored = await fresh.get(OpenLoop, identity)
            assert stored is not None and (
                stored.status == "closed"
                if operation == "close"
                else stored.subject == "Native correction"
            )
    finally:
        async with AsyncSession(async_engine) as cleanup:
            await cleanup.execute(delete(User).where(User.id == owner))
            await cleanup.commit()
