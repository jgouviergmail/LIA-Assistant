"""Real approval/ledger/session/CAS fences with a controlled OAuth provider boundary."""

import asyncio
import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy.exc import OperationalError

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.core.security.utils import decrypt_data, encrypt_data
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.command_status import read_command_status
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.personal_mcp_oauth_callbacks import (
    check_personal_mcp_oauth_callback,
    stage_personal_mcp_oauth_callback,
)
from src.domains.agents.application.personal_mcp_oauth_service import (
    complete_application_personal_mcp_oauth,
    start_application_personal_mcp_oauth,
)
from src.domains.agents.application.secure_continuation import ContinuationCompletionUnknown
from src.domains.agents.services import draft_executor
from src.domains.agents.tools import application_personal_mcp_tools
from src.domains.user_mcp.models import UserMCPServer
from src.domains.user_mcp.personal_oauth_authorization import save_personal_mcp_oauth
from src.domains.user_mcp.personal_state import observe_personal_mcp_state, set_personal_mcp_state
from src.domains.user_mcp.service import UserMCPServerService
from src.infrastructure.application_sessions import bind_browser_session
from src.infrastructure.cache.redis import get_redis_session
from src.infrastructure.cache.session_store import SessionStore
from src.infrastructure.mcp.personal_oauth_contract import PersonalMCPOAuthStart
from src.infrastructure.mcp.personal_state_gateway import (
    PersonalMCPStateGateway,
    configure_personal_mcp_state,
)
from tests.helpers.runtime_context import make_tool_runtime
from tests.integration.application_runtime_context import installed_runtime_context

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("agent_registry")]


