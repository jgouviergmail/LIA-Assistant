"""Journal interpretations are active, dated and never promoted to human facts."""

from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.config import settings
from src.domains.journals.discussion_source import JournalDiscussionSource
from src.domains.journals.models import JournalEntry
from src.domains.shared.discussion_sources import ResearchRequest, SourceKey
from src.domains.users.models import User
from tests.integration.domains.proactive_discussions.test_memory_portrait_sources import (
    NOW,
    read_request,
)

pytestmark = pytest.mark.integration


async def seed_journal(engine: AsyncEngine, owner: UUID) -> None:
    async with AsyncSession(engine) as db:
        user = await db.get(User, owner)
        assert user is not None
        user.journals_enabled = True
        db.add_all(
            [
                JournalEntry(
                    user_id=owner,
                    title="Fictional jazz observation",
                    content="LIA's hypothesis about jazz.",
                    theme="user_observations",
                    confidence="low",
                    level="L0",
                    created_at=NOW - timedelta(days=30),
                ),
                JournalEntry(
                    user_id=owner,
                    title="Archived",
                    content="Must never be read",
                    theme="user_observations",
                    status="archived",
                ),
            ]
        )
        await db.commit()


async def test_active_interpretation_keeps_confidence_and_recording_date(
    async_engine: AsyncEngine,
    discussion_owner: UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "journals_enabled", True)
    await seed_journal(async_engine, discussion_owner)
    result = await JournalDiscussionSource().read(
        read_request(discussion_owner, SourceKey.JOURNALS)
    )
    assert result.total == 1 and result.complete and len(result.items) == 1
    item = result.items[0]
    assert item.assertion == "inferred" and item.derived
    assert item.occurred_at is None and item.recorded_at == NOW - timedelta(days=30)
    assert item.usage_nuance and "low" in item.usage_nuance and "L0" in item.usage_nuance


async def test_search_is_literal_and_does_not_load_embeddings(
    async_engine: AsyncEngine,
    discussion_owner: UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "journals_enabled", True)
    await seed_journal(async_engine, discussion_owner)
    request = read_request(discussion_owner, SourceKey.JOURNALS)
    searched = request.model_copy(
        update={
            "request": ResearchRequest(source=SourceKey.JOURNALS, operation="search", query="jazz")
        }
    )
    result = await JournalDiscussionSource().read(searched)
    assert result.total == 1 and not result.complete
    assert "embedding" not in result.model_dump_json()
    wildcard = searched.model_copy(
        update={
            "request": ResearchRequest(source=SourceKey.JOURNALS, operation="search", query="%")
        }
    )
    empty = await JournalDiscussionSource().read(wildcard)
    assert empty.total == 0 and empty.status == "empty"


async def test_injection_bookkeeping_keeps_semantic_version(
    async_engine: AsyncEngine,
    discussion_owner: UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "journals_enabled", True)
    await seed_journal(async_engine, discussion_owner)
    source = JournalDiscussionSource()
    request = read_request(discussion_owner, SourceKey.JOURNALS)
    before = await source.read(request)
    async with AsyncSession(async_engine) as db:
        row = await db.scalar(
            select(JournalEntry).where(
                JournalEntry.user_id == discussion_owner, JournalEntry.status == "active"
            )
        )
        assert row is not None
        row.injection_count += 10
        row.last_injected_at = NOW
        await db.commit()
    after = await source.read(request)
    assert before.items[0].version == after.items[0].version


async def test_missing_detail_is_stale_instead_of_empty(
    async_engine: AsyncEngine,
    discussion_owner: UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.core.exceptions import ResourceNotFoundError

    monkeypatch.setattr(settings, "journals_enabled", True)
    await seed_journal(async_engine, discussion_owner)
    request = read_request(discussion_owner, SourceKey.JOURNALS).model_copy(
        update={
            "request": ResearchRequest(
                source=SourceKey.JOURNALS, operation="detail", reference=f"journals:{UUID(int=99)}"
            )
        }
    )
    with pytest.raises(ResourceNotFoundError):
        await JournalDiscussionSource().read(request)
