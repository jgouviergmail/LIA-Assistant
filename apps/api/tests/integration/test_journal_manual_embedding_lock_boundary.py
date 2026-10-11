"""Independent connections prove paid manual preparation holds no owner row lock."""

from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.config import settings
from src.domains.journals import manual_embeddings
from src.domains.journals.creation_commands import create_managed_journal_entry
from src.domains.journals.models import JournalEntry
from src.domains.journals.schemas import JournalEntryCreate, JournalEntryUpdate
from src.domains.journals.update_commands import update_managed_journal_entry
from src.domains.users.models import User
from tests.integration.test_application_memory_independent_transactions import (
    assert_independent_lock_control,
)

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("operation", ["create", "update"])
async def test_manual_provider_work_does_not_hold_owner_lock(
    async_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    monkeypatch.setattr(settings, "journals_enabled", True)
    owner = uuid4()
    entry_id = uuid4()
    async with AsyncSession(async_engine) as seed:
        seed.add(User(id=owner, email=f"journal-paid-lock-{owner}@example.test", is_active=True))
        await seed.commit()
        if operation == "update":
            seed.add(
                JournalEntry(
                    id=entry_id,
                    user_id=owner,
                    theme="learnings",
                    title="Old",
                    content="Content",
                    char_count=7,
                )
            )
            await seed.commit()
    calls = []
    try:
        async with AsyncSession(async_engine, expire_on_commit=False) as manager:
            await assert_independent_lock_control(manager, async_engine, owner)

            async def embed(text: str):
                async with AsyncSession(async_engine) as probe:
                    assert await probe.scalar(
                        select(func.pg_backend_pid())
                    ) != await manager.scalar(select(func.pg_backend_pid()))
                    assert (
                        await probe.scalar(
                            select(User.id).where(User.id == owner).with_for_update(nowait=True)
                        )
                        == owner
                    )
                    calls.append(text)
                return None

            async def quota(actor_id, *, layer):
                assert actor_id == owner and layer == "journal_management"

            monkeypatch.setattr(manual_embeddings, "_generate_document_embedding", embed)
            monkeypatch.setattr(manual_embeddings, "enforce_usage_limit", quota)
            result = (
                await create_managed_journal_entry(
                    manager,
                    owner,
                    JournalEntryCreate(
                        theme="learnings", title="Title", content="Content", search_hints=["Hint"]
                    ),
                )
                if operation == "create"
                else await update_managed_journal_entry(
                    manager,
                    owner,
                    entry_id,
                    JournalEntryUpdate(title="Title", search_hints=["Hint"]),
                )
            )
            assert result.content == "Content" and len(calls) == 2
    finally:
        async with AsyncSession(async_engine) as cleanup:
            await cleanup.execute(delete(User).where(User.id == owner))
            await cleanup.commit()
