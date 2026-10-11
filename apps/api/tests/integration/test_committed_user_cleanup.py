"""Independent commits are cleaned up on success and failure, without broad deletes."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.domains.journals.models import JournalEntry
from src.domains.users.models import User
from tests.helpers.committed_users import committed_user_scope

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("fails", [False, True])
async def test_owned_commit_cleanup_cascades_and_preserves_other_accounts(
    async_engine: AsyncEngine, committed_user_ids: list[UUID], fails: bool
) -> None:
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    keeper_id, owner_id, entry_id = uuid4(), uuid4(), uuid4()
    committed_user_ids.append(keeper_id)
    async with factory() as seed:
        seed.add(User(id=keeper_id, email=f"keeper-{keeper_id}@example.test"))
        await seed.commit()

    async def work() -> None:
        async with committed_user_scope(async_engine) as owned:
            owned.append(owner_id)
            async with factory() as seed:
                seed.add(User(id=owner_id, email=f"owned-{owner_id}@example.test"))
                await seed.flush()
                seed.add(
                    JournalEntry(
                        id=entry_id,
                        user_id=owner_id,
                        theme="learnings",
                        title="Owned child",
                        content="Cleanup must cascade",
                        char_count=20,
                    )
                )
                await seed.commit()
            async with factory() as observer:
                assert await observer.get(JournalEntry, entry_id) is not None
            if fails:
                raise AssertionError("controlled post-commit failure")

    if fails:
        with pytest.raises(AssertionError, match="controlled post-commit failure"):
            await work()
    else:
        await work()
    async with factory() as observer:
        assert await observer.get(User, owner_id) is None
        assert await observer.get(JournalEntry, entry_id) is None
        assert await observer.get(User, keeper_id) is not None
