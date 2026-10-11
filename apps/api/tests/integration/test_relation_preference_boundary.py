"""Actual GUI settings and native settings serialize on the same PostgreSQL owner."""

from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import ResourceNotFoundError
from src.domains.relations.overview_scope import RelationOverviewScope
from src.domains.relations.service import RelationsService
from src.domains.users.models import User
from tests.integration.test_application_memory_independent_transactions import (
    assert_independent_lock_control,
)

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("scenario", ["source", "native_off", "inactive"])
async def test_gui_preserves_wire_values_without_native_dependency(
    async_session, test_user, monkeypatch, scenario
):
    owner = test_user.id
    await async_session.commit()
    monkeypatch.setattr(settings, "application_tools_enabled", scenario != "native_off")

    @asynccontextmanager
    async def session():
        yield async_session

    monkeypatch.setattr("src.domains.relations.service.get_db_context", session)
    if scenario == "inactive":
        await async_session.execute(update(User).where(User.id == owner).values(is_active=False))
        await async_session.commit()
        with pytest.raises(ResourceNotFoundError):
            await RelationsService(owner).set_debrief_enabled(False)
        return
    scope = RelationOverviewScope(sections=[], directions=[], roles=[], max_items=3)
    await RelationsService(owner).set_overview_scope(scope)
    assert await RelationsService(owner).get_overview_scope() == scope
    assert await RelationsService(owner).set_debrief_enabled(False) is False
    await async_session.refresh(test_user)
    assert test_user.relation_overview_scope == scope.model_dump(mode="json")
    assert test_user.relation_debrief_enabled is False


async def test_source_gui_cannot_overwrite_a_locked_native_preference(async_engine, monkeypatch):
    owner = uuid4()
    async with AsyncSession(async_engine) as seed:
        seed.add(
            User(
                id=owner,
                email=f"relation-lock-{owner}@example.test",
                full_name="Disposable",
                is_active=True,
            )
        )
        await seed.commit()
    try:
        async with AsyncSession(async_engine) as manager:
            await assert_independent_lock_control(manager, async_engine, owner)
            await manager.scalar(select(User.id).where(User.id == owner).with_for_update())
            async with AsyncSession(async_engine) as writer:
                assert await writer.scalar(select(func.pg_backend_pid())) != await manager.scalar(
                    select(func.pg_backend_pid())
                )
                await writer.execute(text("SET LOCAL lock_timeout = '100ms'"))

                @asynccontextmanager
                async def session():
                    yield writer

                monkeypatch.setattr("src.domains.relations.service.get_db_context", session)
                with pytest.raises(DBAPIError) as blocked:
                    await RelationsService(owner).set_debrief_enabled(False)
                assert getattr(blocked.value.orig, "sqlstate", None) == "55P03"
                await writer.rollback()
    finally:
        async with AsyncSession(async_engine) as cleanup:
            await cleanup.execute(delete(User).where(User.id == owner))
            await cleanup.commit()
