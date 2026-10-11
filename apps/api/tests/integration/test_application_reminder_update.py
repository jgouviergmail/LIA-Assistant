"""Reminder edits approve the full source result and refuse races or moving clocks."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import ResourceConflictError
from src.domains.agents.application.reminder_update import (
    execute_reminder_update,
    prepare_reminder_update,
)
from src.domains.agents.application.reminder_update_schemas import ReminderUpdateRequest
from src.domains.reminders.models import Reminder, ReminderStatus
from src.domains.reminders.schemas import ReminderCreate
from src.domains.reminders.service import ReminderService
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "intervention", ["none", "content", "processing", "timezone", "recurrence_clock"]
)
async def test_reminder_edit_is_proposal_only_and_refuses_stale_source_state(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch, intervention: str
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    test_user.timezone = "UTC"
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
    first = datetime(2099, 1, 15, 9, tzinfo=UTC)
    delta: dict[str, object] = {"content": "After", "trigger_at": first.isoformat()}
    if intervention == "recurrence_clock":
        delta = {
            "recurrence": {
                "freq": "daily",
                "anchor_date": first.date().isoformat(),
                "times": {"mode": "at", "at": [{"hour": 9, "minute": 0}]},
            }
        }
    request = ReminderUpdateRequest.model_validate({"reminder_id": str(identity), "changes": delta})
    with patch("src.domains.reminders.service.now_utc", return_value=first - timedelta(minutes=1)):
        draft = await prepare_reminder_update(async_session, actor_id, request)
    assert row.content == "Before"
    assert "Private" not in draft.model_dump_json()
    if intervention == "content":
        row.content = "Changed elsewhere"
    elif intervention == "processing":
        row.status = ReminderStatus.PROCESSING.value
    elif intervention == "timezone":
        test_user.timezone = "Europe/Paris"
    await async_session.commit()
    receipt = PreferenceWriteReceipt()
    with patch("src.domains.reminders.service.now_utc", return_value=first + timedelta(minutes=1)):
        if intervention == "none":
            await execute_reminder_update(async_session, actor_id, draft, receipt)
        else:
            with pytest.raises(ResourceConflictError):
                await execute_reminder_update(async_session, actor_id, draft, receipt)
    if intervention == "none":
        assert receipt.committed
        stored = await async_session.get(Reminder, identity)
        assert stored is not None and stored.content == "After" and stored.trigger_at == first
    else:
        assert not receipt.committed
        await async_session.rollback()
        stored = await async_session.get(Reminder, identity)
        assert stored is not None
        assert stored.content == ("Changed elsewhere" if intervention == "content" else "Before")


@pytest.mark.parametrize("no_op", [False, True])
async def test_content_only_edit_keeps_the_reminder_stored_zone_and_exact_seconds(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch, no_op: bool
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    test_user.timezone = "UTC"
    actor_id = test_user.id
    instant = datetime.now(UTC) + timedelta(days=2, seconds=19)
    row = await ReminderService(async_session).create_reminder(
        actor_id,
        ReminderCreate(content="Before", original_message="Private", trigger_at=instant),
        "Europe/Paris",
    )
    identity = row.id
    await async_session.commit()
    draft = await prepare_reminder_update(
        async_session,
        actor_id,
        ReminderUpdateRequest.model_validate(
            {"reminder_id": str(identity), "changes": {"content": "Before" if no_op else "After"}}
        ),
    )
    receipt = PreferenceWriteReceipt()
    await execute_reminder_update(async_session, actor_id, draft, receipt)
    stored = await async_session.get(Reminder, identity)
    assert receipt.committed and stored is not None
    assert stored.content == ("Before" if no_op else "After") and stored.trigger_at == instant
    assert stored.user_timezone == "Europe/Paris"
    assert receipt.no_op is no_op
