"""Reminders describe remaining intentions, never a fabricated delivery history."""

from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.exceptions import ResourceNotFoundError
from src.domains.reminders.discussion_source import ReminderDiscussionSource
from src.domains.reminders.schemas import ReminderCreate
from src.domains.reminders.service import ReminderService
from src.domains.shared.discussion_sources import ResearchRequest, SourceKey
from tests.integration.domains.proactive_discussions.test_memory_portrait_sources import (
    NOW,
    read_request,
)

pytestmark = pytest.mark.integration


async def seed_reminders(engine: AsyncEngine, owner: UUID) -> None:
    async with AsyncSession(engine) as db:
        service = ReminderService(db)
        for index, days in enumerate((1, 2, 90)):
            row = await service.create_reminder(
                owner,
                ReminderCreate(
                    content=f"Fictional reminder {index}",
                    original_message="Private source wording",
                    trigger_at=NOW + timedelta(days=days),
                ),
                "UTC",
            )
            if index == 1:
                row.status = "processing"
        await db.commit()


async def test_only_pending_intentions_in_requested_window_are_read(
    async_engine: AsyncEngine,
    discussion_owner: UUID,
) -> None:
    await seed_reminders(async_engine, discussion_owner)
    result = await ReminderDiscussionSource().read(
        read_request(discussion_owner, SourceKey.REMINDERS)
    )
    assert result.total == 1 and result.complete and len(result.items) == 1
    assert result.items[0].assertion == "planned"
    assert result.items[0].recurrence_spec and result.items[0].recurrence_spec.freq == "once"
    assert result.items[0].occurred_at and result.items[0].occurred_at > NOW
    assert "Private source wording" not in result.model_dump_json()


async def test_historical_firings_are_unavailable_not_empty(
    discussion_owner: UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def no_source_read() -> None:
        pytest.fail("reminders retain no firing history")

    monkeypatch.setattr("src.domains.reminders.discussion_source.get_db_context", no_source_read)
    scope = read_request(discussion_owner, SourceKey.REMINDERS).model_copy(
        update={
            "request": ResearchRequest(
                source=SourceKey.REMINDERS,
                operation="history",
                start=NOW - timedelta(days=30),
                end=NOW,
            )
        }
    )
    result = await ReminderDiscussionSource().read(scope)
    assert result.status == "unavailable" and result.reason == "expired" and not result.complete


async def test_missing_detail_does_not_prove_no_reminders(discussion_owner: UUID) -> None:
    scope = read_request(discussion_owner, SourceKey.REMINDERS).model_copy(
        update={
            "request": ResearchRequest(
                source=SourceKey.REMINDERS,
                operation="detail",
                reference=f"reminders:{UUID(int=99)}",
            )
        }
    )
    with pytest.raises(ResourceNotFoundError):
        await ReminderDiscussionSource().read(scope)
