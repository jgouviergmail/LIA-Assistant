"""Description regeneration is an explicitly confirmed, accounted original operation."""

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
from src.domains.user_mcp.personal_description import regenerate_personal_mcp_description
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
    [
        "generated",
        "quota_fallback",
        "no_confirmation",
        "no_tools",
        "late_revocation",
        "changed_during_generation",
        "observer_failure",
    ],
)
async def test_personal_mcp_description_is_confirmed_current_and_truthful(
    async_session, test_user, monkeypatch, mode, scenario
):
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "mcp_enabled", True)
    monkeypatch.setattr(settings, "mcp_user_enabled", True)
    owner = test_user.id
    row = UserMCPServer(
        user_id=owner,
        name="repositories",
        url="https://example.com/private?key=private",
        domain_description="Previous description",
        discovered_tools_cache=(
            None
            if scenario == "no_tools"
            else [
                {
                    "name": "list_repos",
                    "description": "Lists repositories",
                    "input_schema": {"private": "never expose"},
                }
            ]
        ),
    )
    async_session.add(row)
    await async_session.commit()
    server_id = row.id

    async def generate(*args, **kwargs):
        assert kwargs["user_id"] == owner
        if scenario == "late_revocation":
            monkeypatch.setattr(settings, "application_tools_enabled", False)
        if scenario == "changed_during_generation":
            row.domain_description = "Concurrent user edit"
            await async_session.commit()
        return "Answers questions about repositories."

    generator = AsyncMock(side_effect=generate)
    if scenario != "quota_fallback":
        monkeypatch.setattr(UserMCPServerService, "_llm_generate_description", generator)
    quota = AsyncMock(return_value=True)
    monkeypatch.setattr("src.domains.usage_limits.enforcement.spend_blocked", quota)
    previous = configure_personal_mcp_state(
        PersonalMCPStateGateway(
            observe_personal_mcp_state,
            set_personal_mcp_state,
            describe=regenerate_personal_mcp_description,
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
            proposal = await application_personal_mcp_tools.regenerate_lia_personal_mcp_description_tool.coroutine(
                request={"server_id": str(server_id)},
                runtime=make_tool_runtime(
                    user_id=owner,
                    execution_mode=mode,
                    store=InMemoryStore(),
                    side_channel_queue=events,
                ),
            )
            if scenario == "no_tools":
                assert not proposal.success and not generator.called
                return
            assert proposal.success and proposal.metadata["requires_confirmation"]
            item = next(iter(proposal.registry_updates.values()))
            draft = ApplicationActionDraftContent.model_validate(item.payload["content"])
            assert draft.after["personal_mcp_description"]["may_use_platform_llm"] is True
            assert "private" not in str(draft.before) + str(draft.after)
            assert not generator.called and row.domain_description == "Previous description"
            if scenario == "no_confirmation":
                with pytest.raises(CommandRejected, match="CONFIRMATION_MISSING"):
                    await execute_application_action_draft(
                        draft.model_dump(mode="json"), owner, object()
                    )
                assert not generator.called
                return
            if scenario == "observer_failure":
                from src.domains.agents.application import personal_mcp_description

                original_commit = personal_mcp_description.commit_personal_mcp_change

                async def failed_observer(*args, **kwargs):
                    await original_commit(*args, **kwargs)
                    raise RuntimeError("private observer detail")

                monkeypatch.setattr(
                    personal_mcp_description, "commit_personal_mcp_change", failed_observer
                )
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
                    {"configurable": {"thread_id": "personal-mcp-description"}},
                    "personal-mcp-description",
                    "fr",
                )
            assert result.success == (scenario in {"generated", "quota_fallback"})
            saved = await async_session.scalar(
                select(UserMCPServer.domain_description).where(UserMCPServer.id == server_id)
            )
            if result.success or scenario == "observer_failure":
                assert saved and saved != "Previous description" and len(saved) <= 500
                assert (
                    result.result_data["values"]["personal_mcp_description"]["domain_description"]
                    == saved
                )
            else:
                assert saved == (
                    "Concurrent user edit"
                    if scenario == "changed_during_generation"
                    else "Previous description"
                )
            if scenario == "quota_fallback":
                assert quota.await_count == 1 and not generator.called
            else:
                assert generator.await_count == 1
            changes = []
            while not events.empty():
                event = events.get_nowait()
                if event.type == "application_state_changed":
                    changes.append(event)
            assert len(changes) == int(result.success or scenario == "observer_failure")
    finally:
        configure_personal_mcp_state(previous)
