"""Approved configuration accepts secrets only from the original live browser."""

import asyncio
import json
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.core.security.utils import decrypt_data
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.command_status import read_command_status
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.personal_mcp_configuration_service import (
    serve_personal_mcp_configuration,
)
from src.domains.agents.application.secure_continuation import ContinuationCompletionUnknown
from src.domains.agents.services import draft_executor
from src.domains.agents.tools import application_personal_mcp_tools
from src.domains.user_mcp.models import UserMCPServer
from src.domains.user_mcp.personal_configuration import configure_personal_mcp_server
from src.domains.user_mcp.personal_state import observe_personal_mcp_state, set_personal_mcp_state
from src.infrastructure.application_sessions import bind_browser_session
from src.infrastructure.cache.redis import get_redis_session
from src.infrastructure.cache.session_store import SessionStore
from src.infrastructure.mcp.personal_state_gateway import (
    PersonalMCPStateGateway,
    configure_personal_mcp_state,
)
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("creating", [False, True])
@pytest.mark.parametrize(
    "scenario",
    [
        "saved",
        "unconfirmed",
        "other_origin",
        "late_revocation",
        "changed_target",
        "secret_in_tool_input",
        "hidden_hitl_control",
        "source_logout",
        "lost_ack",
        "settlement_unavailable",
    ],
)
async def test_secret_configuration_stays_bound_and_outside_assistant_data(
    async_session, test_user, monkeypatch, creating, scenario
):
    for name in ["application_tools_enabled", "mcp_enabled", "mcp_user_enabled"]:
        monkeypatch.setattr(settings, name, True)
    owner = test_user.id
    row = None
    if not creating:
        row = UserMCPServer(user_id=owner, name="existing", url="https://example.org/previous")
        async_session.add(row)
    await async_session.commit()
    server_id = None if creating else row.id
    sessions = SessionStore(await get_redis_session())
    browser = await sessions.create_session(str(owner))
    other = await sessions.create_session(str(owner))
    origin = bind_browser_session(owner, browser.session_id)
    previous = configure_personal_mcp_state(
        PersonalMCPStateGateway(
            observe_personal_mcp_state,
            set_personal_mcp_state,
            configure=configure_personal_mcp_server,
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

    for module in ["command_service", "draft_execution", "secure_continuation"]:
        monkeypatch.setattr(f"src.domains.agents.application.{module}.get_db_context", database)
    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", database)
    monkeypatch.setattr(application_personal_mcp_tools, "get_db_context", database)
    events = asyncio.Queue()

    async def dns(url):
        if scenario == "late_revocation":
            monkeypatch.setattr(settings, "application_tools_enabled", False)
        if scenario == "source_logout":
            await sessions.delete_session(browser.session_id)
        return True, None

    monkeypatch.setattr("src.domains.user_mcp.service.validate_http_endpoint", dns)
    try:
        with installed_runtime_context(
            user_id=owner, application_origin=origin, deps=object(), side_channel_queue=events
        ):
            public = {"server_id": str(server_id)} if server_id else {}
            if scenario == "secret_in_tool_input":
                public["api_key"] = "private-key"
            proposal = await application_personal_mcp_tools.configure_lia_personal_mcp_server_tool.coroutine(
                request=public,
                runtime=make_tool_runtime(
                    user_id=owner,
                    application_origin=origin,
                    store=InMemoryStore(),
                    side_channel_queue=events,
                ),
            )
            if scenario == "secret_in_tool_input":
                assert not proposal.success
                return
            assert proposal.success and proposal.metadata["requires_confirmation"]
            item = next(iter(proposal.registry_updates.values()))
            draft = ApplicationActionDraftContent.model_validate(item.payload["content"])
            values = {
                "name": "configured",
                "url": "https://example.org/private?key=private",
                "auth_type": "api_key",
                "api_key": "private-key",
                "header_name": "X-Key",
            }
            assert "private-key" not in str(draft.before) + str(draft.after) + str(draft.intent)
            assert "/private?key=private" not in str(draft.before) + str(draft.after) + str(
                draft.intent
            )
            if scenario == "unconfirmed":
                with pytest.raises(AuthorizationError):
                    await serve_personal_mcp_configuration(
                        async_session, owner, draft.command_id, values, origin
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
                    {"configurable": {"thread_id": "mcp-configuration"}},
                    "mcp-configuration",
                    "fr",
                )
            assert not result.success and result.result_data["interaction"]["kind"] == "device"
            assert await async_session.scalar(
                select(func.count())
                .select_from(UserMCPServer)
                .where(UserMCPServer.user_id == owner)
            ) == int(not creating)
            if scenario == "other_origin":
                with pytest.raises(AuthorizationError):
                    await serve_personal_mcp_configuration(
                        async_session,
                        owner,
                        draft.command_id,
                        values,
                        bind_browser_session(owner, other.session_id),
                    )
                return
            if scenario == "changed_target" and not creating:
                row.name = "Concurrent user edit"
                await async_session.commit()
            if scenario == "hidden_hitl_control":
                values["hitl_required"] = False
                with pytest.raises(ValueError, match="Unsupported private form fields"):
                    await serve_personal_mcp_configuration(
                        async_session, owner, draft.command_id, values, origin
                    )
                return
            if scenario == "lost_ack":
                from src.domains.agents.application import personal_mcp_configuration_service

                original = personal_mcp_configuration_service.commit_personal_mcp_change
                original_commit = async_session.commit

                async def lost():
                    await original_commit()
                    raise OperationalError("COMMIT", {}, RuntimeError("lost acknowledgment"))

                async def ambiguous(*args, **kwargs):
                    with patch.object(async_session, "commit", lost):
                        await original(*args, **kwargs)

                monkeypatch.setattr(
                    personal_mcp_configuration_service, "commit_personal_mcp_change", ambiguous
                )
                with pytest.raises(CommandRejected, match="COMPLETION_UNKNOWN"):
                    await serve_personal_mcp_configuration(
                        async_session, owner, draft.command_id, values, origin
                    )
                terminal = await read_command_status(async_session, owner, draft.command_id, origin)
                assert terminal.outcome and not terminal.outcome.committed
                assert (
                    terminal.outcome.error_code == "COMPLETION_UNKNOWN"
                    and not terminal.outcome.values
                )
                with pytest.raises(AuthorizationError):
                    await serve_personal_mcp_configuration(
                        async_session, owner, draft.command_id, values, origin
                    )
                return
            if scenario == "settlement_unavailable":

                async def unavailable(*args, **kwargs):
                    raise ContinuationCompletionUnknown("Settlement unavailable")

                monkeypatch.setattr(
                    "src.domains.agents.application.personal_mcp_configuration_service.finish_application_continuation",
                    unavailable,
                )
                with pytest.raises(ContinuationCompletionUnknown):
                    await serve_personal_mcp_configuration(
                        async_session, owner, draft.command_id, values, origin
                    )
                saved = await async_session.scalar(
                    select(UserMCPServer).where(
                        UserMCPServer.user_id == owner, UserMCPServer.name == "configured"
                    )
                )
                assert saved and saved.credentials_encrypted
                with pytest.raises(AuthorizationError):
                    await serve_personal_mcp_configuration(
                        async_session, owner, draft.command_id, values, origin
                    )
                return
            refused = scenario in {"late_revocation", "source_logout"} or (
                scenario == "changed_target" and not creating
            )
            if refused:
                with pytest.raises((AuthorizationError, ResourceConflictError)):
                    await serve_personal_mcp_configuration(
                        async_session, owner, draft.command_id, values, origin
                    )
                if row:
                    await async_session.refresh(row)
                    assert (
                        row.credentials_encrypted is None
                        and row.url == "https://example.org/previous"
                    )
                return
            status = await serve_personal_mcp_configuration(
                async_session, owner, draft.command_id, values, origin
            )
            assert status.outcome and status.outcome.committed
            assert "private" not in status.model_dump_json()
            saved = await async_session.scalar(
                select(UserMCPServer).where(
                    UserMCPServer.user_id == owner, UserMCPServer.name == "configured"
                )
            )
            assert saved and saved.credentials_encrypted
            assert json.loads(decrypt_data(saved.credentials_encrypted))["api_key"] == "private-key"
            assert (
                "private"
                not in (
                    await read_command_status(async_session, owner, draft.command_id, origin)
                ).model_dump_json()
            )
            with pytest.raises((AuthorizationError, ResourceConflictError)):
                await serve_personal_mcp_configuration(
                    async_session, owner, draft.command_id, values, origin
                )
    finally:
        configure_personal_mcp_state(previous)
        await sessions.delete_session(browser.session_id)
        await sessions.delete_session(other.session_id)
