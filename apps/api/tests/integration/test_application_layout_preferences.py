"""Layout full replacements are previewed, claimed and conflict-checked on PostgreSQL."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.effects.runtime import ClaimTicket
from src.domains.agents.services import draft_executor
from src.domains.agents.tools.application_layout_tools import update_lia_layout_preferences_tool
from src.domains.users.models import User
from src.infrastructure.account_preferences import LayoutPreferencePatch, update_layout_preferences
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("manual_intervention", [False, True])
async def test_pinned_list_replace_preserves_a_newer_visible_ui_change(
    async_session: AsyncSession,
    test_user: User,
    manual_intervention: bool,
) -> None:
    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session
        await async_session.commit()

    test_user.settings_shortcuts = ["font"]
    await async_session.commit()
    ledger = AsyncMock()
    ledger.claim.return_value = ClaimTicket(uuid4(), uuid4(), None)
    with (
        patch("src.domains.agents.tools.application_layout_tools.get_db_context", session),
        patch("src.domains.agents.application.command_service.get_db_context", session),
        patch("src.domains.agents.application.draft_execution.get_db_context", session),
        patch("src.domains.agents.effects.runtime._LEDGER", ledger),
        patch.dict(draft_executor.EXECUTOR_REGISTRY),
        installed_runtime_context(user_id=test_user.id, deps=object(), language="fr"),
    ):
        output = await update_lia_layout_preferences_tool.coroutine(
            patch=LayoutPreferencePatch(settings_shortcuts=["font", "theme"]),
            runtime=make_tool_runtime(user_id=test_user.id, store=InMemoryStore(), language="fr"),
        )
        assert output.success and output.metadata["requires_confirmation"]
        await async_session.refresh(test_user)
        assert test_user.settings_shortcuts == ["font"]
        item = next(iter(output.registry_updates.values()))
        assert item.payload["content"]["before"] == {"settings_shortcuts": ["font"]}
        if manual_intervention:
            await update_layout_preferences(
                async_session, test_user.id, LayoutPreferencePatch(settings_shortcuts=["font-size"])
            )
        draft_executor.register_executor("application_action", execute_application_action_draft)
        result = await draft_executor._execute_confirmed_draft(
            {
                "draft_id": item.id,
                "draft_type": "application_action",
                "draft_content": item.payload["content"],
            },
            {"configurable": {"thread_id": "layout-confirmation"}},
            "layout-confirmation",
            "fr",
        )
    await async_session.refresh(test_user)
    assert result.success is (not manual_intervention)
    assert test_user.settings_shortcuts == (
        ["font-size"] if manual_intervention else ["font", "theme"]
    )
    if manual_intervention:
        assert result.error == "STALE_STATE"
