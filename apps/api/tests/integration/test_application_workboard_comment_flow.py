"""Original comment tool, actual native HITL executor, edit and replay share one action."""

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import patch

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
from src.domains.workboard.models import WorkboardComment
from src.domains.workboard.schemas import TicketCreate
from src.domains.workboard.service import WorkboardService
from tests.helpers.runtime_context import make_tool_runtime
from tests.integration.application_runtime_context import installed_runtime_context

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("agent_registry")]


@pytest.mark.parametrize("scenario", ["confirmed", "no_confirmation", "edit", "replay"])
async def test_comment_tool_requires_human_confirmation(
    async_session, test_user, monkeypatch, scenario
):
    monkeypatch.setattr(settings, "workboard_enabled", True)
    ticket = await WorkboardService(async_session).create(
        test_user, TicketCreate(title="Unique comment target")
    )
    await async_session.commit()

    @asynccontextmanager
    async def session():
        try:
            yield async_session
            await async_session.commit()
        except BaseException:
            await async_session.rollback()
            raise

    for module in ("command_service", "draft_execution", "workboard_comment_editing"):
        monkeypatch.setattr(f"src.domains.agents.application.{module}.get_db_context", session)
    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", session)
    monkeypatch.setattr("src.domains.agents.tools.workboard_comment_tool.get_db_context", session)
    queue = asyncio.Queue()
    with installed_runtime_context(user_id=test_user.id, deps=object(), side_channel_queue=queue):
        proposal = await workboard_tools.comment_ticket_tool.coroutine(
            ticket="Unique comment target",
            body="Literal original comment",
            runtime=make_tool_runtime(user_id=test_user.id, store=InMemoryStore()),
        )
        assert (
            proposal.success and proposal.metadata["requires_confirmation"]
        ), proposal.model_dump()
        assert await async_session.scalar(select(func.count(WorkboardComment.id))) == 0
        item = next(iter(proposal.registry_updates.values()))
        draft = ApplicationActionDraftContent.model_validate(item.payload["content"])
        if scenario == "no_confirmation":
            with pytest.raises(CommandRejected, match="CONFIRMATION_MISSING"):
                await execute_application_action_draft(
                    draft.model_dump(mode="json"), test_user.id, object()
                )
            return
        if scenario == "edit":
            draft = ApplicationActionDraftContent.model_validate(
                await rebuild_application_draft(
                    draft.model_dump(mode="json"),
                    {"intent": {"ticket_id": str(ticket.id), "body": "Edited literal comment"}},
                )
            )
        with patch.dict(draft_executor.EXECUTOR_REGISTRY):
            draft_executor.register_executor("application_action", execute_application_action_draft)
            invocation = {
                "draft_id": item.id,
                "draft_type": "application_action",
                "draft_content": draft.model_dump(mode="json"),
            }
            result = await draft_executor._execute_confirmed_draft(
                invocation, {"configurable": {"thread_id": "comment-flow"}}, "comment-flow", "fr"
            )
            assert result.success, result.to_agent_result()
            if scenario == "replay":
                repeated = await draft_executor._execute_confirmed_draft(
                    invocation,
                    {"configurable": {"thread_id": "comment-flow"}},
                    "comment-flow",
                    "fr",
                )
                assert repeated.success and repeated.result_data == result.result_data
        posted = await async_session.scalar(select(WorkboardComment))
        assert posted.body == (
            "Edited literal comment" if scenario == "edit" else "Literal original comment"
        )
        assert await async_session.scalar(select(func.count(WorkboardComment.id))) == 1
        changes = [
            event
            for event in (queue.get_nowait() for _ in range(queue.qsize()))
            if event.type == "application_state_changed"
        ]
        assert len(changes) == 1 and changes[0].metadata["change"]["resources"] == ["workboard"]
