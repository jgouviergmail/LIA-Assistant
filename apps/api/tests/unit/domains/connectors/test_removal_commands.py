"""Destructive local unlink checks fresh ownership and the precise previewed connection."""

from datetime import UTC, datetime, timedelta
from importlib import import_module
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError, ResourceNotFoundError
from src.domains.connectors.models import Connector, ConnectorStatus, ConnectorType, OAuthGrant
from src.domains.users.models import User

pytestmark = pytest.mark.unit


def connector(actor: User) -> Connector:
    return Connector(
        id=uuid4(),
        user_id=actor.id,
        connector_type=ConnectorType.GOOGLE_GMAIL,
        status=ConnectorStatus.ACTIVE,
        scopes=[],
        credentials_encrypted="private-token",
        connector_metadata={"oauth_account_email": "reader@example.test", "private_key": "secret"},
        oauth_grant_id=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


async def test_changed_connection_requires_another_preview() -> None:
    commands = import_module("src.domains.connectors.removal_commands")
    actor = User(id=uuid4(), is_active=True, deleted_at=None)
    saved = connector(actor)
    before = commands.connector_removal_snapshot(saved)
    saved.updated_at += timedelta(seconds=1)
    db = AsyncMock(spec=AsyncSession)
    db.scalar.side_effect = [actor, saved, saved]
    with pytest.raises(ResourceConflictError):
        await commands.locked_connector_for_removal(db, actor.id, saved.id, expected=before)
    db.commit.assert_not_awaited()
    db.delete.assert_not_awaited()


async def test_a_manually_removed_connection_invalidates_its_previous_preview() -> None:
    commands = import_module("src.domains.connectors.removal_commands")
    actor = User(id=uuid4(), is_active=True, deleted_at=None)
    saved = connector(actor)
    before = commands.connector_removal_snapshot(saved)
    db = AsyncMock(spec=AsyncSession)
    db.scalar.side_effect = [actor, None]
    with pytest.raises(ResourceConflictError):
        await commands.locked_connector_for_removal(db, actor.id, saved.id, expected=before)
    db.commit.assert_not_awaited()


@pytest.mark.parametrize("fault", ["inactive", "foreign"])
async def test_current_owner_is_checked_before_any_grant_lock(fault: str) -> None:
    commands = import_module("src.domains.connectors.removal_commands")
    actor = User(id=uuid4(), is_active=fault != "inactive", deleted_at=None)
    saved = connector(actor)
    if fault == "foreign":
        saved.user_id = uuid4()
    db = AsyncMock(spec=AsyncSession)
    db.scalar.side_effect = [actor, saved]
    with pytest.raises(ResourceNotFoundError):
        await commands.locked_connector_for_removal(db, actor.id, saved.id)
    db.commit.assert_not_awaited()


async def test_shared_grant_is_locked_before_the_connection_to_avoid_oauth_lock_inversion() -> None:
    commands = import_module("src.domains.connectors.removal_commands")
    actor = User(id=uuid4(), is_active=True, deleted_at=None)
    saved = connector(actor)
    saved.oauth_grant_id = uuid4()
    grant = OAuthGrant(id=saved.oauth_grant_id, user_id=actor.id)
    db = AsyncMock(spec=AsyncSession)
    db.scalar.side_effect = [actor, saved, grant, saved]
    assert await commands.locked_connector_for_removal(db, actor.id, saved.id) is saved
    locking = [
        str(call.args[0])
        for call in db.scalar.await_args_list
        if call.args[0]._for_update_arg is not None
    ]
    assert "users" in locking[0] and "oauth_grants" in locking[1] and "connectors" in locking[2]


def test_removal_identity_never_projects_credentials_or_arbitrary_metadata() -> None:
    commands = import_module("src.domains.connectors.removal_commands")
    saved = connector(User(id=uuid4()))
    result = commands.connector_removal_snapshot(saved).model_dump_json()
    assert "reader@example.test" in result
    assert "private-token" not in result and "private_key" not in result and "secret" not in result
