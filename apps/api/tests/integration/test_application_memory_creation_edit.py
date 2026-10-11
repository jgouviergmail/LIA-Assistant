"""A revised creation retains its minted identity but replaces its exact approval."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application.command_repository import get_command, matches_command
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_editing import rebuild_application_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.memory_create_schemas import MemoryCreateConfiguration
from src.domains.agents.tools.application_memory_tools import create_lia_memory_tool
from src.domains.memories.models import Memory
from src.domains.users.models import User
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("injected", [False, True])
async def test_creation_edit_retains_identity_without_write_or_embedding(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch, injected: bool
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    owner = test_user.id

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session

    provider = AsyncMock(side_effect=AssertionError("Proposal editing cannot spend"))
    with (
        installed_runtime_context(user_id=owner, language="fr"),
        patch("src.domains.agents.tools.application_memory_tools.get_db_context", session),
        patch("src.domains.agents.application.draft_editing.get_db_context", session),
        patch(
            "src.domains.agents.application.memory_creation_embeddings._generate_document_embedding",
            provider,
        ),
    ):
        output = await create_lia_memory_tool.coroutine(
            configuration=MemoryCreateConfiguration(content="First fact", category="personal"),
            runtime=make_tool_runtime(user_id=owner, store=InMemoryStore()),
        )
        assert output.success
        item = next(iter(output.registry_updates.values()))
        original = ApplicationActionDraftContent.model_validate(item.payload["content"])
        values: dict[str, object] = {
            "content": "Revised fact",
            "category": "procedural",
            "importance": 0.0,
        }
        if injected:
            values["id"] = str(original.command_id)
            with pytest.raises(CommandRejected, match="INVALID_INPUT"):
                await rebuild_application_draft(item.payload["content"], {"intent": values})
        else:
            revised = ApplicationActionDraftContent.model_validate(
                await rebuild_application_draft(item.payload["content"], {"intent": values})
            )
            saved = await get_command(async_session, original.command_id, owner)
            assert saved is not None and matches_command(saved, revised, item.id)
            assert not matches_command(saved, original, item.id)
            assert revised.command_id == original.command_id
            assert revised.after["memory_to_create"]["pinned"] is True
        assert await async_session.get(Memory, original.command_id) is None
        provider.assert_not_awaited()
