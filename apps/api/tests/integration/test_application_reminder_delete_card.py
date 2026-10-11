"""A native card command retains and revalidates its archived exact target."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.card_composition import CardComposition, CardCompositionRequest, card_composition_ctx
from src.core.config import settings
from src.core.exceptions import ResourceConflictError
from src.domains.agents.application.command_repository import save_command
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_editing import rebuild_application_draft
from src.domains.agents.application.reminder_removal import (
    execute_reminder_removal,
    prepare_reminder_removal,
)
from src.domains.agents.application.reminder_removal_schemas import ReminderDeleteRequest
from src.domains.agents.services import card_composition_service
from src.domains.reminders.models import Reminder
from src.domains.reminders.schemas import ReminderCreate
from src.domains.reminders.service import ReminderService
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from tests.helpers.runtime_context import installed_runtime_context

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("operation", ["execute", "edit"])
@pytest.mark.parametrize("intervention", ["none", "deleted_archive", "retarget"])
async def test_selected_card_is_revalidated_before_execution_and_revision(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    intervention: str,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    actor_id = test_user.id
    row = await ReminderService(async_session).create_reminder(
        actor_id,
        ReminderCreate(
            content="Selected",
            original_message="Selected",
            trigger_at=datetime.now(UTC) + timedelta(days=2),
        ),
        "UTC",
    )
    identity = row.id
    other = await ReminderService(async_session).create_reminder(
        actor_id,
        ReminderCreate(
            content="Another owned reminder",
            original_message="Another",
            trigger_at=datetime.now(UTC) + timedelta(days=3),
        ),
        "UTC",
    )
    other_identity = other.id
    await async_session.commit()
    selection = CardCompositionRequest(
        version=1,
        message_id=str(uuid4()),
        run_id="source",
        registry_id="chosen",
        action="cancel_reminder",
    )
    token = card_composition_ctx.set(
        CardComposition(
            actor_id, "REMINDER", str(identity), "cancel_reminder", None, source=selection
        )
    )
    try:
        draft = await prepare_reminder_removal(
            async_session, actor_id, ReminderDeleteRequest(reminder_id=identity)
        )
    finally:
        card_composition_ctx.reset(token)
    await save_command(async_session, draft, "card-draft")
    metadata = {
        "run_id": "source",
        "lia_card_actions": {
            "version": 1,
            "run_id": "source",
            "items": [
                {
                    "registry_id": "chosen",
                    "kind": "REMINDER",
                    "target_id": str(
                        uuid4()
                        if intervention == "retarget" and operation == "execute"
                        else identity
                    ),
                    "label": "Selected",
                    "provider": None,
                    "account_binding": None,
                    "actions": ["cancel_reminder"],
                }
            ],
        },
    }
    archive = AsyncMock()
    archive.scalar.return_value = None if intervention == "deleted_archive" else metadata

    @asynccontextmanager
    async def archive_session() -> AsyncIterator[AsyncSession]:
        yield archive

    @asynccontextmanager
    async def command_session() -> AsyncIterator[AsyncSession]:
        yield async_session

    receipt = PreferenceWriteReceipt()
    with (
        installed_runtime_context(user_id=actor_id, language="fr", deps=object()),
        patch.object(card_composition_service, "get_db_context", archive_session),
        patch("src.domains.agents.application.draft_editing.get_db_context", command_session),
    ):

        async def attempt() -> None:
            if operation == "execute":
                await execute_reminder_removal(async_session, actor_id, draft, receipt)
            else:
                revised = await rebuild_application_draft(
                    draft.model_dump(mode="json"),
                    {
                        "intent": {
                            "reminder_id": str(
                                other_identity if intervention == "retarget" else identity
                            )
                        }
                    },
                )
                assert revised["intent"]["reminder_to_delete"][
                    "card_selection"
                ] == selection.model_dump(mode="json")

        if intervention == "none":
            await attempt()
        else:
            with pytest.raises((ResourceConflictError, CommandRejected)):
                await attempt()
    assert card_composition_ctx.get() is None
    assert receipt.committed is (operation == "execute" and intervention == "none")
    assert (await async_session.get(Reminder, identity) is None) is receipt.committed
