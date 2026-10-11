"""A shared locked owner applies number changes without preserving false verification."""

from datetime import UTC, datetime
from importlib import import_module
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.core.security.utils import decrypt_data, encrypt_data
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("number", [None, "+33698765432"])
async def test_number_changes_and_clears_share_locked_atomic_source_owner(
    number: str | None,
) -> None:
    module = import_module("src.domains.telephony.number_commands")
    actor = User(
        id=uuid4(),
        is_active=True,
        phone_number_encrypted=encrypt_data("+33612345678"),
        phone_number_verified_at=datetime.now(UTC),
    )
    users = AsyncMock()
    users.get_by_id_for_preference_update.return_value = actor
    users.update = AsyncMock()
    db, receipt = AsyncMock(), PreferenceWriteReceipt()
    await module.update_phone_number(db, actor.id, number, users=users, receipt=receipt)
    users.get_by_id_for_preference_update.assert_awaited_once_with(actor.id)
    changes = users.update.await_args.args[1]
    assert changes["phone_number_verified_at"] is None
    assert (
        decrypt_data(changes["phone_number_encrypted"])
        if number
        else changes["phone_number_encrypted"]
    ) == number
    db.commit.assert_awaited_once()
    assert receipt.committed and not receipt.no_op


async def test_same_number_no_op_preserves_verified_stamp_and_ciphertext() -> None:
    module = import_module("src.domains.telephony.number_commands")
    actor = User(
        id=uuid4(),
        is_active=True,
        phone_number_encrypted=encrypt_data("+33612345678"),
        phone_number_verified_at=datetime.now(UTC),
    )
    users, db = AsyncMock(), AsyncMock()
    users.get_by_id_for_preference_update.return_value = actor
    receipt = PreferenceWriteReceipt()
    await module.update_phone_number(db, actor.id, "+33612345678", users=users, receipt=receipt)
    assert receipt.committed and receipt.no_op
    users.update.assert_not_awaited()
    db.commit.assert_not_awaited()


async def test_changed_verification_or_number_refuses_stale_confirmation() -> None:
    module = import_module("src.domains.telephony.number_commands")
    actor = User(
        id=uuid4(),
        is_active=True,
        phone_number_encrypted=encrypt_data("+33612345678"),
        phone_number_verified_at=None,
    )
    expected = module.phone_number_snapshot(actor)
    actor.phone_number_verified_at = datetime.now(UTC)
    users = AsyncMock()
    users.get_by_id_for_preference_update.return_value = actor
    with pytest.raises(ResourceConflictError):
        await module.update_phone_number(
            AsyncMock(), actor.id, None, expected=expected, users=users
        )
    users.update.assert_not_awaited()


async def test_operator_recheck_after_lock_precedes_any_number_write() -> None:
    module = import_module("src.domains.telephony.number_commands")
    actor = User(id=uuid4(), is_active=True)
    users, db = AsyncMock(), AsyncMock()
    users.get_by_id_for_preference_update.return_value = actor
    check = AsyncMock(side_effect=AuthorizationError(detail={"error_code": "CAPABILITY_DISABLED"}))
    with pytest.raises(AuthorizationError):
        await module.update_phone_number(db, actor.id, "+33612345678", users=users, check=check)
    check.assert_awaited_once()
    users.update.assert_not_awaited()
    db.commit.assert_not_awaited()


@pytest.mark.parametrize("kind", ["missing", "foreign", "inactive", "deleted"])
async def test_locked_number_owner_refuses_lost_authority(kind: str) -> None:
    module = import_module("src.domains.telephony.number_commands")
    actor_id = uuid4()
    actor = User(
        id=uuid4() if kind == "foreign" else actor_id,
        is_active=kind != "inactive",
        deleted_at=datetime.now(UTC) if kind == "deleted" else None,
    )
    users, db = AsyncMock(), AsyncMock()
    users.get_by_id_for_preference_update.return_value = None if kind == "missing" else actor
    with pytest.raises(AuthorizationError):
        await module.update_phone_number(db, actor_id, None, users=users)
    users.update.assert_not_awaited()
    db.commit.assert_not_awaited()


async def test_clear_repairs_unreadable_number_and_orphan_verification_stamp() -> None:
    module = import_module("src.domains.telephony.number_commands")
    actor = User(
        id=uuid4(),
        is_active=True,
        phone_number_encrypted="unreadable-cipher",
        phone_number_verified_at=datetime.now(UTC),
    )
    snapshot = module.phone_number_snapshot(actor)
    assert snapshot.values.number_status == "unreadable" and not snapshot.values.verified
    users, db = AsyncMock(), AsyncMock()
    users.get_by_id_for_preference_update.return_value = actor
    receipt = PreferenceWriteReceipt()
    await module.update_phone_number(
        db, actor.id, None, expected=snapshot, users=users, receipt=receipt
    )
    assert users.update.await_args.args[1] == {
        "phone_number_encrypted": None,
        "phone_number_verified_at": None,
    }
    assert receipt.committed and not receipt.no_op
    db.commit.assert_awaited_once()
