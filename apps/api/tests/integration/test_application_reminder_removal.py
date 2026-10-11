"""Deletion retains the approved reminder and refuses a fired, busy or changed row."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.card_composition import (
    CardComposition,
    CardCompositionRequest,
    CardCompositionUnavailable,
    card_composition_ctx,
)
from src.core.config import settings
from src.core.exceptions import ResourceConflictError
from src.domains.agents.application.reminder_removal import (
    execute_reminder_removal,
    prepare_reminder_removal,
)
from src.domains.agents.application.reminder_removal_schemas import ReminderDeleteRequest
from src.domains.reminders.models import Reminder, ReminderStatus
from src.domains.reminders.schemas import ReminderCreate, ReminderUpdate
from src.domains.reminders.service import ReminderService
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("wrong_target", [False, True])
async def test_card_removal_retains_the_selected_archive_and_refuses_retargeting(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    wrong_target: bool,
) -> None:
    from uuid import uuid4

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
    await async_session.commit()
    selection = CardCompositionRequest(
        version=1,
        message_id=str(uuid4()),
        run_id="archived",
        registry_id="reminder_selected",
        action="cancel_reminder",
    )
    selected = CardComposition(
        user_id=actor_id,
        kind="REMINDER",
        target_id=str(uuid4() if wrong_target else identity),
        action="cancel_reminder",
        provider=None,
        source=selection,
    )
    token = card_composition_ctx.set(selected)
    try:
        if wrong_target:
            with pytest.raises(CardCompositionUnavailable):
                await prepare_reminder_removal(
                    async_session, actor_id, ReminderDeleteRequest(reminder_id=identity)
                )
        else:
            draft = await prepare_reminder_removal(
                async_session, actor_id, ReminderDeleteRequest(reminder_id=identity)
            )
            assert draft.intent["reminder_to_delete"]["card_selection"] == selection.model_dump(
                mode="json"
            )
    finally:
        card_composition_ctx.reset(token)
    assert await async_session.get(Reminder, identity) is not None


@pytest.mark.parametrize("intervention", ["none", "content", "schedule", "processing", "removed"])
async def test_removal_is_proposal_only_and_uses_the_exact_current_source_row(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch, intervention: str
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    actor_id = test_user.id
    source = ReminderService(async_session)
    row = await source.create_reminder(
        actor_id,
        ReminderCreate(
            content="Approved reminder",
            original_message="Private original",
            trigger_at=datetime.now(UTC) + timedelta(days=2),
        ),
        "Europe/Paris",
    )
    identity = row.id
    await async_session.commit()
    draft = await prepare_reminder_removal(
        async_session, actor_id, ReminderDeleteRequest(reminder_id=identity)
    )
    assert await async_session.get(Reminder, identity) is not None
    assert "Private original" not in draft.model_dump_json()
    if intervention == "content":
        await source.update_reminder(
            identity, actor_id, ReminderUpdate(content="Different reminder"), "Europe/Paris"
        )
    elif intervention == "schedule":
        await source.update_reminder(
            identity,
            actor_id,
            ReminderUpdate(trigger_at=row.trigger_at + timedelta(hours=1)),
            "Europe/Paris",
        )
    elif intervention == "processing":
        row.status = ReminderStatus.PROCESSING.value
    elif intervention == "removed":
        await source.cancel_reminder(identity, actor_id)
    await async_session.commit()
    receipt = PreferenceWriteReceipt()
    if intervention == "none":
        await execute_reminder_removal(async_session, actor_id, draft, receipt)
        assert receipt.committed
        assert await async_session.get(Reminder, identity) is None
    else:
        with pytest.raises(ResourceConflictError):
            await execute_reminder_removal(async_session, actor_id, draft, receipt)
        assert not receipt.committed
        assert (await async_session.get(Reminder, identity) is None) is (intervention == "removed")
