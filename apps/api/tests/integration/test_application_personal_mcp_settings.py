"""Non-secret personal settings reuse original constraints and full owned-row CAS."""

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy import select

from src.core.config import settings
from src.core.security.utils import encrypt_data
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.services import draft_executor
from src.domains.agents.tools import application_personal_mcp_tools
from src.domains.user_mcp.models import UserMCPServer
from src.domains.user_mcp.personal_settings import update_personal_mcp_settings
from src.domains.user_mcp.personal_state import observe_personal_mcp_state, set_personal_mcp_state
from src.domains.user_mcp.service import UserMCPServerService
from src.infrastructure.mcp.personal_state_gateway import (
    PersonalMCPStateGateway,
    configure_personal_mcp_state,
)
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("mode", ["pipeline", "react"])
@pytest.mark.parametrize(
    "scenario",
    ["update", "clear", "noop", "duplicate", "stale", "no_confirmation", "missing_writer"],
)
async def test_confirmed_personal_mcp_settings_are_exact_and_preserve_authentication(
    async_session, test_user, monkeypatch, mode, scenario
):
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "mcp_enabled", True)
    monkeypatch.setattr(settings, "mcp_user_enabled", True)
    owner = test_user.id
    original_credentials = encrypt_data('{"token":"private-token"}')
    row = UserMCPServer(
        user_id=owner,
        name="first",
        url="https://example.com/private?token=private",
        domain_description="Old description",
        timeout_seconds=30,
        iterative_mode=False,
        extra_headers={"X-Fixed": "preserve"},
        auth_type="bearer",
        credentials_encrypted=original_credentials,
    )
    second = UserMCPServer(user_id=owner, name="second", url="https://other.example.com")
    async_session.add_all([row, second])
    await async_session.commit()
    server_id = row.id
    disconnect = AsyncMock()
    monkeypatch.setattr(UserMCPServerService, "_disconnect_from_pool", disconnect)
    previous = configure_personal_mcp_state(
        PersonalMCPStateGateway(
            observe_personal_mcp_state,
            set_personal_mcp_state,
            None if scenario == "missing_writer" else update_personal_mcp_settings,
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
    values = {
        "name": "renamed",
        "domain_description": "New description",
        "timeout_seconds": 60,
        "iterative_mode": True,
    }
    if scenario == "clear":
        values = {"domain_description": None}
    elif scenario == "noop":
        values = {"timeout_seconds": 30}
    elif scenario == "duplicate":
        values = {"name": "second"}
    events = asyncio.Queue()
    try:
        with installed_runtime_context(
            user_id=owner, deps=object(), execution_mode=mode, side_channel_queue=events
        ):
            proposal = await application_personal_mcp_tools.update_lia_personal_mcp_server_settings_tool.coroutine(
                request={"server_id": str(server_id), "patch": values},
                runtime=make_tool_runtime(
                    user_id=owner,
                    execution_mode=mode,
                    store=InMemoryStore(),
                    side_channel_queue=events,
                ),
            )
            if scenario == "missing_writer":
                assert not proposal.success and proposal.error_code == "DEPENDENCY_ERROR"
                assert not proposal.registry_updates and not disconnect.called
                return
            assert proposal.success and proposal.metadata["requires_confirmation"]
            item = next(iter(proposal.registry_updates.values()))
            draft = ApplicationActionDraftContent.model_validate(item.payload["content"])
            assert "private" not in str(draft.before) + str(draft.after)
            assert row.name == "first" and not row.iterative_mode
            if scenario == "no_confirmation":
                with pytest.raises(CommandRejected, match="CONFIRMATION_MISSING"):
                    await execute_application_action_draft(
                        draft.model_dump(mode="json"), owner, object()
                    )
                return
            if scenario == "stale":
                row.extra_headers = {"X-Fixed": "private-changed"}
                await async_session.commit()
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
                    {"configurable": {"thread_id": "personal-mcp-settings"}},
                    "personal-mcp-settings",
                    "fr",
                )
            assert result.success == (scenario in {"update", "clear", "noop"})
            saved = await async_session.scalar(
                select(UserMCPServer)
                .where(UserMCPServer.id == server_id)
                .execution_options(populate_existing=True)
            )
            assert (
                saved.url == "https://example.com/private?token=private"
                and saved.credentials_encrypted == original_credentials
            )
            assert not disconnect.called
            if result.success:
                for field, value in values.items():
                    assert getattr(saved, field) == value
            else:
                assert saved.name == "first" and saved.timeout_seconds == 30
            changes = []
            while not events.empty():
                event = events.get_nowait()
                if event.type == "application_state_changed":
                    changes.append(event)
            assert len(changes) == int(result.success and scenario != "noop")
            if changes:
                assert changes[0].metadata["change"]["resources"] == ["user_mcp"]
    finally:
        configure_personal_mcp_state(previous)
