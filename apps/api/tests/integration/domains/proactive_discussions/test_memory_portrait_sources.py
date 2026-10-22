"""Real owned rows prove factual memory and whole-portrait source boundaries."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.config import settings
from src.domains.journals.discussion_source import PortraitDiscussionSource
from src.domains.memories.discussion_source import MemoryDiscussionSource
from src.domains.memories.models import Memory
from src.domains.shared.discussion_sources import ResearchRequest, SourceKey, SourceReadRequest
from src.domains.users.models import User

pytestmark = pytest.mark.integration
NOW = datetime(2026, 10, 20, 10, tzinfo=UTC)


def read_request(
    owner: UUID, source: SourceKey, *, limit: int = 10, chars: int = 16000
) -> SourceReadRequest:
    return SourceReadRequest(
        owner_id=owner,
        run_id=UUID(int=2),
        policy_revision=0,
        request=ResearchRequest(source=source, operation="recent"),
        now=NOW,
        window_start=NOW - timedelta(hours=72),
        window_end=NOW + timedelta(days=7),
        allowed_sources=(source,),
        item_limit=limit,
        item_max_chars=chars,
        call_limit=1,
        timeout_seconds=10,
    )


async def test_factual_memories_exclude_invalidated_rules_and_unconsented_biometrics(
    async_engine: AsyncEngine, discussion_owner: UUID, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "memory_extraction_enabled", True)
    async with AsyncSession(async_engine) as db:
        db.add_all(
            [
                Memory(
                    user_id=discussion_owner,
                    content="I play piano",
                    category="personal",
                    created_at=NOW - timedelta(days=100),
                ),
                Memory(
                    user_id=discussion_owner,
                    content="Old invalid location",
                    category="personal",
                    invalidated_at=NOW,
                ),
                Memory(
                    user_id=discussion_owner, content="Never discuss health", category="procedural"
                ),
                Memory(
                    user_id=discussion_owner,
                    content="Private biometric correlation",
                    category="event",
                    context_biometric={"delta": 1},
                ),
            ]
        )
        await db.commit()
    result = await MemoryDiscussionSource().read(read_request(discussion_owner, SourceKey.MEMORIES))
    assert result.status == "ok" and result.complete and result.total == 1
    assert [item.excerpt for item in result.items] == ["I play piano"]
    assert result.items[0].occurred_at is None
    assert result.items[0].recorded_at == NOW - timedelta(days=100)
    assert result.coverage_kind == "active_facts"


async def test_usage_bookkeeping_does_not_change_semantic_version(
    async_engine: AsyncEngine, discussion_owner: UUID, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "memory_extraction_enabled", True)
    async with AsyncSession(async_engine) as db:
        db.add(Memory(user_id=discussion_owner, content="I play piano", category="personal"))
        await db.commit()
    source = MemoryDiscussionSource()
    request = read_request(discussion_owner, SourceKey.MEMORIES)
    before = await source.read(request)
    async with AsyncSession(async_engine) as db:
        memory = await db.scalar(select(Memory).where(Memory.user_id == discussion_owner))
        assert memory is not None
        memory.usage_count = 100
        memory.last_accessed_at = NOW
        await db.commit()
    after = await source.read(request)
    assert before.items[0].version == after.items[0].version
    async with AsyncSession(async_engine) as db:
        memory = await db.scalar(select(Memory).where(Memory.user_id == discussion_owner))
        assert memory is not None
        memory.content = "I stopped playing piano"
        await db.commit()
    changed = await source.read(request)
    assert changed.items[0].version != before.items[0].version


async def test_memory_history_filters_recording_dates_and_filtered_total(
    async_engine: AsyncEngine, discussion_owner: UUID, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "memory_extraction_enabled", True)
    async with AsyncSession(async_engine) as db:
        db.add_all(
            Memory(
                user_id=discussion_owner,
                content=f"Fictional fact {days} days ago",
                category="personal",
                created_at=NOW - timedelta(days=days),
            )
            for days in (80, 3, 2, 1)
        )
        await db.commit()
    start, end = NOW - timedelta(days=3), NOW - timedelta(days=1)
    request = read_request(discussion_owner, SourceKey.MEMORIES).model_copy(
        update={
            "request": ResearchRequest(
                source=SourceKey.MEMORIES, operation="history", start=start, end=end
            ),
            "window_start": start,
            "window_end": end,
        }
    )
    result = await MemoryDiscussionSource().read(request)
    assert result.total == 2
    assert [item.excerpt for item in result.items] == [
        "Fictional fact 2 days ago",
        "Fictional fact 3 days ago",
    ]
    assert all(item.occurred_at is None for item in result.items)
    assert all(start <= item.recorded_at < end for item in result.items)
    assert result.coverage_kind == "active_facts"


async def test_memory_page_reports_real_total_and_cursor(
    async_engine: AsyncEngine, discussion_owner: UUID, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "memory_extraction_enabled", True)
    async with AsyncSession(async_engine) as db:
        db.add_all(
            [
                Memory(
                    user_id=discussion_owner, content=f"Fictional fact {index}", category="personal"
                )
                for index in range(3)
            ]
        )
        await db.commit()
    source = MemoryDiscussionSource()
    request = read_request(discussion_owner, SourceKey.MEMORIES, limit=1)
    first = await source.read(request)
    assert first.status == "truncated" and first.total == 3 and not first.complete and first.cursor
    second = await source.read(request.model_copy(update={"cursor": first.cursor}))
    assert second.items[0].reference != first.items[0].reference
    assert second.cursor
    third = await source.read(request.model_copy(update={"cursor": second.cursor}))
    assert third.cursor is None and not third.complete


async def test_deleted_or_invalidated_memory_detail_is_not_empty(
    discussion_owner: UUID, monkeypatch
) -> None:
    from src.core.exceptions import ResourceNotFoundError

    monkeypatch.setattr(settings, "memory_extraction_enabled", True)
    scope = read_request(discussion_owner, SourceKey.MEMORIES).model_copy(
        update={
            "request": ResearchRequest(
                source=SourceKey.MEMORIES, operation="detail", reference=f"memories:{UUID(int=99)}"
            )
        }
    )
    with pytest.raises(ResourceNotFoundError):
        await MemoryDiscussionSource().read(scope)


async def test_global_memory_consent_is_checked_fresh(
    async_engine: AsyncEngine, discussion_owner: UUID, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "memory_extraction_enabled", True)
    async with AsyncSession(async_engine) as db:
        user = await db.get(User, discussion_owner)
        assert user is not None
        user.memory_enabled = False
        db.add(Memory(user_id=discussion_owner, content="Must remain private", category="personal"))
        await db.commit()
    result = await MemoryDiscussionSource().read(read_request(discussion_owner, SourceKey.MEMORIES))
    assert result.status == "disabled" and not result.items


async def test_portrait_stays_whole_when_other_discussion_sources_are_refused(
    async_engine: AsyncEngine, discussion_owner: UUID, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "journals_enabled", True)
    async with AsyncSession(async_engine) as db:
        user = await db.get(User, discussion_owner)
        assert user is not None
        user.journals_enabled = True
        user.journal_portrait_brief = "Enjoys jazz. Remembers the trip mentioned in email."
        user.journal_portrait_compiled_at = NOW - timedelta(days=20)
        await db.commit()
    result = await PortraitDiscussionSource().read(
        read_request(discussion_owner, SourceKey.PORTRAIT)
    )
    assert result.status == "ok" and len(result.items) == 1
    assert "Enjoys jazz. Remembers the trip mentioned in email." in result.items[0].excerpt
    assert result.items[0].recorded_at == NOW - timedelta(days=20)
    assert result.items[0].occurred_at is None and result.coverage_kind == "dated_synthesis"
    too_small = await PortraitDiscussionSource().read(
        read_request(discussion_owner, SourceKey.PORTRAIT, chars=10)
    )
    assert (
        too_small.status == "unavailable" and too_small.reason == "budget" and not too_small.items
    )


async def test_unqualified_stored_portrait_is_stale_instead_of_absent(
    async_engine: AsyncEngine, discussion_owner: UUID, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "journals_enabled", True)
    async with AsyncSession(async_engine) as db:
        user = await db.get(User, discussion_owner)
        assert user is not None
        user.journals_enabled = True
        user.journal_portrait_brief = "Fictional legacy interpretation"
        user.journal_portrait_compiled_at = None
        await db.commit()
    result = await PortraitDiscussionSource().read(
        read_request(discussion_owner, SourceKey.PORTRAIT)
    )
    assert result.status == "stale" and not result.complete and not result.items
