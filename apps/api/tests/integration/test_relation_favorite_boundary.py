"""The displayed merged card's favorite is one state across all its saved spellings."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError
from src.domains.relations.favorite_commands import (
    read_relation_favorite,
    set_managed_relation_favorite,
)
from src.domains.relations.models import RelationAlias, RelationFavorite
from src.domains.relations.repository import RelationAliasRepository, RelationFavoriteRepository
from src.domains.relations.service import RelationsService
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from tests.integration.test_application_memory_independent_transactions import (
    assert_independent_lock_control,
)

pytestmark = pytest.mark.integration


async def test_unstarring_merged_card_removes_the_alias_star(async_session, test_user, monkeypatch):
    owner = test_user.id
    async_session.add(
        RelationAlias(
            user_id=owner, alias_key="papa", canonical_key="jean dupont", alias_display_name="Papa"
        )
    )
    async_session.add(RelationFavorite(user_id=owner, name_key="papa", display_name="Papa"))
    await async_session.commit()

    @asynccontextmanager
    async def session():
        yield async_session

    monkeypatch.setattr("src.domains.relations.service.get_db_context", session)
    assert await RelationsService(owner).remove_favorite("Jean Dupont") is True
    assert (
        await async_session.scalar(
            select(RelationFavorite.id).where(RelationFavorite.user_id == owner)
        )
        is None
    )


@pytest.mark.parametrize("scenario", ["change", "noop", "stale_identity", "unrelated"])
async def test_managed_star_pins_the_displayed_source_identity(async_session, test_user, scenario):
    owner = test_user.id
    alias = RelationAlias(
        user_id=owner, alias_key="papa", canonical_key="jean dupont", alias_display_name="Papa"
    )
    async_session.add(alias)
    async_session.add(RelationFavorite(user_id=owner, name_key="papa", display_name="Papa"))
    await async_session.commit()
    selection = await read_relation_favorite(async_session, owner, "Jean Dupont")
    assert selection.starred
    if scenario == "unrelated":
        async_session.add(
            RelationFavorite(user_id=owner, name_key="other person", display_name="Other person")
        )
        await async_session.commit()
    if scenario == "stale_identity":
        await async_session.execute(
            update(RelationAlias)
            .where(RelationAlias.id == alias.id)
            .values(canonical_key="other person")
        )
        await async_session.commit()
    receipt = PreferenceWriteReceipt()
    if scenario == "stale_identity":
        with pytest.raises(ResourceConflictError):
            await set_managed_relation_favorite(
                async_session, owner, selection, False, receipt, AsyncMock()
            )
        assert not receipt.committed
    else:
        await set_managed_relation_favorite(
            async_session, owner, selection, scenario == "noop", receipt, AsyncMock()
        )
        assert receipt.committed and receipt.no_op is (scenario == "noop")
        actual = await read_relation_favorite(async_session, owner, "Jean Dupont")
        assert actual.starred is (scenario == "noop")


@pytest.mark.parametrize("action", ["star", "unstar", "merge", "split"])
async def test_all_gui_identity_writers_share_the_native_parent_lock(
    async_engine, monkeypatch, action
):
    owner = uuid4()
    async with AsyncSession(async_engine) as seed:
        seed.add(
            User(
                id=owner,
                email=f"favorite-lock-{owner}@example.test",
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
                service = RelationsService(owner)
                with pytest.raises(DBAPIError) as blocked:
                    if action == "star":
                        await service.add_favorite("Alice")
                    elif action == "unstar":
                        await service.remove_favorite("Alice")
                    elif action == "merge":
                        await service.merge_relations(source="Alice", target="Bob")
                    else:
                        await service.split_relation("Alice")
                assert getattr(blocked.value.orig, "sqlstate", None) == "55P03"
                await writer.rollback()
    finally:
        async with AsyncSession(async_engine) as cleanup:
            await cleanup.execute(delete(User).where(User.id == owner))
            await cleanup.commit()


async def test_other_connection_merge_refreshes_cached_confirmation_facts(
    async_engine, monkeypatch
):
    owner = uuid4()
    async with AsyncSession(async_engine) as seed:
        seed.add(
            User(
                id=owner,
                email=f"favorite-cache-{owner}@example.test",
                full_name="Disposable",
                is_active=True,
            )
        )
        await seed.commit()
        seed.add(
            RelationAlias(
                user_id=owner,
                alias_key="papa",
                canonical_key="jean dupont",
                alias_display_name="Papa",
            )
        )
        seed.add(RelationFavorite(user_id=owner, name_key="papa", display_name="Papa"))
        await seed.commit()
    try:
        async with AsyncSession(async_engine, expire_on_commit=False) as manager:
            retained_aliases = await RelationAliasRepository(manager).list_for_user(owner)
            retained_stars = await RelationFavoriteRepository(manager).list_for_user(owner)
            expected = await read_relation_favorite(manager, owner, "Jean Dupont")
            await manager.commit()
            async with AsyncSession(async_engine) as writer:
                assert await writer.scalar(select(func.pg_backend_pid())) != await manager.scalar(
                    select(func.pg_backend_pid())
                )

                @asynccontextmanager
                async def session():
                    yield writer
                    await writer.commit()

                monkeypatch.setattr("src.domains.relations.service.get_db_context", session)
                await RelationsService(owner).merge_relations(source="Papa", target="Bob")
            with pytest.raises(ResourceConflictError):
                await set_managed_relation_favorite(
                    manager, owner, expected, False, PreferenceWriteReceipt(), AsyncMock()
                )
            assert retained_aliases and retained_stars
    finally:
        async with AsyncSession(async_engine) as cleanup:
            await cleanup.execute(delete(User).where(User.id == owner))
            await cleanup.commit()
