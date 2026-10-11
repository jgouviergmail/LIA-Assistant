"""Original native HITL approves generated-file deletion once and invalidates the owned gallery."""

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy import select

from src.core.config import settings
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.services import draft_executor
from src.domains.agents.tools import application_gallery_tools
from src.domains.attachments.models import Attachment
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime
from tests.integration.domains.attachments.test_keep_db import _file

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("mode", ["pipeline", "react"])
@pytest.mark.parametrize("confirmed", [False, True])
async def test_original_deletion_confirmation_and_addressed_gallery_refresh(
    async_session, test_user, monkeypatch, tmp_path, mode, confirmed
):
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "generated_assets_keep_max_files", 100)
    monkeypatch.setattr(settings, "generated_assets_keep_max_mb", 100)
    owner = test_user.id
    monkeypatch.setattr(settings, "attachments_storage_path", str(tmp_path))
    row = await _file(async_session, tmp_path, owner)
    asset_id = row.id
    path = tmp_path / row.file_path
    await async_session.commit()

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
    monkeypatch.setattr(application_gallery_tools, "get_db_context", database)
    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", database)
    events = asyncio.Queue()
    with installed_runtime_context(
        user_id=owner, deps=object(), execution_mode=mode, side_channel_queue=events
    ):
        proposal = await application_gallery_tools.delete_lia_generated_assets_tool.coroutine(
            request={"ids": [asset_id]},
            runtime=make_tool_runtime(
                user_id=owner,
                store=InMemoryStore(),
                execution_mode=mode,
                side_channel_queue=events,
            ),
        )
        assert proposal.success and proposal.metadata["requires_confirmation"]
        item = next(iter(proposal.registry_updates.values()))
        draft = ApplicationActionDraftContent.model_validate(item.payload["content"])
        assert path.exists()
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
                    {"configurable": {"thread_id": "asset-delete-flow"}},
                    "asset-delete-flow",
                    "fr",
                )
            assert result.success and result.result_data["committed"]
            with pytest.raises(CommandRejected, match="CONFIRMATION_MISSING"):
                await execute_application_action_draft(
                    draft.model_dump(mode="json"), owner, object()
                )
        assert path.exists() is not confirmed
        assert (
            await async_session.scalar(select(Attachment.id).where(Attachment.id == asset_id))
            is None
        ) is confirmed
        changes = []
        while not events.empty():
            event = events.get_nowait()
            if event.type == "application_state_changed":
                changes.append(event)
        assert len(changes) == int(confirmed)
        if confirmed:
            assert changes[0].metadata["change"]["resources"] == ["generated_assets"]
            assert changes[0].metadata["change"]["changed_fields"] == ["assets_to_delete"]
