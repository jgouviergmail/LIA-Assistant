"""Actual full-forget tools preserve durable approval and honest post-commit outcomes."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_editing import rebuild_application_draft
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.services import draft_executor
from src.domains.agents.tools import application_habit_action_tools
from src.domains.habits.models import UserHabit
from src.domains.habits.repository import HabitsRepository
from src.domains.users.models import User
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("scenario", ["confirmed", "no_confirmation", "edit", "partial"])
async def test_native_full_forget_flow_is_confirmed_and_partial_cleanup_is_not_success(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch, scenario: str
) -> None:
    monkeypatch.setattr(settings, "habits_enabled", True)
    owner = test_user.id
    row = UserHabit(
        user_id=owner,
        kind="recurring_request",
        key="email",
        status="blocked",
        payload={"version": 1},
        last_observed_at=datetime.now(UTC),
    )
    async_session.add(row)
    await async_session.commit()
    identity = row.id
    cleanup = AsyncMock(return_value=scenario != "partial")
    monkeypatch.setattr("src.domains.habits.forgetting.clear_habit_advisory_state", cleanup)

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        try:
            yield async_session
            await async_session.commit()
        except BaseException:
            await async_session.rollback()
            raise

    for module in ("command_service", "draft_execution", "habit_editing"):
        monkeypatch.setattr(f"src.domains.agents.application.{module}.get_db_context", session)
    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", session)
    monkeypatch.setattr(application_habit_action_tools, "get_db_context", session)
    queue: asyncio.Queue[object] = asyncio.Queue()
    with installed_runtime_context(user_id=owner, deps=object(), side_channel_queue=queue):
        proposal = await application_habit_action_tools.delete_all_lia_habits_tool.coroutine(
            request={"scope": "all_owned"},
            runtime=make_tool_runtime(user_id=owner, store=InMemoryStore()),
        )
        assert proposal.success and proposal.metadata["requires_confirmation"]
        item = next(iter(proposal.registry_updates.values()))
        draft = ApplicationActionDraftContent.model_validate(item.payload["content"])
        assert await HabitsRepository(async_session).get_owned(identity, owner) is not None
        cleanup.assert_not_awaited()
        if scenario == "no_confirmation":
            with pytest.raises(CommandRejected, match="CONFIRMATION_MISSING"):
                await execute_application_action_draft(
                    draft.model_dump(mode="json"), owner, object()
                )
            assert queue.empty()
            return
        if scenario == "edit":
            old_digest = draft.intent["habit_data"]["digest"]
            row.payload = {"version": 2}
            await async_session.commit()
            draft = ApplicationActionDraftContent.model_validate(
                await rebuild_application_draft(
                    draft.model_dump(mode="json"), {"intent": {"scope": "all_owned"}}
                )
            )
            assert draft.intent["habit_data"]["digest"] != old_digest
        with patch.dict(draft_executor.EXECUTOR_REGISTRY):
            draft_executor.register_executor("application_action", execute_application_action_draft)
            result = await draft_executor._execute_confirmed_draft(
                {
                    "draft_id": item.id,
                    "draft_type": "application_action",
                    "draft_content": draft.model_dump(mode="json"),
                },
                {"configurable": {"thread_id": "habit-forget-flow"}},
                "habit-forget-flow",
                "fr",
            )
        assert result.success is (scenario != "partial"), result.to_agent_result()
        assert result.result_data["committed"] is True
        assert result.result_data["values"]["advisory_cleanup_confirmed"] is (scenario != "partial")
        assert await HabitsRepository(async_session).get_owned(identity, owner) is None
        events = [queue.get_nowait() for _ in range(queue.qsize())]
        hints = [event for event in events if event.type == "application_state_changed"]
        assert len(hints) == 1 and hints[0].metadata["change"]["resources"] == ["habits"]
        cleanup.assert_awaited_once_with(owner)
