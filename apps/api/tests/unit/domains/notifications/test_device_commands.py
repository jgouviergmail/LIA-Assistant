"""Notification-device management never mistakes a credential for a public identity."""

from datetime import UTC, datetime
from importlib import import_module
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.domains.notifications.models import UserFCMToken
from src.domains.users.models import User

pytestmark = pytest.mark.unit


def device(actor: User) -> UserFCMToken:
    return UserFCMToken(
        id=uuid4(),
        user_id=actor.id,
        token="private-notification-token",
        device_type="web",
        device_name="My browser",
        is_active=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        last_used_at=None,
    )


async def test_rotated_device_token_requires_another_preview_before_removal() -> None:
    commands = import_module("src.domains.notifications.device_commands")
    actor = User(id=uuid4(), is_active=True, deleted_at=None)
    row = device(actor)
    before = commands.notification_device_snapshot(row)
    assert "private-notification-token" not in before.model_dump_json()
    row.token = "different-private-token"
    db = AsyncMock(spec=AsyncSession)
    db.scalar.side_effect = [actor, row]
    with pytest.raises(ResourceConflictError):
        await commands.delete_notification_device(db, actor.id, row.id, expected=before)
    db.delete.assert_not_awaited()
    db.commit.assert_not_awaited()


async def test_formerly_active_account_cannot_remove_a_notification_device() -> None:
    commands = import_module("src.domains.notifications.device_commands")
    actor = User(id=uuid4(), is_active=False, deleted_at=None)
    db = AsyncMock(spec=AsyncSession)
    db.scalar.return_value = actor
    with pytest.raises(AuthorizationError):
        await commands.delete_notification_device(db, actor.id, uuid4())
    assert db.scalar.await_count == 1
    db.delete.assert_not_awaited()


async def test_changed_or_missing_device_has_no_deletion_and_native_conflict() -> None:
    commands = import_module("src.domains.notifications.device_commands")
    actor = User(id=uuid4(), is_active=True, deleted_at=None)
    row = device(actor)
    db = AsyncMock(spec=AsyncSession)
    db.scalar.side_effect = [actor, None]
    with pytest.raises(ResourceConflictError):
        await commands.delete_notification_device(
            db,
            actor.id,
            row.id,
            expected=commands.notification_device_snapshot(row),
        )
    db.delete.assert_not_awaited()
