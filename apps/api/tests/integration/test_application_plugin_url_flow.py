"""Original tool wrapper, confirmed draft executor and refresh registry work in both modes."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.tools import StructuredTool
from langgraph.store.memory import InMemoryStore
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.api.schemas import ChatStreamChunk
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.services import draft_executor
from src.domains.agents.services.draft_executor_types import EXECUTOR_REGISTRY
from src.domains.agents.tools import application_plugin_tools
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.plugins.models import UserPlugin
from src.domains.users.models import User
from tests.helpers.committed_account_session import async_session as async_session
from tests.helpers.runtime_context import make_tool_runtime
from tests.integration.application_runtime_context import installed_runtime_context
from tests.integration.test_application_plugin_url_import import _package

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("agent_registry")]


@pytest.mark.parametrize("mode", ["pipeline", "react"])
@pytest.mark.parametrize("confirmed", [False, True])
async def test_native_plugin_import_has_one_confirmation_and_group_refresh(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mode: str,
    confirmed: bool,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "plugins_enabled", True)
    monkeypatch.setattr(settings, "skills_url_import_enabled", True)
    monkeypatch.setattr(settings, "plugins_users_path", str(tmp_path / "plugins"))
    monkeypatch.setattr(settings, "skills_users_path", str(tmp_path / "skills"))
    owner = test_user.id
    await async_session.commit()
    monkeypatch.setattr(
        "src.domains.agents.application.plugin_url_import.fetch_skill_from_url",
        AsyncMock(return_value=(_package(), "native.zip")),
    )
    monkeypatch.setattr(
        "src.domains.agents.application.plugin_url_import.rate_limit_url_import", AsyncMock()
    )

    @asynccontextmanager
    async def database() -> AsyncIterator[AsyncSession]:
        try:
            yield async_session
            await async_session.commit()
        except BaseException:
            await async_session.rollback()
            raise

    for module in ("command_service", "draft_execution"):
        monkeypatch.setattr(f"src.domains.agents.application.{module}.get_db_context", database)
    monkeypatch.setattr(application_plugin_tools, "get_db_context", database)
    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", database)
    events: asyncio.Queue[ChatStreamChunk] = asyncio.Queue()
    with installed_runtime_context(
        user_id=owner, deps=object(), execution_mode=mode, side_channel_queue=events
    ):
        tool = application_plugin_tools.import_lia_plugin_url_tool
        assert isinstance(tool, StructuredTool) and tool.coroutine is not None
        proposal = await tool.coroutine(
            request={"url": "https://source.example/native.zip"},
            runtime=make_tool_runtime(
                user_id=owner, store=InMemoryStore(), execution_mode=mode, side_channel_queue=events
            ),
        )
        assert isinstance(proposal, UnifiedToolOutput)
        assert proposal.success and proposal.metadata["requires_confirmation"]
        item = next(iter(proposal.registry_updates.values()))
        draft = ApplicationActionDraftContent.model_validate(item.payload["content"])
        assert (
            await async_session.scalar(select(UserPlugin.id).where(UserPlugin.user_id == owner))
            is None
        )
        if confirmed:
            with patch.dict(EXECUTOR_REGISTRY):
                draft_executor.register_executor(
                    "application_action", execute_application_action_draft
                )
                result = await draft_executor._execute_confirmed_draft(
                    {
                        "draft_id": item.id,
                        "draft_type": "application_action",
                        "draft_content": draft.model_dump(mode="json"),
                    },
                    {"configurable": {"thread_id": "plugin-import-flow"}},
                    "plugin-import-flow",
                    "fr",
                )
            assert result.success and result.result_data["committed"]
            with pytest.raises(CommandRejected, match="CONFIRMATION_MISSING"):
                await execute_application_action_draft(
                    draft.model_dump(mode="json"), owner, object()
                )
        installed = await async_session.scalar(
            select(UserPlugin.id).where(UserPlugin.user_id == owner)
        )
        assert (installed is not None) == confirmed
        changes = []
        while not events.empty():
            event = events.get_nowait()
            if event.type == "application_state_changed":
                changes.append(event)
        assert len(changes) == int(confirmed)
        if confirmed:
            metadata = changes[0].metadata
            assert metadata is not None
            assert metadata["change"]["resources"] == ["plugins", "skills", "user_mcp"]
            assert metadata["change"]["changed_fields"] == ["plugin_url_import"]
