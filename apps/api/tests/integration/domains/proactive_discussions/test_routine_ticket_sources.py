"""Native intentions remain intentions; shared workboard visibility is preserved."""

from datetime import date, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.config import settings
from src.core.recurrence import DailyTimes, RecurrenceSpec, TimeOfDay
from src.domains.scheduled_actions.discussion_source import ScheduledActionDiscussionSource
from src.domains.scheduled_actions.models import ScheduledAction
from src.domains.shared.discussion_sources import SourceKey
from src.domains.users.models import User
from src.domains.workboard.discussion_source import WorkboardDiscussionSource
from src.domains.workboard.models import WorkboardTicket
from tests.integration.domains.proactive_discussions.test_memory_portrait_sources import (
    NOW,
    read_request,
)

pytestmark = pytest.mark.integration


async def test_routine_reads_do_not_run_or_promote_assistant_completion_to_personal_action(
    async_engine: AsyncEngine,
    discussion_owner: UUID,
) -> None:
    spec = RecurrenceSpec(
        freq="daily",
        anchor_date=date(2026, 10, 1),
        times=DailyTimes(at=(TimeOfDay(hour=9, minute=0),)),
    )
    async with AsyncSession(async_engine) as db:
        row = ScheduledAction(
            user_id=discussion_owner,
            title="Fictional morning routine",
            action_prompt="Read the plan",
            recurrence=spec.model_dump(mode="json"),
            user_timezone="UTC",
            next_trigger_at=NOW + timedelta(days=1),
            is_enabled=True,
            status="active",
        )
        db.add(row)
        await db.flush()
        identifier = row.id
        await db.commit()
    result = await ScheduledActionDiscussionSource().read(
        read_request(discussion_owner, SourceKey.SCHEDULED_ACTIONS)
    )
    assert result.total == 1 and result.items[0].assertion == "planned"
    assert result.items[0].recurrence_spec == spec
    assert result.items[0].occurred_at is None
    async with AsyncSession(async_engine) as db:
        same = await db.get(ScheduledAction, identifier)
        assert same is not None and same.execution_count == 0 and same.status == "active"


async def test_workboard_keeps_owned_and_assigned_tickets_and_no_execution_internals(
    async_engine: AsyncEngine,
    discussion_owner: UUID,
    committed_user_ids: list[UUID],
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "workboard_enabled", True)
    other = uuid4()
    async with AsyncSession(async_engine) as db:
        db.add(
            User(
                id=other,
                email=f"discussion-peer-{other}@example.test",
                full_name="Fictional peer",
                is_active=True,
            )
        )
        await db.flush()
        committed_user_ids.append(other)
        db.add_all(
            [
                WorkboardTicket(
                    owner_user_id=discussion_owner,
                    title="Owned",
                    assignee_kind="lia",
                    assignee_user_id=discussion_owner,
                    last_run_error="Private executor detail",
                ),
                WorkboardTicket(
                    owner_user_id=other,
                    title="Assigned to me",
                    assignee_kind="human",
                    assignee_user_id=discussion_owner,
                ),
                WorkboardTicket(
                    owner_user_id=other,
                    title="Not visible",
                    assignee_kind="human",
                    assignee_user_id=other,
                ),
            ]
        )
        await db.commit()
    result = await WorkboardDiscussionSource().read(
        read_request(discussion_owner, SourceKey.WORKBOARD)
    )
    assert result.total == 2 and len(result.items) == 2
    assert "Not visible" not in result.model_dump_json()
    assert "Private executor detail" not in result.model_dump_json()
    assert all(item.assertion == "planned" for item in result.items)
