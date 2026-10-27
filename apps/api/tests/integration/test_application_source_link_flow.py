"""The decorated native tool creates no source until the original shared approval executes."""

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy import func, select

from src.core.config import settings
from src.core.constants import GOOGLE_DRIVE_FOLDER_MIME
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.services import draft_executor
from src.domains.agents.tools import application_source_link_tools
from src.domains.rag_spaces.drive_sync import RAGDriveSyncService
from src.domains.rag_spaces.mail_source_service import RAGMailSyncService
from src.domains.rag_spaces.models import RAGDriveSource, RAGMailSource, RAGSpace
from tests.helpers.runtime_context import make_tool_runtime
from tests.integration.application_runtime_context import installed_runtime_context

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("agent_registry")]


@pytest.mark.parametrize("mode", ["pipeline", "react"])
@pytest.mark.parametrize("kind", ["drive", "mail"])
@pytest.mark.parametrize("confirmed", [False, True])
async def test_native_link_original_approval_and_addressed_invalidation(
    async_session, test_user, monkeypatch, mode, kind, confirmed
):
    for flag in (
        "application_tools_enabled",
        "rag_spaces_enabled",
        "rag_spaces_drive_sync_enabled",
        "rag_spaces_mail_sync_enabled",
    ):
        monkeypatch.setattr(settings, flag, True)
    owner = test_user.id
    space = RAGSpace(user_id=owner, name="Destination")
    async_session.add(space)
    await async_session.commit()
    space_id = space.id
    provider_id = "folder" if kind == "drive" else "Label_1"
    client = AsyncMock()
    client.get_file_metadata.return_value = {
        "id": provider_id,
        "name": "Source",
        "mimeType": GOOGLE_DRIVE_FOLDER_MIME,
        "parents": [],
    }
    client.get_label.return_value = {"id": provider_id, "name": "Source"}
    monkeypatch.setattr(RAGDriveSyncService, "_get_drive_client", AsyncMock(return_value=client))
    monkeypatch.setattr(RAGMailSyncService, "_get_gmail_client", AsyncMock(return_value=client))

    @asynccontextmanager
    async def database():
        try:
            yield async_session
            await async_session.commit()
        except BaseException:
            await async_session.rollback()
            raise

    for module in ("command_service", "draft_execution"):
        monkeypatch.setattr(f"src.domains.agents.application.{module}.get_db_context", database)
    monkeypatch.setattr(application_source_link_tools, "get_db_context", database)
    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", database)
    events = asyncio.Queue()
    model = RAGDriveSource if kind == "drive" else RAGMailSource
    with installed_runtime_context(
        user_id=owner, deps=object(), execution_mode=mode, side_channel_queue=events
    ):
        proposal = await application_source_link_tools.link_lia_knowledge_source_tool.coroutine(
            request={"space_id": space_id, "kind": kind, "provider_id": provider_id},
            runtime=make_tool_runtime(
                user_id=owner, store=InMemoryStore(), execution_mode=mode, side_channel_queue=events
            ),
        )
        assert proposal.success and proposal.metadata["requires_confirmation"]
        item = next(iter(proposal.registry_updates.values()))
        draft = ApplicationActionDraftContent.model_validate(item.payload["content"])
        assert (
            await async_session.scalar(
                select(func.count(model.id)).where(model.space_id == space_id)
            )
            == 0
        )
        if confirmed:
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
                    {"configurable": {"thread_id": "source-link-flow"}},
                    "source-link-flow",
                    "fr",
                )
            assert result.success and result.result_data["committed"]
            with pytest.raises(CommandRejected, match="CONFIRMATION_MISSING"):
                await execute_application_action_draft(
                    draft.model_dump(mode="json"), owner, object()
                )
        assert await async_session.scalar(
            select(func.count(model.id)).where(model.space_id == space_id)
        ) == int(confirmed)
        changes = []
        while not events.empty():
            event = events.get_nowait()
            if event.type == "application_state_changed":
                changes.append(event)
        assert len(changes) == int(confirmed)
        if confirmed:
            assert changes[0].metadata["change"]["resources"] == ["spaces"]
            assert changes[0].metadata["change"]["changed_fields"] == ["source_to_link"]
