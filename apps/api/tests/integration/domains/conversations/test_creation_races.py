"""Two real connections serialize first-use creation and durable retries."""

import asyncio
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.config import settings
from src.core.constants import CONVERSATION_OWNER_LOCK_SCOPE
from src.core.conversation_target import ConversationKind
from src.domains.conversations.catalogue_repository import ConversationCatalogueRepository
from src.domains.conversations.catalogue_schemas import ConversationCreateRequest
from src.domains.conversations.catalogue_service import ConversationCatalogueService
from src.domains.conversations.models import Conversation, ConversationCreationReceipt
from src.domains.conversations.service import ConversationService
from src.domains.users.models import User
from src.infrastructure.database.owner_lock import hold_owner_lock

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("legacy_first", [True, False])
async def test_creation_waits_for_the_owner_and_rechecks_after_commit(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
    monkeypatch: pytest.MonkeyPatch,
    legacy_first: bool,
) -> None:
    """A first message and a new tab cannot race Main; retries create once."""
    monkeypatch.setattr(settings, "secondary_conversations_enabled", True)
    owner_id = uuid4()
    committed_user_ids.append(owner_id)
    async with AsyncSession(async_engine) as db:
        db.add(
            User(
                id=owner_id,
                email=f"race-{owner_id}@example.test",
                hashed_password="unused",
                is_active=True,
            )
        )
        await db.commit()

    request = ConversationCreateRequest(title="A race", request_id=uuid4())

    async def create(*, legacy: bool) -> UUID:
        async with AsyncSession(async_engine, expire_on_commit=False) as db:
            if legacy:
                return (await ConversationService().get_or_create_conversation(owner_id, db)).id
            result = await ConversationCatalogueService(db).create_secondary(owner_id, request)
            return result.conversation.id

    async with AsyncSession(async_engine) as blocker:
        await hold_owner_lock(blocker, CONVERSATION_OWNER_LOCK_SCOPE, owner_id)
        blocker_pid = await blocker.scalar(text("SELECT pg_backend_pid()"))
        tasks = [
            asyncio.create_task(create(legacy=legacy_first)),
            asyncio.create_task(create(legacy=False)),
        ]
        try:
            async with asyncio.timeout(5):
                async with async_engine.connect() as observer:
                    while True:
                        waiting = await observer.scalar(
                            text(
                                "SELECT count(*) FROM pg_stat_activity "
                                "WHERE :pid = ANY(pg_blocking_pids(pid))"
                            ),
                            {"pid": blocker_pid},
                        )
                        if waiting == 2:
                            break
                        assert not any(
                            task.done() for task in tasks
                        ), "A creation bypassed the account's lifecycle lock"
                        await asyncio.sleep(0.01)
            await blocker.commit()
            first, second = await asyncio.gather(*tasks)
            assert (first == owner_id) if legacy_first else (first == second)
            assert second != owner_id
        finally:
            await blocker.rollback()
            # A failed assertion still owns every pending coroutine and session.
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async with AsyncSession(async_engine) as db:
        kinds = list(
            (
                await db.scalars(select(Conversation.kind).where(Conversation.user_id == owner_id))
            ).all()
        )
        assert sorted(kinds) == sorted([ConversationKind.MAIN, ConversationKind.SECONDARY])
        assert (
            await db.scalar(
                select(func.count())
                .select_from(ConversationCreationReceipt)
                .where(ConversationCreationReceipt.user_id == owner_id)
            )
            == 1
        )


async def test_resolution_refreshes_a_previously_loaded_identity(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
) -> None:
    """A session identity map cannot conceal a runtime changed by another writer."""
    owner_id = uuid4()
    committed_user_ids.append(owner_id)
    async with AsyncSession(async_engine) as setup:
        setup.add(
            User(
                id=owner_id,
                email=f"fresh-{owner_id}@example.test",
                hashed_password="unused",
                is_active=True,
            )
        )
        await setup.flush()
        setup.add(Conversation(id=owner_id, user_id=owner_id, runtime_id=owner_id))
        await setup.commit()
    async with AsyncSession(async_engine, expire_on_commit=False) as reader:
        repo = ConversationCatalogueRepository(reader)
        old = await repo.get_primary(owner_id)
        assert old is not None and old.revision == 0
        await reader.commit()
        runtime_id = uuid4()
        async with AsyncSession(async_engine) as writer:
            await writer.execute(
                update(Conversation)
                .where(Conversation.id == owner_id)
                .values(
                    revision=1,
                    runtime_id=runtime_id,
                )
            )
            await writer.commit()
        current = await repo.get_owned(owner_id, owner_id)
        assert current is not None
        assert current.revision == 1 and current.runtime_id == runtime_id
