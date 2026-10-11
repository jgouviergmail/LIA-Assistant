"""Standalone server deletion never amputates plugins and requires exact consent."""

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy import select

from src.core.config import settings
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.personal_mcp_delete_editing import rebuild_personal_mcp_delete
from src.domains.agents.services import draft_executor
from src.domains.agents.tools import application_personal_mcp_tools
from src.domains.plugins.models import UserPlugin
from src.domains.user_mcp.models import UserMCPServer
from src.domains.user_mcp.personal_delete import delete_personal_mcp_server
from src.domains.user_mcp.personal_state import observe_personal_mcp_state, set_personal_mcp_state
from src.domains.user_mcp.service import UserMCPServerService
from src.infrastructure.mcp.personal_state_gateway import (
    PersonalMCPStateGateway,
    configure_personal_mcp_state,
)
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime
from tests.integration.domains.skills.test_per_account_skill_names import _user

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("mode", ["pipeline", "react"])
@pytest.mark.parametrize(
    "scenario",
    [
        "delete",
        "foreign",
        "plugin_owned",
        "stale",
        "late_revocation",
        "no_confirmation",
        "lost_ack",
    ],
)
async def test_personal_mcp_delete_is_owned_confirmed_group_safe_and_not_replayable(
    async_session, test_user, monkeypatch, mode, scenario
):
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "mcp_enabled", True)
    monkeypatch.setattr(settings, "mcp_user_enabled", True)
    owner = test_user.id
    foreign = await _user(async_session)
    plugin = UserPlugin(user_id=owner, name="group", spec_version="1.0.0", manifest={})
    async_session.add(plugin)
    await async_session.flush()
    row = UserMCPServer(
        user_id=foreign if scenario == "foreign" else owner,
        name="selected-server",
        url="https://example.com/private?token=private",
        plugin_id=plugin.id if scenario == "plugin_owned" else None,
    )
    survivor = UserMCPServer(user_id=owner, name="survivor", url="https://other.example.com")
    async_session.add_all([row, survivor])
    await async_session.commit()
    server_id, survivor_id = row.id, survivor.id

    async def disconnect_callback(*args):
        if scenario == "late_revocation":
            monkeypatch.setattr(settings, "application_tools_enabled", False)

    disconnect = AsyncMock(side_effect=disconnect_callback)
    monkeypatch.setattr(UserMCPServerService, "_disconnect_from_pool", disconnect)
    previous = configure_personal_mcp_state(
        PersonalMCPStateGateway(
            observe_personal_mcp_state, set_personal_mcp_state, remove=delete_personal_mcp_server
        )
    )

    @asynccontextmanager
    async def database():
        try:
            yield async_session
            await async_session.commit()
        except BaseException:
            await async_session.rollback()
            raise

    for module in ["command_service", "draft_execution"]:
        monkeypatch.setattr(f"src.domains.agents.application.{module}.get_db_context", database)
    monkeypatch.setattr(application_personal_mcp_tools, "get_db_context", database)
    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", database)
    events = asyncio.Queue()
    try:
        with installed_runtime_context(
            user_id=owner, deps=object(), execution_mode=mode, side_channel_queue=events
        ):
            proposal = (
                await application_personal_mcp_tools.delete_lia_personal_mcp_server_tool.coroutine(
                    request={"server_id": str(server_id)},
                    runtime=make_tool_runtime(
                        user_id=owner,
                        execution_mode=mode,
                        store=InMemoryStore(),
                        side_channel_queue=events,
                    ),
                )
            )
            if scenario in {"foreign", "plugin_owned"}:
                assert not proposal.success
                assert proposal.error_code == (
                    "NOT_FOUND_OR_UNAUTHORIZED" if scenario == "foreign" else "CONSTRAINT_VIOLATION"
                )
                assert not disconnect.called
                return
            assert proposal.success and proposal.metadata["requires_confirmation"]
            item = next(iter(proposal.registry_updates.values()))
            draft = ApplicationActionDraftContent.model_validate(item.payload["content"])
            with pytest.raises(CommandRejected, match="INVALID_INPUT"):
                await rebuild_personal_mcp_delete(
                    draft, {"intent": {"server_id": str(survivor_id)}}
                )
            assert "private" not in str(draft.before) + str(draft.after)
            assert not disconnect.called
            if scenario == "no_confirmation":
                with pytest.raises(CommandRejected, match="CONFIRMATION_MISSING"):
                    await execute_application_action_draft(
                        draft.model_dump(mode="json"), owner, object()
                    )
                return
            if scenario == "stale":
                row.extra_headers = {"X-Fixed": "private-change"}
                await async_session.commit()
            if scenario == "lost_ack":
                original_commit = async_session.commit
                failed_ack = False

                async def lost_ack():
                    nonlocal failed_ack
                    is_deleted = (
                        await async_session.scalar(
                            select(UserMCPServer.id).where(UserMCPServer.id == server_id)
                        )
                        is None
                    )
                    await original_commit()
                    if is_deleted and not failed_ack:
                        failed_ack = True
                        raise OSError("private SQL detail")

                monkeypatch.setattr(async_session, "commit", lost_ack)
            with patch.dict(draft_executor.EXECUTOR_REGISTRY):
                draft_executor.register_executor(
                    "application_action", execute_application_action_draft
                )
                result = await draft_executor._execute_confirmed_draft(
                    {
                        "draft_id": item.id,
                        "draft_type": "application_action",
                        "draft_content": draft.model_dump(mode="json"),
                    },
                    {"configurable": {"thread_id": "personal-mcp-delete"}},
                    "personal-mcp-delete",
                    "fr",
                )
            assert result.success == (scenario == "delete")
            assert "private SQL detail" not in str(result.result_data)
            if result.success:
                previous_disconnects = disconnect.call_count
                with patch.dict(draft_executor.EXECUTOR_REGISTRY):
                    draft_executor.register_executor(
                        "application_action", execute_application_action_draft
                    )
                    await draft_executor._execute_confirmed_draft(
                        {
                            "draft_id": item.id,
                            "draft_type": "application_action",
                            "draft_content": draft.model_dump(mode="json"),
                        },
                        {"configurable": {"thread_id": "personal-mcp-delete"}},
                        "personal-mcp-delete",
                        "fr",
                    )
                assert disconnect.call_count == previous_disconnects
            exists = await async_session.scalar(
                select(UserMCPServer.id).where(UserMCPServer.id == server_id)
            )
            assert (exists is None) == (scenario in {"delete", "lost_ack"})
            assert (
                await async_session.scalar(
                    select(UserMCPServer.id).where(UserMCPServer.id == survivor_id)
                )
                == survivor_id
            )
            changes = []
            while not events.empty():
                event = events.get_nowait()
                if event.type == "application_state_changed":
                    changes.append(event)
            assert len(changes) == int(result.success)
            if changes:
                assert changes[0].metadata["change"]["resources"] == ["user_mcp"]
            assert disconnect.call_count == int(
                scenario in {"delete", "lost_ack", "late_revocation"}
            )
    finally:
        configure_personal_mcp_state(previous)
