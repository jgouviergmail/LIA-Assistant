"""Personal MCP state requires explicit consent and a current complete row witness."""

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
from src.domains.agents.services import draft_executor
from src.domains.agents.tools import application_personal_mcp_tools
from src.domains.user_mcp.models import UserMCPServer
from src.domains.user_mcp.personal_state import observe_personal_mcp_state, set_personal_mcp_state
from src.domains.user_mcp.service import UserMCPServerService
from src.infrastructure.mcp.personal_state_gateway import (
    PersonalMCPStateGateway,
    configure_personal_mcp_state,
)
from tests.helpers.runtime_context import make_tool_runtime
from tests.integration.application_runtime_context import installed_runtime_context
from tests.integration.domains.skills.test_per_account_skill_names import _user

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("agent_registry")]


@pytest.mark.parametrize("mode", ["pipeline", "react"])
@pytest.mark.parametrize(
    "scenario",
    [
        "disable",
        "enable",
        "noop",
        "foreign",
        "stale",
        "private_change",
        "off",
        "late_revocation",
        "expired",
        "tamper",
        "no_confirmation",
        "lost_ack",
    ],
)
async def test_personal_mcp_state_has_one_exact_confirmation_and_owned_refresh(
    async_session, test_user, monkeypatch, mode, scenario
):
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "mcp_enabled", True)
    monkeypatch.setattr(settings, "mcp_user_enabled", True)
    owner = test_user.id
    foreign = await _user(async_session)
    row = UserMCPServer(
        user_id=foreign if scenario == "foreign" else owner,
        name="my-server",
        url="https://example.com/private?token=private",
        is_enabled=scenario != "enable",
    )
    async_session.add(row)
    await async_session.commit()
    server_id = row.id
    initial = row.is_enabled
    desired = scenario in {"enable", "noop"}

    async def disconnect_callback(*args):
        if scenario == "late_revocation":
            monkeypatch.setattr(settings, "application_tools_enabled", False)
        if scenario == "expired":

            class ExpiredClock:
                @staticmethod
                def now(tz):
                    return draft.expires_at

            monkeypatch.setattr(
                "src.domains.agents.application.personal_mcp_execution.datetime", ExpiredClock
            )

    disconnect = AsyncMock(side_effect=disconnect_callback)
    monkeypatch.setattr(UserMCPServerService, "_disconnect_from_pool", disconnect)
    previous = configure_personal_mcp_state(
        PersonalMCPStateGateway(observe_personal_mcp_state, set_personal_mcp_state)
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
            proposal = await application_personal_mcp_tools.set_lia_personal_mcp_server_enabled_tool.coroutine(
                request={"server_id": str(server_id), "enabled": desired},
                runtime=make_tool_runtime(
                    user_id=owner,
                    execution_mode=mode,
                    store=InMemoryStore(),
                    side_channel_queue=events,
                ),
            )
            if scenario == "foreign":
                assert not proposal.success and proposal.error_code == "NOT_FOUND_OR_UNAUTHORIZED"
                assert not disconnect.called
                return
            assert proposal.success and proposal.metadata["requires_confirmation"]
            assert "private" not in str(proposal.structured_data)
            item = next(iter(proposal.registry_updates.values()))
            draft = ApplicationActionDraftContent.model_validate(item.payload["content"])
            assert set(draft.after["personal_mcp_state"]) == {
                "id",
                "name",
                "endpoint_host",
                "plugin_id",
                "is_enabled",
            }
            assert row.is_enabled == initial and not disconnect.called
            if scenario == "no_confirmation":
                with pytest.raises(CommandRejected, match="CONFIRMATION_MISSING"):
                    await execute_application_action_draft(
                        draft.model_dump(mode="json"), owner, object()
                    )
                assert row.is_enabled == initial
                return
            if scenario == "stale":
                row.timeout_seconds += 1
                await async_session.commit()
            if scenario == "private_change":
                row.extra_headers = {"X-Fixed": "private-new-value"}
                await async_session.commit()
            if scenario == "off":
                monkeypatch.setattr(settings, "application_tools_enabled", False)
            if scenario == "lost_ack":
                original_commit = async_session.commit
                failed_ack = False

                async def lost_ack():
                    nonlocal failed_ack
                    fail_this_commit = not failed_ack and row.is_enabled == desired
                    await original_commit()
                    if fail_this_commit:
                        failed_ack = True
                        raise OSError("private connection detail")

                monkeypatch.setattr(async_session, "commit", lost_ack)
            with patch.dict(draft_executor.EXECUTOR_REGISTRY):
                draft_executor.register_executor(
                    "application_action", execute_application_action_draft
                )
                content = draft.model_dump(mode="json")
                if scenario == "tamper":
                    content["after"]["personal_mcp_state"]["is_enabled"] = not desired
                result = await draft_executor._execute_confirmed_draft(
                    {
                        "draft_id": item.id,
                        "draft_type": "application_action",
                        "draft_content": content,
                    },
                    {"configurable": {"thread_id": "personal-mcp-state"}},
                    "personal-mcp-state",
                    "fr",
                )
            assert result.success == (scenario in {"disable", "enable", "noop"})
            assert "private connection detail" not in str(result.result_data)
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
                        {"configurable": {"thread_id": "personal-mcp-state"}},
                        "personal-mcp-state",
                        "fr",
                    )
                assert disconnect.call_count == previous_disconnects
            saved = await async_session.scalar(
                select(UserMCPServer.is_enabled).where(UserMCPServer.id == server_id)
            )
            assert saved == (
                desired if scenario in {"disable", "enable", "noop", "lost_ack"} else initial
            )
            changes = []
            while not events.empty():
                event = events.get_nowait()
                if event.type == "application_state_changed":
                    changes.append(event)
            assert len(changes) == int(result.success and scenario != "noop")
            if changes:
                assert changes[0].metadata["change"]["resources"] == ["user_mcp"]
            assert disconnect.call_count == int(
                scenario in {"disable", "lost_ack", "late_revocation", "expired"}
            )
    finally:
        configure_personal_mcp_state(previous)
