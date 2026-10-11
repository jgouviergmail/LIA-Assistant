"""Editing a proposal replaces its saved approval content without changing the reminder."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application.command_repository import get_command, matches_command
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_editing import rebuild_application_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.reminder_update_schemas import ReminderUpdateRequest
from src.domains.agents.tools.application_reminder_tools import update_lia_reminder_tool
from src.domains.reminders.schemas import ReminderCreate
from src.domains.reminders.service import ReminderService
from src.domains.users.models import User
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("intervention", ["none", "injected", "disabled"])
async def test_edit_reprepares_current_source_and_replaces_the_approved_digest(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch, intervention: str
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", intervention != "disabled")
    actor_id = test_user.id
    row = await ReminderService(async_session).create_reminder(
        actor_id,
        ReminderCreate(
            content="Before",
            original_message="Private",
            trigger_at=datetime.now(UTC) + timedelta(days=2),
        ),
        "UTC",
    )
    identity = row.id
    await async_session.commit()

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session

    with (
        installed_runtime_context(user_id=actor_id, language="fr"),
        patch("src.domains.agents.tools.application_reminder_tools.get_db_context", session),
        patch("src.domains.agents.application.draft_editing.get_db_context", session),
    ):
        output = await update_lia_reminder_tool.coroutine(
            selection=ReminderUpdateRequest.model_validate(
                {"reminder_id": str(identity), "changes": {"content": "After"}}
            ),
            runtime=make_tool_runtime(user_id=actor_id, store=InMemoryStore()),
        )
        if intervention == "disabled":
            assert not output.success and output.error_code == "CAPABILITY_DISABLED"
        else:
            assert output.success and output.metadata["requires_confirmation"]
            item = next(iter(output.registry_updates.values()))
            original = ApplicationActionDraftContent.model_validate(item.payload["content"])
            changes: dict[str, object] = {"content": "Revised"}
            if intervention == "injected":
                changes["user_timezone"] = "UTC"
                with pytest.raises(CommandRejected, match="INVALID_INPUT"):
                    await rebuild_application_draft(
                        item.payload["content"],
                        {"intent": {"reminder_id": str(identity), "changes": changes}},
                    )
            else:
                revised = ApplicationActionDraftContent.model_validate(
                    await rebuild_application_draft(
                        item.payload["content"],
                        {"intent": {"reminder_id": str(identity), "changes": changes}},
                    )
                )
                assert revised.command_id == original.command_id
                saved = await get_command(async_session, revised.command_id, actor_id)
                assert saved is not None and matches_command(saved, revised, item.id)
                assert not matches_command(saved, original, item.id)
    assert row.content == "Before"
