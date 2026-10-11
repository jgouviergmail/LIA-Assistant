"""Actual deletion proposal, approval, refresh and replay preserve exact human consent."""

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
from src.domains.workboard.models import WorkboardTicket
from src.domains.workboard.schemas import TicketCreate
from src.domains.workboard.service import WorkboardService
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario", ["confirmed", "no_confirmation", "refresh", "replay", "retarget"]
)
async def test_delete_tool_requires_exact_human_confirmation(
    async_session, test_user, monkeypatch, scenario
):
    monkeypatch.setattr(settings, "workboard_enabled", True)
    service = WorkboardService(async_session)
    ticket = await service.create(test_user, TicketCreate(title="Unique deletion target"))
    other = await service.create(test_user, TicketCreate(title="Unconfirmed other target"))
    await async_session.commit()

    @asynccontextmanager
    async def session():
        try:
            yield async_session
            await async_session.commit()
        except BaseException:
            await async_session.rollback()
            raise

    for module in ("command_service", "draft_execution", "workboard_delete_editing"):
        monkeypatch.setattr(f"src.domains.agents.application.{module}.get_db_context", session)
    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", session)
    monkeypatch.setattr("src.domains.agents.tools.workboard_delete_tool.get_db_context", session)
    queue = asyncio.Queue()
    with installed_runtime_context(user_id=test_user.id, deps=object(), side_channel_queue=queue):
        proposal = await workboard_tools.delete_ticket_tool.coroutine(
            ticket="Unique deletion target",
            runtime=make_tool_runtime(user_id=test_user.id, store=InMemoryStore()),
        )
        assert (
            proposal.success and proposal.metadata["requires_confirmation"]
        ), proposal.model_dump()
        assert proposal.metadata["draft_type"] == "application_action"
        assert await async_session.scalar(select(func.count(WorkboardTicket.id))) == 2
        item = next(iter(proposal.registry_updates.values()))
        draft = ApplicationActionDraftContent.model_validate(item.payload["content"])
        if scenario == "no_confirmation":
            with pytest.raises(CommandRejected, match="CONFIRMATION_MISSING"):
                await execute_application_action_draft(
                    draft.model_dump(mode="json"), test_user.id, object()
                )
            assert await async_session.get(WorkboardTicket, ticket.id) is not None
            return
        if scenario == "retarget":
            with pytest.raises(CommandRejected, match="INVALID_INPUT"):
                await rebuild_application_draft(
                    draft.model_dump(mode="json"), {"intent": {"ticket_id": str(other.id)}}
                )
            assert await async_session.scalar(select(func.count(WorkboardTicket.id))) == 2
            return
        if scenario == "refresh":
            await service.create(
                test_user, TicketCreate(title="New named child", parent_id=ticket.id)
            )
            await async_session.commit()
            draft = ApplicationActionDraftContent.model_validate(
                await rebuild_application_draft(
                    draft.model_dump(mode="json"), {"intent": {"ticket_id": str(ticket.id)}}
                )
            )
            assert draft.after["workboard_delete"]["tickets"] == 2
            assert "New named child" in str(draft.after)
        with patch.dict(draft_executor.EXECUTOR_REGISTRY):
            draft_executor.register_executor("application_action", execute_application_action_draft)
            invocation = {
                "draft_id": item.id,
                "draft_type": "application_action",
                "draft_content": draft.model_dump(mode="json"),
            }
            result = await draft_executor._execute_confirmed_draft(
                invocation, {"configurable": {"thread_id": "delete-flow"}}, "delete-flow", "fr"
            )
            assert result.success, result.to_agent_result()
            if scenario == "replay":
                repeated = await draft_executor._execute_confirmed_draft(
                    invocation, {"configurable": {"thread_id": "delete-flow"}}, "delete-flow", "fr"
                )
                assert repeated.success and repeated.result_data == result.result_data
        assert await async_session.scalar(select(func.count(WorkboardTicket.id))) == 1
        assert (
            await async_session.get(WorkboardTicket, other.id, populate_existing=True) is not None
        )
        changes = [
            event
            for event in (queue.get_nowait() for _ in range(queue.qsize()))
            if event.type == "application_state_changed"
        ]
        assert len(changes) == 1 and changes[0].metadata["change"]["resources"] == ["workboard"]


async def test_legacy_delete_card_cannot_bypass_native_consent(
    async_session, test_user, monkeypatch
):
    monkeypatch.setattr(settings, "workboard_enabled", True)
    ticket = await WorkboardService(async_session).create(
        test_user, TicketCreate(title="Legacy target")
    )
    await async_session.commit()

    @asynccontextmanager
    async def session():
        yield async_session

    monkeypatch.setattr(workboard_tools, "get_db_context", session)
    result = await workboard_tools.execute_ticket_delete_draft(
        {"ticket_id": str(ticket.id), "title": ticket.title, "children": 0}, test_user.id, object()
    )
    assert result["success"] is False and result["error"] == "STALE_STATE"
    assert await async_session.get(WorkboardTicket, ticket.id, populate_existing=True) is not None
