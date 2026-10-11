"""Notification tools expose registered devices without exposing delivery credentials."""

from importlib import import_module
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.users.models import User
from tests.unit.domains.notifications.test_device_commands import device

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def installed_device_owner():
    from src.domains.notifications.device_gateway import SavedNotificationDevices
    from src.infrastructure.notification_devices import configure_notification_devices

    previous = configure_notification_devices(SavedNotificationDevices())
    try:
        yield
    finally:
        configure_notification_devices(previous)


async def test_device_read_contains_no_token_or_private_compare_digest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operations = import_module("src.domains.agents.application.notification_operations")
    schemas = import_module("src.domains.agents.application.notification_schemas")
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    actor = User(id=uuid4(), is_active=True, deleted_at=None)
    row = device(actor)
    db = AsyncMock(spec=AsyncSession)
    db.scalar.side_effect = [None, actor, 1]
    rows = MagicMock()
    rows.all.return_value = [row]
    db.scalars.return_value = rows
    output = await operations.read_notification_devices(
        db, actor.id, schemas.NotificationDevicesRead()
    )
    assert output.total == 1 and output.devices[0].id == row.id
    public = output.model_dump_json()
    assert (
        "token" not in public
        and "digest" not in public
        and "private-notification-token" not in public
    )
    assert output.next_cursor is None


async def test_removal_proposal_has_no_registration_or_permission_effect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operations = import_module("src.domains.agents.application.notification_operations")
    schemas = import_module("src.domains.agents.application.notification_schemas")
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    actor = User(id=uuid4(), is_active=True, deleted_at=None)
    row = device(actor)
    db = AsyncMock(spec=AsyncSession)
    db.scalar.side_effect = [None, actor, row]
    content = await operations.prepare_notification_device_removal(
        db,
        actor.id,
        schemas.NotificationDeviceRemoveRequest(device_id=row.id),
    )
    assert content.before == content.intent
    assert content.after == {"notification_device_to_remove": None}
    assert "private-notification-token" not in content.model_dump_json()
    db.delete.assert_not_awaited()
    db.commit.assert_not_awaited()


def test_future_device_card_fields_require_an_explicit_projection_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pydantic import create_model

    owner = import_module("src.domains.notifications.device_gateway")
    owner.assert_notification_device_coverage()
    future = create_model(
        "FutureDeviceCard", __base__=owner.TokenInfo, delivery_status=(str | None, None)
    )
    monkeypatch.setattr(owner, "TokenInfo", future)
    with pytest.raises(AssertionError, match="projection review"):
        owner.assert_notification_device_coverage()


def test_device_preview_displays_identity_and_removal_without_private_digest() -> None:
    from src.domains.agents.application.draft_rendering import render_application_preview
    from src.domains.agents.application.notification_schemas import NotificationDeviceRemovePatch
    from src.domains.agents.application.preparation import _preference_content
    from src.domains.notifications.device_commands import notification_device_snapshot

    actor = User(id=uuid4())
    snapshot = notification_device_snapshot(device(actor))
    content = _preference_content(
        actor.id,
        NotificationDeviceRemovePatch(notification_device_to_remove=snapshot),
        {"notification_device_to_remove": snapshot.model_dump(mode="json")},
    )
    visible = str(
        render_application_preview(
            content.model_dump(mode="json"),
            {
                "application_field_notification_device_to_remove": "Notification device",
                "application_notification_device_remove": "Remove server registration; browser permission is unchanged",
                "application_before": "Before",
                "application_after": "After",
                "application_expiry": "Expires",
                "application_unavailable": "Unavailable",
            },
            lambda value: value or "",
        )
    )
    assert "My browser" in visible and str(snapshot.id) in visible
    assert "browser permission is unchanged" in visible
    assert snapshot.token_digest not in visible and "private-notification-token" not in visible


def test_device_editor_only_receives_the_public_selector() -> None:
    from src.domains.agents.application.notification_schemas import NotificationDeviceRemovePatch
    from src.domains.agents.application.preparation import _preference_content
    from src.domains.agents.application.prompts import build_application_edit_prompt
    from src.domains.notifications.device_commands import notification_device_snapshot

    actor = User(id=uuid4())
    snapshot = notification_device_snapshot(device(actor))
    content = _preference_content(
        actor.id,
        NotificationDeviceRemovePatch(notification_device_to_remove=snapshot),
        {"notification_device_to_remove": snapshot.model_dump(mode="json")},
    )
    prompt = str(
        build_application_edit_prompt(content.model_dump(mode="json"), "Choisis un autre appareil")
    )
    assert str(snapshot.id) in prompt and "device_id" in prompt
    assert snapshot.token_digest not in prompt and "token_digest" not in prompt
    assert "updated_at" not in prompt and "My browser" not in prompt
