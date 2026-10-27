"""The real tool, durable confirmation, editor and replay preserve exact source reset effects."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_editing import rebuild_application_draft
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.services import draft_executor
from src.domains.agents.tools import application_psyche_reset_tools
from src.domains.psyche.models import PsycheState
from src.domains.users.models import User
from tests.helpers.runtime_context import make_tool_runtime
from tests.integration.application_runtime_context import installed_runtime_context

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("agent_registry")]


@pytest.mark.parametrize("scenario", ["confirmed", "no_confirmation", "edit"])
async def test_native_psyche_reset_requires_exact_confirmation_and_rereads_owned_state(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch, scenario: str
) -> None:
    monkeypatch.setattr(settings, "psyche_enabled", True)
    owner = test_user.id
    row = PsycheState(user_id=owner, mood_pleasure=0.9, relationship_stage="STABLE")
    async_session.add(row)
    await async_session.commit()

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        try:
            yield async_session
            await async_session.commit()
        except BaseException:
            await async_session.rollback()
            raise

    for module in ("command_service", "draft_execution", "psyche_reset_editing"):
        monkeypatch.setattr(f"src.domains.agents.application.{module}.get_db_context", session)
    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", session)
    monkeypatch.setattr(application_psyche_reset_tools, "get_db_context", session)
    queue: asyncio.Queue[object] = asyncio.Queue()
    with installed_runtime_context(user_id=owner, deps=object(), side_channel_queue=queue):
        proposal = await application_psyche_reset_tools.reset_lia_psyche_tool.coroutine(
            request={"level": "soft"},
            runtime=make_tool_runtime(user_id=owner, store=InMemoryStore()),
        )
        assert proposal.success and proposal.metadata["requires_confirmation"]
        item = next(iter(proposal.registry_updates.values()))
        draft = ApplicationActionDraftContent.model_validate(item.payload["content"])
        await async_session.refresh(row)
        assert row.mood_pleasure == 0.9 and queue.empty()
        if scenario == "no_confirmation":
            with pytest.raises(CommandRejected, match="CONFIRMATION_MISSING"):
                await execute_application_action_draft(
                    draft.model_dump(mode="json"), owner, object()
                )
            return
        if scenario == "edit":
            draft = ApplicationActionDraftContent.model_validate(
                await rebuild_application_draft(
                    draft.model_dump(mode="json"), {"intent": {"level": "full"}}
                )
            )
        with patch.dict(draft_executor.EXECUTOR_REGISTRY):
            draft_executor.register_executor("application_action", execute_application_action_draft)
            result = await draft_executor._execute_confirmed_draft(
                {
                    "draft_id": item.id,
                    "draft_type": "application_action",
                    "draft_content": draft.model_dump(mode="json"),
                },
                {"configurable": {"thread_id": "psyche-reset-flow"}},
                "psyche-reset-flow",
                "fr",
            )
        assert result.success, result.to_agent_result()
        await async_session.refresh(row)
        assert row.relationship_stage == ("ORIENTATION" if scenario == "edit" else "STABLE")
        changes = [
            event
            for event in (queue.get_nowait() for _ in range(queue.qsize()))
            if event.type == "application_state_changed"
        ]
        assert len(changes) == 1 and changes[0].metadata["change"]["resources"] == ["psyche"]
