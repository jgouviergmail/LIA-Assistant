"""Native reminder edits use exact HITL and report failures without replay or false success."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.reminder_update_schemas import ReminderUpdateRequest
from src.domains.agents.effects.runtime import ClaimTicket
from src.domains.agents.services import draft_executor
from src.domains.agents.tools.application_reminder_tools import update_lia_reminder_tool
from src.domains.reminders.models import Reminder
from src.domains.reminders.schemas import ReminderCreate, ReminderUpdate
from src.domains.reminders.service import ReminderService
from src.domains.users.models import User
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("intervention", ["none", "writer_off", "commit_unknown", "late_clock"])
async def test_native_update_requires_confirmation_and_rechecks_after_source_io(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    intervention: str,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    test_user.timezone = "UTC"
    actor_id = test_user.id
    row = await ReminderService(async_session).create_reminder(
        actor_id,
        ReminderCreate(
            content="Before",
            original_message="Private original",
            trigger_at=datetime.now(UTC) + timedelta(days=2),
        ),
        "UTC",
    )
    identity = row.id
    await async_session.commit()
    first = datetime.now(UTC) + timedelta(seconds=30)
    source_update = ReminderService.update_reminder

    async def alter_after_update(
        service: ReminderService, target: UUID, owner: UUID, data: ReminderUpdate, timezone: str
    ) -> Reminder:
        updated = await source_update(service, target, owner, data, timezone)
        if intervention == "writer_off":
            monkeypatch.setattr(settings, "application_tools_enabled", False)
        elif intervention == "late_clock":
            monkeypatch.setattr(
                "src.domains.agents.application.reminder_operations.datetime",
                SimpleNamespace(now=lambda zone: first + timedelta(seconds=1)),
            )
        elif intervention == "commit_unknown":
            source_commit = async_session.commit

            async def lose_ack() -> None:
                await source_commit()
                monkeypatch.setattr(async_session, "commit", source_commit)
                raise SQLAlchemyError("simulated lost commit acknowledgement")

            monkeypatch.setattr(async_session, "commit", lose_ack)
        return updated

    monkeypatch.setattr(ReminderService, "update_reminder", alter_after_update)

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
        proposal = await update_lia_reminder_tool.coroutine(
            selection=ReminderUpdateRequest.model_validate(
                {
                    "reminder_id": str(identity),
                    "changes": {"content": "After", "trigger_at": first.isoformat()},
                }
            ),
            runtime=make_tool_runtime(user_id=actor_id, store=InMemoryStore()),
        )
        assert proposal.success and proposal.metadata["requires_confirmation"]
        item = next(iter(proposal.registry_updates.values()))
        content = item.payload["content"]
        with pytest.raises(CommandRejected, match="CONFIRMATION_MISSING"):
            await execute_application_action_draft(content, actor_id, object())
        assert row.content == "Before"
        draft_executor.register_executor("application_action", execute_application_action_draft)
        result = await draft_executor._execute_confirmed_draft(
            {"draft_id": item.id, "draft_type": "application_action", "draft_content": content},
            {"configurable": {"thread_id": "reminder-update"}},
            "reminder-update",
            "fr",
        )
        assert result.success is (intervention == "none")
        stored = await async_session.get(Reminder, identity)
        assert stored is not None and stored.content == (
            "After" if intervention in {"none", "commit_unknown"} else "Before"
        )
        if intervention != "none":
            assert (
                result.error
                == {
                    "writer_off": "CAPABILITY_DISABLED",
                    "commit_unknown": "COMPLETION_UNKNOWN",
                    "late_clock": "STALE_STATE",
                }[intervention]
            )
        assert "Private original" not in str(result.result_data)
        events = [queue.get_nowait() for _ in range(queue.qsize())]
        changes = [event for event in events if event.type == "application_state_changed"]
        assert len(changes) == int(intervention == "none")
        if changes:
            assert changes[0].metadata["change"]["resources"] == ["reminders"]