@pytest.mark.parametrize(
    "scenario",
    [
        "saved",
        "unconfirmed",
        "other_browser",
        "changed_before_callback",
        "logout_before_callback",
        "disabled_before_callback",
        "changed_before_save",
        "logout_before_save",
        "disabled_during_save",
        "pending",
        "duplicate",
        "forged_callback",
        "lost_ack",
        "settlement_unavailable",
    ],
)
async def test_oauth_requires_original_approval_and_live_browser(
    async_session, test_user, monkeypatch, scenario
):
    for name in ["application_tools_enabled", "mcp_enabled", "mcp_user_enabled"]:
        monkeypatch.setattr(settings, name, True)
    monkeypatch.setattr(settings, "mcp_user_oauth_callback_base_url", "https://lia.example")
    owner = test_user.id
    row = UserMCPServer(
        user_id=owner, name="OAuth server", url="https://example.org/mcp", auth_type="oauth2"
    )
    async_session.add(row)
    await async_session.commit()
    server_id = row.id
    store = SessionStore(await get_redis_session())
    browser, other = await store.create_session(str(owner)), await store.create_session(str(owner))
    origin = bind_browser_session(owner, browser.session_id)

    @asynccontextmanager
    async def database():
        try:
            yield async_session
            await async_session.commit()
        except BaseException:
            await async_session.rollback()
            raise

    for module in [
        "command_service",
        "draft_execution",
        "secure_continuation",
        "personal_mcp_oauth_callbacks",
    ]:
        monkeypatch.setattr(f"src.domains.agents.application.{module}.get_db_context", database)
    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", database)
    monkeypatch.setattr(application_personal_mcp_tools, "get_db_context", database)
    started = AsyncMock()

    async def starter(db, user_id, selected_id, *, application_command_id, application_check):
        await application_check(selected_id, user_id, application_command_id)
        assert not db.in_transaction(), "No SQL transaction may span provider discovery"
        await started()
        return PersonalMCPOAuthStart(
            authorization_url="https://provider.example/authorize?state=private-state",
            metadata={"token_endpoint": "https://provider.example/token"},
        )

    async def disconnect(service, user_id, selected_id, *, strict=False):
        assert strict
        if scenario == "disabled_during_save":
            monkeypatch.setattr(settings, "application_tools_enabled", False)

    monkeypatch.setattr(UserMCPServerService, "_disconnect_from_pool", disconnect)
    gateway = PersonalMCPStateGateway(
        observe_personal_mcp_state,
        set_personal_mcp_state,
        oauth_start=starter,
        oauth_save=save_personal_mcp_oauth,
    )
    previous = configure_personal_mcp_state(gateway)
    events = asyncio.Queue()
    try:
        with installed_runtime_context(
            user_id=owner, application_origin=origin, deps=object(), side_channel_queue=events
        ):
            proposal = await application_personal_mcp_tools.authorize_lia_personal_mcp_server_tool.coroutine(
                request={"server_id": str(server_id)},
                runtime=make_tool_runtime(
                    user_id=owner,
                    application_origin=origin,
                    side_channel_queue=events,
                    store=InMemoryStore(),
                ),
            )
            assert proposal.success and proposal.metadata["requires_confirmation"]
            item = next(iter(proposal.registry_updates.values()))
            draft = ApplicationActionDraftContent.model_validate(item.payload["content"])
            started.assert_not_awaited()
            if scenario == "unconfirmed":
                with pytest.raises(AuthorizationError):
                    await start_application_personal_mcp_oauth(
                        async_session, owner, draft.command_id, origin
                    )
                return
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
                    {"configurable": {"thread_id": "mcp-oauth"}},
                    "mcp-oauth",
                    "fr",
                )
            assert not result.success and result.result_data["interaction"]["kind"] == "device"
            started.assert_not_awaited()
            start = await start_application_personal_mcp_oauth(
                async_session, owner, draft.command_id, origin
            )
            await async_session.refresh(row)
            assert "private-state" in start.authorization_url
            assert row.credentials_encrypted is None
            if scenario == "pending":
                with pytest.raises(ResourceConflictError) as failure:
                    await complete_application_personal_mcp_oauth(
                        async_session, owner, draft.command_id, origin
                    )
                assert failure.value.detail["error_code"] == "OAUTH_PENDING"
            if scenario == "changed_before_callback":
                row.name = "concurrent edit"
                await async_session.commit()
            if scenario == "logout_before_callback":
                await store.delete_session(browser.session_id)
            if scenario == "disabled_before_callback":
                monkeypatch.setattr(settings, "application_tools_enabled", False)
            if scenario in {
                "changed_before_callback",
                "logout_before_callback",
                "disabled_before_callback",
            }:
                with pytest.raises((AuthorizationError, ResourceConflictError)):
                    await check_personal_mcp_oauth_callback(server_id, owner, draft.command_id)
                return
            encrypted = encrypt_data(
                json.dumps({"access_token": "private-token", "client_id": "client"})
            )
            if scenario == "forged_callback":
                with pytest.raises(AuthorizationError):
                    await stage_personal_mcp_oauth_callback(
                        uuid4(), owner, draft.command_id, encrypted
                    )
                return
            await stage_personal_mcp_oauth_callback(server_id, owner, draft.command_id, encrypted)
            assert row.credentials_encrypted is None
            state = await read_command_status(async_session, owner, draft.command_id, origin)
            assert state.phase.value == "resuming" and "private" not in state.model_dump_json()
            if scenario == "changed_before_save":
                row.name = "concurrent edit"
                await async_session.commit()
            if scenario == "logout_before_save":
                await store.delete_session(browser.session_id)
            actual_origin = (
                bind_browser_session(owner, other.session_id)
                if scenario == "other_browser"
                else origin
            )
            if scenario in {
                "other_browser",
                "changed_before_save",
                "logout_before_save",
                "disabled_during_save",
            }:
                with pytest.raises((AuthorizationError, ResourceConflictError)):
                    await complete_application_personal_mcp_oauth(
                        async_session, owner, draft.command_id, actual_origin
                    )
                await async_session.refresh(row)
                assert row.credentials_encrypted is None
                return
            if scenario == "lost_ack":
                original_commit = async_session.commit

                async def lost_commit():
                    await original_commit()
                    monkeypatch.setattr(async_session, "commit", original_commit)
                    raise OperationalError("commit", {}, RuntimeError("lost acknowledgment"))

                monkeypatch.setattr(async_session, "commit", lost_commit)
                with pytest.raises(CommandRejected) as failure:
                    await complete_application_personal_mcp_oauth(
                        async_session, owner, draft.command_id, origin
                    )
                assert failure.value.code == "COMPLETION_UNKNOWN"
                await async_session.refresh(row)
                assert (
                    json.loads(decrypt_data(row.credentials_encrypted))["access_token"]
                    == "private-token"
                )
                with pytest.raises(AuthorizationError):
                    await complete_application_personal_mcp_oauth(
                        async_session, owner, draft.command_id, origin
                    )
                return
            if scenario == "settlement_unavailable":
                monkeypatch.setattr(
                    "src.domains.agents.application.secure_continuation.settle_continuation",
                    AsyncMock(side_effect=ConnectionError()),
                )
                with pytest.raises(ContinuationCompletionUnknown):
                    await complete_application_personal_mcp_oauth(
                        async_session, owner, draft.command_id, origin
                    )
                await async_session.refresh(row)
                assert (
                    json.loads(decrypt_data(row.credentials_encrypted))["access_token"]
                    == "private-token"
                )
                with pytest.raises(ResourceConflictError):
                    await complete_application_personal_mcp_oauth(
                        async_session, owner, draft.command_id, origin
                    )
                return
            final = await complete_application_personal_mcp_oauth(
                async_session, owner, draft.command_id, origin
            )
            assert (
                final.phase.value == "committed"
                and final.outcome.values["personal_mcp_oauth"]["authorization_saved"]
            )
            assert "private" not in final.model_dump_json()
            await async_session.refresh(row)
            assert (
                json.loads(decrypt_data(row.credentials_encrypted))["access_token"]
                == "private-token"
            )
            assert row.oauth_metadata["token_endpoint"] == "https://provider.example/token"
            if scenario == "duplicate":
                with pytest.raises(AuthorizationError):
                    await complete_application_personal_mcp_oauth(
                        async_session, owner, draft.command_id, origin
                    )
    finally:
        configure_personal_mcp_state(previous)
        await store.delete_session(browser.session_id)
        await store.delete_session(other.session_id)
