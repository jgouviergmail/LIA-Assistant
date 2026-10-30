"""A confirmed MCP probe guards the real original cache/status write path."""

import asyncio
import time
from contextlib import asynccontextmanager
from types import SimpleNamespace
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
from src.domains.user_mcp.personal_connection import test_personal_mcp_connection as probe_owner
from src.domains.user_mcp.personal_state import observe_personal_mcp_state, set_personal_mcp_state
from src.infrastructure.mcp.personal_state_gateway import (
    PersonalMCPStateGateway,
    configure_personal_mcp_state,
)
from src.infrastructure.mcp.pool_catalogue import PoolEntry
from tests.helpers.runtime_context import make_tool_runtime
from tests.integration.application_runtime_context import installed_runtime_context

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("agent_registry")]


@pytest.mark.parametrize("mode", ["pipeline", "react"])
@pytest.mark.parametrize(
    "scenario",
    [
        "connected",
        "failed",
        "failed_cached",
        "no_confirmation",
        "late_revocation",
        "changed_during_connection",
        "observer_failure",
        "service_unavailable",
        "ssrf_refusal",
    ],
)
async def test_personal_mcp_probe_is_confirmed_current_and_truthful(
    async_session, test_user, monkeypatch, mode, scenario
):
    for name in ["application_tools_enabled", "mcp_enabled", "mcp_user_enabled"]:
        monkeypatch.setattr(settings, name, True)
    owner = test_user.id
    row = UserMCPServer(
        user_id=owner,
        name="repositories",
        url="https://example.org/private?key=private",
        domain_description="Existing description",
        discovered_tools_cache=(
            [{"name": "previous", "description": "Previous cache"}]
            if scenario == "failed_cached"
            else None
        ),
    )
    async_session.add(row)
    await async_session.commit()
    server_id = row.id

    async def connect(**kwargs):
        assert not async_session.in_transaction()
        assert kwargs["user_id"] == owner and kwargs["force_refresh"]
        if scenario == "late_revocation":
            monkeypatch.setattr(settings, "application_tools_enabled", False)
        if scenario == "changed_during_connection":
            row.domain_description = "Concurrent edit"
            await async_session.commit()
        if scenario in {"failed", "failed_cached"}:
            raise TimeoutError("private credential in connection error")
        # The pool's own entry: the generation it reserved before this discovery.
        return PoolEntry(
            user_id=owner,
            server_id=server_id,
            last_used=time.monotonic(),
            tools=[
                {
                    "name": "list_repos",
                    "description": "Repositories",
                    "input_schema": {"private": "schema"},
                }
            ],
            generation=1,
        )

    network = AsyncMock(side_effect=connect)
    pool = SimpleNamespace(get_or_connect=network, disconnect=AsyncMock())
    monkeypatch.setattr(
        "src.infrastructure.mcp.user_pool.get_user_mcp_pool",
        lambda: None if scenario == "service_unavailable" else pool,
    )
    monkeypatch.setattr(
        "src.domains.agents.services.tool_selector.compute_tool_embeddings",
        AsyncMock(return_value={}),
    )
    monkeypatch.setattr(
        "src.domains.user_mcp.personal_connection.validate_http_endpoint",
        AsyncMock(return_value=(scenario != "ssrf_refusal", "private")),
    )
    previous = configure_personal_mcp_state(
        PersonalMCPStateGateway(
            observe_personal_mcp_state,
            set_personal_mcp_state,
            connect=probe_owner,
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
            proposal = await application_personal_mcp_tools.test_lia_personal_mcp_connection_tool.coroutine(
                request={"server_id": str(server_id)},
                runtime=make_tool_runtime(
                    user_id=owner,
                    execution_mode=mode,
                    store=InMemoryStore(),
                    side_channel_queue=events,
                ),
            )
            assert proposal.success and proposal.metadata["requires_confirmation"]
            item = next(iter(proposal.registry_updates.values()))
            draft = ApplicationActionDraftContent.model_validate(item.payload["content"])
            assert draft.after["personal_mcp_connection"]["may_call_read_me"] is True
            assert "private" not in str(draft.before) + str(draft.after)
            assert not network.called
            assert bool(row.discovered_tools_cache) == (scenario == "failed_cached")
            if scenario == "no_confirmation":
                with pytest.raises(CommandRejected, match="CONFIRMATION_MISSING"):
                    await execute_application_action_draft(
                        draft.model_dump(mode="json"), owner, object()
                    )
                assert not network.called
                return
            if scenario == "observer_failure":
                from src.domains.agents.application import personal_mcp_connection

                original = personal_mcp_connection.commit_personal_mcp_change

                async def observer(*args, **kwargs):
                    await original(*args, **kwargs)
                    raise RuntimeError("private observer failure")

                monkeypatch.setattr(personal_mcp_connection, "commit_personal_mcp_change", observer)
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
                    {"configurable": {"thread_id": "personal-mcp-probe"}},
                    "personal-mcp-probe",
                    "fr",
                )
            persisted = await async_session.scalar(
                select(UserMCPServer)
                .where(UserMCPServer.id == server_id)
                .execution_options(populate_existing=True)
            )
            assert persisted is not None
            durable = scenario in {"connected", "failed", "failed_cached", "observer_failure"}
            assert result.success == (scenario in {"connected", "failed", "failed_cached"}), (
                result.error,
                result.result_data,
            )
            if durable:
                observed = result.result_data["values"]["personal_mcp_connection"]
                assert observed["connection_success"] == (
                    scenario not in {"failed", "failed_cached"}
                )
                assert observed["status"] == persisted.status
                assert observed["tool_count"] == (0 if scenario == "failed" else 1)
                assert "private" not in str(observed)
                assert bool(persisted.discovered_tools_cache) == (scenario != "failed")
            else:
                assert persisted.discovered_tools_cache is None and persisted.status == "active"
                assert persisted.domain_description == (
                    "Concurrent edit"
                    if scenario == "changed_during_connection"
                    else "Existing description"
                )
            assert network.await_count == (
                0 if scenario in {"service_unavailable", "ssrf_refusal"} else 1
            )
            changes = []
            while not events.empty():
                event = events.get_nowait()
                if event.type == "application_state_changed":
                    changes.append(event)
            assert len(changes) == int(durable)
            if result.success:
                previous_calls = network.await_count
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
                        {"configurable": {"thread_id": "personal-mcp-probe"}},
                        "personal-mcp-probe",
                        "fr",
                    )
                assert network.await_count == previous_calls
    finally:
        configure_personal_mcp_state(previous)
