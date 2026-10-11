"""Real deletion effects require native confirmation, fresh authority and a known ACK."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.reminder_removal_schemas import ReminderDeleteRequest
from src.domains.agents.effects.runtime import ClaimTicket
from src.domains.agents.services import draft_executor
from src.domains.agents.tools.application_reminder_tools import delete_lia_reminder_tool
from src.domains.agents.tools.reminder_tools import cancel_reminder_tool
from src.domains.reminders.models import Reminder
from src.domains.reminders.schemas import ReminderCreate
from src.domains.reminders.service import ReminderService
from src.domains.users.models import User
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


async def create_reminder(db: AsyncSession, actor_id: UUID) -> UUID:
    row = await ReminderService(db).create_reminder(
        actor_id,
        ReminderCreate(
            content="Approved deletion",
            original_message="Private original",
            trigger_at=datetime.now(UTC) + timedelta(days=2),
        ),
        "UTC",
    )
    identity = row.id
    await db.commit()
    return identity


@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize("enabled", [False, True])
async def test_both_deletion_entries_are_proposals_and_obey_the_switch(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    legacy: bool,
    enabled: bool,
) -> None:
    actor_id = test_user.id
    identity = await create_reminder(async_session, actor_id)
    monkeypatch.setattr(settings, "application_tools_enabled", enabled)

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session

    with (
        installed_runtime_context(user_id=actor_id, language="fr"),
        patch("src.domains.agents.tools.application_reminder_tools.get_db_context", session),
    ):
        runtime = make_tool_runtime(user_id=actor_id, store=InMemoryStore())
        result = (
            await cancel_reminder_tool.coroutine(reminder_identifier="next", runtime=runtime)
            if legacy
            else await delete_lia_reminder_tool.coroutine(
                selection=ReminderDeleteRequest(reminder_id=identity), runtime=runtime
            )
        )
    assert result.success is enabled
    assert await async_session.get(Reminder, identity) is not None
    if enabled:
        assert result.metadata["requires_confirmation"]
    else:
        assert result.error_code == "CAPABILITY_DISABLED"


@pytest.mark.parametrize("intervention", ["none", "writer_off", "commit_unknown"])
async def test_native_deletion_requires_exact_hitl_and_reports_only_committed_effects(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    intervention: str,
) -> None:
    actor_id = test_user.id
    identity = await create_reminder(async_session, actor_id)
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    if intervention != "none":
        source_cancel = ReminderService.cancel_reminder

        async def alter_after_delete(
            service: ReminderService, target: UUID, owner: UUID
        ) -> Reminder:
            deleted = await source_cancel(service, target, owner)
            if intervention == "writer_off":
                monkeypatch.setattr(settings, "application_tools_enabled", False)
            else:
                source_commit = async_session.commit

                async def lose_ack() -> None:
                    await source_commit()
                    monkeypatch.setattr(async_session, "commit", source_commit)
                    raise SQLAlchemyError("simulated lost commit acknowledgement")

                monkeypatch.setattr(async_session, "commit", lose_ack)
            return deleted

        monkeypatch.setattr(ReminderService, "cancel_reminder", alter_after_delete)

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        try:
            yield async_session
            await async_session.commit()
        except Exception:
            await async_session.rollback()
            raise

    ledger = AsyncMock()
    ledger.claim.return_value = ClaimTicket(uuid4(), uuid4(), None)
    queue: asyncio.Queue[object] = asyncio.Queue()
    with (
        installed_runtime_context(
            user_id=actor_id, language="fr", deps=object(), side_channel_queue=queue
        ),
        patch("src.domains.agents.tools.application_reminder_tools.get_db_context", session),
        patch("src.domains.agents.application.command_service.get_db_context", session),
        patch("src.domains.agents.application.draft_execution.get_db_context", session),
        patch("src.domains.agents.effects.runtime._LEDGER", ledger),
        patch.dict(draft_executor.EXECUTOR_REGISTRY),
    ):
        proposal = await delete_lia_reminder_tool.coroutine(
            selection=ReminderDeleteRequest(reminder_id=identity),
            runtime=make_tool_runtime(user_id=actor_id, store=InMemoryStore()),
        )
        assert proposal.success and proposal.metadata["requires_confirmation"]
        item = next(iter(proposal.registry_updates.values()))
        content = item.payload["content"]
        with pytest.raises(CommandRejected, match="CONFIRMATION_MISSING"):
            await execute_application_action_draft(content, actor_id, object())
        assert await async_session.get(Reminder, identity) is not None
        draft_executor.register_executor("application_action", execute_application_action_draft)
        result = await draft_executor._execute_confirmed_draft(
            {"draft_id": item.id, "draft_type": "application_action", "draft_content": content},
            {"configurable": {"thread_id": "reminder-deletion"}},
            "reminder-deletion",
            "fr",
        )
        assert result.success is (intervention == "none")
        assert (await async_session.get(Reminder, identity) is not None) is (
            intervention == "writer_off"
        )
        if intervention != "none":
            assert result.error == (
                "COMPLETION_UNKNOWN" if intervention == "commit_unknown" else "CAPABILITY_DISABLED"
            )
        assert "Private original" not in str(result.result_data)
        changes = [queue.get_nowait() for _ in range(queue.qsize())]
        changes = [event for event in changes if event.type == "application_state_changed"]
        assert len(changes) == int(intervention == "none")
        if changes:
            assert changes[0].metadata["change"]["resources"] == ["reminders"]
