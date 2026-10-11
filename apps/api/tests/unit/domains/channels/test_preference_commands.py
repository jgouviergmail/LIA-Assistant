"""Channel state commands use the current owner, desired state and exact visible CAS."""

from importlib import import_module
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError, ResourceNotFoundError
from src.domains.channels.models import UserChannelBinding
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.unit


def binding(actor: User, enabled: bool = True) -> UserChannelBinding:
    return UserChannelBinding(
        id=uuid4(),
        user_id=actor.id,
        channel_type="telegram",
        channel_user_id="123",
        channel_username="@reader",
        is_active=enabled,
    )


@pytest.mark.parametrize(
    "saved,desired", [(True, False), (False, True), (True, True), (False, False)]
)
async def test_desired_state_is_saved_once_or_verified_as_noop(saved: bool, desired: bool) -> None:
    owner = import_module("src.domains.channels.preference_commands")
    actor = User(id=uuid4(), is_active=True, deleted_at=None)
    current = binding(actor, saved)
    before = owner.channel_binding_snapshot(current)
    db = AsyncMock(spec=AsyncSession)
    db.scalar.side_effect = [actor, current]
    receipt = PreferenceWriteReceipt()
    result = await owner.set_channel_binding_state(
        db, actor.id, current.id, desired, expected=before, receipt=receipt
    )
    assert result is current
    assert current.is_active is desired
    assert receipt.committed and receipt.no_op is (saved == desired)
    assert db.commit.await_count == int(saved != desired)


async def test_changed_visible_binding_refuses_the_old_confirmation_before_write() -> None:
    owner = import_module("src.domains.channels.preference_commands")
    actor = User(id=uuid4(), is_active=True, deleted_at=None)
    current = binding(actor)
    before = owner.channel_binding_snapshot(current)
    current.channel_user_id = "new-provider-account"
    db = AsyncMock(spec=AsyncSession)
    db.scalar.side_effect = [actor, current]
    with pytest.raises(ResourceConflictError):
        await owner.set_channel_binding_state(db, actor.id, current.id, False, expected=before)
    assert current.is_active is True
    db.commit.assert_not_awaited()


@pytest.mark.parametrize("fault", ["inactive", "missing", "foreign"])
async def test_current_ownership_is_required_before_any_channel_write(fault: str) -> None:
    owner = import_module("src.domains.channels.preference_commands")
    actor = User(id=uuid4(), is_active=fault != "inactive", deleted_at=None)
    current = binding(actor)
    if fault == "foreign":
        current.user_id = uuid4()
    db = AsyncMock(spec=AsyncSession)
    db.scalar.side_effect = [
        None if fault == "inactive" else actor,
        None if fault == "missing" else current,
    ]
    with pytest.raises(ResourceNotFoundError):
        await owner.set_channel_binding_state(db, actor.id, current.id, False)
    assert current.is_active is True
    db.commit.assert_not_awaited()


async def test_refresh_failure_does_not_erase_a_committed_channel_receipt() -> None:
    owner = import_module("src.domains.channels.preference_commands")
    actor = User(id=uuid4(), is_active=True, deleted_at=None)
    current = binding(actor)
    db = AsyncMock(spec=AsyncSession)
    db.scalar.side_effect = [actor, current]
    db.refresh.side_effect = RuntimeError("reread unavailable")
    receipt = PreferenceWriteReceipt()
    with pytest.raises(RuntimeError):
        await owner.set_channel_binding_state(db, actor.id, current.id, False, receipt=receipt)
    assert receipt.committed
    assert current.is_active is False


@pytest.mark.parametrize("stale", [False, True])
async def test_unlink_refuses_a_changed_identity_and_records_only_a_real_commit(
    stale: bool,
) -> None:
    owner = import_module("src.domains.channels.preference_commands")
    actor = User(id=uuid4(), is_active=True, deleted_at=None)
    current = binding(actor)
    before = owner.channel_binding_snapshot(current)
    if stale:
        current.channel_user_id = "different-account"
    db = AsyncMock(spec=AsyncSession)
    db.scalar.side_effect = [actor, current]
    receipt = PreferenceWriteReceipt()
    if stale:
        with pytest.raises(ResourceConflictError):
            await owner.unlink_owned_channel_binding(
                db, actor.id, current.id, expected=before, receipt=receipt
            )
        db.delete.assert_not_awaited()
        assert not receipt.committed
    else:
        assert (
            await owner.unlink_owned_channel_binding(
                db, actor.id, current.id, expected=before, receipt=receipt
            )
            == "telegram"
        )
        db.delete.assert_awaited_once_with(current)
        assert receipt.committed and not receipt.no_op
