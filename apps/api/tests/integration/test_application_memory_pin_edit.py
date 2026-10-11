"""Editing a pin rereads the source and replaces the pending approval digest."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import patch

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
from src.domains.agents.application.memory_pin_schemas import MemoryPinRequest
from src.domains.agents.tools.application_memory_tools import set_lia_memory_pin_tool
from src.domains.memories.models import Memory
from src.domains.users.models import User
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("intervention", ["none", "injected", "disabled"])
async def test_edit_refreshes_memory_and_requires_a_new_exact_confirmation(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch, intervention: str
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    owner = test_user.id
    row = Memory(
        user_id=owner,
        content="Original fact",
        category="personal",
        importance=0.7,
        pinned=False,
        char_count=13,
    )
    async_session.add(row)
    await async_session.commit()
    identity = row.id

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session

    with (
        installed_runtime_context(user_id=owner, language="fr"),
        patch("src.domains.agents.tools.application_memory_tools.get_db_context", session),
        patch("src.domains.agents.application.draft_editing.get_db_context", session),
    ):
        output = await set_lia_memory_pin_tool.coroutine(
            selection=MemoryPinRequest(memory_id=identity, pinned=True),
            runtime=make_tool_runtime(user_id=owner, store=InMemoryStore()),
        )
        assert output.success
        item = next(iter(output.registry_updates.values()))
        original = ApplicationActionDraftContent.model_validate(item.payload["content"])
        await async_session.execute(
            update(Memory)
            .where(Memory.id == identity)
            .values(content="Corrected fact")
            .execution_options(synchronize_session=False)
        )
        await async_session.commit()
        modified: dict[str, object] = {"memory_id": str(identity), "pinned": False}
        if intervention == "injected":
            modified["expected"] = original.before
        if intervention == "disabled":
            monkeypatch.setattr(settings, "application_tools_enabled", False)
        if intervention == "injected":
            with pytest.raises(CommandRejected, match="INVALID_INPUT"):
                await rebuild_application_draft(item.payload["content"], {"intent": modified})
        elif intervention == "disabled":
            with pytest.raises(AuthorizationError) as refused:
                await rebuild_application_draft(item.payload["content"], {"intent": modified})
            assert application_access_error_code(refused.value) == "CAPABILITY_DISABLED"
        else:
            revised = ApplicationActionDraftContent.model_validate(
                await rebuild_application_draft(item.payload["content"], {"intent": modified})
            )
            saved = await get_command(async_session, original.command_id, owner)
            assert (
                saved is not None
                and matches_command(saved, revised, item.id)
                and not matches_command(saved, original, item.id)
            )
            assert (
                revised.command_id == original.command_id
                and revised.expected_digest != original.expected_digest
            )
            assert revised.after["memory_pin"]["expected"]["content"] == "Corrected fact"
            assert revised.after["memory_pin"]["pinned"] is False
        await async_session.refresh(row)
        assert row.pinned is False and row.usage_count == 0
