"""The UI and native connector preference writer share strict current-owner CAS."""

from importlib import import_module
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError, ResourceNotFoundError
from src.core.security import decrypt_data, encrypt_data
from src.domains.connectors.models import Connector, ConnectorStatus, ConnectorType
from src.domains.connectors.preferences.schemas import PreferencesRequest
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.unit


def owned():
    actor = User(id=uuid4(), is_active=True, deleted_at=None)
    connector = Connector(
        id=uuid4(),
        user_id=actor.id,
        connector_type=ConnectorType.GOOGLE_CALENDAR,
        status=ConnectorStatus.ACTIVE,
        credentials_encrypted="credential-never-projected",
        preferences_encrypted=encrypt_data('{"default_calendar_name":"Before"}'),
    )
    db = AsyncMock(spec=AsyncSession)
    db.scalar.side_effect = [actor, connector]
    return actor, connector, db


async def test_write_uses_sanitized_preview_and_preserves_credentials() -> None:
    commands = import_module("src.domains.connectors.preferences.commands")
    actor, connector, db = owned()
    expected = commands.connector_preference_snapshot(connector)
    receipt = PreferenceWriteReceipt()
    desired = await commands.update_owned_connector_preferences(
        db,
        actor.id,
        connector.id,
        PreferencesRequest(default_calendar_name=' After\n"{name}" '),
        expected=expected,
        receipt=receipt,
    )
    assert desired.preferences == {"default_calendar_name": "Aftername"}
    assert decrypt_data(connector.preferences_encrypted) == '{"default_calendar_name":"Aftername"}'
    assert connector.credentials_encrypted == "credential-never-projected"
    assert receipt.committed and not receipt.no_op
    db.commit.assert_awaited_once()


@pytest.mark.parametrize("changed", ["preference", "status", "identity", "oauth_account"])
async def test_current_snapshot_conflict_never_replaces_saved_preferences(changed: str) -> None:
    commands = import_module("src.domains.connectors.preferences.commands")
    actor, connector, db = owned()
    expected = commands.connector_preference_snapshot(connector)
    if changed == "preference":
        connector.preferences_encrypted = encrypt_data('{"default_calendar_name":"Manual"}')
    elif changed == "status":
        connector.status = ConnectorStatus.INACTIVE
    elif changed == "oauth_account":
        connector.connector_metadata = {"oauth_account_email": "another-account@example.test"}
    else:
        connector.connector_type = ConnectorType.APPLE_CALENDAR
    with pytest.raises(ResourceConflictError):
        await commands.update_owned_connector_preferences(
            db,
            actor.id,
            connector.id,
            PreferencesRequest(default_calendar_name="After"),
            expected=expected,
        )
    db.commit.assert_not_awaited()


async def test_verified_noop_does_not_reencrypt_or_commit() -> None:
    commands = import_module("src.domains.connectors.preferences.commands")
    actor, connector, db = owned()
    encrypted = connector.preferences_encrypted
    receipt = PreferenceWriteReceipt()
    await commands.update_owned_connector_preferences(
        db,
        actor.id,
        connector.id,
        PreferencesRequest(default_calendar_name="Before"),
        expected=commands.connector_preference_snapshot(connector),
        receipt=receipt,
    )
    assert receipt.committed and receipt.no_op
    assert connector.preferences_encrypted == encrypted
    db.commit.assert_not_awaited()


async def test_foreign_connector_cannot_be_changed_even_by_a_superuser() -> None:
    commands = import_module("src.domains.connectors.preferences.commands")
    actor, connector, db = owned()
    actor.is_superuser = True
    connector.user_id = uuid4()
    with pytest.raises(ResourceNotFoundError):
        await commands.update_owned_connector_preferences(
            db,
            actor.id,
            connector.id,
            PreferencesRequest(default_calendar_name="After"),
        )
    db.commit.assert_not_awaited()


def test_corrupt_saved_preferences_are_unknown_not_an_empty_default() -> None:
    commands = import_module("src.domains.connectors.preferences.commands")
    _, connector, _ = owned()
    connector.preferences_encrypted = "corrupt-private-payload"
    with pytest.raises(ValueError, match="unavailable") as refusal:
        commands.connector_preference_snapshot(connector)
    assert "corrupt-private-payload" not in str(refusal.value)
