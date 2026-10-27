"""The actual registered tool and durable HITL dispatch retain one paid generation."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage
from langgraph.store.memory import InMemoryStore
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_editing import rebuild_application_draft
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.services import draft_executor
from src.domains.agents.tools import application_psyche_tools
from src.domains.psyche.models import PsycheState
from tests.helpers.runtime_context import make_tool_runtime
from tests.integration.application_runtime_context import installed_runtime_context

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("agent_registry")]


@pytest.mark.parametrize("scenario", ["confirmed", "no_confirmation", "edit"])
async def test_summary_real_tool_confirmation_and_edit(
    async_session, test_user, monkeypatch, scenario
):
    monkeypatch.setattr(settings, "psyche_enabled", True)
    owner = test_user.id
    await async_session.commit()
    model = AsyncMock(return_value=AIMessage(content="LIA is curious."))
    monkeypatch.setattr("src.infrastructure.llm.get_llm", lambda *args: MagicMock())
    monkeypatch.setattr("src.infrastructure.llm.invoke_helpers.invoke_with_instrumentation", model)

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        try:
            yield async_session
            await async_session.commit()
        except BaseException:
            await async_session.rollback()
            raise

    for module in ("command_service", "draft_execution", "psyche_summary_editing"):
        monkeypatch.setattr(f"src.domains.agents.application.{module}.get_db_context", session)
    monkeypatch.setattr(application_psyche_tools, "get_db_context", session)
    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", session)
    queue: asyncio.Queue[object] = asyncio.Queue()
    with installed_runtime_context(user_id=owner, deps=object(), side_channel_queue=queue):
        proposal = await application_psyche_tools.generate_lia_psyche_summary_tool.coroutine(
            request={"scope": "current_account"},
            runtime=make_tool_runtime(user_id=owner, store=InMemoryStore()),
        )
        assert proposal.success and proposal.metadata["requires_confirmation"]
        item = next(iter(proposal.registry_updates.values()))
        draft = ApplicationActionDraftContent.model_validate(item.payload["content"])
        model.assert_not_called()
        assert (
            await async_session.scalar(select(PsycheState).where(PsycheState.user_id == owner))
            is None
        )
        if scenario == "no_confirmation":
            with pytest.raises(CommandRejected, match="CONFIRMATION_MISSING"):
                await execute_application_action_draft(
                    draft.model_dump(mode="json"), owner, object()
                )
            return
        if scenario == "edit":
            revised = await rebuild_application_draft(
                draft.model_dump(mode="json"), {"intent": {"scope": "current_account"}}
            )
            draft = ApplicationActionDraftContent.model_validate(revised)
            assert (
                draft.command_id == item.payload["content"]["command_id"]
                or str(draft.command_id) == item.payload["content"]["command_id"]
            )
        with patch.dict(draft_executor.EXECUTOR_REGISTRY):
            draft_executor.register_executor("application_action", execute_application_action_draft)
            result = await draft_executor._execute_confirmed_draft(
                {
                    "draft_id": item.id,
                    "draft_type": "application_action",
                    "draft_content": draft.model_dump(mode="json"),
                },
                {"configurable": {"thread_id": "psyche-summary-flow"}},
                "psyche-summary-flow",
                "fr",
            )
        assert result.success, result.to_agent_result()
        assert model.await_count == 1
        assert "LIA is curious." in str(result.to_agent_result())
        changes = [
            event
            for event in (queue.get_nowait() for _ in range(queue.qsize()))
            if event.type == "application_state_changed"
        ]
        assert len(changes) == 1 and changes[0].metadata["change"]["resources"] == ["psyche"]
