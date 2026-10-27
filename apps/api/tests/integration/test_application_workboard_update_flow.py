"""Original update tool reaches the actual HITL, preserves unspecified fields and executes once."""

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
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
from src.domains.workboard.models import WorkboardTicket, WorkboardTicketEvent
from src.domains.workboard.schemas import TicketCreate
from src.domains.workboard.service import WorkboardService
from tests.helpers.runtime_context import make_tool_runtime
from tests.integration.application_runtime_context import installed_runtime_context

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("agent_registry")]


@pytest.mark.parametrize(
    "scenario", ["confirmed", "no_confirmation", "edit", "replay", "retarget", "run_now"]
)
async def test_update_tool_uses_the_common_confirmed_executor(
    async_session, test_user, monkeypatch, scenario
):
    monkeypatch.setattr(settings, "workboard_enabled", True)
    actor_id = test_user.id
    ticket = await WorkboardService(async_session).create(
        test_user,
        TicketCreate(
            title="Unique update target",
            priority="high",
            assignee="lia" if scenario == "run_now" else "me",
            start_at=datetime.now(UTC) + timedelta(days=1),
        ),
    )
    identity = ticket.id
    await async_session.commit()

    @asynccontextmanager
    async def session():
        try:
            yield async_session
            await async_session.commit()
        except BaseException:
            await async_session.rollback()
            raise

    for module in ("command_service", "draft_execution", "workboard_update_editing"):
        monkeypatch.setattr(f"src.domains.agents.application.{module}.get_db_context", session)
    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", session)
    monkeypatch.setattr("src.domains.agents.tools.workboard_update_tool.get_db_context", session)
    queue = asyncio.Queue()
    with installed_runtime_context(user_id=actor_id, deps=object(), side_channel_queue=queue):
        proposal = await workboard_tools.update_ticket_tool.coroutine(
            ticket="Unique update target",
            status=None if scenario == "run_now" else "done",
            run_now=True if scenario == "run_now" else None,
            runtime=make_tool_runtime(user_id=actor_id, store=InMemoryStore()),
        )
        assert (
            proposal.success and proposal.metadata["requires_confirmation"]
        ), proposal.model_dump()
        before = await async_session.get(WorkboardTicket, identity, populate_existing=True)
        assert before.status == "todo" and before.start_at is not None
        item = next(iter(proposal.registry_updates.values()))
        draft = ApplicationActionDraftContent.model_validate(item.payload["content"])
        if scenario == "no_confirmation":
            with pytest.raises(CommandRejected, match="CONFIRMATION_MISSING"):
                await execute_application_action_draft(
                    draft.model_dump(mode="json"), actor_id, object()
                )
            return
        if scenario == "retarget":
            from uuid import uuid4

            with pytest.raises(CommandRejected, match="INVALID_INPUT"):
                await rebuild_application_draft(
                    draft.model_dump(mode="json"),
                    {"intent": {"ticket_id": str(uuid4()), "status": "done"}},
                )
            return
        if scenario == "edit":
            draft = ApplicationActionDraftContent.model_validate(
                await rebuild_application_draft(
                    draft.model_dump(mode="json"),
                    {"intent": {"ticket_id": str(identity), "priority": "urgent"}},
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
                invocation, {"configurable": {"thread_id": "update-flow"}}, "update-flow", "fr"
            )
            assert result.success, result.to_agent_result()
            count = await async_session.scalar(select(func.count(WorkboardTicketEvent.id)))
            if scenario == "replay":
                repeated = await draft_executor._execute_confirmed_draft(
                    invocation, {"configurable": {"thread_id": "update-flow"}}, "update-flow", "fr"
                )
                assert repeated.success and repeated.result_data == result.result_data
                assert (
                    await async_session.scalar(select(func.count(WorkboardTicketEvent.id))) == count
                )
        actual = await async_session.get(WorkboardTicket, identity, populate_existing=True)
        assert actual.title == "Unique update target"
        assert actual.priority == ("urgent" if scenario == "edit" else "high")
        assert actual.status == ("todo" if scenario in {"edit", "run_now"} else "done")
        assert (actual.start_at is None) == (scenario == "run_now")
        changes = [
            event
            for event in (queue.get_nowait() for _ in range(queue.qsize()))
            if event.type == "application_state_changed"
        ]
        assert len(changes) == 1 and changes[0].metadata["change"]["resources"] == ["workboard"]
