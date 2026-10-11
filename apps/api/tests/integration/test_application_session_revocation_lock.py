"""The operator's DB switch is honored after an actual actor-row lock wait."""

import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.agents.application.preference_dispatch import execute_preference_patch
from src.domains.agents.application.session_revocation_operations import prepare_session_revocation
from src.domains.agents.application.session_revocation_schemas import DeviceSessionRevokeRequest
from src.domains.system_settings.models import SystemSetting, SystemSettingKey
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.application_sessions import bind_browser_session
from src.infrastructure.cache.redis import get_redis_session
from src.infrastructure.cache.session_store import SessionStore
from tests.helpers.runtime_context import installed_runtime_context

pytestmark = pytest.mark.integration


async def test_disable_during_confirmed_revocation_lock_wait_prevents_the_redis_effect(
    async_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    maker = async_sessionmaker(async_engine, expire_on_commit=False)
    actor = User(id=uuid4(), email=f"revocation-lock-{uuid4()}@example.test", is_active=True)
    store = SessionStore(await get_redis_session())
    current = await store.create_session(str(actor.id))
    target = await store.create_session(str(actor.id))
    origin = bind_browser_session(actor.id, current.session_id)
    receipt = PreferenceWriteReceipt()
    key = SystemSettingKey.CAPABILITY_APPLICATION_TOOLS_ENABLED
    previous: str | None = None
    worker_pid: list[int] = []
    started = asyncio.Event()
    try:
        async with maker() as setup:
            setup.add(actor)
            await setup.commit()
            row = await setup.scalar(select(SystemSetting).where(SystemSetting.key == key))
            previous = row.value if row is not None else None
            draft = await prepare_session_revocation(
                setup,
                actor.id,
                DeviceSessionRevokeRequest(display_id=target.display_id),
                origin=origin,
            )

        async def revoke() -> None:
            async with maker() as db:
                pid = await db.scalar(text("SELECT pg_backend_pid()"))
                assert isinstance(pid, int)
                worker_pid.append(pid)
                started.set()
                with installed_runtime_context(user_id=actor.id, application_origin=origin):
                    await execute_preference_patch(
                        db,
                        actor.id,
                        draft.operation_id,
                        draft.intent,
                        draft.before,
                        receipt,
                        approved_until=draft.expires_at,
                    )

        async with maker() as blocker:
            await blocker.scalar(select(User).where(User.id == actor.id).with_for_update())
            task = asyncio.create_task(revoke())
            try:
                await asyncio.wait_for(started.wait(), timeout=5)
                async with maker() as monitor:
                    for _ in range(50):
                        waiting = await monitor.scalar(
                            text("SELECT wait_event_type FROM pg_stat_activity WHERE pid=:pid"),
                            {"pid": worker_pid[0]},
                        )
                        if waiting == "Lock":
                            break
                        await asyncio.sleep(0.02)
                    assert waiting == "Lock", "The worker must actually wait for the actor row"
                async with maker() as operator:
                    row = await operator.scalar(
                        select(SystemSetting).where(SystemSetting.key == key)
                    )
                    if row is None:
                        operator.add(SystemSetting(key=key, value="false"))
                    else:
                        row.value = "false"
                    await operator.commit()
                await blocker.rollback()
                with pytest.raises(AuthorizationError):
                    await asyncio.wait_for(task, timeout=5)
                assert not receipt.committed
                assert await store.redis.exists(f"session:{target.session_id}")
            finally:
                await blocker.rollback()
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)
    finally:
        for session in (current, target):
            await store.delete_session(session.session_id)
        async with maker() as cleanup:
            await cleanup.execute(delete(User).where(User.id == actor.id))
            row = await cleanup.scalar(select(SystemSetting).where(SystemSetting.key == key))
            if row is not None:
                if previous is None:
                    await cleanup.delete(row)
                else:
                    row.value = previous
            await cleanup.commit()
