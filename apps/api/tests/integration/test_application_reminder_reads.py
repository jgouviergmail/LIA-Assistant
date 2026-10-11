"""Native reminder reads reuse the management projection and hide other accounts."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import ResourceNotFoundError
from src.domains.agents.application.reminder_queries import read_reminders
from src.domains.agents.application.reminder_read_schemas import ReminderRead
from src.domains.agents.tools.application_reminder_tools import get_lia_reminders_tool
from src.domains.agents.tools.reminder_tools import list_reminders_tool
from src.domains.reminders.schemas import ReminderCreate
from src.domains.reminders.service import ReminderService
from src.domains.users.models import User
from tests.helpers.runtime_context import make_tool_runtime

pytestmark = pytest.mark.integration


async def test_management_read_returns_each_pending_reminder_once_and_its_source_schedule(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    source = ReminderService(async_session)
    rows = [
        await source.create_reminder(
            test_user.id,
            ReminderCreate(
                content=f"Reminder {index}",
                original_message="Private raw message",
                trigger_at=datetime.now(UTC) + timedelta(days=2),
            ),
            "Europe/Paris",
        )
        for index in range(7)
    ]
    await async_session.commit()
    first = await read_reminders(async_session, test_user.id, ReminderRead(limit=3))
    assert first.total_available == 7 and first.truncated and len(first.reminders) == 3
    assert first.next_cursor == first.reminders[-1].id
    second = await read_reminders(
        async_session, test_user.id, ReminderRead(limit=3, after_id=first.next_cursor)
    )
    third = await read_reminders(
        async_session, test_user.id, ReminderRead(limit=3, after_id=second.next_cursor)
    )
    assert len(third.reminders) == 1 and not third.truncated and third.next_cursor is None
    assert {item.id for page in (first, second, third) for item in page.reminders} == {
        row.id for row in rows
    }
    assert "Private raw message" not in first.model_dump_json()
    assert all(
        item.recurrence.freq == "once"
        and item.user_timezone == "Europe/Paris"
        and item.schedule_display
        for item in first.reminders
    )


async def test_foreign_reminder_and_processing_state_never_appear_in_pending_listing(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    row = await ReminderService(async_session).create_reminder(
        test_user.id,
        ReminderCreate(
            content="Reminder",
            original_message="Reminder",
            trigger_at=datetime.now(UTC) + timedelta(days=2),
        ),
        "Europe/Paris",
    )
    actor_id, row_id = test_user.id, row.id
    await async_session.commit()
    other = User(email="other-reminder@read.test", hashed_password="test", is_active=True)
    async_session.add(other)
    await async_session.commit()
    with pytest.raises(ResourceNotFoundError):
        await read_reminders(async_session, other.id, ReminderRead(reminder_id=row_id))
    foreign = await read_reminders(async_session, other.id, ReminderRead())
    assert foreign.total_available == 0 and not foreign.reminders
    row.status = "processing"
    await async_session.commit()
    pending = await read_reminders(async_session, actor_id, ReminderRead())
    assert pending.total_available == 0 and not pending.reminders


@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize("disabled", [False, True])
async def test_native_and_legacy_read_refuse_an_operator_withdrawal_after_source_io(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    legacy: bool,
    disabled: bool,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    await ReminderService(async_session).create_reminder(
        test_user.id,
        ReminderCreate(
            content="Reminder",
            original_message="Reminder",
            trigger_at=datetime.now(UTC) + timedelta(days=2),
        ),
        "Europe/Paris",
    )
    await async_session.commit()

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session
        await async_session.commit()

    if legacy:
        original_list = ReminderService.list_pending_for_user

        async def read_then_withdraw(service: ReminderService, user_id):
            result = await original_list(service, user_id)
            if disabled:
                monkeypatch.setattr(settings, "application_tools_enabled", False)
            return result

        monkeypatch.setattr(ReminderService, "list_pending_for_user", read_then_withdraw)
    else:
        from src.domains.reminders.repository import ReminderRepository

        original_page = ReminderRepository.page_pending_by_id

        async def page_then_withdraw(repo: ReminderRepository, user_id, *, after_id, limit):
            result = await original_page(repo, user_id, after_id=after_id, limit=limit)
            if disabled:
                monkeypatch.setattr(settings, "application_tools_enabled", False)
            return result

        monkeypatch.setattr(ReminderRepository, "page_pending_by_id", page_then_withdraw)
    with (
        patch("src.infrastructure.database.session.get_db_context", session),
        patch("src.domains.agents.tools.application_reminder_tools.get_db_context", session),
        patch(
            "src.domains.agents.tools.runtime_helpers.get_user_preferences",
            AsyncMock(return_value=("Europe/Paris", "fr", "fr")),
        ),
    ):
        runtime = make_tool_runtime(user_id=test_user.id, store=InMemoryStore())
        tool = list_reminders_tool if legacy else get_lia_reminders_tool
        result = await tool.coroutine(runtime=runtime)
    assert result.success is (not disabled)
    if disabled:
        assert result.error_code == "CAPABILITY_DISABLED"
        assert not result.registry_updates and not result.structured_data
    elif not legacy:
        assert (
            result.structured_data["returned_count"] == 1
            and result.metadata["application_reminder_cursor"]
        )
