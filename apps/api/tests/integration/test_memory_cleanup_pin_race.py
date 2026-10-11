"""A real cleanup must not erase a protection or correction committed after selection."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.memories.models import Memory
from src.domains.memories.repository import MemoryRepository
from src.domains.users.models import User
from src.infrastructure.scheduler import memory_cleanup

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("intervention", ["none", "pinned", "corrected", "used", "procedural"])
async def test_cleanup_keeps_a_changed_candidate_after_its_original_selection(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    intervention: str,
) -> None:
    monkeypatch.setattr(settings, "memory_min_age_for_cleanup_days", 7)
    monkeypatch.setattr(settings, "memory_purge_threshold", 0.5)
    row = Memory(
        user_id=test_user.id,
        content="An old managed fact",
        category="personal",
        importance=0.0,
        pinned=False,
        char_count=19,
        usage_count=0,
        created_at=datetime.now(UTC) - timedelta(days=200),
    )
    async_session.add(row)
    await async_session.commit()
    identity = row.id
    original_selection = MemoryRepository.get_for_cleanup

    async def selection(
        repo: MemoryRepository,
        user_id: UUID,
        min_age_for_cleanup_days: int,
    ) -> list[Memory]:
        candidates = await original_selection(repo, user_id, min_age_for_cleanup_days)
        changes: dict[str, object] = {
            "pinned": {"pinned": True},
            "corrected": {"content": "Corrected by the user"},
            "used": {"usage_count": 1, "last_accessed_at": datetime.now(UTC)},
            "procedural": {"category": "procedural"},
        }.get(intervention, {})
        if changes:
            await async_session.execute(
                update(Memory)
                .where(Memory.id == identity)
                .values(changes)
                .execution_options(synchronize_session=False)
            )
            await async_session.commit()
        return candidates

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session
        await async_session.commit()

    monkeypatch.setattr(MemoryRepository, "get_for_cleanup", selection)
    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", session)
    monkeypatch.setattr(memory_cleanup, "get_redis_cache", AsyncMock(return_value=None))
    monkeypatch.setattr(memory_cleanup, "_purge_invalidated_trail", AsyncMock(return_value=0))
    report = await memory_cleanup.cleanup_memories()
    stored = await async_session.scalar(
        select(Memory).where(Memory.id == identity).execution_options(populate_existing=True)
    )
    if intervention == "none":
        assert stored is None and report["purged"] == 1
    else:
        assert stored is not None and report["purged"] == 0
