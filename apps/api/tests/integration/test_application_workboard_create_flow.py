"""The existing create_ticket_tool now proposes and requires exact, replay-safe HITL."""

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy import func, select

from src.core.config import settings
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_editing import rebuild_application_draft
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.services import draft_executor
from src.domains.agents.tools import workboard_tools
from src.domains.workboard.models import WorkboardTicket
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("scenario", ["confirmed", "no_confirmation", "edit", "replay", "legacy"])
async def test_original_create_tool_human_confirmation(
    async_session, test_user, monkeypatch, scenario
):
    monkeypatch.setattr(settings, "workboard_enabled", True)
    owner = test_user.id

    @asynccontextmanager
    async def session():
        try:
            yield async_session
            await async_session.commit()
        except BaseException:
            await async_session.rollback()
            raise

    for module in ("command_service", "draft_execution", "workboard_create_editing"):
        monkeypatch.setattr(f"src.domains.agents.application.{module}.get_db_context", session)
    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", session)
    monkeypatch.setattr("src.domains.agents.tools.workboard_creation_tool.get_db_context", session)
    monkeypatch.setattr(
        "src.domains.agents.tools.workboard_creation_tool.get_user_preferences",
        AsyncMock(return_value=("Europe/Paris", "fr", "fr-FR")),
    )
    queue = asyncio.Queue()
    with installed_runtime_context(user_id=owner, deps=object(), side_channel_queue=queue):
        args = (
            {"title": "Exact ticket", "due_at": "2026-10-20T12:00:00", "assignee": "LIA"}
            if scenario == "legacy"
            else {
                "request": {
                    "title": "Exact ticket",
                    "description": "Literal brief",
                    "execution_mode": "pipeline",
                }
            }
        )
        proposal = await workboard_tools.create_ticket_tool.coroutine(
            **args, runtime=make_tool_runtime(user_id=owner, store=InMemoryStore())
        )
        assert (
            proposal.success and proposal.metadata["requires_confirmation"]
        ), proposal.model_dump()
        assert await async_session.scalar(select(func.count(WorkboardTicket.id))) == 0
        item = next(iter(proposal.registry_updates.values()))
        draft = ApplicationActionDraftContent.model_validate(item.payload["content"])
        if scenario == "no_confirmation":
            with pytest.raises(CommandRejected, match="CONFIRMATION_MISSING"):
                await execute_application_action_draft(
                    draft.model_dump(mode="json"), owner, object()
                )
            return
        if scenario == "edit":
            old_id = draft.command_id
            draft = ApplicationActionDraftContent.model_validate(
                await rebuild_application_draft(
                    draft.model_dump(mode="json"),
                    {"intent": {"title": "Edited ticket", "execution_mode": "pipeline"}},
                )
            )
            assert draft.command_id == old_id
        with patch.dict(draft_executor.EXECUTOR_REGISTRY):
            draft_executor.register_executor("application_action", execute_application_action_draft)
            invocation = {
                "draft_id": item.id,
                "draft_type": "application_action",
                "draft_content": draft.model_dump(mode="json"),
            }
            result = await draft_executor._execute_confirmed_draft(
                invocation,
                {"configurable": {"thread_id": "workboard-create-flow"}},
                "workboard-create-flow",
                "fr",
            )
            assert result.success, result.to_agent_result()
            if scenario == "replay":
                replay = await draft_executor._execute_confirmed_draft(
                    invocation,
                    {"configurable": {"thread_id": "workboard-create-flow"}},
                    "workboard-create-flow",
                    "fr",
                )
                assert replay.success and replay.result_data == result.result_data
        assert await async_session.scalar(select(func.count(WorkboardTicket.id))) == 1
        row = await async_session.scalar(
            select(WorkboardTicket).where(WorkboardTicket.owner_user_id == owner)
        )
        assert row.title == ("Edited ticket" if scenario == "edit" else "Exact ticket")
        if scenario == "legacy":
            assert row.assignee_kind == "lia" and row.due_at.hour == 10
        else:
            assert row.execution_mode == "pipeline"
        changes = [
            event
            for event in (queue.get_nowait() for _ in range(queue.qsize()))
            if event.type == "application_state_changed"
        ]
        assert len(changes) == 1 and changes[0].metadata["change"]["resources"] == ["workboard"]
