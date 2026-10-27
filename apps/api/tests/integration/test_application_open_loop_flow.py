"""Native raw-Pipeline invocation requires exact durable HITL before source mutation."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application.command_repository import get_command, matches_command
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.open_loop_editing import rebuild_open_loop_draft
from src.domains.agents.services import draft_executor
from src.domains.agents.tools import application_open_loop_action_tools
from src.domains.open_loops.models import OpenLoop
from src.domains.users.models import User
from tests.helpers.runtime_context import make_tool_runtime
from tests.integration.application_runtime_context import installed_runtime_context

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("agent_registry")]


@pytest.mark.parametrize("operation", ["update", "close"])
@pytest.mark.parametrize("scenario", ["confirmed", "no_confirmation", "edit"])
async def test_native_commitment_tool_flow_is_exact_and_single_use(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    scenario: str,
) -> None:
    monkeypatch.setattr(settings, "open_loops_enabled", True)
    actor_id = test_user.id
    row = OpenLoop(
        user_id=actor_id,
        subject="Original commitment",
        direction="user_owes",
        source_ref="private-thread",
    )
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

    for module in ["command_service", "draft_execution", "open_loop_editing"]:
        monkeypatch.setattr(f"src.domains.agents.application.{module}.get_db_context", session)
    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", session)
    monkeypatch.setattr(application_open_loop_action_tools, "get_db_context", session)
    request = {
        "loop_id": str(row.id),
        **(
            {"changes": {"subject": "Confirmed wording"}}
            if operation == "update"
            else {"action": "done"}
        ),
    }
    tool = getattr(application_open_loop_action_tools, f"{operation}_lia_open_loop_tool")
    with installed_runtime_context(user_id=actor_id, deps=object()):
        proposal = await tool.coroutine(
            request=request, runtime=make_tool_runtime(user_id=actor_id, store=InMemoryStore())
        )
        assert proposal.success and proposal.metadata["requires_confirmation"]
        item = next(iter(proposal.registry_updates.values()))
        draft = ApplicationActionDraftContent.model_validate(item.payload["content"])
        await async_session.refresh(row)
        assert row.subject == "Original commitment" and row.status == "open"
        assert "private-thread" not in str(proposal)
        if scenario == "no_confirmation":
            with pytest.raises(CommandRejected, match="CONFIRMATION_MISSING"):
                await execute_application_action_draft(
                    draft.model_dump(mode="json"), actor_id, object()
                )
            return
        if scenario == "edit":
            request = {
                "loop_id": str(row.id),
                **(
                    {"changes": {"subject": "Revised wording"}}
                    if operation == "update"
                    else {"action": "dismissed"}
                ),
            }
            revised = await rebuild_open_loop_draft(draft, {"intent": request})
            saved = await get_command(async_session, draft.command_id, actor_id)
            assert saved is not None and not matches_command(saved, draft, item.id)
            draft = ApplicationActionDraftContent.model_validate(revised)
            assert matches_command(saved, draft, item.id)
        with patch.dict(draft_executor.EXECUTOR_REGISTRY):
            draft_executor.register_executor("application_action", execute_application_action_draft)
            result = await draft_executor._execute_confirmed_draft(
                {
                    "draft_id": item.id,
                    "draft_type": "application_action",
                    "draft_content": draft.model_dump(mode="json"),
                },
                {"configurable": {"thread_id": "open-loop-flow"}},
                "open-loop-flow",
                "fr",
            )
        assert result.success, result.to_agent_result()
        with (
            patch.dict(draft_executor.EXECUTOR_REGISTRY),
            patch(
                "src.domains.agents.application.open_loop_actions.apply_open_loop_change",
                side_effect=AssertionError("A recorded effect must never execute again"),
            ) as source_write,
        ):
            draft_executor.register_executor("application_action", execute_application_action_draft)
            replay = await draft_executor._execute_confirmed_draft(
                {
                    "draft_id": item.id,
                    "draft_type": "application_action",
                    "draft_content": draft.model_dump(mode="json"),
                },
                {"configurable": {"thread_id": "open-loop-flow"}},
                "open-loop-flow",
                "fr",
            )
        assert replay.success and replay.result_data == result.result_data
        source_write.assert_not_awaited()
        await async_session.refresh(row)
        if operation == "update":
            assert row.subject == ("Revised wording" if scenario == "edit" else "Confirmed wording")
        else:
            assert row.status == "closed" and row.closed_reason == (
                "dismissed" if scenario == "edit" else "api"
            )
