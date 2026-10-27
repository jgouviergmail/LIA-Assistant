"""Raw native tools, durable HITL, editor replacement, replay and addressed refresh."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application.command_repository import get_command, matches_command
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_editing import rebuild_application_draft
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.services import draft_executor
from src.domains.agents.tools import application_habit_action_tools
from src.domains.habits.models import UserHabit
from src.domains.habits.repository import HabitsRepository
from src.domains.users.models import User
from tests.helpers.runtime_context import make_tool_runtime
from tests.integration.application_runtime_context import installed_runtime_context

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("agent_registry")]


@pytest.mark.parametrize("operation", ["status", "delete"])
@pytest.mark.parametrize("scenario", ["confirmed", "no_confirmation", "edit"])
async def test_habit_management_real_native_flow(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    scenario: str,
) -> None:
    monkeypatch.setattr(settings, "habits_enabled", True)
    owner = test_user.id
    rows = [
        UserHabit(
            user_id=owner,
            kind="recurring_request",
            key=key,
            status="active",
            payload={"version": 1},
            last_observed_at=datetime.now(UTC),
        )
        for key in ("email", "calendar")
    ]
    async_session.add_all(rows)
    await async_session.commit()
    first_id, second_id = (row.id for row in rows)

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        try:
            yield async_session
            await async_session.commit()
        except BaseException:
            await async_session.rollback()
            raise

    for module in ["command_service", "draft_execution", "habit_editing"]:
        monkeypatch.setattr(f"src.domains.agents.application.{module}.get_db_context", session)
    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", session)
    monkeypatch.setattr(application_habit_action_tools, "get_db_context", session)
    tool = (
        application_habit_action_tools.set_lia_habit_status_tool
        if operation == "status"
        else application_habit_action_tools.delete_lia_habit_tool
    )
    request = {"habit_id": str(first_id), **({"status": "paused"} if operation == "status" else {})}
    queue: asyncio.Queue[object] = asyncio.Queue()
    with installed_runtime_context(user_id=owner, deps=object(), side_channel_queue=queue):
        proposal = await tool.coroutine(
            request=request, runtime=make_tool_runtime(user_id=owner, store=InMemoryStore())
        )
        assert proposal.success and proposal.metadata["requires_confirmation"]
        item = next(iter(proposal.registry_updates.values()))
        draft = ApplicationActionDraftContent.model_validate(item.payload["content"])
        assert (await HabitsRepository(async_session).get_owned(first_id, owner)).status == "active"
        if scenario == "no_confirmation":
            with pytest.raises(CommandRejected, match="CONFIRMATION_MISSING"):
                await execute_application_action_draft(
                    draft.model_dump(mode="json"), owner, object()
                )
            assert queue.empty()
            return
        if scenario == "edit":
            old = draft
            revised = {
                "habit_id": str(second_id),
                **({"status": "blocked"} if operation == "status" else {}),
            }
            draft = ApplicationActionDraftContent.model_validate(
                await rebuild_application_draft(draft.model_dump(mode="json"), {"intent": revised})
            )
            record = await get_command(async_session, draft.command_id, owner)
            assert (
                record is not None
                and matches_command(record, draft, item.id)
                and not matches_command(record, old, item.id)
            )
        approved = {
            "draft_id": item.id,
            "draft_type": "application_action",
            "draft_content": draft.model_dump(mode="json"),
        }
        with patch.dict(draft_executor.EXECUTOR_REGISTRY):
            draft_executor.register_executor("application_action", execute_application_action_draft)
            result = await draft_executor._execute_confirmed_draft(
                approved,
                {"configurable": {"thread_id": "habit-action-flow"}},
                "habit-action-flow",
                "fr",
            )
        assert result.success, result.to_agent_result()
        with (
            patch.dict(draft_executor.EXECUTOR_REGISTRY),
            patch(
                "src.domains.agents.application.habit_actions.change_managed_habit",
                side_effect=AssertionError("Replay must not mutate"),
            ) as write,
        ):
            draft_executor.register_executor("application_action", execute_application_action_draft)
            replay = await draft_executor._execute_confirmed_draft(
                approved,
                {"configurable": {"thread_id": "habit-action-flow"}},
                "habit-action-flow",
                "fr",
            )
        assert replay.success and replay.result_data == result.result_data
        write.assert_not_awaited()
        changed_id = second_id if scenario == "edit" else first_id
        changed = await HabitsRepository(async_session).get_owned(changed_id, owner)
        assert (
            changed is None
            if operation == "delete"
            else changed.status == ("blocked" if scenario == "edit" else "paused")
        )
        preserved = await HabitsRepository(async_session).get_owned(
            first_id if scenario == "edit" else second_id, owner
        )
        assert preserved is not None and preserved.status == "active"
        changes = [queue.get_nowait() for _ in range(queue.qsize())]
        hints = [event for event in changes if event.type == "application_state_changed"]
        assert len(hints) == 1 and hints[0].metadata["change"]["resources"] == ["habits"]
