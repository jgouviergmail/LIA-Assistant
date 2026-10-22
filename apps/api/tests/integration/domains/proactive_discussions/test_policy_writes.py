"""Real commits pin nullable patches and optimistic concurrency semantics."""

import asyncio
from uuid import UUID

import pytest
from sqlalchemy import event, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.exceptions import ResourceConflictError, ResourceNotFoundError
from src.domains.proactive_discussions.models import DiscussionPreference
from src.domains.proactive_discussions.repository import DiscussionRepository
from src.domains.proactive_discussions.write_schemas import DiscussionPolicyPatch
from src.domains.shared.discussion_sources import SourceKey

pytestmark = pytest.mark.integration


async def test_old_account_bootstraps_off_once(
    async_engine: AsyncEngine, discussion_owner: UUID
) -> None:
    async def read():
        async with AsyncSession(async_engine) as db:
            policy = await DiscussionRepository(db).get_policy(discussion_owner)
            await db.commit()
            return policy

    first, second = await asyncio.gather(read(), read())
    assert first == second
    assert first.enabled is False and first.sources == () and first.timezone == "UTC"
    async with AsyncSession(async_engine) as db:
        assert (
            await db.scalar(
                select(func.count())
                .select_from(DiscussionPreference)
                .where(DiscussionPreference.user_id == discussion_owner)
            )
            == 1
        )


async def test_patch_absent_max_preserves_and_null_removes_only_bound(
    async_engine: AsyncEngine, discussion_owner: UUID
) -> None:
    async with AsyncSession(async_engine) as db:
        repository = DiscussionRepository(db)
        first = await repository.update_policy(
            discussion_owner,
            DiscussionPolicyPatch(enabled=True, sources=(SourceKey.PORTRAIT,), daily_max=3),
            expected_revision=0,
        )
        await db.commit()
        second = await repository.update_policy(
            discussion_owner, DiscussionPolicyPatch(start_hour=10), expected_revision=first.revision
        )
        await db.commit()
        third = await repository.update_policy(
            discussion_owner,
            DiscussionPolicyPatch(daily_max=None),
            expected_revision=second.revision,
        )
        await db.commit()
    assert second.daily_max == 3
    assert third.daily_max is None and third.sources == (SourceKey.PORTRAIT,)
    assert third.enabled and third.start_hour == 10


async def test_stale_patch_cannot_overwrite_other_choices(
    async_engine: AsyncEngine, discussion_owner: UUID
) -> None:
    async with AsyncSession(async_engine) as first:
        await DiscussionRepository(first).update_policy(
            discussion_owner, DiscussionPolicyPatch(sources=(SourceKey.SMS,)), expected_revision=0
        )
        await first.commit()
    async with AsyncSession(async_engine) as second:
        with pytest.raises(ResourceConflictError):
            await DiscussionRepository(second).update_policy(
                discussion_owner, DiscussionPolicyPatch(enabled=True), expected_revision=0
            )
        await second.rollback()
        current = await DiscussionRepository(second).get_policy(discussion_owner)
        assert current.sources == (SourceKey.SMS,) and not current.enabled


async def test_unknown_owner_does_not_create_or_read_policy(async_engine: AsyncEngine) -> None:
    async with AsyncSession(async_engine) as db:
        with pytest.raises(ResourceNotFoundError):
            await DiscussionRepository(db).get_policy(UUID(int=987654321))


async def test_combined_patch_validates_result_not_only_individual_fields(
    async_engine: AsyncEngine, discussion_owner: UUID
) -> None:
    async with AsyncSession(async_engine) as db:
        with pytest.raises(ValueError):
            await DiscussionRepository(db).update_policy(
                discussion_owner, DiscussionPolicyPatch(start_hour=20), expected_revision=0
            )
        await db.rollback()
        current = await DiscussionRepository(db).get_policy(discussion_owner)
        assert current.start_hour == 9 and current.revision == 0


async def test_database_rejects_zero_even_if_a_writer_bypasses_schema(
    async_engine: AsyncEngine, discussion_owner: UUID
) -> None:
    async with AsyncSession(async_engine) as db:
        await DiscussionRepository(db).get_policy(discussion_owner)
        await db.commit()
        with pytest.raises(IntegrityError):
            await db.execute(
                update(DiscussionPreference)
                .where(DiscussionPreference.user_id == discussion_owner)
                .values(daily_max=0)
            )
        await db.rollback()
        assert (await DiscussionRepository(db).get_policy(discussion_owner)).daily_max == 2


async def test_policy_authority_does_not_fetch_personal_source_columns(
    async_engine: AsyncEngine, discussion_owner: UUID
) -> None:
    statements: list[str] = []

    def observe(*args: object) -> None:
        statement = args[2]
        assert isinstance(statement, str)
        statements.append(statement)

    event.listen(async_engine.sync_engine, "before_cursor_execute", observe)
    try:
        async with AsyncSession(async_engine) as db:
            await DiscussionRepository(db).get_policy(discussion_owner)
    finally:
        event.remove(async_engine.sync_engine, "before_cursor_execute", observe)
    assert statements
    assert all(
        "journal_portrait" not in statement and "sms_preferences" not in statement
        for statement in statements
    )
