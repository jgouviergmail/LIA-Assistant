"""Editing a pending proposal rereads current source facts without spending."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.agents.application.availability import application_access_error_code
from src.domains.agents.application.command_repository import get_command, matches_command
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_editing import rebuild_application_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.memory_bulk_schemas import MemoryBulkDeleteRequest
from src.domains.agents.application.memory_removal_schemas import MemoryDeleteRequest
from src.domains.agents.application.memory_update_schemas import (
    MemoryUpdateChanges,
    MemoryUpdateRequest,
)
from src.domains.agents.tools.application_memory_tools import (
    delete_all_lia_memories_tool,
    delete_lia_memory_tool,
    update_lia_memory_tool,
)
from src.domains.memories.models import Memory
from src.domains.users.models import User
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("scenario", ["fresh", "injected", "disabled"])
@pytest.mark.parametrize("operation", ["update", "delete", "bulk"])
async def test_editor_replaces_exact_approval_after_fresh_read(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    scenario: str,
    operation: str,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    owner, identity = test_user.id, uuid4()
    async_session.add(
        Memory(
            id=identity,
            user_id=owner,
            content="First fact",
            category="personal",
            importance=0.8,
            emotional_weight=0,
            trigger_topic="",
            usage_nuance="",
            pinned=True,
            char_count=10,
        )
    )
    await async_session.commit()

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session

    provider = AsyncMock(side_effect=AssertionError("Pending edits cannot spend"))
    with (
        installed_runtime_context(user_id=owner, language="fr"),
        patch("src.domains.agents.tools.application_memory_tools.get_db_context", session),
        patch("src.domains.agents.application.draft_editing.get_db_context", session),
        patch(
            "src.domains.agents.application.memory_creation_embeddings._generate_document_embedding",
            provider,
        ),
    ):
        tool = update_lia_memory_tool if operation == "update" else delete_lia_memory_tool
        if operation == "bulk":
            tool = delete_all_lia_memories_tool
        selection = (
            MemoryUpdateRequest(memory_id=identity, changes=MemoryUpdateChanges(importance=0.0))
            if operation == "update"
            else MemoryDeleteRequest(memory_id=identity)
        )
        if operation == "bulk":
            selection = MemoryBulkDeleteRequest()
        output = await tool.coroutine(
            selection=selection, runtime=make_tool_runtime(user_id=owner, store=InMemoryStore())
        )
        assert output.success
        item = next(iter(output.registry_updates.values()))
        original = ApplicationActionDraftContent.model_validate(item.payload["content"])
        await async_session.execute(
            update(Memory).where(Memory.id == identity).values(content="Corrected fact")
        )
        await async_session.commit()
        values: dict[str, object] = {"memory_id": str(identity), "changes": {"importance": 0.2}}
        if operation == "delete":
            values = {"memory_id": str(identity)}
        elif operation == "bulk":
            values = {"preserve_pinned": True}
        if scenario == "injected":
            values["expected"] = original.before[
                {
                    "update": "memory_configuration",
                    "delete": "memory_to_delete",
                    "bulk": "memories_to_delete",
                }[operation]
            ]
        elif scenario == "disabled":
            monkeypatch.setattr(settings, "application_tools_enabled", False)
        if scenario == "fresh":
            revised = ApplicationActionDraftContent.model_validate(
                await rebuild_application_draft(item.payload["content"], {"intent": values})
            )
            saved = await get_command(async_session, original.command_id, owner)
            assert saved is not None and matches_command(saved, revised, item.id)
            assert not matches_command(saved, original, item.id)
            assert revised.command_id == original.command_id
            if operation == "update":
                assert (
                    revised.before["memory_configuration"]["configuration"]["content"]
                    == "Corrected fact"
                )
                assert revised.after["memory_configuration"]["configuration"]["importance"] == 0.2
            elif operation == "delete":
                assert revised.before["memory_to_delete"]["content"] == "Corrected fact"
                assert revised.after == {"memory_to_delete": None}
            else:
                assert revised.before["memories_to_delete"]["selected_count"] == 0
                assert revised.before["memories_to_delete"]["preserved_count"] == 1
                assert revised.after == {"memories_to_delete": None}
        elif scenario == "disabled":
            with pytest.raises(AuthorizationError) as refused:
                await rebuild_application_draft(item.payload["content"], {"intent": values})
            assert application_access_error_code(refused.value) == "CAPABILITY_DISABLED"
        else:
            with pytest.raises(CommandRejected, match="INVALID_INPUT"):
                await rebuild_application_draft(item.payload["content"], {"intent": values})
        provider.assert_not_awaited()
