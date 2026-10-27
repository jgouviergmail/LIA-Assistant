"""Native OAuth disconnect purges tokens only after original explicit HITL."""

import asyncio
import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy import select

from src.core.config import settings
from src.core.security.utils import decrypt_data, encrypt_data
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.services import draft_executor
from src.domains.agents.tools import application_personal_mcp_tools
from src.domains.user_mcp.models import UserMCPServer
from src.domains.user_mcp.personal_oauth_disconnect import disconnect_personal_mcp_oauth
from src.domains.user_mcp.personal_state import observe_personal_mcp_state, set_personal_mcp_state
from src.domains.user_mcp.service import UserMCPServerService
from src.infrastructure.mcp.personal_state_gateway import (
    PersonalMCPStateGateway,
    configure_personal_mcp_state,
)
from tests.helpers.runtime_context import make_tool_runtime
from tests.integration.application_runtime_context import installed_runtime_context

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("agent_registry")]


@pytest.mark.parametrize("mode", ["pipeline", "react"])
@pytest.mark.parametrize(
    "scenario",
    [
        "disconnect",
        "no_confirmation",
        "wrong_auth",
        "changed_credentials",
        "late_revocation",
        "corrupt_credentials",
        "pool_failure",
    ],
)
async def test_oauth_disconnect_is_confirmed_current_and_preserves_client_credentials(
    async_session,
    test_user,
    monkeypatch,
    mode,
    scenario,
):
    for name in ["application_tools_enabled", "mcp_enabled", "mcp_user_enabled"]:
        monkeypatch.setattr(settings, name, True)
    owner = test_user.id
    credentials = {
        "client_id": "public-client",
        "client_secret": "private-secret",
        "access_token": "private-access",
        "refresh_token": "private-refresh",
        "expires_at": 12345,
    }
    row = UserMCPServer(
        user_id=owner,
        name="calendar",
        url="https://example.org/private",
        auth_type="none" if scenario == "wrong_auth" else "oauth2",
        credentials_encrypted=(
            "corrupt-encrypted"
            if scenario == "corrupt_credentials"
            else encrypt_data(json.dumps(credentials))
        ),
    )
    async_session.add(row)
    await async_session.commit()
    server_id = row.id

    async def disconnect(*args, **kwargs):
        assert kwargs["strict"] is True
        if scenario == "late_revocation":
            monkeypatch.setattr(settings, "application_tools_enabled", False)
        if scenario == "pool_failure":
            raise RuntimeError("private cache failure")

    pool_disconnect = AsyncMock(side_effect=disconnect)
    monkeypatch.setattr(UserMCPServerService, "_disconnect_from_pool", pool_disconnect)
    previous = configure_personal_mcp_state(
        PersonalMCPStateGateway(
            observe_personal_mcp_state,
            set_personal_mcp_state,
            oauth_disconnect=disconnect_personal_mcp_oauth,
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
            proposal = await application_personal_mcp_tools.disconnect_lia_personal_mcp_oauth_tool.coroutine(
                request={"server_id": str(server_id)},
                runtime=make_tool_runtime(
                    user_id=owner,
                    execution_mode=mode,
                    store=InMemoryStore(),
                    side_channel_queue=events,
                ),
            )
            if scenario == "wrong_auth":
                assert not proposal.success and not pool_disconnect.called
                return
            assert proposal.success and proposal.metadata["requires_confirmation"]
            item = next(iter(proposal.registry_updates.values()))
            draft = ApplicationActionDraftContent.model_validate(item.payload["content"])
            assert "private" not in str(draft.before) + str(draft.after)
            assert not pool_disconnect.called
            if scenario == "no_confirmation":
                with pytest.raises(CommandRejected, match="CONFIRMATION_MISSING"):
                    await execute_application_action_draft(
                        draft.model_dump(mode="json"), owner, object()
                    )
                return
            if scenario == "changed_credentials":
                credentials["access_token"] = "private-concurrent"
                row.credentials_encrypted = encrypt_data(json.dumps(credentials))
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
                    {"configurable": {"thread_id": "personal-mcp-oauth"}},
                    "personal-mcp-oauth",
                    "fr",
                )
            saved = await async_session.scalar(
                select(UserMCPServer)
                .where(UserMCPServer.id == server_id)
                .execution_options(populate_existing=True)
            )
            assert saved is not None and saved.credentials_encrypted is not None
            assert result.success == (scenario == "disconnect"), result.error
            if scenario == "corrupt_credentials":
                assert (
                    saved.credentials_encrypted == "corrupt-encrypted"
                    and not pool_disconnect.called
                )
            else:
                decoded = json.loads(decrypt_data(saved.credentials_encrypted))
                assert decoded == (
                    {"client_id": "public-client", "client_secret": "private-secret"}
                    if result.success
                    else credentials
                )
            assert saved.status == ("auth_required" if result.success else "active")
            assert pool_disconnect.await_count == int(
                scenario in {"disconnect", "late_revocation", "pool_failure"}
            )
            if result.success:
                assert "private" not in str(result.result_data)
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
                        {"configurable": {"thread_id": "personal-mcp-oauth"}},
                        "personal-mcp-oauth",
                        "fr",
                    )
                assert pool_disconnect.await_count == 1
            changes = []
            while not events.empty():
                event = events.get_nowait()
                if event.type == "application_state_changed":
                    changes.append(event)
            assert len(changes) == int(result.success)
    finally:
        configure_personal_mcp_state(previous)
