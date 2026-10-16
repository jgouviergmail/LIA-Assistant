"""Real SQL confirmation for shared MCP personal preferences and current-state conflicts."""

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage
from langgraph.store.memory import InMemoryStore
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application.command_repository import get_command, matches_command
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.effects.runtime import ClaimTicket
from src.domains.agents.services import draft_executor
from src.domains.agents.services.hitl.draft_modifier import DraftModificationService
from src.domains.agents.tools.application_shared_mcp_tools import (
    get_lia_shared_mcp_preferences_tool,
    update_lia_shared_mcp_preferences_tool,
)
from src.domains.agents.tools.react_tool_wrapper import extract_data_for_llm
from src.domains.user_mcp import shared_preference_commands as owner
from src.domains.user_mcp.admin_router import toggle_admin_server
from src.domains.users.models import User
from src.infrastructure.mcp.preferences_gateway import (
    SharedMCPPreferencesGateway,
    configure_shared_mcp_preferences,
)
from src.infrastructure.mcp.schemas import MCPDiscoveredTool
from tests.helpers.draft_refusals import draft_refusal_code
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


async def test_native_read_pages_remain_complete_under_the_model_budget(
    async_session: AsyncSession,
    test_user: User,
    shared_manager: MagicMock,
) -> None:
    shared_manager.discovered_tools.update({"another": [], "last": []})
    test_user.admin_mcp_disabled_servers = ["last"]
    await async_session.commit()

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session
        await async_session.commit()

    with patch("src.domains.agents.tools.application_shared_mcp_tools.get_db_context", session):
        output = await get_lia_shared_mcp_preferences_tool.coroutine(
            query={"limit": 3},
            runtime=make_tool_runtime(user_id=test_user.id, store=InMemoryStore()),
        )
        assert output.success
        projected = json.loads(extract_data_for_llm(output, budget_tokens=1))
        assert len(projected["servers"]) == 1
        assert projected["next_cursor"] == "another"
        remaining = await get_lia_shared_mcp_preferences_tool.coroutine(
            query={"after_key": projected["next_cursor"]},
            runtime=make_tool_runtime(user_id=test_user.id, store=InMemoryStore()),
        )
    assert [value["server_key"] for value in remaining.structured_data["servers"]] == [
        "last",
        "shared",
    ]
    assert remaining.structured_data["servers"][0]["enabled_for_user"] is False
    assert output.structured_data["next_cursor"] is None
    assert "catalogue_digest" not in str(output.structured_data)


@pytest.fixture
def shared_manager(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "mcp_enabled", True)
    manager = MagicMock()
    manager.discovered_tools = {
        "shared": [
            MCPDiscoveredTool(
                server_name="shared",
                tool_name="read",
                description="Facts",
                input_schema={"type": "object", "properties": {}},
            )
        ]
    }
    monkeypatch.setattr(owner.client_manager, "get_mcp_client_manager", lambda: manager)
    previous = configure_shared_mcp_preferences(
        SharedMCPPreferencesGateway(owner.read_shared_mcp_preferences, owner.set_shared_mcp_enabled)
    )
    try:
        yield manager
    finally:
        configure_shared_mcp_preferences(previous)


@pytest.mark.parametrize("intervention", ["none", "manual", "platform_off", "mcp_off", "catalogue"])
async def test_confirmation_uses_the_http_owner_and_refuses_stale_or_disabled_authority(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    shared_manager: MagicMock,
    intervention: str,
) -> None:
    test_user.admin_mcp_disabled_servers = ["unrelated"]
    await async_session.commit()
    actor_id = test_user.id

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session
        await async_session.commit()

    ledger = AsyncMock()
    ledger.claim.return_value = ClaimTicket(uuid4(), uuid4(), None)
    queue = asyncio.Queue()
    with (
        patch("src.domains.agents.tools.application_shared_mcp_tools.get_db_context", session),
        patch("src.domains.agents.application.command_service.get_db_context", session),
        patch("src.domains.agents.application.draft_execution.get_db_context", session),
        patch("src.domains.agents.effects.runtime._LEDGER", ledger),
        patch.dict(draft_executor.EXECUTOR_REGISTRY),
        installed_runtime_context(
            user_id=actor_id, language="fr", deps=object(), side_channel_queue=queue
        ),
    ):
        proposal = await update_lia_shared_mcp_preferences_tool.coroutine(
            change={"server_key": "shared", "enabled": False},
            runtime=make_tool_runtime(user_id=actor_id, store=InMemoryStore(), language="fr"),
        )
        assert proposal.success and proposal.metadata["requires_confirmation"]
        await async_session.refresh(test_user)
        assert test_user.admin_mcp_disabled_servers == ["unrelated"]
        item = next(iter(proposal.registry_updates.values()))
        draft_executor.register_executor("application_action", execute_application_action_draft)
        if intervention == "manual":
            await toggle_admin_server("shared", test_user, async_session)
        if intervention == "platform_off":
            monkeypatch.setattr(settings, "application_tools_enabled", False)
        if intervention == "mcp_off":
            monkeypatch.setattr(settings, "mcp_enabled", False)
        if intervention == "catalogue":
            shared_manager.discovered_tools["shared"][0].description = "Changed catalogue"
        outcome = await draft_executor._execute_confirmed_draft(
            {
                "draft_id": item.id,
                "draft_type": "application_action",
                "draft_content": item.payload["content"],
            },
            {"configurable": {"thread_id": "shared-confirmation"}},
            "shared-confirmation",
            "fr",
        )
    await async_session.refresh(test_user)
    assert outcome.success is (intervention == "none")
    if outcome.success:
        assert "catalogue_digest" not in str(outcome.to_agent_result())
        assert "_draft_content" not in outcome.result_data
    assert test_user.admin_mcp_disabled_servers == (
        ["unrelated", "shared"] if intervention in {"none", "manual"} else ["unrelated"]
    )
    if intervention in {"manual", "catalogue"}:
        assert draft_refusal_code(outcome) == "STALE_STATE"
    if intervention in {"platform_off", "mcp_off"}:
        assert draft_refusal_code(outcome) == "CAPABILITY_DISABLED"
        ledger.claim.assert_not_awaited()
    hints = [queue.get_nowait() for _ in range(queue.qsize())]
    hints = [event for event in hints if event.type == "application_state_changed"]
    assert len(hints) == int(intervention == "none")
    if hints:
        assert hints[0].metadata["change"]["resources"] == ["shared_mcp_preferences"]


async def test_modifier_rebuilds_an_exact_personal_choice_without_saving(
    async_session: AsyncSession,
    test_user: User,
    shared_manager: MagicMock,
) -> None:
    actor_id = test_user.id

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session
        await async_session.commit()

    llm = MagicMock()
    llm.ainvoke = AsyncMock(
        return_value=AIMessage(
            content=json.dumps(
                {"intent": {"server_key": "shared", "enabled": True}, "remove_fields": []}
            )
        )
    )
    with (
        installed_runtime_context(user_id=actor_id, language="fr"),
        patch("src.domains.agents.tools.application_shared_mcp_tools.get_db_context", session),
        patch("src.domains.agents.application.command_service.get_db_context", session),
        patch("src.domains.agents.application.draft_editing.get_db_context", session),
        patch("src.domains.agents.services.hitl.draft_modifier.get_llm", return_value=llm),
    ):
        proposal = await update_lia_shared_mcp_preferences_tool.coroutine(
            change={"server_key": "shared", "enabled": False},
            runtime=make_tool_runtime(user_id=actor_id, store=InMemoryStore()),
        )
        item = next(iter(proposal.registry_updates.values()))
        original = ApplicationActionDraftContent.model_validate(item.payload["content"])
        modified = await DraftModificationService().modify(
            original.model_dump(mode="json"),
            "Garde le serveur actif",
            "application_action",
            user_language="fr",
            run_id=item.id,
        )
    revised = ApplicationActionDraftContent.model_validate(modified)
    assert revised.after["shared_mcp_server"]["enabled_for_user"] is True
    assert "catalogue_digest" not in str(llm.ainvoke.call_args.args[0])
    await async_session.refresh(test_user)
    assert "shared" not in (test_user.admin_mcp_disabled_servers or [])
    row = await get_command(async_session, original.command_id, actor_id)
    assert row is not None and matches_command(row, revised, item.id)
    assert not matches_command(row, original, item.id)
